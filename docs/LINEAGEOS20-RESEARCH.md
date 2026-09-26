# Port LineageOS 20 na Beelink GT-King PRO (galilei) — research

Stan: 2026-09-15. Research wstępny (faza zbierania info). Gałąź: `lineageos20`.
Kontekst: opcja 2 (mod stocka) zakończona — patrz `HANDOFF.md` sekcja 8; ten dokument dotyczy opcji 1 (ROM ze źródeł).

## Werdykt w skrócie

**Szanse na powodzenie: wysokie (~70–80% na w pełni działający daily-driver).** SoC i cała rodzina G12 są aktywnie utrzymywane w oficjalnym LineageOS (w 2026 r. gałęzie do 24.0), Wi-Fi/BT moduł ma sterownik dokładnie w wersji ze stocka, a my mamy pełny backup wszystkich partycji. Deep-dive (sekcja niżej) dodatkowo potwierdził: mainline Linux ma gotowy DTS dla naszej płyty, oficjalne drzewo g12-common obejmuje G12B/S922X wprost, a 64-bit Android na tym SoC działa w buildach voodika od LOS 16 do 22.1 ATV. Pierwsza bootowalna builda realnie w kilka dni roboczych; pełny bring-up (IR, CEC, audio) — tygodnie. Ryzyko 32-bitowych blobów stocka zredukowane strategią vendora „baza 64-bit + board-specific z backupu".

Nikt wcześniej nie opublikował portu LOS dla GT-King/GT-King Pro (wyszukiwanie GitHub: brak drzew `galilei`/`w400`/`beelink`) — będziemy pierwsi, ale bazujemy na gotowej infrastrukturze rodziny Amlogic, nie piszemy od zera.

## Co dokładnie istnieje i jest dla nas dostępne (zweryfikowane 2026-09)

Wszystko w oficjalnej organizacji **LineageOS** na GitHubie (gałąź `lineage-20` istnieje w każdej z nich):

| Repo | Po co nam |
|---|---|
| `LineageOS/android_device_amlogic_g12-common` | Wspólne drzewo wszystkich boxów G12/SM1 (BoardConfigCommon, init, audio, media, sepolicy). Ma `proprietary-files-atv.txt` (wariant **Android TV!**) i `proprietary-files-tee.txt`. Gałęzie do `lineage-24.0` — aktywnie utrzymywane. |
| `LineageOS/android_kernel_amlogic_linux-4.9` | Kernel 4.9 BSP dla całej rodziny. Zawiera **`g12b_a311d_w400.dts`** — referencyjna płyta w400, na której bazuje GT-King Pro (stock `amlogic-dt-id = g12b_w400_b`). Gałęzie do 22.2. |
| `LineageOS/android_hardware_amlogic_kernel-modules_dhd-driver` | Sterownik Wi-Fi bcmdhd — jest katalog **`bcmdhd.100.10.545.x`**, dokładnie wersja ze stocka (dhd 100.10.545.15, moduł AP6398S/BCM4359). |
| `LineageOS/android_device_amlogic_sepolicy` | Wspólna sepolicy dla Amlogic. |
| `LineageOS/android_device_hardkernel_odroidc4` | Przykład gotowego drzewa urządzenia na bazie g12-common — nasz wzorzec do sklonowania dla `device/beelink/galilei`. |
| `android_hardware_amlogic_tools_imagepacker` / `dtbtool` | Narzędzia do pakowania obrazów Amlogic (install package). |

Poza organizacją LOS:

- **voodik** (maintainer ODROID): kernel `voodik/android_kernel_voodik_odroidg12` z gałęziami `lineage-20.0_odroidg12_t_64` (ATV), `lineage-22.1_odroidg12_64` (aktualizowany 2026-06!) + `android_vendor_amlogic_common_{frameworks,interfaces,external_recovery}` (`s922_9.0.0_master`) — dowód, że **S922X działa na LOS 20/21/22.1 w wariancie Android TV**. Serwer buildów `https://oph.mdrjr.net/voodik/S922X/ODROID-N2/Android/` ma pełną macierz: `LineageOTA-{16.0,17.1,18.1,19.1,20.0,21.0,22.1}-ATV` + warianty bez ATV, każdy w strukturze `full/`, `delta/`, **`selfinstall/`** (obraz samoinstalujący się z karty SD — najbezpieczniejsza droga pierwszej instalacji, analogia do CoreELEC). Drzewo `device_odroidn2_20.0_ATV` nie jest publiczne, ale odroidc4 + g12-common dają to samo.
- **TheMuppets/proprietary_vendor_amlogic_g12-common** — publiczny dump 64-bitowych blobów vendora dla rodziny G12 (gałęzie `lineage-20`…`lineage-23.2`), bazowy zestaw g12-common pochodzi z adt3-user 13 (Android 13). Do tego warianty per urządzenie (`_odroidc4`, `_radxa0`, `_ne-common`, `_sm1-common`, …). Nasz mechanizm `extract-files.sh` może brać z niego bazę zamiast z 32-bitowego stocka.
- **Evervolv/android_device_hardkernel_odroidn2** — alternatywne drzewo urządzenia dla S922X (odniesienie do różnic board-specific).
- Wątki XDA (oficjalne porty rodziny, **bez GT-King** — onn 4K, ADT-3, Dynalink, sabrina, BPI M5, ODROID C4, Radxa Zero):
  - LOS 22: https://xdaforums.com/t/official-lineageos-22-for-amlogic-gxl-gxm-g12a-sm1-ne-family-devices-android-tv-tablet.4649881/
  - LOS 20: https://xdaforums.com/t/official-unofficial-lineageos-20-for-amlogic-gxl-gxm-g12-sm1-ne-family-devices.4534935/
  - Model instalacji: obraz `aml_install_package` wgrywany trybem update (przycisk reset + kabel USB A-A), potem sideload ZIP przez recovery. Cytat z wątku: „almost impossible to brick" — tryb update siedzi w bootromie.
  - Znane bolączki rodziny (trafiają na naszą listę ryzyk): **CEC** popsuty na części boxów, konfiguracja **pilota IR** w setup wizard, USB na BPI M5.

## Deep-dive runda 2 (2026-09-15, popołudnie) — 64-bit, DTS, status funkcji

### „CoreELEC jest 64-bit, czyli się da" — co to dokładnie dowodzi

CoreELEC (Amlogic-ng) to rzeczywiście w pełni aarch64 (64-bit kernel + 64-bit userspace) i działa na GT-King Pro od lat. Sam w sobie dowodzi tylko możliwości sprzętowe (S922X + 64-bit), bo CoreELEC nie używa androidowych blobów — **ale 64-bitowy Android na tym samym SoC też jest udowodniony**: buildy voodika dla ODROID-N2 są 64-bit (gałęzie kernela `_64`, Android 13/15) i są w codziennym użytku. Nasz problem „32-bit vendor" dotyczy wyłącznie **blobów z naszego stocka** — i nie musimy ich używać w całości (patrz strategia vendora niżej).

### Główne drzewo LOS obejmuje G12B wprost

README `android_device_amlogic_g12-common`: *„A common tree for the following SoC's: G12A, **G12B — S922X/A311D**, SM1. This tree utilizes a Google-based Android 13 Linux 4.9 kernel."* Czyli S922X nie jest „zaproszony" tylko przez analogię (voodik), lecz jest wprost w zakresie oficjalnego drzewa. Konfiguracja kernela: `g12a_defconfig` wspólny dla całej rodziny, moduły zewnętrzne budowane z kernela: `mali-driver/bifrost`, `media-4.9`, `optee` (`TARGET_KERNEL_EXT_MODULES` w BoardConfigCommon).

### DTS płyty — trzy źródła referencyjne (wszystkie darmowe)

1. **Mainline Linux: `arch/arm64/boot/dts/amlogic/meson-g12b-gtking-pro.dts`** (obok `meson-g12b-gtking.dts`, `meson-g12b-ugoos-am6.dts`, `meson-g12b-odroid-n2*.dts`) — BayLibre/Christian Hewitt utrzymują pełny opis płyty GT-King Pro: audio TDMOUT_B → tohdmitx → HDMI (8ch), RTC PCF8563 na i2c3, przycisk power GPIOAO_3, biała LED GPIOAO_11, WiFi na `sd_emmc_a` (SDIO, pwrseq GPIOX_6), BT na UART_A (shutdown GPIOX_17), bazuje na `meson-g12b-w400.dtsi`. To najlepszy „opis płyty" do porównania z stock DTB.
2. **`g12b_a311d_w400.dts` w kernelu LOS 4.9** (format BSP Amlogic, gałęzie lineage-20 i 22.1) — bezpośrednia baza dla naszego `g12b_s922x_galilei.dts`.
3. **Stock DTB z boxa** — partycja `dtbo` jest w backupie; właściwy DTB siedzi w `boot.img` (ten layout nie ma osobnej partycji `dtb`), dekompilacja `dtc -I dtb -O dts`. Dodatkowo box nadal bootuje stocka → `adb pull /dev/block/by-name/boot` (i ewentualnie `/sys/firmware/fdt`) w każdej chwili.

### Status funkcji na buildach rodziny (raporty użytkowników, forum ODROID)

- **CEC**: działa w buildach voodika (LOS 16→20), historycznie z potknięciami (audio po powrocie z aplikacji), regulowane w Odroid Settings; w LOS 19.1/20 wątki opisują CEC jako działające po poprawkach voodika.
- **Audio passthrough**: raporty „better audio passthrough working" na LOS 19.1/20 — działa, konfiguracja bywa kapryśna (to i tak nasze kryterium sukcesu do testów na galilei).
- **Widevine**: na buildach Amlogic z kernelem 4.9 BSP — L3 (bez L1, zgodnie z oczekiwaniem); wypowiedź voodika o C4 (mainline kernel): „no Widevine library existing for C4 and modern kernel" — dotyczy mainline, nie naszej ścieżki 4.9 BSP.
- Wątki: LOS 20 N2 `forum.odroid.com/viewtopic.php?t=45758`, LOS 19.1 `t=44124`, LOS 22.1 `t=49491`, C4/ATV eksperymenty `t=48112` (forum za Cloudflare — czytać z przeglądarki).

### Precedens portu na inny box G12B

W oficjalnym wątku XDA LOS 20 (strona 5) użytkownik pyta o port na **Dreambox One/Two (G12B/S922X)** — pytanie o wybór drzewa bazowego; wyniku nie potwierdziłem (XDA blokuje scraping — 403), ale to pokazuje standardową ścieżkę: klony S922X portują się na `g12-common` + własny DTS. LibreELEC forum ma osobny wątek eksperymentów DTS dla Dreamboxa (kernel crash investigations) — realistyczny obraz pracy bring-up.

### Konsekwencja: dynamic partitions

Build g12-common używa **dynamic partitions (super)**: `BOARD_SUPER_PARTITION_SIZE` (odroidc4: ~2 GB), obrazy system/vendor/product/system_ext/odm w super. Instalacja `aml_install_package` **repartycjonuje eMMC** pod nowy layout — backup z `backup/20260914-stock/` jest więc nie tyle opcjonalny, co jedyną drogą powrotu do layoutu stocka (poza USB Burning Tool z oficjalnym `.img`). Dla porównania `gx-common` (starsza rodzina GXL/GXM) wspiera non-dynamic — ale nasza ścieżka to g12/dynamic.

### Strategia vendora (zaktualizowana po deep-dive)

Zamiast walki z 32-bitowymi blobami stocka jako bazą:
- **Baza 64-bit**: `TheMuppets/proprietary_vendor_amlogic_g12-common@lineage-20` (Android 13, G12) + ewentualnie vendor voodika (`android_vendor_amlogic_common_*`) — pod części wspólne.
- **Board-specific z naszego stocka** (te pliki muszą być nasze): firmware/blobs Wi-Fi AP6398S, IR (`remote.cfg` → keylayout), audio routing/passthrough bloby, hwcomposer/gralloc jeśli wstanie na arm64 — wyciągane `extract-files.sh` z `backup/20260914-stock/`.
- **Fallback 32-bit** (jeśli któryś krytyczny HAL nie ma 64-bitowego odpowiednika): wymuszenie 32-bit serwerów (audioserver/mediaserver) w drzewie urządzenia.

## Szanse na powodzenie — co za, co przeciw

**Za (mocne):**
1. Rodzina G12 utrzymywana w LOS od lat, w 2026 dalej żywa (g12-common do lineage-24.0).
2. Ten sam SoC (S922X) działa na LOS 20/21/22.1 ATV w buildach voodika dla ODROID-N2.
3. Referencyjne DTS płyty w **trzech darmowych źródłach**: `g12b_a311d_w400.dts` w kernelu LOS (format BSP), **mainline `meson-g12b-gtking-pro.dts`** (pełny opis płyty) i stock DTB z backupu — port DTS to praca typu diff, nie twórczość od zera.
4. Sterownik Wi-Fi/BT w dokładnie wersji stockowej dostępny in-tree.
5. Treble na stocku (VNDK 28), pełny backup 20 partycji → `extract-files.sh` zrobi vendor bez urządzenia w pętli.
6. Standardowa, dobrze opisana ścieżka instalacji i ratunku (tryb update z bootroma praktycznie nie do zbrickowania; do tego `ddbr` z CoreELEC).
7. Nasz egzemplarz: firmware userdebug **test-keys**, SELinux permissive, ADB root — bootloader otwarty (ryzyko „secure bootloader 0529+" z README dotyczy innych rewizji; build 20220401 test-keys wygląda bezpiecznie, ale flash testowego `aml_install_package` zweryfikuje to bez ryzyka).

**Przeciw / ryzyka (posegregowane):**
1. **32-bit vendor (ryzyko nr 1, zredukowane po deep-dive).** Stock: `zygote32`, ABI armeabi-v7a — bloby w `/vendor` są 32-bit, a LOS 20 buduje arm64. **Nowa strategia**: baza 64-bit z TheMuppets/voodika + board-specific bloby z naszego backupu (patrz „Strategia vendora" w deep-dive) — dokładnie tak portowane są inne boxy tej rodziny. Zostaje ryzyko, że któryś krytyczny HAL (audio passthrough, hwcomposer) nie wystartuje na 64-bit i trzeba go będzie portować albo wrócić do 32-bit serwerów.
2. **Pilot IR**: tabela klawiszy pilota (mamy `/vendor/etc/remote.cfg`, `remote.tab*`, keylayouty — przeniesienie do drzewa to rutyna, ale wymaga testów z pilotem w ręku).
3. **CEC**: znane problemy w rodzinie (np. wade/dopinder) — może wymagać łatek w HAL CEC.
4. **Audio passthrough / HDMI hotplug / auto-framerate**: HAL audio Amlogic w g12-common jest, ale DD/DTS passthrough i refresh-rate switching trzeba przetestować i doregulować (kryterium sukcesu użytkownika!).
5. **Widevine = L3** (założone i zaakceptowane), Dolby Vision raczej nie.
6. **GMS/Android TV**: LOS nie dystrybuuje GApps; dla wariantu ATV — pakiety typu NikGapps ATV (precedens: unofficial buildy npjohnsona z pełnymi GApps ATV działają). Asystent/Pay Store bez certyfikacji — mamy już doświadczenie z opcji 2 (SmartTube itd.).
7. Zasoby builda: pełny sync + build wymaga dedykowanego PC (Mac M3 odpada — za mało dysku, 24 GB).

**Czego NIE grozi:** brick bez ratunku (bootrom update mode + ddbr + backup), utrata Widevine L1 na stocku (bo nie ruszamy stocka dopóki port nie działa; RPMB/keybox nietknięty dopóki nie flashujemy przez USB Burning Tool z „Erase").

## Architektura portu (co budujemy)

```
device/beelink/galilei/            ← nowe drzewo (wzorzec: android_device_hardkernel_odroidc4@lineage-20)
  ├── AndroidProducts.mk, lineage_galilei.mk / lineage_galilei-atv.mk
  ├── BoardConfig.mk (partycje z HANDOFF: system 1.9G? — uwaga, w modelu g12-common system rośnie; dtbo, vbmeta...)
  ├── device.mk (IR tabelka z remote.cfg, keylayouty, wifi bcmdhd AP6398S, audio)
  ├── extract-files.sh (bloby z backup/20260914-stock/, nie z urządzenia)
  └── sepolicy (na bazie android_device_amlogic_sepolicy)
kernel: LineageOS/android_kernel_amlogic_linux-4.9@lineage-20
  └── arch/arm64/boot/dts/amlogic/g12b_s922x_galilei.dts
      ← baza: g12b_a311d_w400.dts (BSP) + dekompilacja stock dtb z boot.img
      ← kontrola krzyżowa: mainline meson-g12b-gtking-pro.dts (opis płyty)
common: LineageOS/android_device_amlogic_g12-common@lineage-20 (+ wariant ATV)
local_manifests + (jeśli opcja B) vendor z drzew N2
```

Wariant docelowy: **lineage-20.0-ATV** (Android 13 + UI Android TV). Po doprowadzeniu do ładu możliwy upgrade do lineage-22.1 (Android 15) — infrastruktura gotowa, voodik ma działające 22.1 na tym samym SoC.

## Potrzebny sprzęt i narzędzia

### Już mamy
- Box GT-King Pro z ADB-root po sieci (192.168.0.100:5555), SELinux permissive, test-keys.
- Pełny backup eMMC (20 partycji + boot0/boot1, sha1) w `backup/`.
- Mac jako konsola zarządzania (adb, docker, gh, git).

### Do kupienia / przygotowania (lista minimalna)

| # | Rzecz | Po co | Szac. koszt |
|---|---|---|---|
| 1 | **PC do buildów**: natywny Linux x86_64 (Ubuntu 22.04/24.04 LTS), **≥32 GB RAM** (16 + swap to minimum), **SSD/NVMe ≥400 GB** wolnego (sync ~250 GB + ccache + out), mocne CPU | Build AOSP/LOS 20; na słabszym się da, ale każdy build trwa wieki | 0 zł jeśli użytkownik ma PC („mam pc do takich rzeczy" — sprawdzić spec!) |
| 2 | **Kabel USB A wtyk–wtyk (męski-męski)** | Tryb update Amlogic (flash install-package, ratunek) | ~10 zł |
| 3 | **Windows** (VM na Macu: UTM/Parallels z passthrough USB, albo dowolny laptop) | Amlogic **USB Burning Tool** jest win-only — oficjalna droga ratunku i wgrywania `.img` | 0 zł (VM) |
| 4 | **microSD 8–16 GB (zapasowa)** | CoreELEC rescue / `ddbr` restore — zero-ryzyko boot niezależny od eMMC | ~20 zł |
| 5 | *(opcjonalnie)* **Adapter USB-TTL 3.3 V** (CP2102 / FT232RL) + kabelki dupont | Konsola UART u-boota, gdyby coś poszło nie tak poniżej kernela; przy okazji przyda się do każdej zabawy z Amlogic | ~15–30 zł |
| 6 | *(opcjonalnie)* drugi pilot USB/2.4G do testów | Nie jest wymagany — pilot BT/IR stockowy powinien wystarczyć | — |

Uwagi:
- **Mac M3 nie nadaje się na build hosta** (24 GB wolnego dysku; AOSP wymaga Linux x86_64 — VM na ARM było by wolne i bez sensu). Mac zostaje konsolą ADB i miejscem backupów (backup trzymać też poza Maciem! — obecnie jedyna kopia jest w `backup/`, użytkownik świadomie to zaakceptował, ale przy porcie warto mieć drugą kopię).
- **Linux zamiast Windowsa do flashowania** — alternatywy open source: `aml-flash-tool` (khadas/utils), `pyamlboot`, `amlogic-usbdl` (nawet unbrick z bootroma: https://github.com/frederic/amlogic-usbdl). Windows VM to jednak najpewniejsza opcja z USB Burning Tool.
- UART na płycie GT-King Pro: brak publicznej dokumentacji pinoutu; do zlokalizowania przy otwarciu obudowy (wątek CoreELEC GT-King ma zdjęcia PCB: https://discourse.coreelec.org/t/s922x-bee-link-gt-king/5334).

### Software (na PC z Linuksem)
- `repo` + OpenJDK 17, `ccache` (ustawić ≥50 GB), zależności LOS 20 (wiki.lineageos.org/dev).
- `dtc` (device tree compiler) — do dekompilacji stock DTS na Macu też się przyda (`brew install dtc`).
- `aml image packer` (jest w LOS: `android_hardware_amlogic_tools_imagepacker`).

## Roadmapa (fazy, orientacyjny wysiłek)

0. **Setup build hosta** (1 dzień): Ubuntu, zależności, `repo init -u https://github.com/LineageOS/android.git -b lineage-20` + local_manifests (g12-common, kernel 4.9, sepolicy, dhd). Pierwszy czysty build odroidc4 jako sanity check infrastruktury (opcjonalnie od razu galilei).
1. **DTS galilei** (1–2 dni): `dtc -I dtb -O dts` na backupie dtb/dtbo → nowy `g12b_s922x_galilei.dts` (baza `g12b_a311d_w400.dts`; różnice: CPU S922X-H, WiFi AP6398S, IR, eMMC, audio). Konfiguracja kernela + defconfig.
2. **Drzewo urządzenia** (2–4 dni): klon odroidc4 → galilei: BoardConfig (partycje wg HANDOFF — system 1.9 GB stock; w LOS standard tej rodziny to większy system → sprawdzić czy zostaje layout czy re-partycjonowanie w install package), extract-files z backupu, remote.cfg → keylayout, wifi.
3. **Pierwsza builda + install** (1–2 dni): `aml_install_package`, flash trybem update, pierwszy boot. Tu weryfikacja ryzyka bootloadera (test-keys — powinno przejść).
4. **Bring-up** (tygodnie, iteracyjnie): display/HDMI → touch/IR → Wi-Fi/BT → audio (passthrough!) → CEC → suspend/encoder. Decyzja vendor 32-bit vs 64-bit (opcja A/B/hybryda) spadnie w fazie audio/hwcomposer.
5. **ATV + GApps + wykończenie**: wariant ATV z g12-common, NikGapps ATV, testy kryteriów sukcesu (Kodi 4K HDR passthrough, IPTV, Plex), packaging + instrukcja restore w duchu `docs/ROM-v1.md`.
6. *(opcjonalnie)* upgrade do lineage-22.1.

## Decyzje otwarte (do ustalenia przed fazą 2/4)

1. **Vendor**: baza 64-bit (TheMuppets g12-common / vendor voodika) + board-specific z backupu; fallback 32-bit serwerów dla krytycznych HAL-i. Decyzja szczegółowa spadnie w fazie bring-up (audio/hwcomposer).
2. **Wariant**: ATV (zgodnie z celem „Android TV UI") — potwierdzone; tablet tylko jako plan B jeśli ATV wariant g12-common okaże się zbyt odległy od G12B.
3. LOS 20 (Android 13) jako cel — zgodnie z gałęzią; upgrade do 22.1 po doprowadzeniu do ładu.
4. Spec PC do buildów — user ma PC; zweryfikować RAM/dysk przed fazą 0.

## Źródła (zweryfikowane 2026-09-15)

- Organizacja LineageOS (gałęzie lineage-20): [g12-common](https://github.com/LineageOS/android_device_amlogic_g12-common) (README: G12B/S922X wprost), [kernel amlogic 4.9](https://github.com/LineageOS/android_kernel_amlogic_linux-4.9), [sepolicy](https://github.com/LineageOS/android_device_amlogic_sepolicy), [odroidc4](https://github.com/LineageOS/android_device_hardkernel_odroidc4), [dhd-driver](https://github.com/LineageOS/android_hardware_amlogic_kernel-modules_dhd-driver) (katalog `bcmdhd.100.10.545.x`), [mali-driver](https://github.com/LineageOS/android_hardware_amlogic_kernel-modules_mali-driver), [media modules](https://github.com/LineageOS/android_hardware_amlogic_kernel-modules_media)
- TheMuppets: [proprietary_vendor_amlogic_g12-common](https://github.com/TheMuppets/proprietary_vendor_amlogic_g12-common) (64-bit bloby, gałęzie lineage-20…23.2)
- Mainline Linux: [meson-g12b-gtking-pro.dts](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/amlogic/meson-g12b-gtking-pro.dts) (+ meson-g12b-w400.dtsi, meson-g12b-ugoos-am6.dts)
- voodik: [kernel odroidg12](https://github.com/voodik/android_kernel_voodik_odroidg12) (gałęzie `lineage-20.0_odroidg12_t_64`, `lineage-22.1_odroidg12_64`), [releases_device_odroidn2_ATV_20](https://github.com/voodik/releases_device_odroidn2_ATV_20), buildy: https://oph.mdrjr.net/voodik/S922X/ODROID-N2/Android/ (macierz ATV 16.0→22.1, selfinstall/full/delta)
- Forum ODROID: [LOS 20 N2 t=45758](https://forum.odroid.com/viewtopic.php?t=45758), [LOS 19.1 t=44124](https://forum.odroid.com/viewtopic.php?t=44124), [LOS 22.1 t=49491](https://forum.odroid.com/viewtopic.php?t=49491), [C4/ATV t=48112](https://forum.odroid.com/viewtopic.php?t=48112) (Cloudflare — czytać z przeglądarki); LibreELEC [Dreambox S922X DTS experiments](https://forum.libreelec.tv/thread/23785-dreambox-dreambox2-s922x-device-tree-experiments/)
- XDA: [LOS 22 Amlogic family](https://xdaforums.com/t/official-lineageos-22-for-amlogic-gxl-gxm-g12a-sm1-ne-family-devices-android-tv-tablet.4649881/), [LOS 20 Amlogic family](https://xdaforums.com/t/official-unofficial-lineageos-20-for-amlogic-gxl-gxm-g12-sm1-ne-family-devices.4534935/) (page 5: pytanie o port na Dreambox One/Two G12B)
- Flashowanie/ratunek na Linuksie: [khadas aml-flash-tool](https://github.com/khadas/utils/tree/master/aml-flash-tool), [pyamlboot](https://github.com/superna9999/pyamlboot), [amlogic-usbdl](https://github.com/frederic/amlogic-usbdl), [CoreELEC aml_usb_tool wiki](https://wiki.coreelec.org/coreelec:aml_usb_tool)
- Evervolv/android_device_hardkernel_odroidn2 (drzewo S922X do odniesienia)
- Wątek sprzętowy GT-King (UART/PCB): https://discourse.coreelec.org/t/s922x-bee-link-gt-king/5334
- Lokalnie: `HANDOFF.md` (fakty z ADB, backupy w `backup/`), `README.md` (ścieżki A/B/C, ryzyko secure bootloader)
