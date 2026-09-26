#!/usr/bin/env bash
# Layer 0: dump every eMMC partition (except data/cache) + diagnostics into backup/<date>-<tag>/.
# Usage: scripts/backup.sh [tag]   (default tag: stock)
source "$(dirname "$0")/lib.sh"

TAG="${1:-stock}"
OUT="$REPO_ROOT/backup/$(date +%Y%m%d)-$TAG"
PARTS="bootloader reserved env logo recovery misc dtbo cri_data param boot rsv tee metadata vbmeta odm system product vendor"
RAW="/dev/block/mmcblk0boot0 /dev/block/mmcblk0boot1"

require_device
mkdir -p "$OUT"

for p in $PARTS; do
  f="$OUT/$p.img"
  want="$(part_size "$p")"
  if [ -f "$f" ] && [ "$(file_size "$f")" = "$want" ]; then log "skip $p (already dumped)"; continue; fi
  log "dump $p ($want bytes)"
  adb_ exec-out "dd if=$BYNAME/$p bs=4194304 2>/dev/null" > "$f"
  got="$(file_size "$f")"
  [ "$got" = "$want" ] || die "$p: size mismatch got=$got want=$want"
done

for raw in $RAW; do
  b="$(basename "$raw")"
  f="$OUT/$b.img"
  want="$(part_size "$raw")"
  if [ -f "$f" ] && [ "$(file_size "$f")" = "$want" ]; then log "skip $b (already dumped)"; continue; fi
  log "dump $b ($want bytes)"
  adb_ exec-out "dd if=$raw bs=4194304 2>/dev/null" > "$f"
  got="$(file_size "$f")"
  [ "$got" = "$want" ] || die "$b: size mismatch got=$got want=$want"
done

ash getprop > "$OUT/getprop.txt"
ash dmesg > "$OUT/dmesg.txt" || true
ash "cat /proc/cmdline" > "$OUT/cmdline.txt"
ash "cat /proc/partitions" > "$OUT/partitions.txt"
ash "ls -la $BYNAME/" > "$OUT/by-name.txt"
ash "pm list packages -f" > "$OUT/packages.txt"
ash "pm list packages -d" > "$OUT/packages-disabled.txt"
adb_ exec-out "cat /proc/config.gz 2>/dev/null" > "$OUT/config.gz" || true
adb_ pull /data/local/tmp/atv_backup "$OUT/atv_backup" >/dev/null 2>&1 || log "no /data/local/tmp/atv_backup on box"

: > "$OUT/SHA1SUMS"
for p in $PARTS; do
  dev="$(dev_sha1 "$p")"
  loc="$(file_sha1 "$OUT/$p.img")"
  [ "$dev" = "$loc" ] || die "$p: sha1 mismatch device=$dev file=$loc"
  echo "$loc  $p.img" >> "$OUT/SHA1SUMS"
done
for raw in $RAW; do
  b="$(basename "$raw")"
  dev="$(dev_sha1 "$raw")"
  loc="$(file_sha1 "$OUT/$b.img")"
  [ "$dev" = "$loc" ] || die "$b: sha1 mismatch device=$dev file=$loc"
  echo "$loc  $b.img" >> "$OUT/SHA1SUMS"
done
log "backup complete: $OUT"
