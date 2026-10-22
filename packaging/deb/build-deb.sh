#!/usr/bin/env bash
# 从已完成的 release bundle 打 GUI deb。
# 前置：flutter build linux --release --no-tree-shake-icons 已成功。
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/app}"
BUNDLE="$APP_DIR/build/linux/riscv64/release/bundle"
P="$(cd "$(dirname "$0")" && pwd)/gui"
DIST="${DIST:-$APP_DIR/../../dist}"

[ -d "$BUNDLE" ] || { echo "找不到 release bundle: $BUNDLE" >&2; exit 1; }

rm -rf "$P"
mkdir -p "$P/DEBIAN" "$P/opt/localsend-gui" "$P/usr/local/bin" \
         "$P/usr/share/applications" "$P/usr/share/icons/hicolor/256x256/apps"

cp -a "$BUNDLE/." "$P/opt/localsend-gui/"
strip --strip-unneeded "$P"/opt/localsend-gui/lib/*_plugin.so 2>/dev/null || true
strip --strip-unneeded "$P/opt/localsend-gui/localsend_app"    2>/dev/null || true

install -m 755 "$(dirname "$0")/localsend-gui.launcher" "$P/usr/local/bin/localsend-gui"
install -m 644 "$(dirname "$0")/localsend-gui.desktop"  "$P/usr/share/applications/localsend-gui.desktop"
install -m 644 "$APP_DIR/assets/img/logo-256.png"       "$P/usr/share/icons/hicolor/256x256/apps/localsend-gui.png"

# 依赖：readelf NEEDED（不是 ldd 闭包）
LIBS=$(for f in "$P/opt/localsend-gui/localsend_app" "$P"/opt/localsend-gui/lib/*.so; do
         readelf -d "$f" 2>/dev/null | grep -a NEEDED | sed 's/.*\[\(.*\)\]/\1/'
       done | sort -u | grep -vE '^(libapp|libflutter_linux_gtk|lib.*_plugin|librust_lib)')
DEPS=""
for l in $LIBS; do
  pkg=$(dpkg -S "*/$l" 2>/dev/null | head -1 | cut -d: -f1)
  [ -n "$pkg" ] && DEPS="$DEPS,$pkg"
done
DEPS=$(echo "$DEPS" | tr ',' '\n' | grep -v '^$' | sort -u | tr '\n' ',' | sed 's/,$//')
DEPS="$DEPS,libegl1,libgbm1,libsecret-1-0"

SIZE=$(du -sk "$P/opt/localsend-gui" | cut -f1)
cat > "$P/DEBIAN/control" <<CTRL
Package: localsend-gui-riscv64
Version: ${VERSION:-1.18.2}
Section: net
Priority: optional
Architecture: riscv64
Maintainer: ${MAINTAINER:-Work-temp <root@localhost>}
Installed-Size: $((SIZE + 20))
Depends: $DEPS
Description: LocalSend Desktop GUI for RISC-V64
 LocalSend 局域网跨设备文件互传工具的桌面 GUI 版，riscv64 原生构建，
 使用自建的 Flutter riscv64 引擎编译。
CTRL

install -m 755 "$(dirname "$0")/postinst" "$P/DEBIAN/postinst"

mkdir -p "$DIST"
dpkg-deb --build --root-owner-group "$P" \
  "$DIST/localsend-gui-riscv64_${VERSION:-1.18.2}_riscv64.deb"
echo "OK: $DIST/localsend-gui-riscv64_${VERSION:-1.18.2}_riscv64.deb"