#!/usr/bin/env bash
# LocalSend（riscv64 / K3）图形入口：在终端窗口里跑 localsend-cli
#   - 有桌面会话 → 开一个 qterminal 窗口
#   - 纯字符终端 → 直接进
# 快捷键：D 设备列表 | 1-9 发送 | W+S 生成浏览器下载链接（手机扫二维码）| W+R 让手机浏览器上传
set -u

BIN="${LOCALSEND_BIN:-/usr/local/bin/localsend-cli}"
export LOCALSEND_DESTINATION="${LOCALSEND_DESTINATION:-$HOME/Downloads}"
mkdir -p "$LOCALSEND_DESTINATION"

if [ ! -x "$BIN" ]; then
  echo "找不到 $BIN" >&2
  exit 127
fi

# 已有实例在跑就不再开第二个（端口占用会直接失败）
if pgrep -f "localsend-cli" >/dev/null 2>&1; then
  echo "LocalSend 已经在运行了"
  exit 0
fi

if [ -t 0 ] && [ -t 1 ]; then
  exec "$BIN" "$@"
fi

if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
  TERM_CMD=""
  for c in qterminal lxterminal xfce4-terminal konsole xterm; do
    command -v "$c" >/dev/null 2>&1 && TERM_CMD="$c" && break
  done
  if [ -n "$TERM_CMD" ]; then
    case "$TERM_CMD" in
      qterminal)        exec qterminal -e "$BIN" "$@" ;;
      lxterminal)       exec lxterminal -e "$BIN" "$@" ;;
      xfce4-terminal)   exec xfce4-terminal -x "$BIN" "$@" ;;
      konsole)          exec konsole -e "$BIN" "$@" ;;
      xterm)            exec xterm -e "$BIN" "$@" ;;
    esac
  fi
  echo "没找到可用的终端模拟器，请在终端里直接运行：$BIN" >&2
  exit 1
fi

echo "当前没有图形会话，请到终端里运行：$BIN" >&2
exit 1
