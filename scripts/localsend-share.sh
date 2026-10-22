#!/usr/bin/env bash
# 把文件分享给浏览器下载：手机/别的电脑打开链接就能下，不用装 LocalSend。
# 用法：
#   localsend-share ~/Downloads/photo.jpg
#   localsend-share ~/Documents/报告.pdf ~/Downloads/*.zip
set -u

BIN="${LOCALSEND_LINK_BIN:-/usr/local/bin/localsend-link}"
PORT="${LOCALSEND_PORT:-53317}"

if [ $# -eq 0 ]; then
  echo "用法: localsend-share <文件或目录>..."
  echo "   把文件分享给同一局域网里的手机/电脑浏览器下载。"
  exit 1
fi
for p in "$@"; do
  if [ ! -e "$p" ]; then
    echo "找不到: $p" >&2
    exit 1
  fi
done

exec "$BIN" --port "$PORT" share "$@"
