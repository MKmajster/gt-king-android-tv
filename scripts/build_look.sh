#!/usr/bin/env bash
# Assemble overlays/gtk-look: generated bootanimation + optional Google Sans → Roboto file override.
# Put GoogleSans-{Regular,Italic,Medium,MediumItalic,Bold,BoldItalic}.ttf in overlays/gtk-look/fonts-src/ to enable fonts.
source "$(dirname "$0")/lib.sh"

MOD="$REPO_ROOT/overlays/gtk-look"
SRC="$MOD/fonts-src"
mkdir -p "$MOD/system/media"
rm -rf "$MOD/system/fonts"

FONT_ARGS=""
[ -f "$SRC/GoogleSans-Medium.ttf" ] && FONT_ARGS="--font $SRC/GoogleSans-Medium.ttf"
# shellcheck disable=SC2086
python3 "$REPO_ROOT/scripts/make_bootanimation.py" "$MOD/system/media/bootanimation.zip" $FONT_ARGS

# GoogleSans style → Roboto file names it replaces (bash 3.2: no associative arrays)
MAP="Regular:Regular Regular:Light Regular:Thin Medium:Medium Bold:Bold Bold:Black \
Italic:Italic Italic:LightItalic Italic:ThinItalic MediumItalic:MediumItalic BoldItalic:BoldItalic BoldItalic:BlackItalic"
for pair in $MAP; do
  gs="${pair%%:*}"; rb="${pair##*:}"
  [ -f "$SRC/GoogleSans-$gs.ttf" ] || continue
  mkdir -p "$MOD/system/fonts"
  cp "$SRC/GoogleSans-$gs.ttf" "$MOD/system/fonts/Roboto-$rb.ttf"
done
[ -d "$MOD/system/fonts" ] && log "fonts: $(ls "$MOD/system/fonts" | wc -l | tr -d ' ') files" || log "fonts: none (no fonts-src)"
ls -la "$MOD/system/media/bootanimation.zip"
