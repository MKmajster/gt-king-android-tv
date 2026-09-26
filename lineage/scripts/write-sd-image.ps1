# Write a raw bootloader image to a microSD card for the BootROM SD-boot test.
#   powershell -ExecutionPolicy Bypass -File lineage\scripts\write-sd-image.ps1 <image> [-Disk N] [-KeepMbr]
# Self-elevates (UAC prompt). Without -Disk it lists USB/SD disks and asks for the number.
# -KeepMbr: leave sector 0 (partition table) alone and write from sector 1 (where the BootROM reads
#   the bootloader); the card's partitions survive if they start at or after 4 MiB. Without it the
#   partition table is cleared and the whole image is written from sector 0 (card contents lost).
# Sectors outside mounted volumes can be written raw as administrator (removable media cannot be
# taken offline); the written range is read back and compared. Transcript: lineage/out/write-sd-image-<time>.log
param([Parameter(Mandatory=$true)][string]$Image, [int]$Disk = -1, [switch]$KeepMbr)
$Image = (Resolve-Path $Image).Path
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $args = "-NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`" `"$Image`""
    if ($Disk -ge 0) { $args += " -Disk $Disk" }
    if ($KeepMbr) { $args += " -KeepMbr" }
    Start-Process powershell -Verb RunAs -ArgumentList $args
    exit
}
Start-Transcript -Path (Join-Path $PSScriptRoot ("..\out\write-sd-image-" + (Get-Date -Format "HHmmss") + ".log")) | Out-Null
Write-Host "Image: $Image ($([math]::Round((Get-Item $Image).Length/1MB,1)) MiB)"
if ($Disk -lt 0) {
    Get-Disk | Where-Object { $_.BusType -eq 'USB' -or $_.BusType -eq 'SD' } | Format-Table Number, FriendlyName, BusType, @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}}, PartitionStyle -AutoSize
    $n = Read-Host "Disk number of the microSD card (anything else aborts)"
    if ($n -notmatch '^\d+$') { Write-Host "aborted"; exit 1 }
    $Disk = [int]$n
}
$d = Get-Disk -Number $Disk
if ($d.BusType -ne 'USB' -and $d.BusType -ne 'SD') { Write-Host "disk $Disk is not USB/SD - aborted"; exit 1 }
if ($d.Size -gt 256GB) { Write-Host "disk $Disk is larger than 256 GB - not a card, aborted"; exit 1 }
Write-Host "Target: disk $Disk $($d.FriendlyName) $([math]::Round($d.Size/1GB,1)) GB, KeepMbr=$KeepMbr"
Set-Disk -Number $Disk -IsReadOnly $false -ErrorAction SilentlyContinue
if (-not $KeepMbr) {
    Write-Host "Clearing partition table..."
    Clear-Disk -Number $Disk -RemoveData -RemoveOEM -Confirm:$false -ErrorAction SilentlyContinue
}
$start = 0
if ($KeepMbr) { $start = 512 }
$dev = "\\.\PhysicalDrive$Disk"
$fs = [System.IO.File]::Open($dev, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
$src = [System.IO.File]::OpenRead($Image)
$src.Position = $start; $fs.Position = $start
$buf = New-Object byte[] (1MB)
$total = 0
while (($r = $src.Read($buf, 0, $buf.Length)) -gt 0) {
    if ($r % 512 -ne 0) { $r = [int][math]::Ceiling($r / 512) * 512 }
    $fs.Write($buf, 0, $r); $total += $r
}
$fs.Flush(); $fs.Close(); $src.Close()
Write-Host "wrote $total bytes from offset $start"
$fs = [System.IO.File]::Open($dev, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
$fs.Position = $start
$chk = New-Object byte[] (2MB); $got = $fs.Read($chk, 0, $chk.Length); $fs.Close()
$src = [System.IO.File]::OpenRead($Image); $src.Position = $start; $ref = New-Object byte[] (2MB); $src.Read($ref, 0, $ref.Length) | Out-Null; $src.Close()
if ([System.Linq.Enumerable]::SequenceEqual($chk, $ref)) { Write-Host "OK: 2 MiB read back identical. Remove the card and put it in the box, then power-cycle." } else { Write-Host "MISMATCH on read-back - do not use this card." }
Stop-Transcript | Out-Null
