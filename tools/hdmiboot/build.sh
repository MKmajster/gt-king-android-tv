#!/bin/bash
# Build the Amlogic HDMI boot dongle firmware (tchebb/amlogic-hdmiboot-avr) for ATmega328P.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! command -v avr-gcc >/dev/null; then
  echo "installing avr toolchain..."; sudo apt-get install -y -q gcc-avr avr-libc binutils-avr >/dev/null 2>&1 || sudo apt-get install -y gcc-avr avr-libc binutils-avr
fi
avr-gcc --version | head -1
for mcu in atmega328p atmega168 atmega32u4 atmega2560; do
  avr-gcc -mmcu=$mcu -Wall -Wextra -O2 -std=gnu11 -DBOOT_SEL=5 -c i2c-flash.c -o i2c-flash-$mcu.o
  avr-gcc -mmcu=$mcu i2c-flash-$mcu.o -o i2c-flash-$mcu.elf
  avr-objcopy -O ihex -R .eeprom i2c-flash-$mcu.elf i2c-flash-$mcu.hex
  avr-size i2c-flash-$mcu.elf | tail -1 | awk -v m=$mcu '{print m": text "$1" data "$2" bss "$3}'
done
ls -la *.hex
