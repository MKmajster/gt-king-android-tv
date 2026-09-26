#!/usr/bin/env bash
# Build LineageOS 22.2 ATV for galilei inside WSL (16 GB RAM host: 14 GB for the VM + 24 GB swap).
#   TOP=~/android/lineage lineage/scripts/build.sh [targets...]     (default: bacon aml_upgrade)
# Log: ~/android/build-galilei.log ; run detached with:
#   nohup setsid bash /mnt/c/<path-to-repo>/lineage/scripts/build.sh > /dev/null 2>&1 &
set -o pipefail
TOP="${TOP:-$HOME/android/lineage}"
LOG="${LOG:-$HOME/android/build-galilei.log}"
JOBS="${JOBS:-8}"
TARGETS="${*:-bacon aml_upgrade}"

cd "$TOP" || exit 1
{
echo "=== $(date) build start: $TARGETS (-j$JOBS)"
export USE_CCACHE=1 CCACHE_EXEC=/usr/bin/ccache CCACHE_DIR="$HOME/.ccache"
ccache -M 50G >/dev/null
# soong: only one memory-hungry action (metalava, big links) at a time
export NINJA_HIGHMEM_NUM_JOBS=1
export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
breakfast galilei || { echo "breakfast failed"; exit 1; }
echo "=== $(date) breakfast ok: $(get_build_var TARGET_PRODUCT) $(get_build_var TARGET_BUILD_VARIANT)"
m -j"$JOBS" $TARGETS
rc=$?
echo "=== $(date) build exit=$rc"
ls -la out/target/product/galilei/*.zip out/target/product/galilei/aml_*package.img 2>/dev/null
exit $rc
} 2>&1 | tee -a "$LOG"
