#!/usr/bin/env python3
"""Drive the box's UI over adb without looking at the TV: dump the view tree, list what is on screen,
tap an element by its text / content-description / resource-id.

    py -3.14 box-ui.py [--ip 192.168.0.100] dump            texts + clickable nodes with centres
    py -3.14 box-ui.py tap "Dalej"                           tap the first node whose text/desc/id contains it
    py -3.14 box-ui.py key DPAD_DOWN DPAD_CENTER BACK        key events
Used to walk first-run wizards of the emulators unattended (ARMSX2, Dolphin ...).
"""
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

here = os.path.dirname(os.path.abspath(__file__))
top = os.path.abspath(os.path.join(here, "..", ".."))
ADB = os.path.join(top, "tools", "platform-tools", "adb.exe")


def sh(dev, cmd):
    return subprocess.run([ADB, "-s", dev, "shell", cmd], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def dump(dev):
    for _ in range(3):
        sh(dev, "uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1")
        x = sh(dev, "cat /data/local/tmp/ui.xml")
        if x.strip().startswith("<?xml"):
            return ET.fromstring(x)
        time.sleep(1)
    raise SystemExit("uiautomator dump failed")


def centre(b):
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", b))
    return (x1 + x2) // 2, (y1 + y2) // 2


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    ip = "192.168.0.100"
    if a[:1] == ["--ip"]:
        ip, a = a[1], a[2:]
    dev = f"{ip}:5555"
    top_act = sh(dev, "dumpsys activity activities | grep -m1 topResumedActivity").strip()
    print(top_act)
    if not a or a[0] == "dump":
        root = dump(dev)
        for n in root.iter("node"):
            t, d, rid = n.get("text", ""), n.get("content-desc", ""), n.get("resource-id", "")
            flags = "".join(c for c, k in (("C", "clickable"), ("F", "focused"), ("K", "checked")) if n.get(k) == "true")
            if t or d or "C" in flags:
                print(f"{flags:3} {centre(n.get('bounds'))} {t!r} {d!r} {rid.split('/')[-1]}")
    elif a[0] == "tap":
        root = dump(dev)
        want = a[1].lower()
        nodes = list(root.iter("node"))
        exact = [n for n in nodes if want in (n.get("text", "").lower(), n.get("content-desc", "").lower())]
        for n in exact + nodes:
            hay = " ".join((n.get("text", ""), n.get("content-desc", ""), n.get("resource-id", ""))).lower()
            if want in hay:
                x, y = centre(n.get("bounds"))
                sh(dev, f"input tap {x} {y}")
                print(f"tap {a[1]!r} at {x},{y}")
                return 0
        print(f"not found: {a[1]!r}")
        return 1
    elif a[0] == "key":
        for k in a[1:]:
            sh(dev, f"input keyevent KEYCODE_{k}")
            time.sleep(0.4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
