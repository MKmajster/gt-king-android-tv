# Wymuszenie trybu USB przez HDMI (BootROM, niezależnie od bootloadera)

Stan 2026-09-18: box zapętlony w `preboot` naszego u-boota galilei v1. Ustalone na konsoli UART (CP2102, COM7, 94 % czytelnych znaków):
- pętla to nasz u-boot z 12 września, obieg ~0,6 s: `gpio: pin GPIOAO_3 (gpio 3) value is 1` → `## Starting application at 0x01000000` → banner → … i od nowa;
- **Ctrl-C nie może przerwać tej pętli**: w `common/cli_hush.c` tego u-boota `ctrlc()` jest sprawdzane tylko w `while`/`until`/`for` (funkcja `run_list_real`), a `preboot` to samo `if`. Pad 3 (RX boxa) jest przez to bez znaczenia;
- `upgrade_key=if gpio input GPIOAO_3; then echo detect upgrade key; run update;fi;` wykonuje się co obieg i dałoby tryb USB, ale **GPIOAO_3 nie ma na płycie żadnego przycisku** (stockowy DTS opisuje „power button", Beelink go nie zamontował). Przełącznik przy baterii to klawisz ADC (pinhole), nieodczytywany w naszym `preboot`;
- kabel A-A z linią 5 V wpięty w OTG zakłóca konsolę (kolizja 5 V PC ↔ 5 V boxa), ale box pracuje dalej. Przy zimnym starcie z takim kablem box nie startuje („czerwone oczy").

## Mechanizm

BootROM Amlogic (GXL/GXM/G12A/**G12B**/SM1) przy każdym starcie odczytuje **8 bajtów z EEPROM-u I2C pod adresem 0x52, offset 0xF8 (248), na liniach DDC złącza HDMI**. Wartości:

| napis | skutek |
|---|---|
| `boot@USB` | start z USB → BootROM zgłasza się jako `1B8E:C003` |
| `boot@SDC` | start z karty SD |
| `boot@SPI` | start z SPI NOR |

Źródło: `doc/board/amlogic/boot-flow.rst` w U-Boocie, wiki „Amlogic HDMI Boot Dongle" (superna9999), projekt `tchebb/amlogic-hdmiboot-avr`. Dzieje się to **przed** odczytem eMMC, więc stan bootloadera i env nie ma znaczenia.

## Sprzęt

Arduino z ATmega328P (Nano / Uno / Pro Mini) udające EEPROM. Firmware: `tools/hdmiboot/i2c-flash.c` (40 linii; slave I2C 0x52, odpowiada `boot@USB` od offsetu 0xF8; bez clock-stretchingu, którego BootROM nie obsługuje). Skompilowane hexy: `tools/hdmiboot/i2c-flash-<mcu>.hex` (atmega328p, atmega168, atmega32u4, atmega2560). Wgrywanie: `tools/hdmiboot/flash-arduino.py` (avrdude 8.3 w `tools/hdmiboot/avrdude/`).

```powershell
py -3.14 tools\hdmiboot\flash-arduino.py             # auto-port, 115200 potem 57600 (stary bootloader Nano)
```

Połączenie (wtyk HDMI męski, np. przejściówka HDMI → listwa zaciskowa; numeracja pinów HDMI typu A):

| Arduino Nano | HDMI |
|---|---|
| A5 (SCL) | pin 15 (DDC SCL) |
| A4 (SDA) | pin 16 (DDC SDA) |
| GND | pin 17 (DDC/CEC GND) |

Pin 18 (+5 V) zostaje wolny. Arduino zasilane z USB komputera. Wewnętrzne pull-upy AVR są włączone w firmware; box ma własne pull-upy DDC.

Alternatywa bez mikrokontrolera: EEPROM 24C02 z A1=VCC, A0=A2=GND (adres 0x52) i wpisanym `boot@USB` pod 0xF8 — ale żeby go zaprogramować, i tak potrzeba Arduino.

## Procedura

1. Zasilanie boxa odłączone. Dongle HDMI wpięty w gniazdo HDMI boxa (TV odłączony). Arduino w USB komputera (świeci, nic więcej nie robi).
2. Kabel A-A: port **USB 2.0** boxa ↔ komputer.
3. USB Burning Tool → File → Import Image → `lineage/out/tree/aml_upgrade_package_chainload+stockbl.img` (**ta paczka ma BL33 v2**; `+stockbl+recovery` ma v1, nie używać) → Start.
4. Podłączyć zasilanie boxa. BootROM czyta dongle, wchodzi w tryb USB, tool wykrywa urządzenie i wgrywa (kilka minut).
5. Po zakończeniu tool ustawia `upgrade_step=1`. Następny start: stockowy u-boot → `defenv_reserv` kasuje nasz hook z env → `storeboot` nie umie wystartować LOS → **13-sekundowe okna burn** → `py -3.14 lineage\scripts\catch-burn.py --wait 300` zakłada hook warunkowy (`if test ${aml_dt} != g12b_s922x_galilei`), `upgrade_step=2`, `saveenv`, `reset`.
6. Stock → hook → `store read bl33` → `go` → galilei v2 (kasuje `preboot` w `board_late_init`) → `storeboot` → LineageOS. Konsola UART (COM7, panel `uart-dashboard.py`) pokazuje log jądra.

Wyjęcie dongle'a HDMI po wgraniu, inaczej każdy start będzie szedł w USB.

## Uwagi

- Sterownik Amlogic: Burning Tool używa libusb0 (oem29); `catch-burn.py` rozmawia przez libusb1 po tym samym sterowniku. Nie przełączać na WinUSB (Zadig), bo tool przestanie widzieć box.
- W trybie BootROM `catch-burn.py` nie działa (wymaga Stage x.16 = u-boot); w BootROM (Stage 0.0) działa tylko Burning Tool / pyamlboot.
- `tools/hdmiboot/build.sh` buduje hexy w WSL (`gcc-avr avr-libc`).
