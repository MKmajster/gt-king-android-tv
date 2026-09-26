#!/usr/bin/env bash
# Download redistributable APKs into apps/: Kodi (arm32), SmartTube (arm32), Aerial Views.
source "$(dirname "$0")/lib.sh"
A="$REPO_ROOT/apps"; mkdir -p "$A"

KODI_DIR="https://mirrors.kodi.tv/releases/android/arm/"
KODI="$(curl -fsS "$KODI_DIR" | grep -oE 'kodi-[0-9]+\.[0-9]+-[A-Za-z]+-armeabi-v7a\.apk' | sort -u \
  | sed -E 's/^kodi-([0-9]+)\.([0-9]+)-.*/\1 \2 &/' | sort -k1,1n -k2,2n | tail -1 | awk '{print $3}' || true)"
[ -n "$KODI" ] || die "could not list Kodi releases"
log "kodi: $KODI"
[ -f "$A/$KODI" ] || curl -fL -o "$A/$KODI" "$KODI_DIR$KODI"

gh release download -R yuliskov/SmartTube -p 'SmartTube_stable_*_armeabi-v7a.apk' -D "$A" --skip-existing
gh release download -R theothernt/AerialViews -p '*.apk' -D "$A" --skip-existing
ls -la "$A"
