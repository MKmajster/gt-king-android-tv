#!/system/bin/sh
# FPS of the app currently on screen, from SurfaceFlinger's frame timestamps (works for any app:
# GL/Vulkan SurfaceViews included). Usage: sh sf-fps.sh <package substring> [samples]
PKG=$1; N=${2:-3}
# Android 15 lists "RequestedLayerState{<name> parentId=..}"; the frames of a GL/Vulkan app land on
# its "SurfaceView[...](BLAST)#N" layer
L=$(dumpsys SurfaceFlinger --list | grep -i "$PKG" | grep "SurfaceView\[" | grep "(BLAST)" | tail -1 \
    | sed 's/^RequestedLayerState{//; s/ parentId=.*//; s/}$//')
[ -z "$L" ] && { echo "no layer for $PKG"; exit 1; }
i=0
while [ $i -lt $N ]; do
    dumpsys SurfaceFlinger --latency-clear "$L" >/dev/null
    sleep 5
    # line 1 = refresh period; then "desired present / actual present / frame ready" in ns
    dumpsys SurfaceFlinger --latency "$L" | awk 'NR>1 && $2>0 && $2<9e18 {n++; if (n==1) a=$2; b=$2} END {if (n>1) printf "fps %.1f (%d frames)\n", (n-1)/((b-a)/1e9), n; else print "no frames"}'
    i=$((i+1))
done
echo "layer: $L"
