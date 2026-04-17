#!/bin/zsh
set -euo pipefail

APP_NAME="ctrip-hotel-price-alert"
LABEL="com.local.${APP_NAME}"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "Removed: ${LABEL}"
