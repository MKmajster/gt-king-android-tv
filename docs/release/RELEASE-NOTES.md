# Android 15 TV for Beelink GT-King — release v2, 64-bit (2026-09-26)

Discussion, questions and test reports: [XDA thread](https://xdaforums.com/t/rom-android-15-unofficial-s922x-lineageos-22-2-64-bit-android-tv-for-beelink-gt-king-galilei.4802970/)

v2 moves the box to a **64-bit (arm64 + arm) userspace**: voodik's LineageOS 22.1 Android TV build
for the ODROID-N2 (same S922X SoC, Mali r51p0 drivers with lib64, Vulkan 1.3) on voodik's 4.9.337
kernel source with six GT-King patches, the GT-King device tree, AP6275S Wi-Fi/Bluetooth and the
same bootloader chain as v1. v1 (32-bit, LineageOS 22.2, below) stays available.

## Package

| File | Size | SHA-256 |
|---|---|---|
| `aml_upgrade_package_v2-final.img` | 2 244 113 164 B | `152503a627b504eaf6eab5a029e8d8c3ba062ea12b41054f4b90023173a2d45c` |

Kernel `galilei-v2` build #11, vendor M1p, multi-DTB with the v2 partition table (system 3 GiB,
vendor 768 MiB), Google apps for Android TV (from voodik's build). userdebug, test-keys.

## What 64-bit brings (measured on the lab unit, 1080p60 TV)

| | v1 (32-bit) | v2 (64-bit) |
|---|---|---|
| PlayStation 2 | not possible (no 32-bit PS2 emulator) | ARMSX2: God of War (PAL) 50/50 fps with 16:9 and no-interlace patches, 8x AF, CAS sharpening |
| GameCube / Wii | not possible (Dolphin is 64-bit only) | Dolphin (arm64) installs; not tested (no GameCube/Wii games on the lab unit) |
| PlayStation 1 | PCSX-ReARMed, native resolution | SwanStation 5x (1080p), PGXP, 24-bit colour, 16:9: 50/50 fps |
| PSP | 32-bit libretro core | standalone PPSSPP, Vulkan 2x: God of War – Ghost of Sparta 60/60 fps |
| GPU driver | Mali r32p1, 32-bit blobs (ADT-3) | Mali r51p0, lib64, Vulkan 1.3, GLES 3.2 |
| Apps | armeabi-v7a only | arm64-v8a and armeabi-v7a |

The big gain is what could not run at all before: ARMSX2 reserves ~8 GB of address space for its
fastmem mapping and Dolphin has been 64-bit only for years. No same-game fps comparison between v1
and v2 was made (v1 is no longer on the unit). Part of the PSP result comes from the standalone
Vulkan emulator rather than from 64-bit alone (the arm64 libretro PPSSPP core reached 42 fps at 1x).
PS2 at full speed also needs the Mali GPU fixed at 800 MHz (v2 does this at boot: the bifrost
devfreq load reading is 0, so simple_ondemand stayed at 399 MHz and PS2 ran at 84 % speed).
Upscaling PS2 is beyond the Mali-G52 (1.5x/2x = 20–34 fps).

## Verified on the lab unit (v2)

- Boot to the Android TV home screen, IR remote, HDMI 1080p60, Wi-Fi 5 GHz auto-connect, ADB root
  over Wi-Fi (userdebug), Bluetooth on/off cycles (AP6275S on UART, patch loaded by the kernel),
  HDMI-CEC service enabled, USB gamepad (hot-plug, also after the screen was off).
- YouTube / SmartTube: 4K60 VP9 on the hardware decoder, 0 dropped frames; HDMI audio L-PCM 48 kHz.
- Wi-Fi under sustained load (~28 MB/s transfers of 8 GB files) without firmware traps.
- Temperatures: 39–40 °C idle, 62–64 °C in PS2 (GPU at 800 MHz), control target 80 °C.
- Standby: power key = screen off, instant wake; deep sleep is always aborted by Wi-Fi wakeups
  (no resume hangs).

## Known issues (v2)

- **Bootloader hook after flashing**: once on the lab unit the first boot after a USB Burning Tool
  flash of a v2 package came up with the stock `preboot` (no chain-load): the stock u-boot started
  the kernel with the wrong DTB and the box switched itself off after ~12 s. Fix over the internal
  UART: `serial-console.py --port COMx --break --fix-hook` (see INSTALL.md §4). Not seen with the v1
  packages; please report if it happens to you.
- Based on voodik's userdebug build (test-keys): the ODROID-specific settings app is disabled, the
  device model reads `lineage_odroidn2`.
- Widevine L3; Netflix Android TV app refuses the device (-13); Chromecast receiver cannot register;
  Ethernet untested; ADB over USB not available (same as v1).
- The lab TV reports only 60 Hz modes, so 50 Hz / 24 Hz auto frame rate and ALLM were not tested;
  PAL games (50 fps) on a 60 Hz output judder slightly - use a game's 60 Hz mode where it has one.

## Changelog (v2)

- v2 (2026-09-26): 64-bit userspace (voodik ODROID-N2 LineageOS 22.1 ATV). Kernel patches on top of
  voodik's source: Amlogic eMMC partition table; SCPI timeout; stmmac PM notifier double
  registration (the boot hang); meson_wdt; hci_bcm setup return code (Bluetooth over a plain HCI UART);
  suspend: unblock device probing when freezing tasks fails (no USB hot-plug after the first screen-off).
  Vendor: ueventd rules for Mali/ION, Wi-Fi HAL entry for the SDIO AP6275S, `btuart-attach` (2 KB
  static aarch64 HCI UART attach helper), Bluetooth firmware, BT/CEC feature properties, dhd `war=0x11`
  (no firmware re-init traps under load), `persist.wifi_arg`, zram 1 GiB, Mali devfreq governor
  `performance`, thermal targets 70/80 °C. DTB: efuse node, bt-dev `power_down_disable`.

---

# LineageOS 22.2 (Android 15 TV) for Beelink GT-King — release v1 (2026-09-25)

## Packages (Amlogic USB Burning Tool)

| File | Size | SHA-256 |
|---|---|---|
| `aml_upgrade_package_galilei-los22.2-gapps.img` | 1 519 721 556 B | `370e6b75cada6d71b63764126c663dec9929a25987d61899a530f2a98681735b` |

The package carries the stock Beelink bootloader with the chain-load hook in its default
environment (`patch-stock-bl33-env.py`), the LineageOS second-stage u-boot (`bl33`), the
multi-DTB, kernel 4.9.337 and LineageOS 22.2 with MindTheGapps for Android TV.

## Verified on the lab unit (GT-King, GTKing-D4X16 V4.0, 4/64 GB)

- Flash with USB Burning Tool 2.2.0 (Erase flash on, Erase bootloader off) → first boot without a
  serial console: BL2/BL31 accept the re-signed BL33, the stock u-boot chain-loads from its default
  environment after the tool's environment reset.
- Boot to Android in ~28 s, Google TV setup wizard with the infrared remote, Wi-Fi 5 GHz + DHCP.
- YouTube (Android TV app) plays 4K VP9 hardware-decoded (3840×2160, 0 dropped frames, 49 °C).
- Hardware video decoding H.264/HEVC/VP9 (decoder frame counters checked), HDMI audio, Mali-G52 GLES 3.2 / Vulkan 1.1, Bluetooth,
  USB host, microSD, RTC, IR remote (stock key table), thermal throttling on both clusters.
- Power key: screen off / instant wake, no reboot (`postflash-check.sh` standby cycle).
- `lineage/scripts/postflash-check.sh` on the flashed GApps package (build before the HDMI standby
  rule, otherwise identical; the rule itself was tested by hand): **56 / 56 PASS** (bootloader hook in
  env, kernel patches, thermal, GPU/Vulkan, HDMI + audio, HW codecs with local firmware, Wi-Fi idle
  tuning, IR table, power HAL + standby cycle without reboot, GmsCore/GSF, Google TV launcher, 30 s
  six-core stress at 74.6 °C).
- Widevine L3 end to end without any account: a public Widevine DASH test stream (Shaka's "Angel One",
  cwip-shaka-proxy license) plays in a WebView browser - EME `com.widevine.alpha`, robustness
  `SW_SECURE_CRYPTO`, streaming license acquired, encrypted VP9 on the hardware decoder, 1339 frames,
  0 dropped, 0 decode errors.
- Streaming apps: HBO Max, Prime Video and SkyShowtime install from the Play Store and start;
  Disney+ and Netflix are not offered by the Play Store on uncertified devices. The Netflix Android TV
  app refuses the device (`CONFIG_DEVICE_NOT_PERMITTED`, -13); the Netflix phone app installs and runs.
- Emulation (32-bit userspace): RetroArch 32-bit with PCSX-ReARMed (PS1), PPSSPP (PSP), Snes9x, FCEUmm
  at full speed (PS1/SNES/NES 50/60 FPS, PSP title screens at 59.9 FPS).

## Known issues

- Widevine L3 only (no L1 keybox on this hardware, stock was L3 too).
- 32-bit userspace (as stock and all LineageOS Amlogic builds).
- Standby turns the screen and the HDMI signal off but keeps the SoC awake; deep sleep disabled
  (hdmitx resume hang, `lineage/patches/wip/`).
- Ethernet untested (lab unit's PHY is dead in hardware).
- Chromecast built-in receiver cannot register (no per-device Cast certificate).
- ADB over USB does not work (use ADB over network).
- 4K/HDR/AFR/CEC not verified on a TV yet (lab display is a 1080p DVI monitor).
- Not certified by Google: register the GSF ID at google.com/android/uncertified if Play complains.

## Changelog

- v1 rebuild (2026-09-26): AP6275S firmware config `war=0x11` (the fix for firmware re-init traps
  under sustained Wi-Fi load found on v2; the same bcmdhd 101.10.x driver parses it) and a neutral
  build identity. Only the GApps variant is released from now on. This rebuild was not re-flashed
  on the lab unit; everything else is identical to the verified build below.
- v1 (2026-09-25): first public build. Video decoder microcode loaded by the kernel instead of
  OP-TEE (`tee.disable_flag=1`; without it every video was black). Chain-load hook compiled into the stock u-boot's default
  env; complete privileged-permission allowlists for the Google TV apps; GoogleServicesFramework on
  /system so GmsCore Pano 23.48 does not crash-loop on Android 15; galilei init rc in
  /vendor/etc/init; plan-B standby with the HDMI signal switched off while the screen is off (the TV
  shows "no signal" and can go to sleep); stmmac and meson_wdt kernel fixes; galilei DTS (audio DAIs,
  cooling map, AP6275S); `dhd_idletime=0`.
