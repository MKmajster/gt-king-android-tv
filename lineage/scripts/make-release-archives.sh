#!/usr/bin/env bash
# Release archives for GitHub (2 GiB per asset) / XDA: every burn package as 7z, split into 1900 MB
# volumes when bigger, plus SHA-256 of the packages and of every archive file.
#   bash lineage/scripts/make-release-archives.sh      (Git Bash on Windows, uses 7-Zip)
# Output: lineage/out/release/{v1,v2,stock}/ + SHA256SUMS.txt + copies of the release docs.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
Z="/c/Program Files/7-Zip/7z.exe"
T=lineage/out/tree
R=lineage/out/release
mkdir -p "$R/v1" "$R/v2" "$R/stock"
pack() {  # dir package
    local d=$1 img=$2 base
    base=$(basename "$img" .img)
    rm -f "$R/$d/$base".7z*
    echo "== $(date +%T) $img -> $d/$base.7z"
    "$Z" a -t7z -mx=5 -mmt=on -v1900m "$R/$d/$base.7z" "$T/$img" > "$R/$d/$base.7z.log"
    # a single volume keeps the .001 suffix - give it the plain name
    if [ -f "$R/$d/$base.7z.001" ] && [ ! -f "$R/$d/$base.7z.002" ]; then mv "$R/$d/$base.7z.001" "$R/$d/$base.7z"; fi
    rm -f "$R/$d/$base.7z.log"
}
pack v1 aml_upgrade_package_galilei-los22.2-gapps.img
pack v2 aml_upgrade_package_v2-final.img
pack stock aml_upgrade_package_stock-restore+stockbl.img
echo "== $(date +%T) checksums"
{
    echo "# SHA-256 of the burn packages (.img, after unpacking)"
    (cd "$T" && sha256sum aml_upgrade_package_galilei-los22.2-gapps.img aml_upgrade_package_v2-final.img \
        aml_upgrade_package_stock-restore+stockbl.img)
    echo
    echo "# SHA-256 of the release files (7z archives / volumes)"
    (cd "$R" && sha256sum v1/* v2/* stock/*)
} > "$R/SHA256SUMS.txt"
cp docs/release/RELEASE-NOTES.md docs/release/INSTALL.md "$R/"
ls -la "$R" "$R"/*/ | awk '{print $5, $9}'
cat "$R/SHA256SUMS.txt"
echo "== $(date +%T) done"
