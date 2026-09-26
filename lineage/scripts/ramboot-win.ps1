# RAM-boot a u-boot candidate on the GT-King Pro over USB (BootROM mode) with pyamlboot.
# Nothing is written to eMMC: power-cycle the box and it boots stock again.
#
# Prerequisites (one-time, needs admin): box in BootROM USB mode shows up as
# "WorldCup Device" (USB\VID_1B8E&PID_C003) -> install the WinUSB driver for it
# with Zadig (tools\zadig.exe, run as administrator; Options > List All Devices,
# or Device > Create New Device with VID 1B8E PID C003 when the box is not connected).
# Cable: USB-A <-> USB-A into the box's USB 2.0 (OTG) port. Verified 2026-09-15:
# the box enumerates on this PC (Hub_#0002 Port_#0003) in u-boot burn mode
# (adb reboot update -> VID 1B8E PID C003 for ~6 s) and in u-boot fastboot
# (adb reboot fastboot -> VID 18D1 PID 0D02).
# Entering BootROM mode (needed for RAM boot, waits indefinitely for the host):
# hold the reset pinhole (inside the AV jack) while connecting power.
#
# Usage:  powershell -ExecutionPolicy Bypass -File ramboot-win.ps1 [hybrid|radxa|list|<path to u-boot.bin>]
#         list = only enumerate USB devices libusb can open (driver + cable check)
param([string]$Candidate = "hybrid")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # <repo>
$out = Join-Path $root "lineage\out"

$py = "py"
# pyusb needs libusb-1.0.dll on PATH (Windows); the pip package "libusb" ships it
$dll = Join-Path $env:APPDATA "Python\Python314\site-packages\libusb\_platform\windows\x86_64"
if (Test-Path (Join-Path $dll "libusb-1.0.dll")) {
    $env:PATH = "$dll;" + $env:PATH
} else {
    Write-Host "warning: libusb-1.0.dll not found under $dll (py -3.14 -m pip install --user libusb)" -ForegroundColor Yellow
}

if ($Candidate -eq "list") {
    # devices libusb can open: WinUSB/libusbK-driven ones show up here, driverless ones (PnP status Error) do not
    & $py -3.14 -c "import usb.core; print(sorted(set('%04x:%04x' % (d.idVendor, d.idProduct) for d in usb.core.find(find_all=True))))"
    exit 0
}

switch ($Candidate) {
    "hybrid" { $bin = Join-Path $out "u-boot-galilei-hybrid-stockbl2.bin" }   # stock BL2 (Beelink DDR timing) + LOS FIP
    "radxa"  { $bin = Join-Path $out "u-boot-galilei-radxafip.bin" }          # pure LOS build (Radxa Zero 2 Pro BL2)
    default  { $bin = $Candidate }
}
if (-not (Test-Path $bin)) { throw "candidate image not found: $bin" }

$script = Join-Path $env:APPDATA "Python\Python314\Scripts\boot-g12.py"
if (-not (Test-Path $script)) { throw "pyamlboot not installed for the Windows Python: py -3.14 -m pip install --user pyamlboot pyusb libusb" }

$dev = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like 'USB\VID_1B8E&PID_C003*' }
if (-not $dev) {
    Write-Host "No Amlogic BootROM device (VID 1B8E PID C003) present." -ForegroundColor Yellow
    Write-Host "Put the box in USB boot mode (reset pinhole while powering on) and connect the USB-A<->USB-A cable to the USB 2.0 port."
    exit 2
}
Write-Host ("Device: {0} [{1}] {2}" -f $dev.FriendlyName, $dev.Status, $dev.InstanceId)
if ($dev.Status -ne "OK") {
    Write-Host "Driver not OK - install WinUSB for this device with Zadig (admin), then run again." -ForegroundColor Yellow
    exit 3
}

Write-Host "Booting $bin ..."
& $py -3.14 $script $bin
Write-Host "Done. Watch the HDMI output: Amlogic/LineageOS logo or a u-boot console means BL2 initialised the DDR and BL33 runs."
