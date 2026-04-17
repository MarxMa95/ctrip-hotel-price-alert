#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

cd "$APP_DIR"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo '未找到可用 Python，请先安装 Python 3。'
  exit 1
fi

echo ''
echo '==> 1/3 Python 语法检查'
"$PYTHON_BIN" -m py_compile app.py hotel_price_alert/*.py hotel_price_alert/services/*.py tests/*.py

echo ''
echo '==> 2/3 运行核心回归测试'
"$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v

echo ''
echo '==> 3/4 真实浏览器冒烟检查'
./scripts/run_smoke_checks.sh

echo ''
echo '==> 4/4 核心回归通过'
