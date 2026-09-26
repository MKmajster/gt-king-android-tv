"""Open the Amlogic USB device (VID 1B8E PID C003) with whichever pyusb backend matches the bound
Windows driver: libusb0 (libusb-win32, installed by the USB Burning Tool) or libusb1 (WinUSB via Zadig).
Returns a pyamlboot.AmlogicSoC whose .dev uses that backend.

    from amlusb import open_soc
    soc, backend = open_soc()
"""
import os

VID, PID = 0x1B8E, 0xC003


def _prep_dlls():
    for d in (os.path.join(os.environ.get("APPDATA", ""), r"Python\Python314\site-packages\libusb\_platform\windows\x86_64"),
              r"C:\Windows\System32", r"C:\Program Files (x86)\Amlogic\USB_Burning_Tool"):
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
            try:
                os.add_dll_directory(d)
            except Exception:
                pass


def identify_ok(dev, tries=5):
    """IDENTIFY with retries: through the libusb0.sys driver libusb-1.0 occasionally returns a
    truncated control-IN buffer (1 byte instead of 8); the next attempt is normally fine."""
    import time
    last = None
    for _ in range(tries):
        try:
            b = bytes(dev.ctrl_transfer(0xC0, 0x20, 0, 0, 8, timeout=3000))
            if len(b) == 8:
                return True, b
            last = f"short identify {list(b)}"
        except Exception as e:
            last = repr(e)
        time.sleep(0.3)
    return False, last


def open_soc(prefer=None):
    """Try libusb0 first when its DLL exists (device bound to libusb0.sys), verify with IDENTIFY,
    fall back to libusb1. Returns (AmlogicSoC, backend_name)."""
    _prep_dlls()
    import usb.core
    from pyamlboot import pyamlboot
    order = ["libusb0", "libusb1"] if prefer is None else [prefer]
    last = None
    for name in order:
        try:
            if name == "libusb0":
                import usb.backend.libusb0 as b
            else:
                import usb.backend.libusb1 as b
            be = b.get_backend()
            if be is None:
                continue
            dev = usb.core.find(idVendor=VID, idProduct=PID, backend=be)
            if dev is None:
                last = f"{name}: device not found"
                continue
            ok, info = identify_ok(dev)
            if not ok:
                last = f"{name}: identify -> {info}"
                continue
            soc = pyamlboot.AmlogicSoC.__new__(pyamlboot.AmlogicSoC)
            soc.dev = dev
            soc.backend_name = name
            soc.ident = info
            return soc, name
        except Exception as e:
            last = f"{name}: {e}"
    raise RuntimeError(f"no usable USB backend for the Amlogic device ({last})")


def describe(ident):
    b = ident
    stage = {0: "BootROM", 8: "BL2/SPL", 16: "u-boot(TPL)"}.get(b[3], f"stage {b[2]}.{b[3]}")
    return f"ROM {b[0]}.{b[1]} Stage {b[2]}.{b[3]} = {stage}; password needed={b[4]} ok={b[5]}"
