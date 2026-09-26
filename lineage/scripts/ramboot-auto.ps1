# Wait for the Amlogic USB device (VID 1B8E PID C003, WinUSB driver = status OK) and immediately
# RAM-boot the given u-boot candidate with pyamlboot (boot-g12.py). Nothing is written to eMMC.
# Needed because on the GT-King Pro the USB window can be only a few seconds long.
#
# Usage: powershell -ExecutionPolicy Bypass -File ramboot-auto.ps1 [hybrid|radxa|<u-boot.bin>] [timeoutSeconds]
param([string]$Candidate = "hybrid", [int]$TimeoutSec = 600)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $root "lineage\out"
switch ($Candidate) {
    "hybrid" { $bin = Join-Path $out "u-boot-galilei-hybrid-stockbl2.bin" }
    "radxa"  { $bin = Join-Path $out "u-boot-galilei-radxafip.bin" }
    default  { $bin = $Candidate }
}
if (-not (Test-Path $bin)) { throw "candidate image not found: $bin" }
$dll = Join-Path $env:APPDATA "Python\Python314\site-packages\libusb\_platform\windows\x86_64"
if (Test-Path (Join-Path $dll "libusb-1.0.dll")) { $env:PATH = "$dll;" + $env:PATH }
$script = Join-Path $env:APPDATA "Python\Python314\Scripts\boot-g12.py"

function Now { (Get-Date).ToString("HH:mm:ss.fff") }
Write-Host "$(Now) waiting up to $TimeoutSec s for USB\VID_1B8E&PID_C003 (candidate: $bin)"
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$seenNotOk = $false
while ((Get-Date) -lt $deadline) {
    $dev = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like 'USB\VID_1B8E&PID_C003*' } | Select-Object -First 1
    if ($dev) {
        if ($dev.Status -eq "OK") {
            Write-Host "$(Now) device present: $($dev.InstanceId) [$($dev.Status)] -> booting"
            & py -3.14 $script $bin 2>&1 | ForEach-Object { "$(Now) $_" }
            Write-Host "$(Now) boot-g12.py exit=$LASTEXITCODE"
            Start-Sleep -Seconds 3
            $still = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like 'USB\VID_1B8E&PID_C003*' }
            Write-Host "$(Now) device still present after boot: $([bool]$still)"
            exit 0
        } elseif (-not $seenNotOk) {
            Write-Host "$(Now) device present but status $($dev.Status) (driver not bound yet?)"
            $seenNotOk = $true
        }
    }
    Start-Sleep -Milliseconds 150
}
Write-Host "$(Now) timeout - no usable device appeared"
exit 2
