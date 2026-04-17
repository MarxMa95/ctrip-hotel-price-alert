#!/bin/zsh
set -euo pipefail
APP_NAME="ctrip-hotel-price-alert"
LABEL="com.local.${APP_NAME}"
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null || echo "Service not loaded: ${LABEL}"
