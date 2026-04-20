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

make_shortcut 'Launch Ctrip Hotel Alert.command' 'Launch Ctrip Hotel Alert.command'
make_shortcut 'Run Core Checks.command' 'Run Core Checks.command'
make_shortcut 'Environment Check.command' 'Environment Check.command'
make_shortcut 'Pre-Publish Check.command' 'Pre-Publish Check.command'

echo 'Desktop shortcuts refreshed:'
ls -1 "$DESKTOP_DIR" | grep -E 'Launch Ctrip Hotel Alert|Run Core Checks|Environment Check|Pre-Publish Check' || true
