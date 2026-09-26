# Wymuszenie trybu USB przez zwarcie linii eMMC (GTKing-D4X16 Ver:4.0)

Stan 2026-09-20. Box zapętlony w `preboot` naszego BL33 v1; konsola nie może tego przerwać
(`HDMI-BOOT.md`), przycisku GPIOAO_3 nie ma, karty SD nie ma. Zostaje BootROM: jeśli przy
podaniu zasilania eMMC nie odpowie, BootROM idzie eMMC → SD → **USB** i zgłasza się jako
`1B8E:C003` (WorldCup Device) — tego stanu oczekuje USB Burning Tool. Stan bootloadera i env
nie ma wtedy znaczenia.

## Co jest pewne (karta katalogowa + pomiary)

Kość: **Kioxia THGAMRG9T23BAIL**, obudowa P-WFBGA153-1113-0.50: 13,0 × 11,5 mm, 153 kulki,
raster 0,5 mm, pole kulek 6,5 × 6,5 mm na środku, kolumny `A B C D E F G H J K L M N P`
(bez I i O) wzdłuż **długiego** boku 13 mm, wiersze 1..14 wzdłuż krótkiego 11,5 mm.
Kropka indeksu = narożnik A1. Mapa kulek jest standardem JEDEC (identyczna u każdego
producenta 153-ball). Źródło: `lineage/out/research/kioxia/kioxia_THGAMRG9T23BAIL_digikey_rev3_0_20200210.pdf`,
strona 1 („Top View") i 4 (wymiary); współrzędne wszystkich nazwanych kulek w
`lineage/out/research/kioxia/ball_coordinates_THGAMRG9T23BAIL.json`.

| sygnał | kulka | od krawędzi strony A (13 mm) | od krawędzi wiersza 1 (11,5 mm) | uwaga |
|---|---|---|---|---|
| **CLK** | **M6** | 8,75 mm (4,25 mm od strony P) | 5,00 mm | zegar; przy bezczynności ~0 V, **nie** piszczy do masy |
| **CMD** | **M5** | 8,75 mm | 4,50 mm | linia komend, pull-up → ~1,8 V |
| **DAT0** | **A3** | 3,25 mm | 3,50 mm | dane bit 0, pull-up → ~1,8 V |
| DAT5 = **POC1** | B4 | 3,75 mm | 4,00 mm | strap BootROM (BOOT_5): nisko przy starcie = **USB jako pierwsze** |
| RST_n | K5 | 7,75 mm | 4,50 mm | reset eMMC, pull-up |
| DS | H5 | 6,75 mm | 4,50 mm | tylko HS400 — zwarcie nic nie daje |
| VCCQ 1,8 V | C6 M4 N4 P3 P5 | | | I/O eMMC jest **1,8 V** (nie 3,3 V) |
| VCC 3,3 V | E6 F5 J10 K9 | | | |
| VSS/VSSQ | A6 E7 G5 H10 J5 K8 / C4 N2 N5 P4 P6 | | | |

Na naszej płycie (góra, tekst kości czytelny normalnie, kropka w lewym dolnym rogu, dłuższy
bok poziomo) to dokładnie orientacja „Top View" z karty: **A1 lewy-dół, kolumny A→P w prawo,
wiersze 1→14 w górę**. Nakładka na naszym zdjęciu: `lineage/out/emmc-ballmap-overlay.jpg`.
CLK/CMD leżą więc w prawej części kości (4,25 mm od prawej krawędzi), lekko poniżej połowy
wysokości; DAT0/DAT5 w lewej części, w dolnej połowie. **Żadna z tych kulek nie jest dostępna
z góry** — zwiera się przelotkę / pad elementu leżący na tej samej sieci.

SoC S922X (agent „amlogic-poc", z `pinctrl-meson-g12a.c` i `boot-flow.rst`): eMMC siedzi na
banku BOOT: D0–D7 = BOOT_0..7, CLK = BOOT_8, CMD = BOOT_10, RST = BOOT_12, DS = BOOT_13.
Strapy POC0/1/2 = BOOT_4/5/6 = **DAT4/DAT5/DAT6**, wewnętrznie podciągnięte, zatrzaskiwane
przy resecie; domyślnie 1/1/1 = eMMC → SD → USB. **POC1 (DAT5) nisko przez 4,7 kΩ przy
starcie = USB → eMMC → SD** — to ten sam mechanizm co pad „Maskrom" na Khadas VIM3
(schemat: `EMMC_D5 —4,7k— Q10 —GND`, `lineage/out/research/generic/vim3-sch-p6-maskrom-wide.png`).
W tym samym schemacie referencyjnym EMMC_CLK ma szeregowy **0 Ω R0402** (`vim3-sch-p6-emmcclk-crop.png`),
więc na płycie może istnieć osobny rezystor 0402 na zegarze.

Sieci zmierzone dotąd i wykluczone (nie zwierać ponownie): TP1 = VCCQ 1,8 V, TP2 = GND,
TP3 = VCC ~3,0–3,3 V (trzy przelotki przy lewej krawędzi kości); klaster 6 padów przy UART
(domena 3,3 V); dwie przelotki przy złączach antenowych (SDIO WiFi); pierścień śruby (zasilanie).
**Nie zwierać** też dwóch rezystorów przy gnieździe RJ45 zaznaczonych 20.09 w
`lineage/out/short-pads-v2-full.jpg` — to wskazanie z porównania ze zdjęciem, które okazało się
zdjęciem małpy z ekranu TV (`identical-board-marked.jpg`), a schemat Beelinka dotyczy
rev 3.2 z innym rozkładem spodu.

## Gdzie to jest na spodzie

Spód nie ma dedykowanych padów „short" (jak rev 3.2). Pod kością, po drugiej stronie, leży
klaster 22 elementów 0402 w trzech kolumnach plus dwa układy SOT-23-6 — typowo kondensatory
VCC/VCCQ oraz **pull-upy 10 k do VCCQ na CMD, DAT0–7 i RST_n**. Każdy pull-up ma jeden
koniec na 1,8 V, a drugi **na linii sygnałowej** — to są punkty do zwierania.

Rzut obrysu i kulek na spód (`lineage/out/emmc-bottom-footprint.jpg`, mapa pomiarowa
`lineage/out/emmc-bottom-numbered.jpg`, orientacja `lineage/out/emmc-bottom-locator.jpg`)
zrobiony przez podobieństwo z dwóch przelotek TP1/TP2, które widać z obu stron (zdjęcie spodu
`short-pads-v2-full.jpg` z 20.09). Dokładność ok. ±1,5 mm (3 rastry). W tej orientacji
(zdjęcie spodu, naklejka S/N u góry): kolumny A→P biegną **z góry na dół**, wiersze 1→14
**z prawej na lewo**; CLK/CMD wypadają przy **dolnym końcu środkowej kolumny** elementów,
DAT0/DAT5 między kolumną środkową a prawą, w górnej części.

## Identyfikacja multimetrem (DT9208A)

Odniesienia tuż obok: **TP2 = masa** (piszczy), **TP1 = VCCQ 1,8 V**. Elementy numerować od
góry: kolumna L (lewa, z U1), S (środkowa, 8 szt.), P (prawa, 8 szt.) — jak na
`emmc-bottom-numbered.jpg`. Dla **każdego końca** każdego elementu:

1. Box **wyłączony** (zasilacz odpięty): buzzer do TP2 → piszczy = masa (pomijamy).
2. Box wyłączony, zakres 20 kΩ do TP1: ~0 Ω = VCCQ (pomijamy); **ok. 10 k (4,7–100 k) = koniec
   pull-upu na linii sygnałowej — kandydat**; „1" (poza zakresem) = inna sieć (sprawdzić jeszcze
   do TP3 = VCC).
3. Box **włączony** (pętla): V DC na kandydatach: **~1,75–1,80 V = CMD/DATx/RST_n**;
   **~0–0,9 V bez piszczenia do masy = CLK** (zegar bramkowany w spoczynku czyta ~0 V,
   wolnobieżny ~0,9 V) albo DS.

Kandydatów CLK szukać także z **góry**, na prawo od kości: pojedynczy element 0402 (na
`emmc-ballmap-overlay.jpg` na wysokości CLK, przy prawej krawędzi kadru, pod górną grupą 2×2)
— jeśli oba końce mają ~0 V i nie piszczą do masy, to szeregowy rezystor zegara; dwie grupy
2×2 obok to najpewniej kondensatory VCCQ/VCC (jeden koniec piszczy).

Kolejność prób zwierania (każda to osobny start boxa):
1. koniec pull-upu przy rzucie **CMD/CLK** (dolny koniec kolumny S i sąsiedzi),
2. każdy inny „1,8 V, ~10 k do TP1" po kolei (wśród nich są DAT0 i DAT5; DAT1–3/7 mogą nic nie dać, ale nie szkodzą),
3. każdy „~0 V bez piszczenia" (CLK lub DS).

## Procedura zwarcia + Burning Tool

1. microSD wyjęta, zasilacz odpięty, USB Burning Tool otwarty: Import Image →
   `lineage/out/tree/aml_upgrade_package_chainload+stockbl.img` (BL33 v2; **nie** `+stockbl+recovery`),
   odznaczone „Erase bootloader" i „Erase all", **Start** wciśnięty (tool czeka na urządzenie).
   Nie uruchamiać `catch-burn.py` — jego IDENTIFY psuje handshake toola.
2. Kabel A-A do portu **USB 2.0** boxa (nie USB 3.0). Jeśli box z kablem przy zimnym starcie
   nie rusza („czerwone oczy"), zakleić pin 1 (VBUS, +5 V) po stronie boxa albo przeciąć czerwoną
   żyłę — box ma własne 12 V.
3. Pęsetą zewrzeć wybrany punkt do **TP2** (masa) i trzymać; podać 12 V; trzymać **5–8 s**;
   puścić. W trybie CMD/DAT0/CLK BootROM po nieudanym eMMC zostaje w trybie USB bez limitu
   czasu, więc kabel można wpiąć także po puszczeniu pęsety. W trybie **DAT5 (POC1)** USB jest
   próbowane **pierwsze i krótko** — kabel musi być wpięty i tool uzbrojony **przed** podaniem zasilania.
4. Sukces: Menedżer urządzeń pokazuje „WorldCup Device" (`1B8E:C003`, sterownik libusb0),
   tool zaczyna wgrywać (kilka minut). Brak reakcji = ta sieć nie była CLK/CMD/DAT0/DAT5 —
   następny kandydat.

## Próba 21.09 — pierwsze wejście przez zwarcie: enumeracja pada

Zwarcie **działa** (BootROM przechodzi do USB — Windows coś wykrywa), ale enumeracja
nie dochodzi do skutu i tool nie zaczyna wgrywać. Fakty z sesji (20:45–21:10):

- Tool: **V2.1.9.0** (nie 2.2.0 jak wcześniej zapisano), uruchomiony jako administrator,
  obraz `+stockbl` zaimportowany 20:45 (`temp/burn_config.xml` zawiera `PARTITION bootloader`
  — wariant właściwy), Start wciśnięty, tool skanował na każde DBT arrival.
- Windows: urządzenie jako `USB\VID_0000&PID_0002` „żądanie deskryptora urządzenia nie
  powiodło się", port 9 root huba kontrolera **AMD xHCI ven_1022&dev_43d5**; tool loguje
  `GET NODE CONNECTION Error! connect status 2` (= DeviceFailedEnumeration).
- **Port i sterownik wykluczone**: wpis rejestru `USB\VID_1B8E&PID_C003\6&3AF0F9CE&0&10`
  ( klasa libusb-win32) pokazuje, że 15–16.09 na tym samym porcie WorldCup enumerował się
  poprawnie — wtedy jednak wejście w burn było z Androida (`adb reboot update`), nie ze
  zimnego startu. `worldcup_device.inf` (libusb-win32) siedzi w driver store.
- 12× `pnputil /restart-device` na zawieszonym węźle + 3 fizyczne retry (21:06/21:08/21:09):
  bez zmian. Zawieszony węzeł nie odpowiada na reset portu — box trzeba przełączyć zasilaniem.
- Python w tle (elevated) okazał się `C:\binance-bot\scripts\compute_worker.py` — nie catch-burn,
  nie zakłóca. Wykluczone.
- Wniosek: zimny start z wpiętym kablem = VBUS z PC zasila boxa (dokumentowane „czerwone
  oczy"), USB phy w stanie pół-żywym → deskryptor nieczytelny. **Następny krok: zaklejka
  pinu 1 (VBUS) we wtyku od strony boxa** (multimetrem: +5 V na wolnym końcu przy drugim
  wpiętym w PC), potem pełny power-cycle ze zwarciem. Alternatywy: port na drugim kontrolerze
  (ven_1022&dev_149c), hub USB 2.0 między PC a boxem, inny kabel A-A.
- Narzędzie: `tools/watcher.ps1` — pętla w tle, pikanie gdy pojawi się `VID_1B8E` (9 min na
  uruchomienie); `tools/diag-usb.ps1`, `tools/elevated-fix.ps1` (identyfikacja procesów +
  restarty portu, wymaga UAC).

## Po udanym flashu

Jak w `HDMI-BOOT.md` §5: pierwszy start stockowego u-boota (`upgrade_step=1` → `defenv_reserv`
czyści hook) → `storeboot` nie umie wystartować LOS → 13-sekundowe okna burn →
`py -3.14 lineage\scripts\catch-burn.py --wait 300 --bl33 lineage\out\bl33-v2.img` zakłada hook
warunkowy, `upgrade_step=2`, `saveenv`, `reset` → stock → hook → BL33 v2 → LineageOS.

## Ryzyko

Zwarcie linii I/O 1,8 V do masy przez kilka sekund to standardowa praktyka na Amlogic (CLK
jest sterowany przez SoC z ograniczeniem prądu pada). Nie zwierać sieci VCC/VCCQ (TP1/TP3) ani
pinów układów U1/U2. Pęseta pionowo, czubkami tylko na dwóch punktach.

## Co nie zostało sprawdzone

Sweep forów (4PDA oba wątki, FreakTab, XDA, BBS Beelink, ZNDS, YouTube) z 20.09 pobrał
strony do `lineage/out/research/`, ale agenci czytający je padli na limicie sesji; wstępny grep
(`lineage/out/research/short-snippets.txt`) nie wskazał punktów dla rev 4.0. Rev 3.2 ma
punkty pod naklejką DKEY (`lineage/out/beelink-gtkingpro-short-points.png`) — inny spód.
