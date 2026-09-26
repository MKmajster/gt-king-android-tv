#!/usr/bin/env bash
# Flash partition images from a backup dir back to the box (ADB root + dd), with size/sha1 guards.
# Usage: scripts/restore.sh <backup_dir> <partition> [<partition>...]
#        DRY_RUN=1 scripts/restore.sh backup/20260914-stock boot
source "$(dirname "$0")/lib.sh"

[ $# -ge 2 ] || die "usage: restore.sh <backup_dir> <partition>..."
DIR="$1"; shift
FORBIDDEN="bootloader tee rpmb cri_data param env"
require_device

for p in "$@"; do
  case " $FORBIDDEN " in *" $p "*) die "refusing to flash $p (protected partition)";; esac
  f="$DIR/$p.img"
  [ -f "$f" ] || die "missing $f"
  want="$(part_size "$p")"; got="$(file_size "$f")"
  [ "$got" -le "$want" ] || die "$p: image $got bytes > partition $want bytes"
  loc="$(file_sha1 "$f")"
  if [ "$(dev_sha1 "$p" "$got")" = "$loc" ]; then log "$p already identical, skip"; continue; fi
  if [ "${DRY_RUN:-0}" = 1 ]; then log "DRY_RUN: would flash $p from $f"; continue; fi
  log "flash $p ($got bytes)"
  adb_ push "$f" /data/local/tmp/restore.img >/dev/null || die "$p: adb push failed — nothing written"
  if ! ash "dd if=/data/local/tmp/restore.img of=$BYNAME/$p bs=4194304 && sync"; then
    log "$p: dd reported an error — partition may be partially written"
  fi
  ash "rm -f /data/local/tmp/restore.img" || true
  [ "$(dev_sha1 "$p" "$got")" = "$loc" ] || die "$p: verify FAILED after flash — DO NOT REBOOT, fix the connection and re-run restore"
  log "$p OK"
done
