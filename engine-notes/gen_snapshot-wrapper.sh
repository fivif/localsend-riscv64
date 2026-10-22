#!/bin/bash
# riscv64 AOT 包装：frontend_server 产出 40.0.dev 的 SDK hash，而本 gen_snapshot 是 51.0.dev，
# 直接编会 ApiError / exit 254。编译前把输入 dill 的 hash 改成本引擎期望值。
REAL="$(dirname "$(readlink -f "$0")")/gen_snapshot.real"
TARGET_HASH="69672e35b9"
PATCHER="/root/flutter-riscv64-engine/scripts/patch-kernel-hash.py"
# 最后一个不以 - 开头的参数就是输入 dill
IN=""
for a in "$@"; do case "$a" in -*) ;; *) IN="$a" ;; esac; done
if [ -n "$IN" ] && [ -f "$IN" ] && [ -f "$PATCHER" ]; then
  python3 "$PATCHER" "$IN" "$TARGET_HASH" >/dev/null 2>&1
fi
exec "$REAL" "$@"
