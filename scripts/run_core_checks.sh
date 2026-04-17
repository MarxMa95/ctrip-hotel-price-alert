#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

cd "$APP_DIR"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo 'No usable Python interpreter found. Please install Python 3 first.'
  exit 1
fi

echo ''
echo '==> 1/3 Python syntax check'
"$PYTHON_BIN" -m py_compile app.py hotel_price_alert/*.py hotel_price_alert/services/*.py tests/*.py

echo ''
echo '==> 2/3 Run core regression tests'
"$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v

echo ''
echo '==> 3/4 Real-browser smoke check'
./scripts/run_smoke_checks.sh

echo ''
echo '==> 4/4 Core regression checks passed'
