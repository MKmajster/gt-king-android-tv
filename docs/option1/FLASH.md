# Flashowanie LineageOS 22.2 na GT-King (galilei) — wariant B (stockowy bootloader + chainload)

> **Box to Beelink GT-King (czarna obudowa), nie GT-King PRO** — stockowy ROM podaje `ro.product.model=GTKing PRO`
> i to zmyliło całą wcześniejszą dokumentację. Moduł WiFi/BT to **AP6275S (BCM43752A2 + BCM4362A2)**, nie AP6398S.

## B. Procedura 2026-09-24 (z konsolą UART) — AKTUALNA, zastępuje sekcję A

Wymagania: konsola UART działa (`docs/option1/UART.md`; Waveshare FT232 = COM9, 115200, zworka 3.3V, GND na kwadratowym padzie), USB Burning Tool, kabel A‑A.

### B.0 Co się zmieniło względem A
- **`_aml_dtb` musi być multi-DTB**: stockowy u-boot czyta go do własnego board-initu i z pojedynczym DTB galilei wiesza się na init ethernetu (zimny start). Multi-DTB = `galilei` (wpis 0) + stockowy `g12b_w400_b` z przeszczepionym węzłem `/partitions` LOS-a (wpis 1; tablica partycji siedzi w DTB, bez tego tool pada na `Partition bl33/Initialize partition`). Budowa: `lineage/scripts/make-multi-dtb.py OUT.img galilei.dtb lineage/out/stock-w400_b+losparts.dtb`; `stock-w400_b+losparts.dtb` powstał z `research/device/boot-second.bin` (dtc, węzeł partitions z galilei). Paczki: `make-packages-with-bootloader.sh` z `DTBIMG=<multi> OUT_SUFFIX=<x> ONLY_CHAINLOAD=1`.
- **BL33 v4** (`CONFIG_GALILEI_FIXED_BOOTENV`): nasz u-boot bierze kompilowane `CONFIG_PREBOOT`/`CONFIG_BOOTCOMMAND`, nigdy env-owe (v3 nadpisywał hook własnym `saveenv`, a env-owy `bootcmd` stocka odpalał `ddr_auto_fast_boot_check` = reset co start). `lineage/out/bl33-v4.img` crc32 `ee34b493`.
- **Hook** bez zmian (`lineage/scripts/hook.py`), ale po **każdym** flashu toolem env wraca do domyślnego — hook zakłada się z konsoli (B.2 p.4).
- DTS: `&vddcpu0/1` ze stockowymi parametrami PWM (bez tego `meson-cpufreq` BUG w 2 s), ethernet z oboma `compatible` i zegarem `stmmaceth`; kernel z łatką `lineage/patches/kernel-stmmac-pm-notifier-double-register.patch` (bez niej nieudany probe PHY + drugi probe = PID 1 wisi przed `init`).

### B.1 Narzędzia konsolowe (`lineage/scripts/`)
| Narzędzie | Do czego |
|---|---|
| `serial-watch.py <s> [baud]` | pasywny log UART (nic nie wysyła, wznawia port po ubytku) |
| `serial-console.py --port COM9 --break [--fix-hook] [--cmd X] [--after N]` | Ctrl-C przy „Hit Enter" → prompt (`g12b_w400_v1#` stock, `g12b_galilei_v1#` nasz); `--fix-hook` = hook + `upgrade_step 2` + `saveenv` |
| `uart-ymodem.py --port COM9 --addr 0x1000000 multi.img --cmd "store dtb write 0x1000000 0x2f000" --reset` | nowy DTB w 20 s przez `loady`, bez toola |
| `uart-shell.py --port COM9 --cmd "..."` | shell Androida na ttyS0 (uid shell; `reboot`, `am`, `settings`, `logcat`) |
| `adb connect <ip>:5555` | po WiFi; `adb root` działa (userdebug), klucz PC w `/data/misc/adb/adb_keys` |

Uwaga: tylko jeden proces może trzymać COM9 — przed nową sesją zabić poprzednią (`Get-CimInstance Win32_Process | ? CommandLine -like '*serial-*' | % { Stop-Process -Id $_.ProcessId -Force }`). Skrypty z `--break` wysyłają Ctrl-C ciągle — **nie uruchamiać w trakcie burna** (przerwie `loady`/burn).

### B.2 Kroki
1. Burning Tool → Import `lineage/out/tree/aml_upgrade_package_chainload+stockbl+multidtb-final.img` (albo nowsza) → odznacz „Erase bootloader"/„Erase all" → Start.
2. Wejście w burn: z promptu u-boota `update` (`serial-console.py --break --cmd update`) albo zimny start z kablem A‑A w PC (BootROM; tool sam ładuje bootloader — `Download DDR.USB`). Wgrywanie ~4 min.
3. „Burning successfully" → Stop w toolu (działa jako admin, skrypt go nie zamknie) → kabel z PC → cykl 12 V.
4. Pierwszy start: `serial-console.py --port COM9 --break --break-seconds 600 --fix-hook --cmd "store read bl33 0x1000000 0 0x130000" --cmd "crc32 0x1000000 0x130000"` (oczekiwane `ee34b493` dla v4) → `serial-console.py --port COM9 --cmd reset --after 240`.
5. Boot: stock (`Find match dtb: 1`) → `## Starting application at 0x01000000` → `U-Boot 2015.01 (Sep 24 2026)` → `Find match dtb: 0` → `Starting kernel` → `init second stage` ~8 s → launcher ~35 s (pierwszy boot ~2 min). Kreator LOS: ekran parowania BT — Back/Home pilotem albo `uart-shell.py --cmd "am force-stop org.lineageos.setupwizard; am force-stop com.android.tv.settings"`.
6. Iteracja DTB bez toola: zbudować DTB (`cpp` + `KERNEL_OBJ/scripts/dtc/dtc -@ …`, patrz `rebuild-final.sh`/historia sesji), `make-multi-dtb.py`, potem `adb reboot` (lub `uart-shell --cmd reboot`) i w tle `serial-console.py --break` → `uart-ymodem.py … --reset`.
7. Kernel (`boot.img`) bez toola: `adb root; adb push boot.img /data/local/tmp/; adb shell dd if=/data/local/tmp/boot.img of=/dev/block/by-name/boot; adb reboot`.

### B.3 Diagnostyka, która się sprawdziła
- `initcall_debug ignore_loglevel` w bootargs (z promptu naszego u-boota: `setenv bootargs "${bootargs} initcall_debug ignore_loglevel"; run storeboot`) — **oba** parametry, inaczej linie `calling…` są filtrowane; ostatni `calling` bez `returned` = zawieszony initcall.
- Zawieszka „wędrująca" między sterownikami = wspólny lock; tu łańcuch notyfikatorów PM (self-loop po podwójnej rejestracji w `stmmac_dvr_probe`).
- Czarny ekran przy działającym systemie: `hdmitx: edid: raw data are all zeroes` → fallback 720p; `echo 1080p60hz > /sys/class/display/mode` (root). sysrq przez BREAK na konsoli nie działa.

## A. Procedura 2026-09-22 (bez UART) — *historyczna, patrz B*

### A.0 Co poszło źle 16.09 i 21.09 (żeby nie powtórzyć)
1. **Hook warunkowy `if test ${aml_dt} != g12b_s922x_galilei` nigdy nie odpalał.** u-boot ustawia `aml_dt` tylko dla
   **multi-DTB** w `_aml_dtb` (`common/aml_dt.c` → `checkhw()`); nasza paczka wpisuje tam **pojedynczy** DTB, więc
   `${aml_dt}` jest puste, `test != x` ma `argc=3 < 4` i zwraca fałsz (`common/cmd_test.c`). `catch-burn` logował
   `aml_dt=None` — to był sygnał. Stockowy u-boot bootował LOS-owy `boot.img` sam, na ślepo.
2. **Pierwotna pętla 16.09**: hook bezwarunkowy + wspólny env → galilei u-boot v1 chainloadował sam siebie. v2 zerował
   `preboot` (`setenv NULL`), ale przez to w naszym u-boocie przestały działać `bcb`/`switch_bootmode`/`forceupdate`
   (`adb reboot update|recovery`, pinhole).
3. Hook zastępował **cały** stockowy `preboot`, więc `forceupdate` (pinhole ADC) nie działał — jedyna fizyczna
   droga do burn mode była martwa; `run upgrade_key` (GPIOAO_3) na tej płycie nie ma przycisku.
4. WiFi: port był skonfigurowany na BCM4359C0 — na tym module nigdy by nie ruszył.

### A.1 Co jest teraz inaczej
- **Hook** (`lineage/scripts/hook.py`, jedna definicja dla `catch-burn.py`/`chainload-env.py`/`serial-console.py`):
  `run upgrade_check; forceupdate; if store read bl33 0x1000000 0 0x140000; then dcache off; icache off; go 0x1000000; fi; run update`
  - `forceupdate` **przed** chainloadem: pinhole (gniazdo AV) trzymany ~4 s przy podłączeniu zasilania → stockowy
    burn mode, zanim cokolwiek naszego się uruchomi. To jest droga powrotna bez UART.
  - bez warunku na `aml_dt`; ochronę przed pętlą daje **BL33 v3**: `board_late_init` robi `setenv("preboot",
    CONFIG_PREBOOT)` (kompilowany preboot galilei, z `forceupdate`, `bcb uboot-command`, `switch_bootmode`).
  - `run update` na końcu: gdy `store read bl33` się nie uda, od razu okno burn (łapie `catch-burn.py`), a nie
    cichy `storeboot` naszego `boot.img` przez stockowy u-boot.
- **BL33 v3** = `lineage/out/bl33-v3.img`; wszystkie paczki w `lineage/out/tree/` z 22.09 mają v3 w partycji `bl33`
  (`chainload`, `chainload+stockbl`, `stock-restore+stockbl`). Paczka `+stockbl+recovery` (v1) skasowana.
- **WiFi/BT**: firmware `fw_bcm43752a2_ag.bin`/`nvram_ap6275s.txt`/`clm_bcm43752a2_ag.blob` + stockowy
  `BCM4362A2.hcd` w `device/beelink/galilei/{wifi,bluetooth}` (z `backup/20260914-stock/vendor.img`).
- **ADB po TCP od pierwszego bootu** (`service.adb.tcp.port=5555`, userdebug) — jedyna „konsola" bez UART:
  `tools\platform-tools\adb.exe connect <IP boxa z DHCP routera>`.

### A.2 Kroki
0. Box działa na SlimBoxie (`sbx_beelink_gtking_p0_wol_aosp_54_21`, wgrany 22.09 09:36). **Najpierw test drogi
   powrotnej**: kabel A-A w USB 2.0 boxa, Burning Tool otwarty (bez Start), przytrzymaj pinhole i podłącz zasilanie,
   trzymaj ~5 s → w Menedżerze urządzeń pojawia się „WorldCup Device" (1B8E:C003). Jeśli tak — pinhole = ADC key
   działa na tej płycie i z hookiem `forceupdate` zawsze wrócisz do burn mode. Wyłącz zasilanie (bez flashowania).
1. USB Burning Tool → Import `lineage/out/tree/aml_upgrade_package_chainload+stockbl.img` → **Start**.
   W drugim oknie (Git Bash, katalog repo): `bash lineage/scripts/after-burn-hook.sh` (czeka na „Burning
   successfully", zamyka tool, łapie okno burn, zakłada hook + zapisuje BL33 v3 + `reset`).
2. Z Androida SlimBox: `adb connect <IP>` → `adb reboot update` → tool wgrywa (kilka minut) → skrypt z p.1 robi resztę
   (log `lineage/out/after-burn-<data>.log`; oczekiwane `saveenv -> success`, `store write bl33 -> success`).
3. Po `reset`: stock u-boot → hook → `go` → galilei v3 → `storeboot` → jądro LOS. Obserwuj: HDMI (logo → animacja
   LineageOS, pierwszy boot 3–6 min), dioda, lease DHCP na routerze, potem `adb connect <IP>:5555` → `adb logcat`,
   `dmesg`. Bez obrazu i bez DHCP po 10 min = problem w jądrze/DTS → p.4.
4. Powrót/diagnostyka bez UART: pinhole przy włączeniu → burn mode stocka → `py -3.14 lineage\scripts\catch-burn.py
   --show-only` (env) / `--restore` (zdjęcie hooka) / `--cmd "..."` (komendy u-boota po USB, `printenv` przez
   `env export` do RAM) — to jest nasza konsola. Pełny powrót do stocka: `aml_upgrade_package_stock-restore+stockbl.img`.

Stan: 2026-09-15. Paczka: `lineage/out/tree/aml_upgrade_package_chainload.img` (powstaje automatycznie po buildzie, `lineage/scripts/post-build.sh`). Bootloader Beelinka (BL2/BL30/BL31/BL33 w partycji `bootloader`) **nie jest ruszany**; nasz u-boot ląduje w nowej partycji `bl33` i jest uruchamiany przez hook w env stocka. Cofnięcie = przywrócenie partycji ze `backup/20260914-stock/` (patrz sekcja 6).

## 0. Wymagania na PC
- Amlogic USB Burning Tool v2.2.0 — zainstalowany (`C:\Program Files (x86)\Amlogic\USB_Burning_Tool`).
- Sterownik: Burning Tool używa `libusb0.dll`, więc urządzenie „WorldCup Device" (VID 1B8E, PID C003) musi być przypięte do **libusb-win32**, nie do WinUSB z Zadiga. Przełączenie: box w trybie burn → Zadig jako administrator → z listy wybrać „WorldCup Device" → sterownik docelowy **libusb-win32 (v1.2.6.0)** → Replace Driver. Skrypty `lineage/scripts/*.py` (libusb-1.0) działają z oboma sterownikami.
- Kabel USB-A↔USB-A w porcie **USB 2.0** boxa, karta microSD **wyjęta**.

## 1. Wejście w tryb burn (jedyna pewna droga na tym boxie) — *historyczne, patrz A*
Z **działającego Androida** (kabel już wpięty): `tools\platform-tools\adb.exe connect 192.168.0.100:5555`, potem `adb reboot update`. Box pojawia się jako „WorldCup Device". (Zimny start z wpiętym kablem zatrzymuje box na czerwonych oczach i enumeracja BootROM‑u na tym PC jest zawodna — nie używać.)
Po flashu, gdy Androida stocka już nie ma: **pinhole (reset w gnieździe AV) przytrzymany przy podłączaniu zasilacza** → stockowy `preboot` wykonuje `upgrade_key` → `run update` → tryb burn.

## 2. Flash paczki (USB Burning Tool)
1. Uruchom USB Burning Tool → File → Import Image → `aml_upgrade_package_chainload.img` (import trwa chwilę).
2. **Odznacz** „Erase bootloader" i „Erase all" (paczka i tak nie zawiera wpisu `PARTITION bootloader`, ale to druga blokada). „Erase flash" może zostać na Normal erase.
3. Kliknij **Start**, dopiero potem wprowadź box w tryb burn (sekcja 1). Narzędzie wykrywa urządzenie, wgrywa `dtb.img` → nowa tablica partycji (z `bl33` i `super` 4 GiB; stare `system/vendor/product/odm/cache/data` są kasowane i tworzone od nowa), potem `boot`, `bl33`, `dtbo`, `logo`, `recovery`, `super`, `vbmeta`.
4. Po 100% kliknij Stop i odłącz USB. Box zrestartuje się (stockowy u-boot).

## 2a. Co się stało przy pierwszym flashu (2026-09-15/16) — lekcje
- Po flashu paczki `chainload` (bez wpisu `bootloader`) box po czystym starcie siedział w **BootROM** (Stage 0.0): narzędzie wykasowało obszar bootloadera (opcja „Erase bootloader" / normal erase), a paczka go nie zapisała. Naprawa: paczka **`aml_upgrade_package_chainload+stockbl.img`** (ta sama + `PARTITION bootloader` = stockowy `u-boot.bin`) wgrana z trybu BootROM — Burning Tool sam ładuje bootloader do RAM i zapisuje eMMC. **Zawsze używać wariantu `+stockbl`.** Analogicznie `aml_upgrade_package_stock-restore+stockbl.img` do powrotu.
- Po naprawie: zielone oczy, czarny ekran, USB boxa miga co ~18 s = stockowy `storeboot` nie bootuje `boot.img` LOS → `run update` (okno burn ~13 s) → recovery → reset → pętla. `lineage/scripts/catch-burn.py` łapie to okno (IDENTIFY kasuje timeout) i zakłada hook.
- **TPL_CMD przez EP0 przyjmuje < 64 bajtów** — długi `setenv preboot …` pada z I/O; hook składany z `p1/p2/p3` + `setenv preboot "$p1 $p2 $p3"` (hush). Odczyty IN pod sterownikiem libusb0 (Burning Tool) bywają ucięte — zapisy są pewne, statusy czytać z retry.
- Sterownik: po instalacji Burning Tool Windows przypina „WorldCup Device" do libusb0 sam — Zadig niepotrzebny; pyusb/libusb1 działa przez ten sterownik z ponawianiem IDENTIFY (`amlusb.py`). BootROM→BL2 (AMLC) przez ten sterownik **nie działa** (`bootrom-boot.py` wymaga WinUSB).

## 3. Pierwszy start po flashu i założenie hooka — *historyczne (stary hook), patrz A*
- Pierwszy boot: stockowy u-boot ma `upgrade_step=1` → `defenv_reserv` (reset env do domyślnych; zachowane tylko `aml_dt, firstboot, lock, upgrade_step, bootloader_version`) → `storeboot`. Możliwe wyniki: (a) stockowy u-boot sam zabootuje `boot.img` LOS (ma ramdysk, więc bez `skip_initramfs`; DTB w `_aml_dtb` jest pojedyncze, więc `aml_dt=g12b_w400_b` nie przeszkadza) — wtedy LOS wstanie już teraz; (b) zawiśnie/czarny ekran — normalne, przejdź dalej.
- Wejdź w stockowy tryb burn pinhole’em (sekcja 1) i załóż hook: `py -3.14 lineage\scripts\chainload-env.py --show` (podgląd), potem `--set`. Skrypt odmówi, jeśli rozmawia z naszym u-bootem zamiast stockowego. Hook: `preboot=run upgrade_key; if store read bl33 0x1000000 0 0x140000; then dcache off; icache off; go 0x1000000; fi`.
- `py -3.14 lineage\scripts\burn-cmd.py --reset` → normalny restart → stock → hook → nasz u-boot → LOS.

## 4. Co obserwować
- HDMI: logo z partycji `logo` (nasze `logo.img` z drzewa LOS), potem animacja LineageOS. Pierwszy boot LOS: 3–6 min.
- Sieć: LOS nie włącza ADB po TCP; użyj ADB po USB (ten sam kabel, port USB 2.0 boxa) po włączeniu debugowania w Ustawieniach → lub `adb` po pierwszym uruchomieniu kreatora.
- Jeśli po hooku box nie startuje: pinhole przy starcie → tryb burn stocka (hook zaczyna od `run upgrade_key`) → `chainload-env.py --restore` → stock bez hooka.

## 5. Ryzyka i ich cofanie
| Sytuacja | Skutek | Cofnięcie |
|---|---|---|
| Zły `bl33` / nasz u-boot nie startuje | czarny ekran po logo stocka | pinhole → burn → `chainload-env.py --restore` |
| Flash przerwany w połowie | partycje LOS niespójne, bootloader nietknięty | powtórzyć flash paczki (albo stock: sekcja 6) |
| Stock ROM potrzebny z powrotem | — | sekcja 6 |
Bootloader, `tee`, `rpmb`, `cri_data`, `param` nie są dotykane przez żaden z tych kroków.

## 6. Powrót do stocka
Tablica partycji stocka wraca tylko przez pełny obraz Beelinka w USB Burning Tool (`.img` producenta) **albo** naszą paczką ze stockowymi partycjami: `lineage/scripts/make-stock-package.sh` → `lineage/out/tree/aml_upgrade_package_stock-restore.img` (sha1-zweryfikowane `backup/20260914-stock/{boot,recovery,dtbo,logo,misc,vbmeta,odm,product,vendor,system}.img` + stockowy multi-DTB `research/device/boot-second.bin` jako `dtb.img`/`_aml_dtb`; bez bootloadera/env/tee/param/cri_data). Flash tak samo jak w sekcji 2 (bez „Erase bootloader"). Przed flashem stocka **zdjąć hook**: `chainload-env.py --restore` (inaczej stock po powrocie próbowałby czytać nieistniejącą partycję `bl33` — nieszkodliwe, ale zbędne). Paczkę zbudować i mieć pod ręką **przed** pierwszym flashem LOS.

## C. Pakiet finalny (2026-09-25) — co zawiera i dlaczego

`lineage/scripts/rebuild-final.sh` → `lineage/out/tree/aml_upgrade_package_chainload+stockbl+multidtb-final.img`:

| plik w pakiecie | źródło | uwagi |
|---|---|---|
| `u-boot.bin` (DDR/UBOOT/bootloader) | stockowy bootloader Beelink (`lineage/out/u-boot-stock-beelink.bin`) | BL2 z treningiem LPDDR4 — nie zastępujemy |
| `dtb.img` (`_aml_dtb`) | `make-multi-dtb.py`: `g12b_s922x_galilei` + `g12b_w400_b`+partycje LOS | stock u-boot bierze w400_b do własnego initu, nasz u-boot bierze galilei |
| `bl33.img` | LineageOS u-boot v4 (`gen_galilei_board.py`) | ładowany hookiem z env |
| `env.img` (**nowe**) | `make-env-image.py` z env działającego boxa + hook, `upgrade_step=2` | ma zastąpić `--fix-hook` po flashu; CRC obejmuje 64 KiB |
| `boot.img`, `recovery.img`, `dtbo.img`, `vbmeta.img`, `logo.img`, `super.img` | build LOS | super = system/vendor/product/system_ext/odm (dynamic) |

Do sprawdzenia przy pierwszym flashu z `env.img`: czy u-boot Toola nie nadpisuje env po zapisie partycji (w logu Toola/konsoli szukaj „Saving Environment”). Jeśli hook zniknął → `serial-console.py --break --fix-hook`.

Wariant bez GApps: `GAPPS=none` przed `setup-tree.sh` (pakiet nazwać `…-vanilla.img` ręcznie — `rebuild-final.sh` zawsze pisze `-final`).

## D. 25.09 — hook w domyślnym env bootloadera (bez UART po flashu)

Burning Tool kończy każde wypalanie własnym u-bootem, który robi `saveenv` **domyślnego** env, więc ani `env.img` w pakiecie, ani hook wpisany przez `--fix-hook` przed flashem nie przeżywają (stock bez hooka bootuje nasz kernel sam → `BUG at cpufreq.c:1390` po 1,8 s → pętla watchdoga). Od 25.09 pakiety zawierają jako `PARTITION bootloader` stockowy u-boot z hookiem w **skompilowanym domyślnym `preboot`** (`lineage/scripts/patch-stock-bl33-env.py`: BL33 z FIP rozpakowany z LZ4, 147-znakowy `preboot=` podmieniony, obraz podpisany `aml_encrypt_g12b --bl3sig --level v3 --compress lz4`; BL2/BL30/BL31/BL32 bez zmian). Pozycje `USB DDR/UBOOT` (u-boot narzędzia) zostają czystym stockiem; `env.img` domyślnie wyłączony (`ENVIMG=` w `make-packages-with-bootloader.sh`). Krok „Pierwszy start” z §C (`--fix-hook`) jest więc tylko awaryjny. BootROM tego boxa bootuje eMMC przed SD (`eMMC boot @ 0`, FIP z user area), więc podmienionego bootloadera nie da się sprawdzić z karty — pierwszy test to flash Burning Toolem. Karta z `aml_autoscript` przy starcie = „press update key!” w `forceupdate` → boot z karty (jak na stocku); hook przeżywa `saveenv` autoscriptu.
