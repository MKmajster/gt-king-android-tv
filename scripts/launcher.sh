#!/usr/bin/env bash
# Switch the HOME launcher: launcherx (Google TV Home port) | projectivy | stock | status.
source "$(dirname "$0")/lib.sh"

STOCK=com.google.android.tvlauncher
LX=com.google.android.apps.tv.launcherx
PJ=com.spocky.projengmenu
AAPT="$HOME/Library/Android/sdk/build-tools/37.0.0/aapt"
require_device

resolve_home() {  # $1 = package → component of its HOME activity (empty if none; never aborts under set -e)
  ash "cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME" \
    | grep -E "^[[:space:]]*$1/" | head -1 | tr -d ' ' || true
}
set_home() {  # $1 = already-resolved component
  ash "cmd package set-home-activity $1"
  log "HOME = $1"
}

case "${1:-status}" in
  launcherx)
    [ -x "$AAPT" ] || die "aapt not found at $AAPT"
    ls "$REPO_ROOT"/apps/launcherx/*.apk >/dev/null 2>&1 || die "put LauncherX + katniss APKs in apps/launcherx/"
    for f in "$REPO_ROOT"/apps/launcherx/*.apk; do
      min="$("$AAPT" dump badging "$f" 2>/dev/null | grep -oE "sdkVersion:'[0-9]+'" | grep -oE '[0-9]+' || true)"
      [ "${min:-0}" -le 28 ] || die "$(basename "$f") needs SDK ${min:-?} > 28 — pick an older build"
      log "install $(basename "$f")"; adb_ install -r -g "$f"
    done
    comp="$(resolve_home "$LX")"; [ -n "$comp" ] || die "$LX has no HOME activity"
    ash "pm disable-user --user 0 $STOCK" >/dev/null
    set_home "$comp" ;;
  projectivy)
    ash "pm path $PJ" >/dev/null || die "Projectivy not installed"
    comp="$(resolve_home "$PJ")"; [ -n "$comp" ] || die "$PJ has no HOME activity"
    ash "pm disable-user --user 0 $STOCK" >/dev/null
    set_home "$comp" ;;
  stock)
    ash "pm enable $STOCK" >/dev/null
    comp="$(resolve_home "$STOCK")"; [ -n "$comp" ] || die "$STOCK has no HOME activity"
    set_home "$comp" ;;
  status)
    ash "cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME"
    ash "dumpsys activity activities | grep mResumedActivity" || true ;;
  *) die "usage: launcher.sh launcherx|projectivy|stock|status" ;;
esac
if [ "${1:-status}" != status ]; then
  ash "am start -a android.intent.action.MAIN -c android.intent.category.HOME" >/dev/null || true
fi
