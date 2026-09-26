# Android 15 TV for the Beelink GT-King — `galilei`

**English** · [Polski](README.pl.md) · [简体中文](README.zh-CN.md)

The Beelink GT-King (Amlogic **S922X**, 4×Cortex-A73 @2.2 GHz + 2×A53, Mali-G52, 4 GB LPDDR4,
64 GB eMMC, AP6275S Wi-Fi 5/BT 5) never got anything newer than Android 9 — not from Beelink, not
from the community ROMs built on the stock firmware. This repository is the complete bring-up of
**Android 15 Android TV** on that box: device tree, kernel fixes, bootloader chain, flashing
packages, the tooling used to get there and the notes of every dead end.

Two builds, same bootloader chain, same flashing procedure:

| | **v1** — LineageOS 22.2 | **v2** — 64-bit |
|---|---|---|
| Userspace | 32-bit (armeabi-v7a), like the stock firmware | **arm64 + arm** |
| Base | LineageOS 22.2 built from source with this device tree | voodik's LineageOS 22.1 ATV for the ODROID-N2 (same S922X) + GT-King kernel, DTB and vendor fixes |
| GPU driver | Mali r32p1 (32-bit) | Mali r51p0, Vulkan 1.3, GLES 3.2 |
| Google apps | included (MindTheGapps for Android TV) | included |
| Choose it for | a plain, lean Android TV | emulation (PS2, GameCube/Wii need 64-bit) |

Downloads: [GitHub Releases](https://github.com/MKmajster/gt-king-android-tv/releases/latest) ·
flashing: [`docs/release/INSTALL.md`](docs/release/INSTALL.md) ·
release notes and checksums: [`docs/release/RELEASE-NOTES.md`](docs/release/RELEASE-NOTES.md) ·
discussion and support: [XDA thread](https://xdaforums.com/t/rom-android-15-unofficial-s922x-lineageos-22-2-64-bit-android-tv-for-beelink-gt-king-galilei.4802970/)

## Screenshots

| | |
|---|---|
| ![Android TV home](docs/screenshots/home.png) | ![About: Android 15, kernel 4.9.337](docs/screenshots/about.png) |
| ![PlayStation 2: God of War (ARMSX2, 16:9)](docs/screenshots/ps2.jpg) | ![PSP: God of War: Ghost of Sparta (PPSSPP Vulkan 2x)](docs/screenshots/psp.jpg) |
| ![PlayStation: Crash Bandicoot 3 (SwanStation 5x = 1080p)](docs/screenshots/psx.jpg) | v2 screenshots, captured on the box over ADB (1920×1080) |

## What works

| | |
|---|---|
| System | Android 15 TV UI, kernel 4.9.337 (arm64), userdebug; ADB over the network |
| Video | Hardware H.264 / HEVC / VP9 decode — YouTube and SmartTube play 4K60 VP9 without dropped frames; 4K output modes present (not tested on a 4K TV) |
| Audio | HDMI L-PCM through the Amlogic "auge" sound card (the DAI set had to be fixed in the DTS) |
| Wi-Fi / BT | AP6275S (BCM43752) 5 GHz 11ac; Bluetooth 5 (v2: over a plain HCI UART with a kernel fix) |
| Remote | Stock infrared remote with the Beelink key table; USB/BT remotes, keyboards, gamepads (v2: hot-plug also after standby) |
| Power | Thermal control on both CPU clusters (the stock DTS never throttled the A53s), standby with the HDMI signal off and instant wake (the SoC stays awake) |
| Storage | eMMC, microSD, USB host (2.0 + 3.0 behind a Fresco Logic hub) |
| Misc | RTC (HYM8563), HDMI-CEC driver/HAL (TV control not tested yet), Widevine L3 + ClearKey |

Known limitations (details in [`docs/release/INSTALL.md`](docs/release/INSTALL.md)): Widevine L3
only (no L1 keybox on this box, even on stock), the Netflix Android TV app refuses uncertified
devices, the Chromecast built-in receiver cannot register (per-device certificate), standby without
deep sleep, ADB over USB does not work (use ADB over the network), Ethernet untested (the test
unit's PHY is dead in hardware).

## Emulation on v2 (measured, 1080p60 TV)

| System | Emulator | Result |
|---|---|---|
| PlayStation 2 | ARMSX2 (Vulkan, native resolution, 16:9 + no-interlace patches, 8x AF, sharpening) | God of War (PAL) 50/50 fps; Crash Bandicoot: The Wrath of Cortex 38–50 fps in play with per-game speed hacks (EE cycle rate/skip, GPU palette conversion) — the heaviest game tested |
| PSP | PPSSPP standalone (Vulkan, 2x) | God of War: Ghost of Sparta 60/60 fps |
| PlayStation | RetroArch SwanStation (5x = 1080p, PGXP, 24-bit colour, 16:9) | 50/50 fps |
| SNES / NES | RetroArch Snes9x / FCEUmm with CRT shader and run-ahead | full speed |

PS2 at full speed needs the Mali clock pinned at 800 MHz (v2 does this at boot: the devfreq load
reading of the bifrost driver is always 0, so the governor stayed at 399 MHz). PS2 upscaling is
beyond the Mali-G52 (1.5x/2x = 20–34 fps). None of this is possible on v1: a PS2 emulator reserves
~8 GB of address space and Dolphin is arm64-only.

## Flashing

See [`docs/release/INSTALL.md`](docs/release/INSTALL.md). Short version: Amlogic USB Burning Tool
2.2.0, the unpacked `.img`, `adb reboot update` with a USB-A↔A cable in the OTG port, wait 5–8
minutes, power-cycle. The package `aml_upgrade_package_stock-restore+stockbl` goes back to the
Beelink firmware.

## How it boots (and why it is unusual)

The GT-King ships a locked-down Amlogic u-boot 2015 whose BL2 carries the board's LPDDR4
training. Rather than replacing it, the packages keep the **stock bootloader** and install a
second-stage loader:

1. stock BL2 → BL31/BL32 → stock u-boot (`g12b_w400`),
2. its `preboot` hook: `if store read bl33 …; then go 0x1000000` — loads **our** LineageOS
   u-boot (BL33 v4, `lineage/uboot/gen_galilei_board.py`) from a dedicated `bl33` partition and
   jumps into it,
3. our u-boot boots `boot` with the GT-King DTB.

Both u-boots read the same `_aml_dtb`, so it is an Amlogic **multi-DTB container** with two
entries: the stock `g12b_w400_b` DTB (with the new partition table transplanted into it — the stock
u-boot hangs in its Ethernet init on anything else) and our `g12b_s922x_galilei` DTB.
The hook lives in the stock u-boot's **compiled-in default environment**: the BL33 inside the
stock FIP is unpacked (LZ4), its 147-byte `preboot=` string is replaced and the image is re-signed
with Amlogic's `aml_encrypt_g12b` (`lineage/scripts/patch-stock-bl33-env.py`); BL2/BL30/BL31/BL32
stay byte-identical. That is what makes the package flash-and-go: the USB Burning Tool ends every
burn with a `saveenv` of the default environment, so a hook that only lives in the saved
environment is gone before the first boot (the stock u-boot then boots the kernel itself, which
stops at 1.8 s without the A73 cluster clock set up).

## Repository map

| Path | Content |
|---|---|
| `lineage/device/beelink/galilei/` | LineageOS device tree for v1 (inherits `device/amlogic/g12-common`): board config, remote key tables, Wi-Fi/BT firmware config, init rc, GApps hook |
| `lineage/device/beelink/galilei/v2/` | v2 vendor helpers: `btuart-attach.c` (2 KB static HCI UART attach for the AP6275S Bluetooth), `btdiag.c` |
| `lineage/kernel/dts/` | `g12b_s922x_galilei.dts` (v1) and `v2/` (v2 DTB + partition table) — stock w400 values + fixes: audio DAIs, thermal cooling map, CPU regulators, Wi-Fi/BT, Ethernet |
| `lineage/patches/` | v1 kernel patches (stmmac double PM notifier = boot hang without a PHY; meson_wdt reload on resume); `v2/` = the six patches on top of voodik's kernel (eMMC partition table, SCPI timeout, stmmac, meson_wdt, hci_bcm setup, USB probing after a failed suspend); `wip/` = hdmitx resume lock-up investigation (not applied) |
| `lineage/uboot/gen_galilei_board.py` | Generates the `g12b_galilei_v1` board for the LineageOS u-boot (fixed boot env, no Ethernet, chainload-safe) |
| `lineage/scripts/` | v1: `setup-tree.sh`, `rebuild-final.sh`, `patch-stock-bl33-env.py`, `gen-privapp-allowlist.py`, `make-gapps-vendor.py`, `make-multi-dtb.py`, `make-packages-with-bootloader.sh`, `postflash-check.sh`; v2: `extract-voodik-vendor.sh`, `v2-kernel-patches.sh`, `v2-build-kernel.sh`, `v2-build-dhd.sh`, `v2-build-dtb.sh`, `v2-make-multidtb.sh`, `v2-make-m1.sh`, `v2-adb-flash.py`; release: `make-release-archives.sh`; serial console: `serial-console.py`, `uart-*.py`; measuring: `sf-fps.sh`, `ps2-bench.sh` |
| `docs/option1/` | Bring-up documentation: `BRINGUP.md` (build from source), `FLASH.md` (packages, console procedure), `UART.md` (header pinout), `EMMC-SHORT.md`, `HDMI-BOOT.md` |
| `docs/release/` | `INSTALL.md`, `RELEASE-NOTES.md`, `XDA-thread.bbcode`, `PUBLISH.md` |
| `tools/` | `hdmiboot/` (BootROM HDMI-boot dongle on an Arduino), `cp210x/` (USB-UART driver) |

Polish notes from the research phase: [`docs/RESEARCH-NOTES-PL.md`](docs/RESEARCH-NOTES-PL.md).

## Building

v1 (LineageOS 22.2 from source):

```
# once: sync LineageOS 22.2 with the Amlogic g12-common trees (docs/option1/BRINGUP.md)
TOP=~/android/lineage bash lineage/scripts/setup-tree.sh        # device tree, DTS, u-boot board, GApps
TOP=~/android/lineage bash lineage/scripts/rebuild-final.sh      # bacon + multi-DTB + Burning Tool package
```

`GAPPS=none` builds without Google apps. `setup-tree.sh` also applies the kernel patches from
`lineage/patches/` to `kernel/amlogic/linux-4.9` (idempotent).

v2 (64-bit; needs voodik's ODROID-N2 ATV 22.1 image and the v1 GApps package as the base for the
bootloader partitions):

```
bash lineage/scripts/extract-voodik-vendor.sh <his OTA zip> vendor system   # -> ~/voodik/*.img
bash lineage/scripts/v2-kernel-patches.sh        # voodik's kernel @660a3bebdf92 + lineage/patches/v2
bash lineage/scripts/v2-build-kernel.sh
bash lineage/scripts/v2-build-dhd.sh             # AP6275S driver module
bash lineage/scripts/v2-build-dtb.sh && bash lineage/scripts/v2-make-multidtb.sh
TAG=final bash lineage/scripts/v2-make-m1.sh     # -> aml_upgrade_package_v2-final.img
```

## Support

A hobby project, free and open. If it brought your GT-King back from the drawer, you can buy me a
coffee on [Ko-fi](https://ko-fi.com/mkmajster) (card or PayPal) — entirely optional.

Test reports help just as much: Ethernet, 4K/HDR TVs and HDMI-CEC are still untested.

Another Android TV box, or a project that needs a similar bring-up? I am open to taking on a new
project or helping with an existing one — open an issue here or send me a PM on XDA.

## Credits

LineageOS and the Amlogic g12-common maintainers (the v1 device tree inherits their common tree and
kernel); **voodik** — his LineageOS ATV for the ODROID-N2 and its kernel are the base of v2
([GitHub](https://github.com/voodik), [ODROID-N2 builds](https://oph.mdrjr.net/voodik/S922X/ODROID-N2/Android/));
Hardkernel; MindTheGapps; the CoreELEC and Khadas communities for the S922X/G12B knowledge; the
ARMSX2/PCSX2, PPSSPP, DuckStation/SwanStation and RetroArch projects; Beelink for the stock firmware
whose bootloader and blobs these builds still rely on.

## License

Device tree, scripts and documentation: Apache-2.0. Kernel patches: GPL-2.0 (they modify the
Amlogic 4.9 kernel). Proprietary vendor blobs and Google apps are not part of this repository.
