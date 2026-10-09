# Installing LineageOS 22.2 (Android 15 TV) on the Beelink GT-King (S922X)

**Codename:** `galilei` · **Board:** GTKing-D4X16 (rev 2.0–4.0, S922X, 4 GB LPDDR4, 64 GB eMMC, AP6275S Wi-Fi/BT)
**Status:** userdebug build, Google apps for Android TV included ("full" variant), Widevine L3.

> Read the *Known limitations* section before flashing. Flashing replaces the whole eMMC
> (Android partitions, bootloader and its environment). Make a backup of the stock firmware first if
> you ever want to go back (the stock 2022-04-01 Beelink image restores everything).

## What you need

- Windows PC with **Amlogic USB Burning Tool 2.2.0** (v2.1.9 also works) — run it as administrator.
- **USB-A ↔ USB-A cable** (both ends male) connected to the box's **USB 2.0 (OTG) port** — the one
  next to the SD slot. The USB 3.0 ports are host-only and will not work.
- The package (both shipped 7z-compressed, unpack with 7-Zip; SHA-256 sums in `SHA256SUMS.txt`):
  **v1** `aml_upgrade_package_galilei-los22.2-gapps.img` (~1.5 GB, LineageOS 22.2, Google apps
  included) or **v3 (64-bit, recommended)** `aml_upgrade_package_v3-final.img`
  (~2.2 GB, Google apps included) — same procedure. (v3 = v2 with the HDMI/S/PDIF/analog audio fix;
  v2 is no longer offered.)
- A way to reach burn mode (see step 2). On the stock firmware: *Settings → About → build number ×7 →
  Developer options → USB debugging*, plus `adb` on the PC.

## 1. Load the package

1. Start USB Burning Tool → *File → Import image* → pick the `.img` package.
2. Leave **Erase flash** ticked, leave **Erase bootloader** unticked. The box is wiped on every flash
   either way (Amlogic's burn u-boot requests `wipe_data` for the first boot), so back up first —
   the package writes the stock Beelink bootloader itself (with the chain-load hook in its default
   environment) and adds its own second-stage loader.
3. Press **Start**. The tool now waits for the device.

## 2. Put the box into burn mode

The reliable way (from a running Android, stock or LineageOS):

```
adb connect <box-ip>:5555      # LineageOS: Settings → Developer options → ADB over network
adb reboot update
```

Connect the USB-A ↔ USB-A cable **before** running the command. The box reboots into the Amlogic
burn mode, Windows enumerates a *WorldCup Device* and the tool starts writing (5–8 minutes).
Do not plug the cable in while the box is powered off — on this board that hangs the bootloader.

If the box has no working Android any more: on this board the classic tricks (reset pinhole,
cable plugged in at power-on, SD card) did **not** get the BootROM into USB mode in our tests. What
works is the `update` command at the u-boot prompt over the internal UART header
(`lineage/scripts/serial-console.py --port COMx --break --cmd update`), or the eMMC short
procedure described in `docs/option1/EMMC-SHORT.md`. Keep a working Android on the box until you
are done, and do not erase the bootloader.

## 3. First boot

- Unplug the USB-A cable when the tool reports *Success*, then power-cycle the box.
- The first boot takes ~2 minutes (the LineageOS boot animation, then the Google TV setup wizard).
  Everything in the wizard can be done with the infrared remote (D-pad, OK, Back).
- Sign in to Google, let the Play Store update itself, done.
- For testers: Settings → System → About → tap *Build* 7× → Developer options → *Android
  debugging* and *ADB over network* (and *Rooted debugging* for `adb root`); then
  `bash lineage/scripts/postflash-check.sh` from the repository prints a PASS/FAIL list of ~45
  checks (bootloader hook, GApps, GmsCore, codecs, Wi-Fi, standby, stress).

## 4. If it does not boot into LineageOS

The package keeps the stock Beelink bootloader (its BL2 carries the board's DDR training) and
chain-loads the LineageOS u-boot from a `bl33` partition. The hook that does this lives in the
**compiled-in default environment** of the stock u-boot shipped in the package
(`lineage/scripts/patch-stock-bl33-env.py`), so it survives the USB Burning Tool's environment
reset and any `env default`. An environment-only hook does not: the tool ends every burn with a
`saveenv` of the defaults, and the stock u-boot then boots the LineageOS kernel itself, which
stops at 1.8 s (the A73 cluster clock is never set up) and the box reboots in a loop.

- Stock Beelink logo forever / burn mode after flashing → the `bootloader` partition was not
  written (an old package, or *Erase bootloader* ticked with one). Flash again as described above.
- A microSD card with an Amlogic `aml_autoscript` (CoreELEC, Armbian, ...) inserted at power-on
  boots that card, exactly like on the stock firmware (`forceupdate` runs before the chain-load).
  Remove the card to boot LineageOS again; the hook survives the card's `saveenv`.
- Last resort, internal UART header (3 pads next to the DKEY sticker, 3.3 V TTL, 115200 8N1 —
  see `docs/option1/UART.md`): `py -3 lineage/scripts/serial-console.py --port COMx --break --fix-hook`
  writes the hook into the saved environment and reboots. Please report in the thread if you ever
  needed this.
- **v3 / v2 (64-bit):** once on the lab unit, the first boot after flashing a 64-bit package came up with the stock
  `preboot` (the saved environment had `upgrade_step=2`, so the stock u-boot never restored its
  hooked defaults): it booted the kernel itself with the wrong DTB and the box **switched itself
  off after ~12 s**. The UART `--fix-hook` above fixed it permanently. Symptom check on the UART
  log: after the stock `U-Boot 2015.01-gcc0379a5f9` banner there must be
  `## Starting application at 0x01000000` and a second `U-Boot 2015.01` banner.

## Going back to stock

Flash the stock Beelink image (`GTKing_..._20220401`) or the `stock-restore` package from this
project with the same procedure. The bootloader is never removed, so recovery is always possible.

## Known limitations (this build)

| Area | State |
|---|---|
| Widevine | **L3** (software). Netflix from the Play Store is hidden on uncertified devices; the sideloaded Android-TV APK plays in SD. Disney+/Prime/Max play in SD. Kodi + Netflix add-on works (SD/720p). The GT-King never had an L1 keybox — the stock firmware was L3 as well. |
| Standby | Power key = screen and HDMI signal off (the TV sees "no signal" and goes to standby by itself), the box keeps running and wakes instantly on any remote key. The kernel early-suspend path and deep sleep are disabled: the LineageOS hdmitx driver locks the SoC up on resume with the lab's DVI monitor (`lineage/patches/wip/README.md`). `persist.vendor.galilei.deepsleep=1` releases the wakelock for experiments. |
| Ethernet | Driver and DTS are complete; the test unit's RTL8211F PHY is not answering on MDIO (hardware, also under the stock firmware), so Gigabit Ethernet is **untested**. Please report. |
| Chromecast built-in | Receiver needs a per-device Cast certificate (certified devices only) — the box does not appear as a cast target. Casting from apps on the box works. |
| USB gadget | ADB over USB does not work (dwc2 gadget), use ADB over network. USB host ports work. |
| Userspace | v1: 32-bit (armeabi-v7a), like the stock firmware — 64-bit-only apps (PS2 emulators, Dolphin) do not run. **v2: 64-bit** (arm64 + arm); see RELEASE-NOTES.md for measured emulator results. |
| HDMI-CEC | Driver and HAL present; verified only that the monitor in the lab has no CEC. |
| 4K / HDR / auto frame rate | Lab display is 1080p — needs testing on a 4K TV. |
| BT remote wake | Not supported. |
