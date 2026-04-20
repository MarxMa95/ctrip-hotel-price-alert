#!/bin/zsh
set -u

SCRIPT_PATH="$0"
case "$SCRIPT_PATH" in
  /*) ;;
  *) SCRIPT_PATH="$PWD/$SCRIPT_PATH" ;;
esac
APP_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
APP_URL="http://127.0.0.1:8766"
APP_PORT="8766"
APP_MATCH="app.py"
LOG_STDOUT="$APP_DIR/logs/new-launch-stdout.log"
LOG_STDERR="$APP_DIR/logs/new-launch-stderr.log"

cd "$APP_DIR" || {
  echo "Unable to enter project directory: $APP_DIR"
  read '?Press Enter to close...'
  exit 1
}

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo 'Python 3 was not found. Please install Python 3 first.'
  read '?Press Enter to close...'
  exit 1
fi

get_port_pid() {
  lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $2}'
}

get_pid_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

get_pid_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd 2>/dev/null | awk 'NR==2 {print $NF}'
}

wait_port_release() {
  local i
  for i in {1..10}; do
    if [[ -z "$(get_port_pid)" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_service_up() {
  local i
  for i in {1..15}; do
    if curl -fsS "$APP_URL/api/version" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo 'Stopping any previous local service...'
pkill -f "$APP_MATCH" >/dev/null 2>&1 || true
sleep 1

PORT_PID=$(get_port_pid)
if [[ -n "$PORT_PID" ]]; then
  PORT_CMD=$(get_pid_command "$PORT_PID")
  PORT_CWD=$(get_pid_cwd "$PORT_PID")
  if [[ "$PORT_CWD" == "$APP_DIR" || "$PORT_CMD" == *" app.py"* ]]; then
    echo "An older local process is still using port $APP_PORT. Stopping PID=$PORT_PID"
    kill "$PORT_PID" >/dev/null 2>&1 || true
    if ! wait_port_release; then
      echo "Port $APP_PORT is still busy. Please try again in a moment."
      read '?Press Enter to close...'
      exit 1
    fi
  else
    echo "Port $APP_PORT is already in use by another program: PID=$PORT_PID"
    echo "Command: ${PORT_CMD:-unknown}"
    echo "Working directory: ${PORT_CWD:-unknown}"
    echo 'Please stop the process using that port, or switch this app to another port.'
    read '?Press Enter to close...'
    exit 1
  fi
fi

mkdir -p "$APP_DIR/logs"

echo 'Starting local service...'
"$PYTHON_BIN" app.py > "$LOG_STDOUT" 2> "$LOG_STDERR" &
PID=$!

sleep 2

if ! wait_service_up; then
  echo 'The service failed to start and did not begin listening successfully.'
  echo ''
  echo 'Recent error log:'
  tail -n 80 "$LOG_STDERR" 2>/dev/null || echo 'No error log available.'
  echo ''
  read '?Press Enter to close...'
  exit 1
fi

echo "App URL: $APP_URL"
open "$APP_URL" >/dev/null 2>&1 || true

echo "Background PID: $PID"
echo 'Service is up.'
read '?Press Enter to close...'
