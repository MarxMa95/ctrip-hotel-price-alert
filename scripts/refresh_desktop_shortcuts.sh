#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$HOME/Desktop"

mkdir -p "$DESKTOP_DIR"

make_shortcut() {
  local target_name="$1"
  local shortcut_name="$2"
  cat > "$DESKTOP_DIR/$shortcut_name" <<SCRIPT
#!/bin/zsh
cd "$APP_DIR" || exit 1
exec "$APP_DIR/$target_name"
SCRIPT
  chmod +x "$DESKTOP_DIR/$shortcut_name"
}

make_shortcut '携程酒店提醒-启动.command' '携程酒店提醒-启动.command'
make_shortcut '核心回归检查.command' '核心回归检查.command'
make_shortcut '环境自检.command' '环境自检.command'
make_shortcut '上传前自检.command' '上传前自检.command'

echo '桌面快捷入口已刷新：'
ls -1 "$DESKTOP_DIR" | grep -E '携程酒店提醒-启动|核心回归检查|环境自检|上传前自检' || true
