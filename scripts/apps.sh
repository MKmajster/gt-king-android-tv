#!/usr/bin/env bash
# install: sideload every apps/*.apk (launcherx/ is handled by launcher.sh). store: open Play Store pages for store-only apps.
source "$(dirname "$0")/lib.sh"
require_device
STORE_PKGS="com.plexapp.android ar.tvplayer.tv com.androidfung.drminfo"   # Plex, TiviMate, DRM Info

case "${1:-install}" in
  install)
    ls "$REPO_ROOT"/apps/*.apk >/dev/null 2>&1 || die "no APKs in apps/ — run scripts/fetch_apps.sh first"
    for f in "$REPO_ROOT"/apps/*.apk; do
      log "install $(basename "$f")"; adb_ install -r -g "$f"
    done ;;
  store)
    for pkg in $STORE_PKGS; do
      ash "am start -a android.intent.action.VIEW -d market://details?id=$pkg" >/dev/null
      read -r -p "Play Store: install $pkg with the remote, then press Enter… "
    done ;;
  *) die "usage: apps.sh install|store" ;;
esac
ash "pm list packages" | grep -E 'org.xbmc.kodi|org.smarttube.stable|com.neilturner.aerialviews|com.plexapp.android|ar.tvplayer.tv|com.androidfung.drminfo' || true
