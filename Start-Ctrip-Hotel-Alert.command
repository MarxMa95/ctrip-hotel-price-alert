#!/bin/zsh
set -u

SCRIPT_PATH="$0"
case "$SCRIPT_PATH" in
  /*) ;;
  *) SCRIPT_PATH="$PWD/$SCRIPT_PATH" ;;
esac
APP_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
START_SCRIPT="$APP_DIR/scripts/start.sh"
APP_PORT=8766
APP_URL="http://127.0.0.1:${APP_PORT}"
LOG_DIR="$APP_DIR/logs"
LOG_STDOUT="$LOG_DIR/new-launch-stdout.log"
LOG_STDERR="$LOG_DIR/new-launch-stderr.log"
mkdir -p "$LOG_DIR"

cd "$APP_DIR" || {
  echo "Unable to enter project directory: $APP_DIR"
  read '?Press Enter to close...'
  exit 1
}

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo 'No usable Python interpreter found. Please install Python 3 first.'
  read '?Press Enter to close...'
  exit 1
fi

port_pid="$(lsof -tiTCP:${APP_PORT} -sTCP:LISTEN 2>/dev/null | head -n 1)"
if [[ -n "$port_pid" ]]; then
  port_cmd="$(ps -p "$port_pid" -o command= 2>/dev/null)"
  port_cwd="$(lsof -a -p "$port_pid" -d cwd 2>/dev/null | awk 'NR==2 {for (i=9; i<=NF; i++) printf $i (i<NF?OFS:ORS)}')"
  if [[ "$port_cwd" == "$APP_DIR"* ]]; then
    echo 'Stopping the previous stable service...'
    kill "$port_pid" >/dev/null 2>&1 || true
    for _ in {1..20}; do
      sleep 0.3
      if ! lsof -tiTCP:${APP_PORT} -sTCP:LISTEN >/dev/null 2>&1; then
        break
      fi
    done
    port_pid="$(lsof -tiTCP:${APP_PORT} -sTCP:LISTEN 2>/dev/null | head -n 1)"
    if [[ -n "$port_pid" ]]; then
      echo "The previous stable service is still holding port $APP_PORT. Terminating PID=$port_pid"
      kill -9 "$port_pid" >/dev/null 2>&1 || true
      sleep 1
      if lsof -tiTCP:${APP_PORT} -sTCP:LISTEN >/dev/null 2>&1; then
        echo "Port $APP_PORT is still busy. Please try again in a moment."
        read '?Press Enter to close...'
        exit 1
      fi
    fi
  else
    echo "Port $APP_PORT is already occupied by another process: PID=$port_pid"
    echo "Command: ${port_cmd:-unknown}"
    echo "Working directory: ${port_cwd:-unknown}"
    echo 'Please stop the process using this port or switch to another port.'
    read '?Press Enter to close...'
    exit 1
  fi
fi

echo 'Starting the stable service...'
nohup "$START_SCRIPT" >"$LOG_STDOUT" 2>"$LOG_STDERR" &
PID=$!

for _ in {1..50}; do
  sleep 0.3
  if curl -fsS "$APP_URL/api/version" >/dev/null 2>&1; then
    echo "Web URL: $APP_URL"
    echo "Background PID: $PID"
    echo 'Service started successfully.'
    open "$APP_URL" >/dev/null 2>&1 || true
    read '?Press Enter to close...'
    exit 0
  fi
done

echo 'The stable service failed to start and did not begin listening.'
echo ''
echo 'Recent error log:'
tail -n 80 "$LOG_STDERR" 2>/dev/null || echo 'No error log available.'
read '?Press Enter to close...'
exit 1
