#!/usr/bin/env python3
"""实测 localsend-link（本地新增的网页直传入口）。

测试项：
  1. share 模式起服务，网页下载页 HTML 正常返回
  2. 按 v2 协议 prepare-download + download 取回文件内容一致
  3. serve 模式接收另一台「设备」按 v2 协议上传的文件，落盘一致
"""
import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import sys
import time
import urllib.request

BIN = "/root/localsend-riscv64/build/target/release/localsend-link"
PORT = int(os.environ.get("LS_TEST_PORT", 53400 + (os.getpid() % 400)))
DEST = "/tmp/ls-link-recv"
SHARE_DIR = "/tmp/ls-link-share"
BASE = f"http://127.0.0.1:{PORT}"
SBASE = f"https://127.0.0.1:{PORT}"
TLS = ssl._create_unverified_context()

# serve 模式仍走 TLS（和 LocalSend App 一致），share 模式走明文（浏览器要能打开）。
_current_base = BASE


def base_for(mode):
    global _current_base
    _current_base = BASE if mode == "share" else SBASE
    return _current_base
results = []


def rec(ok, name, detail=""):
    results.append((ok, name, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))


class Proc:
    def __init__(self, argv, env_extra=None):
        env = dict(os.environ)
        env.update(env_extra or {})
        self.log_path = f"/tmp/ls-link-{os.getpid()}-{id(self)}.log"
        self.log = open(self.log_path, "w+")
        self.p = subprocess.Popen(argv, stdout=self.log, stderr=subprocess.STDOUT, env=env)

    def wait_ready(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            self.log.seek(0)
            if "监听地址" in self.log.read():
                return True
            if self.p.poll() is not None:
                return False
            time.sleep(0.2)
        return False

    def text(self):
        self.log.seek(0)
        return self.log.read()

    def stop(self):
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGINT)
            for _ in range(30):
                if self.p.poll() is not None:
                    break
                time.sleep(0.1)
            if self.p.poll() is None:
                self.p.kill()
        self.log.close()


def http_json(path, payload, timeout=20):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(_current_base + path, data=data, method="POST",
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=TLS) as resp:
        return json.loads(resp.read().decode())


def http_get(path, timeout=20):
    with urllib.request.urlopen(_current_base + path, timeout=timeout, context=TLS) as resp:
        return resp.status, resp.read()


def info_block():
    return {"alias": "peer-device", "version": "2.2", "deviceType": "desktop",
            "fingerprint": "0123456789ABCDEF", "port": PORT,
            "protocol": "http", "download": False}


def test_share():
    shutil.rmtree(SHARE_DIR, ignore_errors=True)
    os.makedirs(SHARE_DIR)
    sample = os.path.join(SHARE_DIR, "link-share.txt")
    content = "localsend-link share payload\n" * 4
    open(sample, "w").write(content)

    base_for("share")
    proc = Proc([BIN, "--port", str(PORT), "--alias", "K3-Link", "share", sample])
    try:
        ok = proc.wait_ready()
        rec(ok, "share：服务启动", "" if ok else proc.text()[-300:])
        if not ok:
            return
        rec(str(PORT) in proc.text(), f"share：监听端口 {PORT}")
        rec(re.search(r"分享 1 个文件", proc.text()) is not None, "share：列出 1 个文件")

        code, html = http_get("/")
        rec(code == 200 and b"<" in html and len(html) > 500,
            "share：GET / 返回下载页", f"{code}, {len(html)} B")

        prep = http_json("/api/localsend/v2/prepare-download", {"info": info_block()})
        sid = prep.get("sessionId")
        files = prep.get("files") or {}
        fid = next(iter(files), None)
        rec(bool(sid and fid), "share：prepare-download 返回会话与文件列表",
            json.dumps(prep, ensure_ascii=False)[:140])
        if not (sid and fid):
            return

        # 下载 URL 不带 token（download 会话按 client IP 绑定）。
        code, got = http_get(
            f"/api/localsend/v2/download?sessionId={sid}&fileId={fid}")
        rec(code == 200 and got.decode() == content, "share：download 内容一致",
            f"{code}, {len(got)} B")
        time.sleep(0.4)
        rec("[网页] 下载" in proc.text(), "share：日志记录下载事件")
    finally:
        proc.stop()


def test_serve():
    shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(DEST, exist_ok=True)
    base_for("serve")
    proc = Proc([BIN, "--port", str(PORT), "--alias", "K3-Link",
                 "--destination", DEST, "serve"])
    try:
        ok = proc.wait_ready()
        rec(ok, "serve：服务启动", "" if ok else proc.text()[-300:])
        if not ok:
            return

        payload = b"receive-through-link\n"
        body = {
            "info": info_block(),
            "files": {"f1": {"id": "f1", "fileName": "got-it.txt",
                             "size": len(payload), "fileType": "text/plain"}},
        }
        prep = http_json("/api/localsend/v2/prepare-upload", body)
        sid = prep.get("sessionId")
        token = (prep.get("files") or {}).get("f1")
        rec(bool(sid and token), "serve：自动接受上传请求",
            json.dumps(prep, ensure_ascii=False)[:140])
        if not (sid and token):
            return

        req = urllib.request.Request(
            f"{_current_base}/api/localsend/v2/upload?sessionId={sid}&fileId=f1&token={token}",
            data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=20, context=TLS) as resp:
            rec(resp.status == 200, "serve：upload 返回 200", str(resp.status))

        time.sleep(1.0)
        target = os.path.join(DEST, "got-it.txt")
        got = open(target, "rb").read() if os.path.exists(target) else None
        rec(got == payload, "serve：文件落盘", repr(got)[:80] if got else "缺失")
        rec("接收" in proc.text(), "serve：日志记录接收")
    finally:
        proc.stop()


if __name__ == "__main__":
    print("=== share 模式 ===")
    test_share()
    time.sleep(0.8)
    print("\n=== serve 模式 ===")
    test_serve()
    print("\n=== 汇总 ===")
    ok = sum(1 for r in results if r[0])
    print(f"{ok}/{len(results)} 通过")
    for good, name, detail in results:
        print(("  OK   " if good else "  NG   ") + name + ("  | " + detail if detail else ""))
    sys.exit(0 if ok == len(results) else 1)
