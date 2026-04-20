#!/bin/zsh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
DOCTOR_SCRIPT="$SCRIPT_DIR/doctor.py"

cd "$APP_DIR" || exit 1

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Python 3 was not found. Please install Python 3 first."
  exit 1
fi

if ! "$PYTHON_BIN" "$DOCTOR_SCRIPT"; then
  echo ''
  echo 'Environment checks failed. The service will not start.'
  echo 'Please review the messages above.'
  exit 1
fi

exec "$PYTHON_BIN" app.py
