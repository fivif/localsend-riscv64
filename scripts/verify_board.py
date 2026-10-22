#!/usr/bin/env python3
"""板端实测：用 pty 驱动 localsend-cli 的交互界面，验证两条链路。

测试 1「接收」：交互模式 -> W+R 打开浏览器上传页 -> 按 v2 协议上传 -> 检查落盘
测试 2「分享」：带文件启动 -> Esc 关设备列表 -> W+S 打开浏览器下载页 -> 取回文件

prepare-upload 的 HTTP 响应会一直挂到用户按 Y/N，所以请求必须放到线程里，
主线程负责 pump TUI 并按键。
"""
import json
import os
import pty
import re
import select
import shutil
import signal
import sys
import threading
import time
import urllib.error
import urllib.request

BIN = "/root/localsend-riscv64/dist/localsend-cli"
PORT = 53317
DEST = "/tmp/ls-recv"
SHARE_DIR = "/tmp/ls-share"
BASE = f"http://127.0.0.1:{PORT}"
results = []

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")


def strip_ansi(text):
    return ANSI.sub("", text)


def rec(passed, name, detail=""):
    results.append((passed, name, detail))
    print(("  PASS  " if passed else "  FAIL  ") + name + ("  | " + detail if detail else ""))


class Tui:
    def __init__(self, argv, env_extra=None, cols=120, rows=40):
        env = dict(os.environ)
        env.update(env_extra or {})
        env.setdefault("TERM", "xterm-256color")
        self.buf = b""
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvpe(argv[0], argv, env)
        # TUI 需要真实窗口尺寸，否则 ratatui 会在 0x0 上出错
        import fcntl
        import struct
        import termios
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
        return strip_ansi(self.buf.decode("utf-8", "replace"))

    def wait_for(self, pattern, timeout=15.0):
        end = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < end:
            if rx.search(self.text()):
                return True
            self.pump(0.2)
        return False

    def send(self, keys, settle=0.45):
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


class Req:
    """在后台线程里发一个 HTTP 请求，主线程继续 pump TUI。"""

    def __init__(self, fn, *a, **kw):
        self.out = None
        self.err = None
        self.t = threading.Thread(target=self._run, args=(fn, a, kw), daemon=True)
        self.t.start()

    def _run(self, fn, a, kw):
        try:
            self.out = fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            self.err = exc

    def wait(self, timeout=20):
        self.t.join(timeout)
        if self.t.is_alive():
            raise TimeoutError("HTTP 请求超时")
        if self.err:
            raise self.err
        return self.out


def http_json(path, payload, timeout=30):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def http_get(path, timeout=20):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return resp.status, resp.read()


def http_post_bytes(path, body, timeout=30):
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def info_block(alias, fingerprint):
    return {
        "alias": alias,
        "version": "2.2",
        "deviceModel": "test",
        "deviceType": "desktop",
        "fingerprint": fingerprint,
        "port": PORT,
        "protocol": "http",
        "download": False,
    }


# ---------------------------------------------------------------- 测试 1 接收
def test_receive():
    shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(DEST, exist_ok=True)
    tui = Tui([BIN, "--port", str(PORT), "--alias", "K3-RV-Board"],
              {"LOCALSEND_DESTINATION": DEST})
    try:
        if not tui.wait_for(r"Ready to accept requests", 20):
            rec(False, "接收：CLI 启动", tui.text()[-300:])
            return
        rec(True, "接收：CLI 启动并监听 " + str(PORT))

        tui.send("w")
        tui.send("r", settle=1.5)
        ok = tui.wait_for(r"Receive via link enabled", 15)
        rec(ok, "接收：W+R 打开浏览器上传页（加密关闭）", "" if ok else tui.text()[-400:])
        if not ok:
            return

        payload = "hello-from-riscv64-test\n"
        size = len(payload.encode())
        body = {
            "info": info_block("loopback-tester", "ABCDEF0123456789"),
            "files": {"f1": {"id": "f1", "fileName": "riscv-test.txt",
                             "size": size, "fileType": "text/plain"}},
        }
        prep_req = Req(http_json, "/api/localsend/v2/prepare-upload", body)
        if tui.wait_for(r"Accept\? Y/N", 12):
            tui.send("y", settle=1.0)
        else:
            rec(False, "接收：弹出 Y/N 确认", tui.text()[-400:])
            return
        rec(True, "接收：弹出 Y/N 确认")

        prep = prep_req.wait(20)
        sid = prep.get("sessionId")
        token = (prep.get("files") or {}).get("f1")
        rec(bool(sid and token), "接收：v2 prepare-upload 返回会话与 token",
            json.dumps(prep, ensure_ascii=False)[:160])
        if not (sid and token):
            return

        code, resp = http_post_bytes(
            f"/api/localsend/v2/upload?sessionId={sid}&fileId=f1&token={token}",
            payload.encode())
        rec(code in (200, 204), "接收：v2 upload 返回 " + str(code),
            resp[:100].decode("utf-8", "replace"))

        time.sleep(1.5)
        target = os.path.join(DEST, "riscv-test.txt")
        got = open(target, "rb").read().decode() if os.path.exists(target) else None
        rec(got == payload, "接收：文件落盘 " + target, repr(got)[:100])
        tui.pump(1.0)
        rec(bool(re.search(r"Received 1 file", tui.text())), "接收：界面显示接收完成",
            "" if re.search(r"Received 1 file", tui.text()) else tui.text()[-300:])
    finally:
        tui.stop()


# ---------------------------------------------------------------- 测试 2 分享
def test_share():
    shutil.rmtree(SHARE_DIR, ignore_errors=True)
    os.makedirs(SHARE_DIR, exist_ok=True)
    sample = os.path.join(SHARE_DIR, "share-me.txt")
    content = "localsend-riscv64 web share payload\n" * 3
    with open(sample, "w") as fh:
        fh.write(content)

    tui = Tui([BIN, "--port", str(PORT), "--alias", "K3-RV-Board", "send", sample],
              {"LOCALSEND_DESTINATION": DEST})
    try:
        if not tui.wait_for(r"Ready to accept requests|Select|Esc", 20):
            rec(False, "分享：CLI 启动", tui.text()[-300:])
            return
        rec(True, "分享：带文件启动")
        tui.send("\x1b", settle=0.8)          # Esc 关掉设备列表
        tui.send("w")
        tui.send("s", settle=1.8)
        ok = tui.wait_for(r"Share via link enabled", 15)
        rec(ok, "分享：W+S 打开浏览器下载页", "" if ok else tui.text()[-500:])
        if not ok:
            return

        code, html = http_get("/")
        rec(code == 200 and b"<" in html, "分享：GET / 返回下载页 HTML", f"{code}, {len(html)} B")

        prep = http_json("/api/localsend/v2/prepare-download",
                         {"info": info_block("loopback-tester", "ABCDEF0123456789")})
        sid = prep.get("sessionId")
        files = prep.get("files") or {}
        fid = next(iter(files), None)
        token = files.get(fid) if fid else None
        rec(bool(sid and fid and token), "分享：prepare-download 返回会话",
            json.dumps(prep, ensure_ascii=False)[:160])
        if not (sid and fid and token):
            return

        code, got = http_get(
            f"/api/localsend/v2/download?sessionId={sid}&fileId={fid}&token={token}")
        rec(code == 200 and got.decode() == content, "分享：download 取回内容一致",
            f"{code}, {len(got)} B")
    finally:
        tui.stop()


if __name__ == "__main__":
    print("=== 测试 1：接收（浏览器上传页） ===")
    test_receive()
    time.sleep(1.0)
    print("\n=== 测试 2：分享（浏览器下载页） ===")
    test_share()
    print("\n=== 汇总 ===")
    p = sum(1 for r in results if r[0])
    print(f"{p}/{len(results)} 通过")
    for passed, name, detail in results:
        print(("  OK   " if passed else "  NG   ") + name + ("  | " + detail if detail else ""))
    sys.exit(0 if p == len(results) else 1)
