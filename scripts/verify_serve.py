#!/usr/bin/env python3
"""用 core 自己的客户端（Rust）验证 localsend-link 的接收链路。

Python 侧握手不带客户端证书，服务端按 mTLS 设计直接断开——这是对的，
所以接收链路改用真客户端：写一个极小的 Rust 测试 bin，用
LsHttpClientV2 上传一个文件，然后检查落盘。
"""
import os
import shutil
import signal
import subprocess
import sys
import time

ROOT = "/root/localsend-riscv64"
LINK = f"{ROOT}/build/target/release/localsend-link"
CLIENT = f"{ROOT}/build/target/release/localsend-upload-probe"
PORT = 53511
DEST = "/tmp/ls-serve-recv"
results = []


def rec(ok, name, detail=""):
    results.append((ok, name, detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))


def main():
    shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(DEST)
    log = open(f"/tmp/ls-serve-{os.getpid()}.log", "w+")
    proc = subprocess.Popen([LINK, "--port", str(PORT), "--alias", "K3-Link",
                             "--destination", DEST, "serve"],
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        ok = False
        for _ in range(100):
            log.seek(0)
            if "监听地址" in log.read():
                ok = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        rec(ok, "serve：服务启动")
        if not ok:
            log.seek(0)
            print(log.read())
            return

        sample = "/tmp/serve-probe.txt"
        with open(sample, "w") as fh:
            fh.write("uploaded through real client\n" * 3)

        r = subprocess.run([CLIENT, "--port", str(PORT), "--file", sample],
                           capture_output=True, text=True, timeout=90)
        rec(r.returncode == 0, "serve：真客户端上传成功",
            (r.stdout or r.stderr).strip()[:200])

        time.sleep(1.0)
        target = os.path.join(DEST, "serve-probe.txt")
        got = open(target, "rb").read() if os.path.exists(target) else None
        expect = open(sample, "rb").read()
        rec(got == expect, "serve：落盘内容一致", f"{len(got)} B" if got else "缺失")

        log.seek(0)
        text = log.read()
        rec("[接收]" in text, "serve：日志记录接收事件")
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()


if __name__ == "__main__":
    main()
    ok = sum(1 for r in results if r[0])
    print(f"\n{ok}/{len(results)} 通过")
    sys.exit(0 if ok == len(results) else 1)
