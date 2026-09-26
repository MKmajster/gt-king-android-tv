#!/usr/bin/env bash
# Remote-free UI driving over ADB: dump (text + bounds), tap <text>, key <KEYCODE>, shot <file.png>.
# Usage: scripts/ui.sh dump | tap "<text or content-desc substring>" | key <KEYCODE> [n] | shot <out.png> | text "<string>"
source "$(dirname "$0")/lib.sh"
require_device
CMD="${1:?dump|tap|key|shot|text}"; ARG="${2:-}"
dump() { adb_ shell "uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml" </dev/null | python3 -c '
import sys,re,xml.etree.ElementTree as ET
d=sys.stdin.read(); i=d.find("<?xml")
if i<0: sys.exit("no ui dump")
t=ET.fromstring(d[i:])
for n in t.iter("node"):
    label=n.get("text") or n.get("content-desc")
    if not label: continue
    x1,y1,x2,y2=map(int,re.findall(r"\d+",n.get("bounds")))
    print("%d,%d\t%s\t%s%s%s"%((x1+x2)//2,(y1+y2)//2,n.get("class").split(".")[-1],label.replace("\n"," ")[:90],
          " [focused]" if n.get("focused")=="true" else "", " [checked]" if n.get("checked")=="true" else ""))'; }
case "$CMD" in
  dump) dump ;;
  tap)  line="$(dump | grep -iF "$ARG" | head -1)"; [ -n "$line" ] || die "no UI element matching '$ARG'"
        xy="${line%%	*}"; ash "input tap ${xy%,*} ${xy#*,}"; log "tapped '$ARG' at $xy" ;;
  key)  n="${3:-1}"; for i in $(seq 1 "$n"); do ash "input keyevent $ARG"; done ;;
  text) ash "input text '$ARG'" ;;
  shot) adb_ exec-out screencap -p > "$ARG"; log "saved $ARG" ;;
  *) die "usage: ui.sh dump|tap|key|shot|text" ;;
esac
