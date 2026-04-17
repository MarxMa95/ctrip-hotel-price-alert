#!/bin/zsh
set -u

SCRIPT_PATH="$0"
case "$SCRIPT_PATH" in
  /*) ;;
  *) SCRIPT_PATH="$PWD/$SCRIPT_PATH" ;;
esac
APP_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
DOCTOR_SCRIPT="$APP_DIR/scripts/doctor.py"

cd "$APP_DIR" || {
  echo "无法进入项目目录：$APP_DIR"
  read '?按回车键关闭...'
  exit 1
}

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo '未找到可用 Python，请先安装 Python 3。'
  read '?按回车键关闭...'
  exit 1
fi

"$PYTHON_BIN" "$DOCTOR_SCRIPT"
code=$?
echo ''
if [[ $code -eq 0 ]]; then
  echo '环境自检通过。'
else
  echo "环境自检失败，退出码：$code"
fi
read '?按回车键关闭...'
exit $code
