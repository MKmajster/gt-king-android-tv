#!/usr/bin/env bash
# Wait for pipeline.sh's Android build to finish, then build the chainload package.
#   nohup setsid bash /mnt/c/<path-to-repo>/lineage/scripts/post-build.sh > /dev/null 2>&1 &
# Log: ~/android/post-build.log
set -o pipefail
export PATH="$HOME/bin:$PATH"
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$HOME/android/post-build.log"
{
echo "=== $(date '+%F %T') waiting for 'android build exit=' in pipeline.log"
while ! grep -q 'android build exit=' "$HOME/android/pipeline.log"; do sleep 120; done
rc=$(grep 'android build exit=' "$HOME/android/pipeline.log" | tail -1 | sed 's/.*exit=//')
echo "=== $(date '+%F %T') android build exit=$rc"
if [[ "$rc" != "0" ]]; then
    echo "build failed - last errors:"; grep -nE "FAILED:|error:" "$HOME/android/build-galilei.log" | grep -v -- "-Werror" | tail -20
    exit 1
fi
echo "=== chainload package"
TOP="$TOP" bash "$SRC/scripts/make-chainload-package.sh"
echo "=== artifacts"; ls -la "$SRC/out/tree/"
echo "=== $(date '+%F %T') done"
} >> "$LOG" 2>&1
