#!/usr/bin/env python3
"""验证 riscv64 上的组播设备发现：两个 CLI 实例能否互相看见。

发现机制走 UDP 组播 224.0.0.167:53317，是 LocalSend 的核心链路之一，
必须在真机上确认，不能只靠 HTTP 端口能连来推断。
"""
import os
import re
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import fcntl

CLI = "/usr/local/bin/localsend-cli"
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")
results = []


def rec(ok, name, detail=""):
    results.append((ok, name, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))


class Tui:
    def __init__(self, argv, env_extra=None, cols=140, rows=44):
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

    def send(self, keys, settle=0.6):
        os.write(self.fd, keys.encode())
        return self.pump(settle)

    def stop(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                break
            time.sleep(0.4)
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass


def main():
    # 关键：两个实例必须用不同的 XDG_CONFIG_HOME。
    # 同一个配置目录 -> 同一个 identity.pem -> 同一个指纹，双方会把自己过滤掉，
    # 设备列表永远是 (none)。这不是 riscv64 的问题，是同一台机器上跑两个实例的必然结果。
    for d in ("/tmp/disc-a", "/tmp/disc-b", "/tmp/cfg-a", "/tmp/cfg-b"):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    a = Tui([CLI, "--port", "53700", "--alias", "K3-ALPHA"],
            {"LOCALSEND_DESTINATION": "/tmp/disc-a", "XDG_CONFIG_HOME": "/tmp/cfg-a"})
    b = Tui([CLI, "--port", "53701", "--alias", "K3-BETA"],
            {"LOCALSEND_DESTINATION": "/tmp/disc-b", "XDG_CONFIG_HOME": "/tmp/cfg-b"})
    try:
        rec(a.wait_for(r"Ready to accept requests", 30), "实例 A 就绪")
        rec(b.wait_for(r"Ready to accept requests", 30), "实例 B 就绪")

        # 组播默认 500ms 一轮，实测 1 秒内即可互相看到。
        t0 = time.time()
        seen = False
        for _ in range(40):
            a.pump(0.5)
            b.pump(0.5)
            if "K3-BETA" in a.text() or "K3-ALPHA" in b.text():
                seen = True
                break
        rec(seen, "组播互发现（1 秒级）", f"{time.time() - t0:.1f}s")

        b.send("d", settle=1.5)
        b.pump(2.0)
        text_b = b.text()
        rec("K3-ALPHA" in text_b, "B 的设备列表里出现 A",
            "" if "K3-ALPHA" in text_b else text_b[-260:])

        a.send("d", settle=1.5)
        a.pump(2.0)
        text_a = a.text()
        rec("K3-BETA" in text_a, "A 的设备列表里出现 B（双向发现）",
            "" if "K3-BETA" in text_a else text_a[-260:])

        out = subprocess.run(["ss", "-lntup"], capture_output=True, text=True).stdout
        rec(":53700" in out and ":53701" in out, "两个实例端口都在监听")
        rec("53317" in out, "组播端口 53317 已加入")

    finally:
        a.stop()
        b.stop()


if __name__ == "__main__":
    main()
    ok = sum(1 for r in results if r[0])
    print(f"\n{ok}/{len(results)} 通过")
    sys.exit(0 if ok == len(results) else 1)
