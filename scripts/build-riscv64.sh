#!/usr/bin/env bash
# LocalSend riscv64 构建脚本（进迭时空 K3 系列 / Bianbu 4.0.1）
# 用法：bash build-riscv64.sh
set -euo pipefail

ROOT="${ROOT:-/root/localsend-riscv64}"
SRC="$ROOT/src/localsend"
export CARGO_TARGET_DIR="$ROOT/build/target"
mkdir -p "$ROOT"/{src,build,dist,logs}

echo "==> 1/4 取源码"
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 https://github.com/localsend/localsend "$SRC"
else
  git -C "$SRC" fetch --depth 1 origin main && git -C "$SRC" reset --hard FETCH_HEAD
fi
git -C "$SRC" log --oneline -1

echo "==> 2/4 工具链自检"
rustc -vV | sed -n '1,4p'
gcc --version | head -1

echo "==> 3/4 编译 localsend-cli（协议 v2 + HTTP 服务端 + 组播发现，features=full）"
cd "$SRC"
cargo build -p localsend-cli --release 2>&1 | tee "$ROOT/logs/build-cli.log"

echo "==> 4/4 收集产物"
mkdir -p "$ROOT/dist"
cp -v "$CARGO_TARGET_DIR/release/localsend-cli" "$ROOT/dist/"
file "$ROOT/dist/localsend-cli"
ls -lh "$ROOT/dist/localsend-cli"
echo "OK"
