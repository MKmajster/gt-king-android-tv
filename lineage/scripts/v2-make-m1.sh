#!/usr/bin/env bash
# v2 milestone 1: voodik's ODROID-N2 LineageOS 22.1 ATV userspace (system + vendor, arm64) on the
# GT-King through our chain-load bootloader and the galilei v2 multi-DTB, plus the GT-King pieces.
#   bash lineage/scripts/v2-make-m1.sh           (WSL) -> lineage/out/tree/aml_upgrade_package_v2-${TAG}.img
# Env: KERNEL (default: our galilei-v2 build ~/v2/kout/.../Image.gz; voodik's own: ~/voodik/bootx/kernel)
#      TAG (default m1b)
# Vendor additions (debugfs, no mount):
#   * etc/init/hw/init.amlogic.rc - our u-boot passes androidboot.hardware=amlogic; imports his
#     init.odroidn2.rc + init.odroid.wifi.rc (normally imported through wifi.config.prefix from
#     /odm/odm.prop, which the GT-King layout does not use), loads dhd.ko after his cfg80211.ko, and
#     defines ir_config first (init keeps the first definition) with the GT-King remote table;
#   * lib/modules/dhd.ko (bcmdhd 101.10.591, v2-build-dhd.sh) + firmware/wifi/* (AP6275S, from v1);
#   * etc/remote-gtking.{cfg,tab} + usr/keylayout/Vendor_0001_Product_0001.kl (v1 remote);
#   * build.prop: his odm.prop values, service.adb.tcp.port=5555 (ADB over Wi-Fi for testing).
set -euo pipefail
TOP=$HOME/android/lineage
BIN=$TOP/out/host/linux-x86/bin
V=$HOME/voodik
O=$HOME/v2/out
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV=$SRC/device/beelink/galilei
KERNEL=${KERNEL:-$HOME/v2/kout/arch/arm64/boot/Image.gz}
TAG=${TAG:-m1b}
M=$O/$TAG
V1PKG=$SRC/out/tree/aml_upgrade_package_galilei-los22.2-gapps.img
OUTPKG=$SRC/out/tree/aml_upgrade_package_v2-$TAG.img
mkdir -p "$M"

echo "== boot.img: kernel $KERNEL + his ramdisk, galilei v2 DTB, v1 header layout"
python3 "$TOP/system/tools/mkbootimg/mkbootimg.py" --header_version 2 \
    --kernel "$KERNEL" --ramdisk "$V/bootx/ramdisk" --dtb "$O/g12b_s922x_galilei_v2.dtb" \
    --pagesize 2048 --base 0 --kernel_offset 0x01080000 --ramdisk_offset 0xfff88000 \
    --tags_offset 0xfef88100 --dtb_offset 0x01f00000 --os_version 15.0.0 --os_patch_level 2025-04 \
    --cmdline "otg_device=1 tee.disable_flag=1 androidboot.boot_devices=ffe07000.emmc" \
    -o "$M/boot.img"
if [ "${BOOT_ONLY:-0}" = 1 ]; then   # kernel/DTB iteration: only boot.img (usb-flash-part.py writes it)
    cp "$M/boot.img" "$SRC/out/v2-$TAG-boot.img"; ls -l "$SRC/out/v2-$TAG-boot.img"; exit 0
fi

echo "== vendor"
cp "$V/vendor.img" "$M/vendor.img"
cat > "$M/init.amlogic.rc" <<'RC'
# galilei (Beelink GT-King) v2 on voodik's ODROID-N2 vendor
import /vendor/etc/init/hw/init.odroidn2.rc
import /vendor/etc/init/hw/init.odroid.wifi.rc

# AP6275S (BCM43752A2) Wi-Fi on SDIO; cfg80211.ko is loaded on post-fs-data (init.odroid.board.rc)
on boot
    insmod /vendor/lib/modules/cfg80211.ko
    insmod /vendor/lib/modules/dhd.ko firmware_path=/wifi/ nvram_path=/wifi/

# AP6275S Bluetooth (BCM4362A2) on UART_A. voodik's btlinux HAL needs an hci0, which only USB
# dongles give him; btuart-attach puts /dev/ttyS1 into the kernel HCI UART line discipline with the
# Broadcom protocol (the kernel loads /vendor/firmware/brcm/BCM.hcd itself). The chip is powered by
# the bt-dev driver at probe (DTB power_down_disable = <1>; before that it only powered up on an
# rfkill 0 -> 1 toggle, which the btlinux HAL then also did on every Bluetooth off/on, resetting the
# patched chip). The toggle below is kept for a DTB without that property. Needs kernel galilei-v2
# with the hci_bcm setup fix (5th patch), else hci0 never leaves HCI_SETUP.
on boot
    write /sys/class/rfkill/rfkill0/state 0
    write /sys/class/rfkill/rfkill0/state 1
    start btuart

# Mali-G52 at 800 MHz: the bifrost devfreq load reading stays 0, so simple_ondemand never left
# 285-399 MHz and PS2 (ARMSX2, God of War) ran at 42 of 50 fps; fixed 800 MHz = full speed at
# 62-64 C. The GPU is power-gated when idle, so the fixed clock costs little.
on property:sys.boot_completed=1
    write /sys/class/devfreq/ffe40000.bifrost/governor performance
    # power_allocator: switch-on 65 -> 70 C, control target 75 -> 80 C (soc), 60/75 -> 65/80 (ddr).
    # Long PS2 sessions (Vulkan, GPU 96 %) reached 74 C; at 75 C the GPU/CPU clocks would be cut.
    # Hot 95 C / critical 110 C stay as they are.
    write /sys/class/thermal/thermal_zone0/trip_point_0_temp 70000
    write /sys/class/thermal/thermal_zone0/trip_point_1_temp 80000
    write /sys/class/thermal/thermal_zone1/trip_point_0_temp 65000
    write /sys/class/thermal/thermal_zone1/trip_point_1_temp 80000

# Wi-Fi country: nothing sets one here (no telephony, no ro.boot.wificountrycode), so cfg80211 stays
# in world mode "00", where 5 GHz is passive-scan only: the router's 5 GHz BSS was rarely found and
# the box sat on a busy 2.4 GHz channel (Moonlight: network frame drops every few seconds; after
# forcing PL: 5 GHz at 351 Mbit/s, 0 % ping loss). Two-letter code, e.g. `setprop
# persist.vendor.galilei.wifi_country PL` once; unset = world mode as before.
on property:sys.boot_completed=1 && property:persist.vendor.galilei.wifi_country=*
    exec_background u:r:shell:s0 root shell -- /system/bin/cmd wifi force-country-code enabled ${persist.vendor.galilei.wifi_country}

service btuart /vendor/bin/btuart-attach /dev/ttyS1
    class hal
    user root
    group bluetooth
    disabled

# GT-King remote (NEC 0x7f80); overrides /vendor/etc/init/ir_config.rc, which wants /odm/remote.tab4
service ir_config /vendor/bin/remotecfg -c /vendor/etc/remote-gtking.cfg -t /vendor/etc/remote-gtking.tab
    user root
    group system
    oneshot
    disabled
RC
debugfs -R "cat /build.prop" "$V/vendor.img" 2>/dev/null > "$M/build.prop"
cat >> "$M/build.prop" <<'PROP'

# galilei v2: voodik's odm.prop values (/odm is not used on the GT-King layout), ADB over Wi-Fi
wifi.config.prefix=wifi
ro.surface_flinger.primary_display_orientation=ORIENTATION_0
external_storage.sdcardfs.enabled=false
ro.hwui.use_vulkan=false
debug.renderengine.vulkan=true
service.adb.tcp.port=5555
# his SystemConfig patch drops features unless enabled: android.hardware.bluetooth* needs
# persist.disable_bluetooth=false (default true), android.hardware.hdmi.cec needs persist.hdmi_cec.enable
persist.disable_bluetooth=false
persist.hdmi_cec.enable=true
# Amlogic: HDMI hot-plug low must not put the box to sleep (TV input switch, flaky cable); CEC follows the TV
persist.sys.hdmi.keep_awake=true
# his Wi-Fi HAL reloads the driver (after a Wi-Fi off/on or a firmware-hang recovery) with
# finit_module(dhd.ko, ${persist.wifi_arg}) - without the paths dhd finds no firmware
persist.wifi_arg=firmware_path=/wifi/ nvram_path=/wifi/
# Bluetooth adapter name (the stack falls back to this; ro.product.model is lineage_odroidn2)
bluetooth.device.default_name=GT-King
PROP
printf 'u:object_r:vendor_file:s0\0' > "$M/l_file"
printf 'u:object_r:vendor_configs_file:s0\0' > "$M/l_cfg"
put() {  # dir name src mode label
    printf 'cd %s\nrm %s\nwrite %s %s\nsif %s mode 0100%s\nsif %s uid 0\nsif %s gid 0\nea_set -f %s %s security.selinux\n' \
        "$1" "$2" "$3" "$2" "$2" "$4" "$2" "$2" "$5" "$2"
}
{
    put /etc/init/hw init.amlogic.rc "$M/init.amlogic.rc" 644 "$M/l_cfg"
    put / build.prop "$M/build.prop" 600 "$M/l_file"
    put /lib/modules dhd.ko "$O/modules/dhd.ko" 644 "$M/l_file"
    printf 'cd /\nmkdir firmware\ncd /firmware\nmkdir wifi\n'   # debugfs mkdir wants a name in cwd
    printf 'sif /firmware mode 040755\nea_set -f %s /firmware security.selinux\n' "$M/l_file"
    printf 'sif /firmware/wifi mode 040755\nea_set -f %s /firmware/wifi security.selinux\n' "$M/l_file"
    for f in "$DEV"/wifi/*; do put /firmware/wifi "$(basename "$f")" "$f" 644 "$M/l_file"; done
    put /etc remote-gtking.cfg "$DEV/remote/remote.cfg" 644 "$M/l_cfg"
    put /etc remote-gtking.tab "$DEV/remote/remote.tab1" 644 "$M/l_cfg"
    put /usr/keylayout Vendor_0001_Product_0001.kl "$DEV/keylayout/Vendor_0001_Product_0001.kl" 644 "$M/l_cfg"
    # his device node rules live in the system root as /ueventd.odroidn2.rc, read only when
    # ro.hardware=odroidn2; ours is 'amlogic' -> /dev/mali0, /dev/ion ... stayed root 0600 and
    # SurfaceFlinger aborted ("no suitable EGLConfig"). /vendor/etc/ueventd.rc is always imported.
    put /etc ueventd.rc "$M/ueventd.rc" 644 "$M/l_cfg"
    # his Wi-Fi HAL (libwifi-hal.so, ODROID USB-dongle variant) only "loads the driver" for a USB
    # vid/pid listed in wifi_id_list.txt ("vid pid module /vendor/etc/modprobe.d/<list of .ko>");
    # the SDIO AP6275S never matches -> "Failed to load WiFi driver", Wi-Fi stays off. Entry for the
    # always-present USB 2.0 root hub (1d6b:0002) -> dhd; finit_module EEXIST (loaded on boot above)
    # counts as success and the HAL sets wlan.driver.status=ok.
    put /etc wifi_id_list.txt "$M/wifi_id_list.txt" 644 "$M/l_cfg"
    put /etc/modprobe.d dhd "$M/modprobe-dhd" 644 "$M/l_cfg"
    # Bluetooth: HCI UART attach helper (lineage/device/beelink/galilei/v2/btuart-attach.c) + patch
    put /bin btuart-attach "$O/btuart-attach" 755 "$M/l_exec"
    printf 'cd /firmware\nmkdir brcm\nsif /firmware/brcm mode 040755\nea_set -f %s /firmware/brcm security.selinux\n' "$M/l_file"
    put /firmware/brcm BCM.hcd "$DEV/bluetooth/BCM4362A2.hcd" 644 "$M/l_file"
    put /firmware/brcm BCM4362A2.hcd "$DEV/bluetooth/BCM4362A2.hcd" 644 "$M/l_file"
    # zram 256 MiB -> 1 GiB (3.7 GiB RAM; PS2/GameCube emulation + TV apps in the background)
    put /etc fstab.odroidn2 "$M/fstab.odroidn2" 644 "$M/l_cfg"
} > "$M/debugfs.cmd"
debugfs -R "cat /etc/fstab.odroidn2" "$V/vendor.img" 2>/dev/null | sed 's/zramsize=268435456/zramsize=1073741824/' > "$M/fstab.odroidn2"
grep -q "zramsize=1073741824" "$M/fstab.odroidn2" || { echo "fstab.odroidn2: zramsize not patched"; exit 1; }
printf 'u:object_r:vendor_file:s0\0' > "$M/l_exec"
clang=$HOME/android/lineage/prebuilts/clang/host/linux-x86/clang-r536225/bin/clang
"$clang" --target=aarch64-linux-gnu -O2 -ffreestanding -fno-stack-protector -fno-builtin -nostdlib -static \
    -fuse-ld=lld -Wall -o "$O/btuart-attach" "$DEV/v2/btuart-attach.c"
{ echo "1d6b 0002 dhd /vendor/etc/modprobe.d/dhd"; debugfs -R "cat /etc/wifi_id_list.txt" "$V/vendor.img" 2>/dev/null; } > "$M/wifi_id_list.txt"
echo /vendor/lib/modules/dhd.ko > "$M/modprobe-dhd"
debugfs -R "cat /ueventd.odroidn2.rc" "$V/system.img" 2>/dev/null > "$M/ueventd.rc"
[ -s "$M/ueventd.rc" ] || { echo "no ueventd.odroidn2.rc in system.img"; exit 1; }
debugfs -w -f "$M/debugfs.cmd" "$M/vendor.img" > "$M/debugfs.log" 2>&1
grep -i -E "error|not found|could not|no free" "$M/debugfs.log" | grep -v "rm: File not found" || true
for f in /etc/init/hw/init.amlogic.rc /lib/modules/dhd.ko /firmware/wifi/fw_bcm43752a2_ag.bin /etc/remote-gtking.tab /etc/ueventd.rc /etc/wifi_id_list.txt /etc/modprobe.d/dhd; do
    echo "  $f: $(debugfs -R "stat $f" "$M/vendor.img" 2>/dev/null | grep -o 'Size: *[0-9]*') $(debugfs -R "ea_list $f" "$M/vendor.img" 2>/dev/null | grep -o 'u:object_r:[a-z_]*')"
done
debugfs -R "cat /build.prop" "$M/vendor.img" 2>/dev/null | tail -3
e2fsck -fn "$M/vendor.img" > "$M/e2fsck.log" 2>&1 && echo "vendor fsck clean" || { tail -8 "$M/e2fsck.log"; exit 1; }
if [ "${VENDOR_ONLY:-0}" = 1 ]; then   # vendor iteration: raw image for usb-flash-part.py (chunked)
    cp "$M/vendor.img" "$SRC/out/v2-$TAG-vendor.img"; ls -l "$SRC/out/v2-$TAG-vendor.img"; exit 0
fi

echo "== sparse images"
[ -f "$O/m1/system.simg" ] && cp "$O/m1/system.simg" "$M/system.simg" || "$BIN/img2simg" "$V/system.img" "$M/system.simg"
"$BIN/img2simg" "$M/vendor.img" "$M/vendor.simg"
ls -l "$M"/*.simg "$M/boot.img"

echo "== package"
python3 "$SRC/scripts/repack-package-items.py" "$V1PKG" "$OUTPKG" "$BIN/aml_image_packer" \
    --dtb "$O/multi-dtb-v2.img" --set boot="$M/boot.img" --drop super --drop vbmeta \
    --add system="$M/system.simg" --add vendor="$M/vendor.simg" | tail -2
(cd "$(dirname "$OUTPKG")" && sha256sum "$(basename "$OUTPKG")" | tee "SHA256SUMS-v2-$TAG")
