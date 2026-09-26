#!/usr/bin/env bash
# Apply or remove a /system overlay from overlays/<id>/ (variant B: adb root + remount rw).
#   overlays/<id>/system/**    copied over /system/** (originals saved on the box first)
#   overlays/<id>/system.prop  key=value lines: existing keys in /system/build.prop are replaced, new ones appended
#   overlay paths: no whitespace; files are installed 0644 (no executables)
# Usage: scripts/overlay.sh install <id> | remove <id> | list      (reboot afterwards; remove overlays in LIFO order)
source "$(dirname "$0")/lib.sh"

CMD="${1:?install|remove|list}"; ID="${2:-}"
BK=/data/local/gtk-backup            # device-side originals, one subdir per overlay
require_device

if [ "$CMD" != list ]; then
  case "$ID" in ''|*[!A-Za-z0-9_-]*) die "overlay id required, [A-Za-z0-9_-]+ only" ;; esac
fi

RW=0
sys_rw_tracked() { sys_rw; RW=1; }
on_exit() {
  rc=$?
  [ "$RW" = 1 ] && sys_ro
  if [ "$rc" -ne 0 ]; then
    if [ "$RW" = 1 ] && [ -n "$ID" ]; then
      log "overlay.sh failed (rc=$rc) — if an install was interrupted, run: scripts/overlay.sh remove $ID"
    else
      log "overlay.sh failed (rc=$rc)"
    fi
  fi
  exit "$rc"
}
trap on_exit EXIT

overlay_files() { (cd "$REPO_ROOT/overlays/$ID/system" 2>/dev/null && find . -type f | sed 's#^\./##') || true; }

install_file() {  # $1 = path relative to /system
  local rel="$1"
  if ash "test -e /system/$rel"; then
    ash "mkdir -p $BK/$ID/files/$(dirname "$rel") && cp -a /system/$rel $BK/$ID/files/$rel"
  else
    ash "echo $rel >> $BK/$ID/new-files"
  fi
  ash "mkdir -p /system/$(dirname "$rel") && chmod 755 /system/$(dirname "$rel") && chcon u:object_r:system_file:s0 /system/$(dirname "$rel")"
  adb_ push "$REPO_ROOT/overlays/$ID/system/$rel" "/system/$rel" >/dev/null || die "push /system/$rel failed"
  ash "chown root:root /system/$rel && chmod 644 /system/$rel && chcon u:object_r:system_file:s0 /system/$rel"
  log "installed /system/$rel"
}

install_props() {  # replace-or-append keys from overlays/<id>/system.prop into /system/build.prop (edited locally, no shell/sed interpolation)
  local tmp; tmp="$(mktemp -d)"
  ash "cp /system/build.prop $BK/$ID/build.prop"
  adb_ pull /system/build.prop "$tmp/build.prop" >/dev/null || die "pull build.prop failed"
  python3 - "$tmp/build.prop" "$REPO_ROOT/overlays/$ID/system.prop" <<'PY' || die "system.prop invalid — build.prop untouched"
import re, sys
bp, sp = sys.argv[1], sys.argv[2]
lines = open(bp, encoding="utf-8").read().splitlines()
for raw in open(sp, encoding="utf-8").read().splitlines():
    if not raw.strip() or raw.lstrip().startswith("#"):
        continue
    if "=" not in raw:
        sys.exit("malformed line (no '='): %r" % raw)
    key, val = raw.split("=", 1)
    if not re.fullmatch(r"[A-Za-z0-9_.]+", key):
        sys.exit("bad key: %r" % key)
    hits = [i for i, l in enumerate(lines) if l.startswith(key + "=")]
    if hits:
        lines[hits[0]] = key + "=" + val
    else:
        lines.append(key + "=" + val)
    print("prop " + key + "=" + val, file=sys.stderr)
open(bp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  adb_ push "$tmp/build.prop" /system/build.prop >/dev/null || die "push build.prop failed"
  ash "chown root:root /system/build.prop && chmod 644 /system/build.prop && chcon u:object_r:system_file:s0 /system/build.prop"
  rm -rf "$tmp"
}

case "$CMD" in
  install)
    [ -d "$REPO_ROOT/overlays/$ID" ] || die "no overlay dir overlays/$ID"
    FILES="$(overlay_files)"
    if printf '%s\n' "$FILES" | grep -q '[[:space:]]'; then die "overlay paths must not contain whitespace"; fi
    ash "test -d $BK/$ID" && die "$ID already installed — remove it first"
    ash "mkdir -p $BK/$ID/files"
    sys_rw_tracked
    for rel in $FILES; do install_file "$rel"; done
    [ -f "$REPO_ROOT/overlays/$ID/system.prop" ] && install_props
    sys_ro
    RW=0
    log "$ID installed — reboot to apply" ;;
  remove)
    ash "test -d $BK/$ID" || die "$ID not installed"
    sys_rw_tracked
    for rel in $(ash "cd $BK/$ID/files 2>/dev/null && find . -type f | sed 's#^\./##'"); do
      ash "cp -a $BK/$ID/files/$rel /system/$rel"; log "restored /system/$rel"
    done
    for rel in $(ash "cat $BK/$ID/new-files 2>/dev/null"); do ash "rm -f /system/$rel"; log "removed /system/$rel"; done
    ash "test -f $BK/$ID/build.prop && cp $BK/$ID/build.prop /system/build.prop && chmod 644 /system/build.prop" || true
    ash "rm -rf $BK/$ID"
    sys_ro
    RW=0
    log "$ID removed — reboot to apply" ;;
  list) ash "ls -1 $BK 2>/dev/null" ;;
  *) die "usage: overlay.sh install <id> | remove <id> | list" ;;
esac
