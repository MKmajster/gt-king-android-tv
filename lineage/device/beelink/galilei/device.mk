#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

## Bluetooth
PRODUCT_PACKAGES += \
    BluetoothOverlayTarget \
    libbt-vendor

$(call soong_config_set,brcm_libbt,bdroid_buildcfg_include_dir,$(LOCAL_PATH)/bluetooth/include)
$(call soong_config_set,brcm_libbt,custom_bt_config,//$(LOCAL_PATH):vnd_galilei.txt)

## Bluetooth firmware: the module is AP6275S (BCM43752A2 WiFi + BCM4362A2 BT).
## The stock Beelink BCM4362A2.hcd differs from the dhd-driver one; ship the stock
## file (first PRODUCT_COPY_FILES entry wins) and keep bluetooth.mk for the rest.
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/bluetooth/BCM4362A2.hcd:$(TARGET_COPY_OUT_VENDOR)/etc/bluetooth/BCM4362A2.hcd
include kernel/amlogic/kernel-modules/dhd-driver/firmware/bluetooth/bluetooth.mk

## Factory
PRODUCT_HOST_PACKAGES += \
    aml_image_packer

## Init
PRODUCT_PACKAGES += \
    init.amlogic.wifi_buildin.rc \
    init.galilei.rc

## IR remote: stock Beelink key tables (override the ADT-3 ones from the
## g12-common vendor tree; the first PRODUCT_COPY_FILES entry wins)
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/remote/remote.cfg:$(TARGET_COPY_OUT_VENDOR)/etc/remote.cfg \
    $(LOCAL_PATH)/remote/remote.tab1:$(TARGET_COPY_OUT_VENDOR)/etc/remote.tab1 \
    $(LOCAL_PATH)/remote/remote.tab2:$(TARGET_COPY_OUT_VENDOR)/etc/remote.tab2 \
    $(LOCAL_PATH)/remote/remote.tab3:$(TARGET_COPY_OUT_VENDOR)/etc/remote.tab3

## Keylayout (aml_keypad IR input device: Vendor 0001 Product 0001)
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/keylayout/Vendor_0001_Product_0001.kl:$(TARGET_COPY_OUT_VENDOR)/usr/keylayout/Vendor_0001_Product_0001.kl

## Platform
TARGET_AMLOGIC_SOC := g12b

## Bring-up: no UART on this box, so adbd listens on TCP from the first boot
## (userdebug, ro.adb.secure=0). Drop this once the port is done.
PRODUCT_SYSTEM_PROPERTIES += \
    service.adb.tcp.port=5555

## TEE
# Stock has OP-TEE in the tee partition, but LineageOS does not ship a
# matching TA set; use software keymaster/gatekeeper like radxa02pro.
TARGET_HAS_TEE := false

## Soong Namespaces
PRODUCT_SOONG_NAMESPACES += \
    $(LOCAL_PATH) \
    hardware/broadcom/libbt

## Wi-Fi firmware: AP6275S = BCM43752A2 (stock dmesg: fw_bcm43752a2_ag.bin, nvram_ap6275s.txt,
## clm_bcm43752a2_ag.blob). dhd-driver has no bcm43752a2 firmware, so these come from the stock
## vendor image (backup/20260914-stock, /vendor/etc/wifi/43752a2/), named the way
## bcmdhd.101.10.591.x dhd_config.c builds the names for chip 43752 rev 2 (ap6275s).
# wifi/config_bcm43752a2_ag.txt carries dhd_idletime=0: with the default idle timeout (1 tick) the
# bcmdhd 101.10 bus sleeps between packets and every KSO wake-up costs a cmd52 timeout on sd_emmc_a
# ("meson-mmc: sdio: resp_timeout", ~0.6/s idle, none under load; measured 2026-09-24). Keeping the
# bus awake removes them and halves the idle ping latency (18.8 -> 7.7 ms). dhd_slpauto=0 breaks
# the data path on this firmware - do not use it.
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/wifi/fw_bcm43752a2_ag.bin:$(TARGET_COPY_OUT_VENDOR)/firmware/wifi/fw_bcm43752a2_ag.bin \
    $(LOCAL_PATH)/wifi/fw_bcm43752a2_ag_apsta.bin:$(TARGET_COPY_OUT_VENDOR)/firmware/wifi/fw_bcm43752a2_ag_apsta.bin \
    $(LOCAL_PATH)/wifi/fw_bcm43752a2_ag_p2p.bin:$(TARGET_COPY_OUT_VENDOR)/firmware/wifi/fw_bcm43752a2_ag_p2p.bin \
    $(LOCAL_PATH)/wifi/nvram_ap6275s.txt:$(TARGET_COPY_OUT_VENDOR)/firmware/wifi/nvram_ap6275s.txt \
    $(LOCAL_PATH)/wifi/clm_bcm43752a2_ag.blob:$(TARGET_COPY_OUT_VENDOR)/firmware/wifi/clm_bcm43752a2_ag.blob \
    $(LOCAL_PATH)/wifi/config_bcm43752a2_ag.txt:$(TARGET_COPY_OUT_VENDOR)/firmware/wifi/config_bcm43752a2_ag.txt
include kernel/amlogic/kernel-modules/dhd-driver/firmware/wifi/wifi.mk

## Inherit from the common tree product makefile
## Power HAL hints: the g12-common powerhint.json maps INTERACTIVE to
## /sys/power/early_suspend_trigger (kernel early-suspend = HDMI off on screen-off). On this box the
## hdmitx late-resume path still locks the SoC up (see lineage/patches/kernel-hdmitx-*), so until
## that is fixed the galilei copy drops the INTERACTIVE action: the screen goes black, HDMI stays
## up, the box never enters the early-suspend path. Listed before g12.mk so this copy wins.
PRODUCT_COPY_FILES +=     $(LOCAL_PATH)/configs/power/powerhint.json:$(TARGET_COPY_OUT_VENDOR)/etc/powerhint.json

$(call inherit-product, device/amlogic/g12-common/g12.mk)

## Inherit from the proprietary files makefile
$(call inherit-product, vendor/beelink/galilei/galilei-vendor.mk)
