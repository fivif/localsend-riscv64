#!/usr/bin/env python3
"""端到端验收：localsend-cli（pty 驱动，真实交互界面）+ 真实 mTLS 客户端上传 2MB 文件。

检查：sha256 一致、界面提示接收完成。
"""
import hashlib
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import fcntl
import time

CLI = "/usr/local/bin/localsend-cli"
PROBE = "/root/localsend-riscv64/build/target/release/localsend-upload-probe"
PORT = 53600
DEST = "/tmp/e2e-recv"
SRC = "/tmp/e2e-big.bin"
SIZE = 2 * 1024 * 1024
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")
results = []


def rec(ok, name, detail=""):
    results.append((ok, name, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))


class Tui:
    def __init__(self, argv, env_extra=None, cols=120, rows=40):
        env = dict(os.environ)
        env.update(env_extra or {})
        env.setdefault("TERM", "xterm-256color")
        self.buf = b""
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvpe(argv[0], argv, env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        os.set_blocking(self.fd, False)

    def pump(self, seconds=0.5):
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    chunk = os.read(self.fd, 65536)
                except OSError:
                    return self.text()
                if not chunk:
                    return self.text()
                self.buf += chunk
        return self.text()

    def text(self):
        return ANSI.sub("", self.buf.decode("utf-8", "replace"))

    def wait_for(self, pattern, timeout=20.0):
        end = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < end:
            if rx.search(self.text()):
                return True
            self.pump(0.2)
        return False

    def send(self, keys, settle=0.5):
        os.write(self.fd, keys.encode())
        return self.pump(settle)

    def stop(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                break
            time.sleep(0.5)
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(DEST)
    with open(SRC, "wb") as fh:
        fh.write(os.urandom(SIZE))
    src_hash = sha256(SRC)
    print(f"输入 {SRC}  {SIZE} B  sha256={src_hash}")

    tui = Tui([CLI, "--port", str(PORT), "--alias", "K3-E2E"],
              {"LOCALSEND_DESTINATION": DEST})
    try:
        ok = tui.wait_for(r"Ready to accept requests", 25)
        rec(ok, "CLI 启动并监听")
        if not ok:
            return

        proc_holder = {}
        import threading

        def run_probe():
            proc_holder["r"] = subprocess.run(
                [PROBE, "--port", str(PORT), "--file", SRC],
                capture_output=True, text=True, timeout=120)

        t = threading.Thread(target=run_probe, daemon=True)
        t.start()

        got_prompt = tui.wait_for(r"Accept\? Y/N|Y/N", 30)
        rec(got_prompt, "收到上传请求并弹出确认")
        if got_prompt:
            tui.send("y", settle=1.0)

        t.join(120)
        r = proc_holder.get("r")
        rec(r is not None and r.returncode == 0, "客户端上传成功",
            ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " ")[:160] if r else "超时")

        tui.pump(2.0)
        rec(bool(re.search(r"Received 1 file", tui.text())), "界面显示接收完成",
            "" if re.search(r"Received 1 file", tui.text()) else tui.text()[-200:])

        target = os.path.join(DEST, "e2e-big.bin")
        if os.path.exists(target):
            out_hash = sha256(target)
            rec(out_hash == src_hash, "2MB 文件 sha256 一致",
                f"{os.path.getsize(target)} B, {out_hash[:16]}…")
        else:
            rec(False, "2MB 文件落盘", "缺失")
    finally:
        tui.stop()


if __name__ == "__main__":
    main()
    ok = sum(1 for r in results if r[0])
    print(f"\n{ok}/{len(results)} 通过")
    sys.exit(0 if ok == len(results) else 1)
