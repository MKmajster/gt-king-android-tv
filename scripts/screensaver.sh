#!/usr/bin/env bash
# Set Aerial Views as the system screensaver (must be installed first — see apps.sh).
source "$(dirname "$0")/lib.sh"
PKG=com.neilturner.aerialviews
require_device
ash "pm path $PKG" >/dev/null || die "$PKG not installed"
SVC="$(ash "cmd package query-services --brief -a android.service.dreams.DreamService" | grep -oE "$PKG/[A-Za-z0-9_.]+" | head -1 || true)"
[ -n "$SVC" ] || die "no DreamService found in $PKG"
ash "settings put secure screensaver_components $SVC; settings put secure screensaver_enabled 1; settings put secure screensaver_activate_on_sleep 1"
log "screensaver = $SVC ($(ash 'settings get secure screensaver_components'))"
