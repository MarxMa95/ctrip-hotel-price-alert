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
  echo "Unable to enter project directory: $APP_DIR"
  read '?Press Enter to close...'
  exit 1
}

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo 'No usable Python interpreter found. Please install Python 3 first.'
  read '?Press Enter to close...'
  exit 1
fi

"$PYTHON_BIN" "$DOCTOR_SCRIPT"
code=$?
echo ''
if [[ $code -eq 0 ]]; then
  echo 'Environment check passed.'
else
  echo "Environment check failed with exit code: $code"
fi
read '?Press Enter to close...'
exit $code
