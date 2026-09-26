#!/usr/bin/env bash
# Download StevenBlack unified hosts into overlays/gtk-hosts/system/etc/hosts.
source "$(dirname "$0")/lib.sh"
DST="$REPO_ROOT/overlays/gtk-hosts/system/etc"; mkdir -p "$DST"
curl -fsSL https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts -o "$DST/hosts"
grep -qE '^127\.0\.0\.1[[:space:]]+localhost' "$DST/hosts" || die "downloaded hosts lacks localhost entry"
log "hosts: $(wc -l < "$DST/hosts" | tr -d ' ') lines"
