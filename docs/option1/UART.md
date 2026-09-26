# Konsola UART GT-King PRO (galilei) przez ESP32-C3 jako adapter USB-TTL

Stan 2026-09-16: box w pętli chainload (hook `preboot` w env eMMC wykonywany także przez nasz u-boot). Wszystkie miękkie wejścia w tryb burn są martwe (patrz `FLASH.md` §2a i pamięć sesji). Konsola UART_AO (ttyS0, 115200 8N1, 3,3 V TTL) daje prompt u-boota: strumień Ctrl-C przerywa `preboot` (brak `CONFIG_AUTOBOOT_KEYED`), a z promptu `update` otwiera tryb burn USB na żądanie.

## Płyta i pady

`GTKing-D4X16 V4.0` (S922X / 4G / 64G / **AP6275S** / HDMI). Spód: 4 pady przelotowe w rzędzie na prawo od naklejki „S/N Code", zdjęcie z oznaczeniem: `lineage/out/uart_pads_zoom.png` i `lineage/out/gtking-pro-uart-annotated.jpg`.

| Pad | Pozycja | Funkcja | Podłączenie |
|-----|---------|---------|-------------|
| 1 | dolny, **kwadratowy** | **GND** (zmierzone multimetrem 2026-09-18) | GND adaptera |
| 2 | drugi od dołu | TX boxa (potwierdzone: dane, 100 % czytelne) | RXD adaptera |
| 3 | trzeci od dołu | RX boxa | TXD adaptera |
| 4 | górny | najpewniej 3V3 | **NIE PODŁĄCZAĆ** |

Wcześniejsze założenie „kwadratowy = 3V3, górny = GND" było błędne i kosztowało dwa dni pracy bez wspólnej masy. Reguła: **kwadratowy pad = pin 1 = GND** na tej płycie.

## Masa: najważniejszy przewód, i nie ta śruba

**Miedziany pierścień śruby obok listwy nie jest masą.** Podpięcie do niego masy ESP32 powoduje przepływ prądu i zanik zasilania boxa (gaśnie dioda) — to prawie na pewno przelotka zasilania. Nie używać.

Bezpieczna masa: metalowa obudowa gniazda HDMI / USB / Ethernet na tylnym panelu. Kolejność ma znaczenie: **najpierw odłączyć 12 V od boxa, podpiąć masę, dopiero potem włączyć zasilanie** — zetknięcie dwóch mas o różnym potencjale przy pracujących urządzeniach daje skok prądu.

Pad 4 powinien być masą listwy, ale przed podpięciem trzeba to sprawdzić bezpiecznie: drut z padu do **GPIO4** (wejście, wysoka impedancja, nic nie zewrze) i `--probe` / przycisk „Diagnostyka padów". Werdykt „na stałe NISKI" = masa, „na stałe WYSOKI" = zasilanie (nie podłączać).

## Bez wspólnej masy UART nie działa, choć coś odbiera

Prąd powrotny szuka drogi przez zasilacze i kabel Ethernet, więc poziomy odniesienia obu stron się rozjeżdżają i stan niski nie schodzi poniżej progu. Objaw jest bardzo charakterystyczny: **przekłamania idą tylko w jedną stronę, zera przychodzą jako jedynki** (`timeout` → `wimeouv`, `storage` → `svoryge`). Zmierzone: 4–6 kB/s na padzie 2 przy 40 % czytelnych znaków i zero reakcji boxa na 1500 bajtów Ctrl-C.

To samo dotyczy nadawania: nasz stan niski też nie dociera, więc Ctrl-C nie przerywa pętli.

## Kontakt mechaniczny

Luźny drucik w otworze daje styk rezystancyjny: widać wtedy tylko iglice 1–3 µs, a nie impulsy o szerokości bitu (8,7 µs przy 115200). `--probe` i `--contact` rozróżniają te dwa przypadki, dioda LED na ESP32 miga, gdy dane naprawdę płyną. Trwałe rozwiązanie to wlutowany goldpin.

Mostek **nie włącza pull-up** na pinie RX (`--rx-pull none`), bo sterownik UART w ESP-IDF robi to domyślnie i przy słabym styku dociąga linię do 3,3 V.

## Czym się podłączyć (stan 2026-09-16)

Użyty ESP32-C3 **padł** podczas prób (znikał z USB co kilka sekund, wcześniej dwa razy się zawiesił i raz wypisał crash dump). Najpewniejsza przyczyna: praca bez wspólnej masy, przez co prąd z padów wchodził diodami zabezpieczającymi w wejścia układu. Kopia jego firmware: `lineage/out/esp32c3-backup-e072a16c39e0.bin`.

Narzędzia obsługują teraz **dwa tryby**, wykrywane automatycznie po VID portu:
- `direct` — zwykły adapter USB-TTL (CH340 `1A86`, CP2102 `10C4`, FTDI `0403`, PL2303 `067B`, Arduino, Pico). Port szeregowy **jest** konsolą boxa, żadnego pośrednika. To ścieżka zalecana.
- `bridge` — ESP32 z MicroPythonem (VID `303A`), dodatkowo z diagnostyką padów.

Czego użyć:
| Sprzęt | Nadaje się? |
|---|---|
| Moduł USB-TTL CH340 / CP2102 / FTDI, 3,3 V | tak, wprost, nic nie trzeba robić |
| Arduino Uno / Nano | tak, po zwarciu RESET do GND; ale logika 5 V → dzielnik na TX |
| Raspberry Pi Pico | tak, z MicroPythonem, natywnie 3,3 V |
| Kabel VAG-KKL 409.1 | dopiero po otwarciu i wlutowaniu się w FT232RL (TXD=1, RXD=5, GND=7); na wtyku OBD jest K-line 12 V, nie TTL |
| ELM327 | nie — między układem USB a złączem siedzi mikrokontroler AT |
| Port COM1 na płycie PC | nie wprost — to RS-232 ±12 V, potrzebny konwerter MAX3232 |

Przy adapterze 5 V na linii do **RX boxa** (pad 3) obowiązkowo dzielnik: 1 kΩ szeregowo, 2 kΩ do masy. W drugą stronę nie trzeba, bo 3,3 V z boxa przekracza próg wejścia adaptera.

## Panel na żywo: `lineage/scripts/uart-dashboard.py`

```powershell
py -3.14 lineage/scripts/uart-dashboard.py     # -> http://localhost:8080/
```
Pokazuje stan każdego padu, prędkość odbioru, dowód nadawania (tylko odpowiedź boxa liczy się jako dowód), rozpoznane napisy u-boota, konsolę surową i z naprawionymi bitami. Przyciski: diagnostyka padów, salwa Ctrl-C, naprawa (`update` + `catch-burn.py`), wysyłka komendy. **Automat** sam rusza z salwą Ctrl-C, gdy sygnał przekroczy 72 % czytelnych znaków — czyli w chwili podłączenia prawdziwej masy.

## Narzędzie: `lineage/scripts/esp32-bridge.py`

ESP32-C3 (SuperMini, VID:PID `303A:1001`, natywne USB-Serial-JTAG, COM4) z MicroPythonem v1.29.0. Host wchodzi w raw REPL i wgrywa do RAM przezroczysty mostek UART1 (`micropython.kbd_intr(-1)`, więc Ctrl-C leci do boxa, a nie do MicroPythona). Port jest otwierany z `dtr=False, rts=False` — inaczej C3 resetuje się przy każdym otwarciu. Trzy Ctrl-] (0x1D) kończą mostek.

**Nie zwierać EN do GND** (to wariant dla WROOM-32 z CP2102) — u C3 odcięłoby to USB.

```powershell
# 1. Co jest na którym padzie? (tylko wejścia, nic nie steruje; box musi być włączony)
py -3.14 lineage\scripts\esp32-bridge.py --probe

# 2. Regulacja drucików: LED miga, gdy pad 2 naprawdę dowozi dane
py -3.14 lineage\scripts\esp32-bridge.py --contact 120

# 3. Pełny automat: czeka na styk -> mostek -> salwa Ctrl-C -> prompt -> hook warunkowy
#    -> saveenv -> reset -> 120 s logu startu
py -3.14 lineage\scripts\esp32-bridge.py --auto 45

# ręcznie, krok po kroku:
py -3.14 lineage\scripts\esp32-bridge.py --watch 20
py -3.14 lineage\scripts\esp32-bridge.py --break --fix-hook
py -3.14 lineage\scripts\esp32-bridge.py --break --drop-hook     # czysty stock
py -3.14 lineage\scripts\esp32-bridge.py --break --cmd "printenv preboot" --cmd "update"

# gdy TX/RX odwrotnie:
py -3.14 lineage\scripts\esp32-bridge.py --rx 3 --tx 2 --watch 20
# test samego mostka: zworka GPIO2<->GPIO3
py -3.14 lineage\scripts\esp32-bridge.py --loopback
```

Cały odbiór leci do `lineage/out/serial-COM4.log`.

### Interpretacja `--probe`
- `TX of the box: real 115200 data` — pad z danymi, tu wpiąć GPIO2.
- `high with only ~1-3 us spikes: crosstalk` — **zły styk**, docisnąć/wlutować.
- `high but sags with pull-down: RX of the box` — pad RX, tu GPIO3.
- `steady 3.3 V that does not sag` — 3V3, nie podłączać.
- `floating` — brak styku albo box wyłączony.

## Wariant B: ESP32 WROOM-32 (ze scalakiem CP2102/CH340)
1. **EN → GND** na ESP32 (ESP32 trzymany w resecie).
2. **box GND → ESP32 GND**.
3. **box TX → pin ESP32 „TX/TX0" (GPIO1)**, **box RX → pin „RX/RX0" (GPIO3)**.
4. Nie łączyć 3V3/5V. ESP32 zasilany tylko z USB PC.

Obsługa: `lineage\scripts\serial-console.py --port COMx --watch 10` / `--break --fix-hook`.

## Po uzyskaniu promptu
Z promptu (`--cmd`): `update` → tryb burn USB → `py -3.14 lineage\scripts\catch-burn.py --wait 60 --bl33 lineage\out\bl33-v2.img` (wgrywa BL33 v2 ignorujący hook, zapisuje hook warunkowy, `reset`). Potem obserwacja startu LOS na konsoli (kernel log na ttyS0) — to zarazem narzędzie do dalszego bring-upu.

Alternatywa bez UART: zwarcie linii eMMC przy starcie → BootROM USB → Burning Tool z `aml_upgrade_package_chainload+stockbl+recovery.img` (ryzykowne, BGA).

## Po naprawie: przywrócenie firmware ESP32
Oryginalny firmware (Supla, „Szambo A02YYUW") jest w `lineage/out/esp32c3-backup-e072a16c39e0.bin` (4 MiB, odczyt zweryfikowany):
```powershell
py -3.14 -m esptool --port COM4 --chip esp32c3 --baud 460800 write-flash 0 lineage\out\esp32c3-backup-e072a16c39e0.bin
```
