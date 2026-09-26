#!/usr/bin/env bash
# Common helpers for GT-King PRO scripts. Source it; do not execute.
set -euo pipefail

ADB_SERIAL="${ADB_SERIAL:-192.168.0.100:5555}"
BYNAME="/dev/block/platform/ffe07000.emmc/by-name"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }
adb_() { adb -s "$ADB_SERIAL" "$@"; }
# Run a shell command on the box; no stdin (safe inside while-read loops); strip CR.
ash() { adb_ shell "$@" </dev/null | tr -d '\r'; }

# Connect, and make sure adb shell runs as root (userdebug build: `adb root` restarts adbd as root).
require_device() {
  if [ "$(adb_ get-state 2>/dev/null || true)" != "device" ]; then
    adb connect "$ADB_SERIAL" >/dev/null 2>&1 || true
  fi
  [ "$(adb_ get-state 2>/dev/null || true)" = "device" ] || die "device $ADB_SERIAL not connected"
  if [ "$(ash id -u)" != "0" ]; then
    adb_ root >/dev/null 2>&1 || true
    for i in 1 2 3 4 5; do sleep 1; adb connect "$ADB_SERIAL" >/dev/null 2>&1 || true; [ "$(ash id -u 2>/dev/null || true)" = "0" ] && break; done
  fi
  [ "$(ash id -u)" = "0" ] || die "adb shell is not root on $ADB_SERIAL (adb root failed)"
}

sys_rw() { ash "mount -o remount,rw /" || die "remount rw / failed"; }
sys_ro() { ash "sync; mount -o remount,ro /" || log "WARNING: remount ro / failed — will be ro after reboot"; }

part_size() {
  local dev="$1"
  case "$dev" in
    /*) ;;  # absolute device path, use as-is
    *) dev="$BYNAME/$dev" ;;  # partition name, prefix with BYNAME
  esac
  ash "blockdev --getsize64 $dev"
}

# sha1 of a partition or device; optional 2nd arg limits to first N bytes (for images smaller than the partition)
dev_sha1() {
  local dev="$1"
  case "$dev" in
    /*) ;;  # absolute device path, use as-is
    *) dev="$BYNAME/$dev" ;;  # partition name, prefix with BYNAME
  esac
  if [ -n "${2:-}" ]; then ash "head -c $2 $dev | sha1sum" | awk '{print $1}'
  else ash "sha1sum $dev" | awk '{print $1}'; fi
}

file_sha1() { shasum -a 1 "$1" | awk '{print $1}'; }
file_size() { stat -f%z "$1"; }
