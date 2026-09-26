#!/usr/bin/env bash
# Rebuild only the kernel Image.gz in the existing LineageOS KERNEL_OBJ (incremental, minutes) and
# repack it into a boot.img - for kernel-patch iterations without the hour-long `m bootimage`
# (soong analysis dominates on this 16 GB host). Mirrors vendor/lineage/build/tasks/kernel.mk +
# vendor/lineage/config/BoardConfigKernel.mk for galilei (arm64, clang r536225, gcc 4.9 binutils
# for CROSS_COMPILE, ld.lld, HOSTCC=clang).
#   TOP=~/android/lineage bash lineage/scripts/kernel-quick.sh            -> lineage/out/boot-quick.img
# The ramdisk/cmdline/offsets come from the last full-build boot.img (unpack_bootimg); the AVB
# hash footer is unsigned like the build's (Algorithm NONE, verification disabled on this board).
set -euo pipefail
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="$TOP/out/target/product/galilei"
KOBJ="$P/obj/KERNEL_OBJ"
CLANG="$TOP/prebuilts/clang/host/linux-x86/clang-r536225"
GCC64="$TOP/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/bin"
GCC32="$TOP/prebuilts/gcc/linux-x86/arm/arm-linux-androideabi-4.9/bin"
B="$TOP/out/host/linux-x86/bin"
[[ -f "$KOBJ/.config" ]] || { echo "no $KOBJ/.config - run the full build once first" >&2; exit 1; }

export PATH="$B:$CLANG/bin:$GCC64:$TOP/prebuilts/tools-lineage/linux-x86/bin:$GCC32:$PATH"
export LD_LIBRARY_PATH="$CLANG/lib64:${LD_LIBRARY_PATH:-}"
export HIP_PATH=none PERL5LIB="$TOP/prebuilts/tools-lineage/common/perl-base"
cd "$TOP"
"$TOP/prebuilts/build-tools/linux-x86/bin/make" -j"$(getconf _NPROCESSORS_ONLN)" \
    HOSTCFLAGS="-I/usr/include -I/usr/include/x86_64-linux-gnu" HOSTLDFLAGS="-L/usr/lib/x86_64-linux-gnu -L/usr/lib64 -fuse-ld=lld" \
    HOSTCC="$CLANG/bin/clang" HOSTCXX="$CLANG/bin/clang++" LD="$CLANG/bin/ld.lld" AR="$CLANG/bin/llvm-ar" DTC_EXT="$B/dtc" \
    -C kernel/amlogic/linux-4.9 O="$KOBJ" ARCH=arm64 \
    CROSS_COMPILE="$GCC64/aarch64-linux-android-" CROSS_COMPILE_ARM32="$GCC32/arm-linux-androidkernel-" CROSS_COMPILE_COMPAT="$GCC32/arm-linux-androidkernel-" \
    CLANG_TRIPLE=aarch64-linux-gnu- CC="/usr/bin/ccache clang" LLVM_IAS=1 Image.gz 2>&1 | grep -E "^  (CC|LD|GZIP|OBJCOPY|AS).*(hdmi|vmlinux|Image)|error|Error|warning: .*hdmi" || true
[[ ${PIPESTATUS[0]} == 0 ]] || { echo "KERNEL BUILD FAILED" >&2; exit 1; }
# CC and LLVM_IAS=1 must match what the LineageOS build recorded in KERNEL_OBJ/**/.*.cmd, otherwise
# kbuild rebuilds every object (and the vdso then fails with the external assembler).
ls -la --time-style=+%H:%M:%S "$KOBJ/arch/arm64/boot/Image.gz" | awk '{print $5, $6, $7}'

# repack boot.img: same header/ramdisk/cmdline as the last full build
W=/tmp/bootrepack-quick; rm -rf "$W"; mkdir -p "$W"
"$B/unpack_bootimg" --boot_img "$P/boot.img" --out "$W" --format mkbootimg > "$W/args.txt"
ARGS=$(sed "s|--kernel $W/kernel|--kernel $KOBJ/arch/arm64/boot/Image.gz|" "$W/args.txt")
eval "$B/mkbootimg" $ARGS -o "$W/boot-quick.img"
"$B/avbtool" add_hash_footer --image "$W/boot-quick.img" --partition_size 16777216 --partition_name boot
cp "$W/boot-quick.img" "$SRC/out/boot-quick.img"
sha256sum "$SRC/out/boot-quick.img"
strings "$KOBJ/arch/arm64/boot/Image" 2>/dev/null | grep -m1 "Linux version" | cut -c1-110 || true
