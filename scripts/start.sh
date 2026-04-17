#!/bin/zsh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
DOCTOR_SCRIPT="$SCRIPT_DIR/doctor.py"

cd "$APP_DIR" || exit 1

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "未找到可用 Python，请先安装 Python 3"
  exit 1
fi

if ! "$PYTHON_BIN" "$DOCTOR_SCRIPT"; then
  echo ''
  echo '启动前自检失败，服务不会继续启动。'
  echo '请查看上面的中文提示。'
  exit 1
fi

exec "$PYTHON_BIN" app.py
