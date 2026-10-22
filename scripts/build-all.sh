#!/usr/bin/env bash
# 一键构建 + 打 deb（在 K3 / Bianbu riscv64 上执行）
set -euo pipefail
ROOT="${ROOT:-/root/localsend-riscv64}"
export CARGO_TARGET_DIR="$ROOT/build/target"

echo "== 1/4 源码 =="
if [ ! -d "$ROOT/src/localsend/.git" ]; then
  git clone --depth 1 https://github.com/localsend/localsend "$ROOT/src/localsend"
else
  git -C "$ROOT/src/localsend" fetch --depth 1 origin main
  git -C "$ROOT/src/localsend" reset --hard FETCH_HEAD
fi
git -C "$ROOT/src/localsend" log --oneline -1

echo "== 2/4 编译上游 CLI =="
( cd "$ROOT/src/localsend" && cargo build -p localsend-cli --release )
cp -f "$CARGO_TARGET_DIR/release/localsend-cli" "$ROOT/dist/"

echo "== 3/4 编译网页直传入口 localsend-link =="
( cd "$ROOT/link" && cargo build --release )
cp -f "$CARGO_TARGET_DIR/release/localsend-link" "$ROOT/dist/"

echo "== 4/4 打 deb =="
VER=$(grep -m1 '^version' "$ROOT/src/localsend/cli/Cargo.toml" | sed 's/.*"\(.*\)".*/\1/')
VER="${VER:-1.18.2}"
VER="$VER" UPVER="$VER" bash "$ROOT/scripts/package-deb.sh"

echo "完成："
ls -lh "$ROOT/dist/"
file "$ROOT/dist/localsend-cli" "$ROOT/dist/localsend-link"
