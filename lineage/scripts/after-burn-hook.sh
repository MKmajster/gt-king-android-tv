#!/bin/bash
# Wait for a NEW "Burning successfully" in today's USB Burning Tool log, then CLOSE the tool
# (otherwise it grabs the box again after our reset and re-flashes it, wiping the env) and run
# catch-burn.py against the box still sitting in u-boot burn mode: hook (hook.py) + BL33 v3 + reset.
LOGDIR="/c/Program Files (x86)/Amlogic/USB_Burning_Tool/log/$(date +%Y.%m)/$(date +%Y.%m.%d)"
base=$(cat "$LOGDIR"/*.txt 2>/dev/null | grep -a -c 'Burning successfully')
echo "$(date +%T) armed: waiting for a new 'Burning successfully' (baseline $base)"
while [ "$(cat "$LOGDIR"/*.txt 2>/dev/null | grep -a -c 'Burning successfully')" -le "$base" ]; do sleep 1; done
echo "$(date +%T) Burning successfully seen -> closing USB_Burning_Tool"
taskkill /IM USB_Burning_Tool.exe /F >/dev/null 2>&1 && echo "$(date +%T) tool closed" || echo "$(date +%T) tool was not running"
sleep 2
PYTHONUNBUFFERED=1 py -3.14 lineage/scripts/catch-burn.py --wait 240 --bl33 lineage/out/bl33-v3.img
echo "$(date +%T) catch-burn exit code $?"
