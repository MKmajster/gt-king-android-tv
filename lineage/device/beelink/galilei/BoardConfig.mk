#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/beelink/galilei

## Bluetooth
BOARD_HAVE_BLUETOOTH := true

## Bootloader
TARGET_BOOTLOADER_BOARD_NAME := galilei

## DTB
TARGET_DTB_NAME := g12b_s922x_galilei

## Kernel modules
TARGET_KERNEL_EXT_MODULES := \
    dhd-driver/bcmdhd.101.10.591.x

## Partitions
# Must match the "super" partition size in the kernel DTS
# (partition_mbox_dynamic_galilei.dtsi): 4 GiB. eMMC is 61 GB.
BOARD_SUPER_PARTITION_SIZE := 4294967296

## Properties
TARGET_VENDOR_PROP += $(DEVICE_PATH)/vendor.prop

## SELinux
BOARD_VENDOR_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/vendor

## Wi-Fi (AP6275S = BCM43752A2; NOT AP6398S - the stock dhd version string misled the first port)
BOARD_HOSTAPD_PRIVATE_LIB := lib_driver_cmd_bcmdhd
BOARD_WLAN_DEVICE := bcmdhd
BOARD_WPA_SUPPLICANT_DRIVER := NL80211
BOARD_WPA_SUPPLICANT_PRIVATE_LIB := lib_driver_cmd_bcmdhd
WIFI_DRIVER_FW_PATH_AP := "/wifi/fw_bcm43752a2_ag_apsta.bin"
WIFI_DRIVER_FW_PATH_STA := "/wifi/fw_bcm43752a2_ag.bin"
WIFI_DRIVER_FW_PATH_PARAM := "/sys/module/dhd/parameters/firmware_path"
WPA_SUPPLICANT_VERSION := VER_0_8_X

## Include the common tree BoardConfig makefile
include device/amlogic/g12-common/BoardConfigCommon.mk

## Kernel
# g12a_defconfig from the common tree plus a board fragment merged on top
# (arch/arm64/configs/galilei.config: HYM8563 RTC). Must come after the
# common BoardConfig, which sets TARGET_KERNEL_CONFIG := g12a_defconfig.
TARGET_KERNEL_CONFIG := g12a_defconfig galilei.config

## Video firmware: load the decoder microcode from the kernel, not through OP-TEE.
# The stock Beelink BL32 is OP-TEE, so the media driver's tee_enabled() is true and every decoder
# asks the secure world for its microcode (TEE_SMC_LOAD_VIDEO_FW). The secure world only has it
# after tee-supplicant + tee_preload_fw pushed video_ucode.bin into it - which this build does not
# ship (TARGET_HAS_TEE := false, no optee.ko). Result without this flag: "VP9: the TEE fw loading
# failed, err: ffff0007", decoders never produce a frame, every video app shows black (2026-09-25).
# tee.disable_flag=1 (drivers/amlogic/tee/tee.c module_param) makes tee_enabled() false and the
# driver loads /vendor/lib/firmware/video/video_ucode.bin itself; H.264/HEVC/VP9 verified.
BOARD_KERNEL_CMDLINE += tee.disable_flag=1

## Include the proprietary BoardConfig makefile
include vendor/beelink/galilei/BoardConfigVendor.mk
