#!/bin/zsh
set -u

SCRIPT_PATH="$0"
case "$SCRIPT_PATH" in
  /*) ;;
  *) SCRIPT_PATH="$PWD/$SCRIPT_PATH" ;;
esac
APP_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
CHECK_SCRIPT="$APP_DIR/scripts/prepublish_check.sh"

cd "$APP_DIR" || {
  echo "无法进入项目目录：$APP_DIR"
  read '?按回车键关闭...'
  exit 1
}

if ! "$CHECK_SCRIPT"; then
  code=$?
  echo ''
  echo "上传前自检未通过，退出码：$code"
  read '?按回车键关闭...'
  exit $code
fi

echo ''
echo '上传前自检已通过。'
read '?按回车键关闭...'
