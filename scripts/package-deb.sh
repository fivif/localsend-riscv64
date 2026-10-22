#!/usr/bin/env bash
# 打 .deb 包（在板端执行）。
# 产物：/root/localsend-riscv64/dist/localsend-riscv64_<ver>_riscv64.deb
set -euo pipefail

ROOT="${ROOT:-/root/localsend-riscv64}"
VER="${VER:-1.18.2}"
UPVER="${UPVER:-1.18.2}"
PKG="$ROOT/build/pkg/localsend-riscv64"
BIN="$PKG/usr/local/bin"
SHARE="$PKG/usr/share"

rm -rf "$PKG"
mkdir -p "$BIN" "$SHARE/applications" "$SHARE/icons/hicolor/scalable/apps" "$PKG/DEBIAN"

install -m 0755 "$ROOT/dist/localsend-cli"          "$BIN/localsend-cli"
install -m 0755 "$ROOT/dist/localsend-link"         "$BIN/localsend-link"
install -m 0755 "$ROOT/scripts/localsend-launch.sh" "$BIN/localsend-launch"
install -m 0755 "$ROOT/scripts/localsend-share.sh"  "$BIN/localsend-share"
install -m 0644 "$ROOT/scripts/localsend.desktop"   "$SHARE/applications/localsend.desktop"
if [ -f "$ROOT/scripts/localsend.svg" ]; then
  install -m 0644 "$ROOT/scripts/localsend.svg" "$SHARE/icons/hicolor/scalable/apps/localsend.svg"
fi

SIZE=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
sed -e "s/__VERSION__/$VER/" -e "s/__UPVER__/$UPVER/" -e "s/__SIZE__/$SIZE/" \
    "$ROOT/scripts/deb-control.tpl" > "$PKG/DEBIAN/control"
chmod 0644 "$PKG/DEBIAN/control"

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/localsend-riscv64_${VER}_riscv64.deb"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$OUT" >/dev/null
echo "built: $OUT"
dpkg-deb -I "$OUT" | sed -n '2,14p'
echo "--- 内容 ---"
dpkg-deb -c "$OUT" | awk '{print $6, $3}'
