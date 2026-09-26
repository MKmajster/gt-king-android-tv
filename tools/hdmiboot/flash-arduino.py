#!/usr/bin/env python3
"""Flash the Amlogic HDMI-boot dongle firmware onto an Arduino (Nano/Uno/Pro Mini = ATmega328P).

    py -3.14 tools/hdmiboot/flash-arduino.py            auto-detect the port, try 115200 then 57600
    py -3.14 tools/hdmiboot/flash-arduino.py --port COM8 --mcu atmega328p

After flashing the board is an I2C slave at 0x52 answering "boot@USB" at offset 0xF8:
    Arduino A5 (SCL) -> HDMI pin 15,  A4 (SDA) -> HDMI pin 16,  GND -> HDMI pin 17.
"""
import argparse, os, subprocess, sys
import serial.tools.list_ports

HERE = os.path.dirname(os.path.abspath(__file__))
AVRDUDE = os.path.join(HERE, "avrdude", "avrdude.exe")

ap = argparse.ArgumentParser()
ap.add_argument("--port")
ap.add_argument("--mcu", default="atmega328p", choices=["atmega328p", "atmega168", "atmega32u4", "atmega2560"])
a = ap.parse_args()

port = a.port
if not port:
    for p in serial.tools.list_ports.comports():
        if p.vid in (0x1A86, 0x0403, 0x2341, 0x2A03, 0x10C4) and "CP210x" not in (p.description or ""):
            port = p.device; print("port:", p.device, p.description); break
if not port:
    print("nie znaleziono Arduino (CH340/FTDI/Arduino VID) - podaj --port COMx"); sys.exit(2)

hexf = os.path.join(HERE, f"i2c-flash-{a.mcu}.hex")
prog = {"atmega328p": ("arduino", [115200, 57600]), "atmega168": ("arduino", [19200]),
        "atmega32u4": ("avr109", [57600]), "atmega2560": ("wiring", [115200])}[a.mcu]
for baud in prog[1]:
    cmd = [AVRDUDE, "-c", prog[0], "-p", a.mcu, "-P", port, "-b", str(baud), "-D", "-U", f"flash:w:{hexf}:i"]
    print(">", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print(f"\nOK: firmware wgrany ({a.mcu}, {baud} baud). Dongle gotowy: A5->HDMI 15, A4->HDMI 16, GND->HDMI 17.")
        sys.exit(0)
    print(f"(nieudane przy {baud} baud, probuje dalej)")
sys.exit(1)
