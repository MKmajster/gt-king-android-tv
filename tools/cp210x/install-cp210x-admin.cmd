@echo off
echo === Instalacja sterownika CP210x (Silicon Labs VCP 11.6.0) ===
cd /d "%~dp0"
pnputil /add-driver silabser.inf /install
echo.
echo === Ponowne skanowanie urzadzen ===
pnputil /scan-devices
echo.
echo === Stan urzadzenia CP2102 ===
powershell -NoProfile -Command "Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -like 'USB\VID_10C4&PID_EA60*' } | Select-Object Name,Status,ConfigManagerErrorCode | Format-List"
echo.
echo Gotowe. Okno zamknie sie za 8 s.
timeout /t 8 >nul
