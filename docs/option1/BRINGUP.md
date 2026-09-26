# Opcja 1 — bring-up LineageOS 22.2 ATV na GT-King PRO (galilei)

Stan: 2026-09-15 (PC/WSL).
Wszystko, co jest w repo pod `lineage/`, wchodzi do drzewa LOS skryptem `lineage/scripts/setup-tree.sh`.

## 0. Co jest w `lineage/`

| Ścieżka w repo | Trafia do drzewa LOS | Co to |
|---|---|---|
| `lineage/device/beelink/galilei/` | `device/beelink/galilei/` | drzewo urządzenia (klon `radxa02pro` + rzeczy Beelinka: tabele IR `remote/`, keylayout, BT `vnd_galilei.txt`, `factory/` pod USB Burning Tool, super 4 GiB) |
| `lineage/kernel/dts/g12b_s922x_galilei.dts` | `kernel/amlogic/linux-4.9/arch/arm64/boot/dts/amlogic/` | DTS płyty: baza `g12b_a311d_w400.dts` + wartości ze stockowego DTB (OPP S922X, LED GPIOAO_11, PHY RTL8211F/RGMII, RTC HYM8563, S/PDIF, eMMC HS200, bez NPU/ISP/wentylatora) |
| `lineage/kernel/dts/partition_mbox_dynamic_galilei.dtsi` | j.w. | layout partycji (jak `deadpool`, ale `super` = 4 GiB) — **musi się zgadzać z `BOARD_SUPER_PARTITION_SIZE`** |
| `lineage/kernel/configs/galilei.config` | `arch/arm64/configs/` | fragment defconfig (`CONFIG_RTC_DRV_HYM8563`), scalany przez `TARGET_KERNEL_CONFIG := g12a_defconfig galilei.config` (LOS 22.2 `kernel.mk` + reguła `%.config` kernela 4.9) |
| `lineage/uboot/gen_galilei_board.py` | generuje `board/amlogic/g12b_galilei_v1/`, `configs/g12b_galilei_v1.h`, `defconfigs/…`, łata `board/amlogic/Kconfig` | płyta u-boot = W400 + HDMI zamiast panelu, bez DV w logo, power → recovery, bez sieci |
| `lineage/uboot/build_galilei.sh` | `hardware/amlogic/u-boot_build/` | build BL33 + pakowanie z `fip-radxa-zero2` (BL2/BL30/BL31 G12B, LPDDR4) |
| `lineage/local_manifests/galilei.xml` | `.repo/local_manifests/` | repozytoria Amlogic G12 + TheMuppets |

Zweryfikowane offline (2026-09-15): DTS kompiluje się `cpp`+`dtc` bez błędów (ostrzeżenia identyczne jak w w400), generator u-boota przechodzi na kopii drzewa.

## 1. Kolejność pracy na PC (WSL Ubuntu 24.04, `~/android/lineage`)

```bash
# 1. sync (raz; trwa godziny) — uruchomiony 2026-09-15, log ~/android/sync.log
repo init -u https://github.com/LineageOS/android.git -b lineage-22.2 --git-lfs --depth=1 --no-clone-bundle
cp <repo>/lineage/local_manifests/galilei.xml .repo/local_manifests/
repo sync -c -j4 --no-clone-bundle --no-tags --force-sync

# 2. port do drzewa
TOP=~/android/lineage bash /mnt/c/<path-to-repo>/lineage/scripts/setup-tree.sh

# 3. u-boot (ściąga toolchain linaro 4.8 ~100 MB; wynik: vendor/beelink/galilei/radio/bootloader.img
#    + hardware/amlogic/u-boot_build/uboot-bins/u-boot.bin{,.sd.bin,.usb.bl2,.usb.tpl})
device/beelink/galilei/build_u-boot.sh

# 4. Android
source build/envsetup.sh
breakfast galilei
export NINJA_HIGHMEM_NUM_JOBS=1     # 16 GB RAM
m -j6 bacon aml_upgrade             # OTA zip + aml_upgrade_package.img (USB Burning Tool)
```

Punkt kontrolny A (zielony build `radxa02pro`) zastąpiony bezpośrednim buildem `galilei` — drzewo galilei jest klonem radxa02pro, więc błędy toolchainu i tak wyjdą na nim.

## 2. Bootloader — jedyne realne ryzyko

Fakty:
- Stock: U-Boot 2015.01 Beelink (2022-04-01), BL2 „g12b gfa34f81 Aug 2 2019”, **nieszyfrowany** (stringi czytelne) → secure boot najpewniej wyłączony (potwierdzenie: test RAM przez pyamlboot — BootROM odrzuci niepodpisany obraz, jeśli SB jest włączony).
- LOS: BL33 (u-boot) budujemy sami; BL2/BL30/BL31 + firmware DDR to prebuilty z `fip-radxa-zero2` (Radxa Zero 2 Pro: A311D + **4 GB LPDDR4**, jak u nas). Timing LPDDR4 siedzi w BL2 (`acs.bin` = skompilowany `timing.c`), więc BL2 Radxy może nie zainicjalizować kości DDR Beelinka.
- Układ `bootloader.img` (partycja): 512 B zer + `u-boot.bin` = [BL2 podpisany 64 KiB, nagłówek `@AML` @+0x10] + [FIP: bl30/bl31/bl33 + ddr fw]. `u-boot.bin` = `bootloader.img[0x200:]`.

Analiza binarna (2026-09-15, `lineage/scripts/hybrid-bootloader.py` + skrypty w scratchpadzie):
- Nagłówek FIP (TOC `aa640001`) i sloty firmware DDR w stocku i w naszym `u-boot.bin` są **w tych samych miejscach**; ciała firmware LPDDR4 (`lpddr4_1d/2d`, `diag_lpddr4`, `piei`, `ddr4_2d`, `ddr3_1d`, `lpddr3_1d`) są **bajt w bajt identyczne** — różnią się tylko `ddr4_1d` i `aml_ddr` (tego stock w ogóle nie ma; BL2 2019 go nie zna).
- Timing DDR siedzi w ostatnich 4 KiB podpisanego BL2 (`acs`, offset 0xF000). Stockowy `acs` ma inny układ niż w BL2 Radxy (2019 `LPDDR4_PHY_V_0_1_15` vs 2020 `V_0_1_22`) → **nie przeszczepiać samego acs**; przeszczepia się cały BL2.
- Stock FIP ma BL32 (OP-TEE 256 KB); nasz go nie ma (`TARGET_HAS_TEE := false`, secmon w DTS zostawiony 36 MB jak w stocku).

Kandydaci do testu RAM (wszystkie w `lineage/out/`, każdy jako `.usb.bl2` + `.usb.tpl` dla pyamlboot; `.usb.bl2` = pierwsze 64 KiB `u-boot.bin`, `.usb.tpl` = reszta):
1. `u-boot-galilei-radxafip.bin` — czysty LOS: BL2 Radxy (2020, timing LPDDR4 Radxa Zero 2 Pro) + nasz FIP.
2. `u-boot-galilei-hybrid-stockbl2.bin` — **stockowy BL2** (timing Beelinka, znany dobry) + nasz FIP (identyczne firmware LPDDR4, nowsze BL30/BL31, nasz BL33).
Jeśli 1 nie inicjalizuje DDR (brak logo, brak enumeracji), 2 jest właściwym kandydatem. Jeśli oba padają na etapie BL2 → BootROM odrzuca niepodpisany BL2 = secure boot włączony (wtedy tylko stockowy bootloader + kernel LOS przez `boot`/`dtb` — plan awaryjny).

Procedura (w tej kolejności):
1. **Test RAM bez flashowania** — kabel **USB‑A ↔ USB‑A** do portu **USB 2.0** boxa (OTG; porty USB 3.0 są za hubem Fresco Logic i są tylko hostowe), box w trybie BootROM USB (pinhole reset przy włączaniu albo `adb reboot update` ze stocka; Windows widzi „WorldCup Device” VID 1B8E PID C003). Z Windows: `pyamlboot` (`boot-g12.py u-boot.bin.usb.bl2 + .usb.tpl`) albo USB Burning Tool w trybie „boot” — jeśli na HDMI pojawi się logo/konsola u-boota, DDR działa.
2. Jeśli DDR nie wstaje z BL2 Radxy → **hybryda**: stockowy BL2 (pierwsze 64 KiB stockowego `u-boot.bin`) + nasz FIP (`lineage/scripts/hybrid-bootloader.sh`, do napisania po analizie nagłówków).
3. Dopiero potem flash całości USB Burning Tool (`aml_upgrade_package.img`, **bez** „Erase bootloader/all” chyba że świadomie; `aml_sdc_burn.ini` ma `erase_bootloader=1` bo bootloader i tak podmieniamy).
4. Ratunek: oficjalny firmware Beelink GT‑King Pro (`.img`) do USB Burning Tool — pobrać **przed** krokiem 3. Tryb burn siedzi w BootROM, więc zły bootloader nie brickuje boxa na stałe.

### Narzędzia USB na Windows
- Python 3.14 jest na PC (`py -3.14`); `pyamlboot 1.0.0` + `pyusb` + `libusb` zainstalowane (`pip --user`). Skrypt `boot-g12.py <u-boot.bin>` bierze **cały** `u-boot.bin` (sam ładuje pierwsze 64 KiB = BL2 pod 0xfffa0000, a resztę BL2 dociąga protokołem AMLC) — gotowy wrapper: `powershell -ExecutionPolicy Bypass -File lineage\scripts\ramboot-win.ps1 hybrid|radxa`.
- Box w trybie BootROM USB musi mieć sterownik **WinUSB** (Zadig → „WorldCup Device”, VID 1B8E PID C003) — Zadig wymaga admina, robi to użytkownik.
- Alternatywa bez pyamlboot: **Amlogic USB Burning Tool** (też admin do instalacji sterownika); do RAM-testu nie nadaje się, tylko do pełnego flashu `aml_upgrade_package.img`.
- W WSL pyamlboot działa dopiero z `usbipd-win` (brak na PC; instalacja = admin).

### Stan połączenia USB PC ↔ box (zweryfikowane 2026-09-15, sesja 4)
- Kabel USB‑A↔USB‑A w porcie USB 2.0 boxa **działa**: po `adb reboot update` Windows widzi „WorldCup Device” `USB\VID_1B8E&PID_C003` (Hub_#0002 Port_#0003, ~6 s, potem u-boot bootuje dalej), po `adb reboot fastboot` — `USB\VID_18D1&PID_0D02` (fastboot u-boota). Oba bez sterownika (status Error, kod 28).
- W Androidzie gadżet dalej pokazuje `DISCONNECTED` mimo VBUS z PC (GOTGCTL BSesVld=1) — stock nie wystawia ADB po USB; nieistotne dla portu (liczy się BootROM/u-boot).
- `pyusb` na Windows: `libusb-1.0.dll` z pakietu pip `libusb` nie jest na PATH → `ramboot-win.ps1` dodaje `%APPDATA%\Python\Python314\site-packages\libusb\_platform\windows_64` sam; `ramboot-win.ps1 list` wypisuje urządzenia widoczne dla libusb (test sterownika).
- Do zrobienia przez użytkownika (admin): `tools\zadig.exe` → Options → List All Devices; ponieważ tryb burn trwa 6 s, wygodniej Device → Create New Device: nazwa `WorldCup Device`, USB ID `1B8E` `C003`, sterownik **WinUSB** → Install Driver. Opcjonalnie to samo dla `18D1` `0D02` (fastboot u-boota → `fastboot.exe reboot` zamiast odłączania zasilania).
- **Uwaga — karta microSD w boxie**: w boxie siedzi microSD z Linuksem (mmcblk1, 8 partycji; OpenSSH 9.9 + Samba). Stockowy u-boot po `adb reboot update` (gdy żaden PC nie podłączy się w 6 s) przechodzi do `sdc_burn` → `recovery_from_sdcard` i **bootuje kartę** (box widoczny tylko na porcie 22, bez adb); powrót do Androida wyłącznie przez odłączenie zasilania. Karta z `aml_sdc_burn.ini` flashowałaby box automatycznie. **Przed eksperymentami z bootloaderem wyjąć kartę.**
- Tryb BootROM (RAM-boot czeka na hosta bez limitu czasu): box bez zasilania, kabel A‑A wpięty, wykałaczką przytrzymać reset w gnieździe AV i podłączyć zasilacz, trzymać ~5 s → w Windows „WorldCup Device”. Potem `powershell -ExecutionPolicy Bypass -File lineage\scripts
amboot-win.ps1 hybrid` (albo `radxa`), patrzeć na HDMI.

### WYNIK 2026-09-15 17:28 — nasz u-boot (BL33 `g12b_galilei_v1`) DZIAŁA na boxie (test w RAM)
Metoda (`lineage/scripts/chainload-test.py`, nic nie zapisuje na eMMC): Android → kabel A‑A w USB 2.0 → `adb reboot update` → stockowy u-boot w trybie burn (IDENTIFY `ROM 0.7 Stage 0.16`, **pw=0 = brak blokady secure‑boot**) → znacznik w RAM‑owym env (`setenv aaa_marker …`), `env export -t 0x0a000000` + odczyt przez USB → upload surowego BL33 (`lineage/out/u-boot-galilei-bl33-raw.bin`, 1 241 920 B, wejście 0x01000000) z `dcache off`/`icache off` → `go 0x1000000`.
Dowody: (1) USB zniknęło 17:28:12 i wróciło 17:28:15 — nowa instancja u-boota zainicjalizowała gadżet i (bo reboot_mode=update) weszła w **swój** tryb burn; (2) znacznik zniknął — env wczytany na nowo z eMMC; (3) env zawiera **`aml_dt=g12b_s922x_galilei`** (ustawia to tylko kod naszej płyty; stock daje `g12b_w400_b`). Czyli: relokacja, DDR (ze stockowego BL2), odczyt env i DTB z eMMC, USB — wszystko działa w naszym BL33.
Bonus `run storeboot` w naszym u-boocie: `imgread kernel boot` + `bootm` przeszły (USB zostało zenumerowane, ale przestało odpowiadać = CPU w kernelu), Android **nie wstał** — stockowy boot.img nie ma ramdysku i wymaga `skip_initramfs` + `root=…`, a nasz `storeboot` dodaje `skip_initramfs` tylko gdy `get_system_as_root_mode` zwróci 1; dla obrazu LOS (ramdysk + dynamic partitions) to nieistotne. Do sprawdzenia przy okazji: logo na HDMI w naszym preboot (użytkownik zgłaszał czarny ekran przy pierwszej próbie).
Niezmienione ryzyko: BL2/DDR z FIP Radxy nadal nieprzetestowane (wymaga BootROM — patrz niżej); hybryda ze stockowym BL2 tego ryzyka nie ma.
Praktyka: po `go` box zostaje w (naszym) trybie burn — `burn-cmd.py --reset` restartuje go normalnie; po zawieszeniu kernela konieczny reset zasilaniem **z wypiętym kablem** (zimny start z kablem = BootROM czeka na hosta, „czerwone oczy", a enumeracja BootROM‑u na tym PC jest zawodna).

### Instalacja — wariant B (rekomendowany): stockowy bootloader + chainload naszego BL33
Skoro nasz BL33 działa po skoku `go` ze stockowego u-boota, bootloadera Beelinka **nie trzeba w ogóle wymieniać**:
1. Layout partycji galilei dostał partycję **`bl33`** (2 MiB, przed `super`; `parts = <16>`) — surowy `build/u-boot.bin` naszej płyty.
2. Paczka `aml_upgrade_package_chainload.img` (`lineage/scripts/make-chainload-package.sh`, config `factory/image_upgrade_chainload.cfg`): jak zwykła paczka LOS, ale **bez** wpisu `PARTITION bootloader`, z `bl33.img` → `bl33`, `erase_bootloader=0`; `u-boot.bin` w paczce = stockowy (używany tylko przez USB Burning Tool w etapie BootROM, nie flashowany).
3. Hook w env stocka (`lineage/scripts/chainload-env.py --set`, box w trybie burn): `preboot=run upgrade_key; if store read 0x1000000 bl33 0 0x140000; then dcache off; icache off; go 0x1000000; fi` — zmienna `preboot` nadpisuje kompilowany `CONFIG_PREBOOT`. `run upgrade_key` na początku zostawia furtkę: pinhole/klawisz power przy starcie → stockowy tryb burn → `chainload-env.py --restore`. Dopóki partycji `bl33` nie ma, `store read` cicho pada i stock bootuje normalnie — hook można założyć przed flashem.
4. Po chainloadzie nasz u-boot sam obsługuje reboot reason (normal/recovery/update), czyta tablicę partycji LOS z nowego `_aml_dtb` i bootuje `boot.img`.
Ryzyko bricka bootloadera: zero (BL2/BL30/BL31/BL33 Beelinka nietknięte; do cofnięcia: env z `backup/20260914-stock/env.img` albo `--restore`). Koszt: ~1–2 s dłuższy start (dwa u-booty).
Wariant A (hybryda: stock BL2 + FIP LOS) zostaje jako opcja na później; jego BL30/bl301 z FIP Radxa Zero 2 jest elektrycznie zgodne z GT‑King Pro (identyczne regulatory VDDCPU_A=PWM_A, VDDCPU_B=PWM_AO_D, 1250 ns; WiFi 32k=PWM_E — mainline `meson-g12b-radxa-zero2.dts` vs `meson-g12b-w400.dtsi`), ale FIP z `aml_encrypt_g12b` 2020 pod BL2 z 2019 nie da się przetestować bez BootROM.
Hipoteza „czerwone oczy" (do sprawdzenia przez użytkownika, bezpieczne): zimny start z wpiętym kablem A‑A = **standby** (LED czerwony), nie BootROM — box czeka na klawisz power (pinhole = GPIOAO_3 = power key; przytrzymany dłużej przy starcie daje 6‑7 s okno burn u-boota przez `upgrade_key`). Test: z kablem wpiętym po zimnym starcie nacisnąć power na pilocie/pinhole raz → powinien wystartować Android.

### Ratunek — oficjalny firmware Beelink (pobrać PRZED flashem bootloadera)
- DroiX KB: https://droix.net/knowledge-base/article/how-to-update-the-gt-king-and-gt-king-pro-firmware/ (GT‑King Pro, prefiksy SN C92H/S92H/SB9H, paczka 2022‑07‑01; link `go.droix.net/GT-KING-PRO-FW-1` nie rozwiązuje się z tego PC — pobrać w przeglądarce).
- Forum Beelink: https://bbs.bee-link.com/ (dział GT‑King Pro; wątek GT‑King: https://bbs.bee-link.com/d/4250-gt-king-firmware-update). Kubełek `beelink.oss-cn-hongkong.aliyuncs.com` zwraca 403 (2026‑09‑15).
- Wątek CoreELEC z linkami (GT‑King Pro 925P0, prefiks 6B9H, Yandex): https://discourse.coreelec.org/t/beelink-gt-king-stock-firmware-download-links/17629
- **Sprawdzić prefiks SN na naklejce boxa** (C92H/S92H/SB9H/6B9H) i dobrać firmware; nasz stock to build `galilei-userdebug 9 PPR1.180610.011 20220401`. Pełny backup partycji (`backup/20260914-stock`) przywraca stock tylko przy działającym bootloaderze/ADB.

### GApps (Android TV, arm)
Build g12-common jest 32‑bit (`TARGET_ARCH := arm`) → **MindTheGapps 15.0.0‑arm‑ATV** (https://github.com/MindTheGapps/15.0.0-arm-ATV/releases): wariant `full` (Google TV launcher + rekomendacje) lub `minimal` (zostaje launcher LOS). Sideload z recovery po pierwszym boocie, przed konfiguracją.

## 3. Co zweryfikować po pierwszym boocie (kolejność)

1. Logo u-boota na HDMI → DDR + BL33 OK.
2. Kernel: `adb` po USB (OTG) lub po sieci; `dmesg | grep -iE 'mmc|dhd|meson-remote|hym8563|eth'`.
3. eMMC (super/dynamic partitions montują się), WiFi (`/wifi/fw_bcm4359c0_ag.bin`, `nvram_ap6398s.txt`), BT (`/dev/ttyS1`, `BCM4359C0.hcd`), Ethernet (RTL8211F, gigabit).
4. Pilot IR (`remote.tab1` przez `remotecfg`, keylayout `Vendor_0001_Product_0001.kl`), przycisk power (GPIOAO_3), LED.
5. HDMI-CEC, audio: HDMI (tdmout_b), S/PDIF (GPIOAO_10), passthrough w Kodi.
6. Dekodowanie HW 4K HEVC/VP9 (moduły `media-4.9`), HDR10.
7. GApps ATV (MindTheGapps/NikGapps TV arm) → Google TV Home.

## 4. Znane różnice/decyzje

- 32-bit userspace (ABI `armeabi-v7a`, jak cała rodzina g12-common na LOS) na kernelu arm64 — blob-y ADT‑3 są 32-bit.
- `TARGET_HAS_TEE := false` (jak radxa02pro): software keymaster; Widevine L3.
- Codec `ad82584f` na i2c3 zostawiony w liście codeców tdmb tak jak w stocku (stock działa z tym samym DTS).
- `super` 4 GiB (deadpool ma 1,9 GiB) — miejsce na ATV + GApps; `cache` 800 MB; `data` reszta (~55 GB).
- Moduł WiFi: `bcmdhd.101.10.591.x` (radxa02pro); alternatywa `bcmdhd.101.10.361.x` (sabrina, ten sam AP6398S) gdyby 591 sprawiał problemy.
