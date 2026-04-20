#!/bin/zsh
set -u

SCRIPT_PATH="$0"
case "$SCRIPT_PATH" in
  /*) ;;
  *) SCRIPT_PATH="$PWD/$SCRIPT_PATH" ;;
esac
APP_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
CHECK_SCRIPT="$APP_DIR/scripts/run_core_checks.sh"

cd "$APP_DIR" || {
  echo "Unable to enter project directory: $APP_DIR"
  read '?Press Enter to close...'
  exit 1
}

if ! "$CHECK_SCRIPT"; then
  code=$?
  echo ''
  echo "Core regression checks failed with exit code: $code"
  read '?Press Enter to close...'
  exit $code
fi

echo ''
echo 'Core regression checks passed.'
read '?Press Enter to close...'
