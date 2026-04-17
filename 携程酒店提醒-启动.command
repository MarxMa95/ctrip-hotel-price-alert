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
  echo "无法进入项目目录：$APP_DIR"
  read '?按回车键关闭...'
  exit 1
}

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo '未找到可用 Python，请先安装 Python 3。'
  read '?按回车键关闭...'
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

echo '正在停止旧的稳定版服务...'
pkill -f "$APP_MATCH" >/dev/null 2>&1 || true
sleep 1

PORT_PID=$(get_port_pid)
if [[ -n "$PORT_PID" ]]; then
  PORT_CMD=$(get_pid_command "$PORT_PID")
  PORT_CWD=$(get_pid_cwd "$PORT_PID")
  if [[ "$PORT_CWD" == "$APP_DIR" || "$PORT_CMD" == *" app.py"* ]]; then
    echo "检测到旧的稳定版进程仍占用端口 $APP_PORT，正在结束：PID=$PORT_PID"
    kill "$PORT_PID" >/dev/null 2>&1 || true
    if ! wait_port_release; then
      echo "端口 $APP_PORT 仍未释放，请稍后重试。"
      read '?按回车键关闭...'
      exit 1
    fi
  else
    echo "端口 $APP_PORT 已被其他程序占用：PID=$PORT_PID"
    echo "命令：${PORT_CMD:-未知}"
    echo "工作目录：${PORT_CWD:-未知}"
    echo '请先关闭占用该端口的程序，或改用其他端口。'
    read '?按回车键关闭...'
    exit 1
  fi
fi

mkdir -p "$APP_DIR/logs"

echo '正在启动稳定版服务...'
"$PYTHON_BIN" app.py > "$LOG_STDOUT" 2> "$LOG_STDERR" &
PID=$!

sleep 2

if ! wait_service_up; then
  echo '稳定版服务启动失败，未能正常监听接口。'
  echo ''
  echo '最近错误日志：'
  tail -n 80 "$LOG_STDERR" 2>/dev/null || echo '暂无错误日志'
  echo ''
  read '?按回车键关闭...'
  exit 1
fi

echo "网页地址：$APP_URL"
open "$APP_URL" >/dev/null 2>&1 || true

echo "后台进程 PID：$PID"
echo '服务已确认启动成功。'
read '?按回车键关闭...'
