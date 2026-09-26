#!/usr/bin/env bash
# disable | enable every package in scripts/debloat.list (pm disable-user, reversible). status: list disabled packages.
source "$(dirname "$0")/lib.sh"
LIST="$REPO_ROOT/scripts/debloat.list"
require_device
CMD="${1:-status}"
pkgs() { grep -vE '^[[:space:]]*(#|$)' "$LIST"; }
case "$CMD" in
  disable) for p in $(pkgs); do ash "pm path $p" >/dev/null 2>&1 && { ash "pm disable-user --user 0 $p" >/dev/null; log "disabled $p"; } || log "absent $p"; done ;;
  enable)  for p in $(pkgs); do ash "pm enable $p" >/dev/null 2>&1 && log "enabled $p" || log "absent $p"; done ;;
  status)  ash "pm list packages -d" ;;
  *) die "usage: debloat.sh disable|enable|status" ;;
esac
