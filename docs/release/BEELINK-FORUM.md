Android 15 TV for the GT-King (not Pro) — LineageOS 22.2 and a 64-bit build

> Flashing replaces the whole eMMC and is done at your own risk. For the **GT-King** (black, S922X, 4 GB / 64 GB, board GTKing-D4X16 rev 2.0–4.0) only — **not** for the GT-King Pro.

The last official GT-King firmware is Android 9 (2022-04-01). I have brought a current Android TV to it:

- **v1** — LineageOS 22.2 (Android 15 TV), 32-bit userspace like the stock firmware, Google apps included.
- **v3** — Android 15 TV with a **64-bit** userspace (based on voodik's LineageOS 22.1 ATV for the ODROID-N2, same S922X) with GT-King kernel, device tree and driver fixes. Take v3 for emulation: PS2 (God of War 50/50 fps), PSP (60 fps at 2x), PS1 at 1080p. (v3 = the former v2 with the audio fix below; v2 is superseded and no longer offered.)

Both keep the stock Beelink bootloader and chain-load a second u-boot from a separate partition, so the box can always go back to stock (a stock-restore package is in the release).

**New in v3 (2026-10-09):** fixes HDMI / S-PDIF / analog (3.5 mm) audio, which was silent on v2 — only Bluetooth audio worked. The 64-bit device tree pointed the internal audio mux at the wrong source; v3 corrects it. If you are on v2 and only get sound over Bluetooth, flash v3.

![Android TV home](https://raw.githubusercontent.com/MKmajster/gt-king-android-tv/main/docs/screenshots/home.png)
![About](https://raw.githubusercontent.com/MKmajster/gt-king-android-tv/main/docs/screenshots/about.png)
![PS2 on v3](https://raw.githubusercontent.com/MKmajster/gt-king-android-tv/main/docs/screenshots/ps2.jpg)

**What works:** stock IR remote, Android TV home + Play Store, Wi-Fi 5 GHz, Bluetooth, hardware H.264/HEVC/VP9 (YouTube 4K60 without dropped frames), HDMI / S-PDIF / analog audio (fixed in v3), USB gamepads/keyboards, microSD, thermal control, standby with instant wake, ADB over the network.

**Known limits:** Widevine L3 only (the GT-King never had L1, stock neither), the Netflix Android TV app refuses uncertified devices, Chromecast built-in cannot register, no deep sleep, ADB over USB does not work, Ethernet untested (the test unit's PHY is dead), 4K/HDR and HDMI-CEC not tested yet — reports welcome.

**Install (short):** Amlogic USB Burning Tool 2.2.0 → import the unpacked `.img` → Start ("Erase flash" on, "Erase bootloader" off) → USB-A↔A cable in the USB 2.0 OTG port next to the SD slot → `adb reboot update` from the running box → 5–8 minutes → power-cycle. Full guide: [INSTALL.md](https://github.com/MKmajster/gt-king-android-tv/blob/main/docs/release/INSTALL.md)

- **Downloads:** [GitHub Releases](https://github.com/MKmajster/gt-king-android-tv/releases/latest) (v3, v1, stock restore, SHA-256 sums)
- **Source code** (device tree, kernel patches, bootloader chain, tools): [github.com/MKmajster/gt-king-android-tv](https://github.com/MKmajster/gt-king-android-tv)
- **Discussion and help:** [XDA thread](https://xdaforums.com/t/rom-android-15-unofficial-s922x-lineageos-22-2-64-bit-android-tv-for-beelink-gt-king-galilei.4802970/)

Credits: LineageOS, the Amlogic g12-common maintainers, voodik, Hardkernel, MindTheGapps, CoreELEC and Khadas communities, and Beelink for the stock bootloader and blobs.

A hobby project, free and open — if it brought your GT-King back from the drawer, you can [buy me a coffee on Ko-fi](https://ko-fi.com/mkmajster). Another box or project that needs a similar bring-up? Send me a message.
