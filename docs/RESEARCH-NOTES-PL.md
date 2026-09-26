# Beelink GT-King — własny system Android TV

Stan researchu: 2026-09. Katalog roboczy projektu.

## Sprzęt

- SoC: **Amlogic S922X** (rodzina G12B, 4×A73 + 2×A53), 4 GB DDR4, eMMC
- Stock: Android 9 (Pie). Urządzenie **dyskontynuowane** — oficjalnie nigdy nie było Android 10+
- Wi-Fi/BT: moduł Ampak/Broadcom (zależnie od rewizji płyty)

## Twarde fakty (zanim cokolwiek wgrasz)

1. **Backup eMMC to krok zero.** Klucze Widevine L1 i produkcja partycji TEE żyją w eMMC.
   Bez backupu możesz nieodwracalnie stracić L1 (Netflix/Prime HD już nigdy nie wrócą).
   Najprościej: boot z karty SD (CoreELEC/Armbian) → `ddbr` (backup/restore całego eMMC do pliku na SD/USB).
2. **Secure bootloader w późnych egzemplarzach.** Beelink dodał podpisany bootloader (bl32) w produkcji
   od firmware ~0529+. Egzemplarze z 2019 (wcześniejsze) flashują się swobodnie, późniejsze mogą
   odmówić bootowania starszych/custom obrazów Androida (bootloop). Karta SD (CoreELEC) działa zawsze.
3. **Widevine L1 ≠ custom ROM.** Każdy czysty AOSP/LineageOS port = zwykle Widevine **L3**
   → Netflix/Disney+/Prime tylko w SD. Netflix HD wymaga L1 **i** certyfikacji urządzenia
   (GT-King nawet na stocku nie ma Netflix HD/4K — XDA review to potwierdza).
4. Custom ROM ≠ gorsze kodeki: sprzętowe dekodowanie VPU, HDR10, passthrough HD-audio działają
   na buildach opartych o vendor Amlogic (kernel 4.9).

## Ścieżki (od najłatwiejszej do najtrudniejszej)

### Ścieżka A — firmware Android TV na bazie stocka (najbliżej „działa wszystko")
- **Alvatech Custom ROM** (Android TV 9, baza Beelink/Amlogic vendor) — Netflix działał,
  hw kodeki + DRM z vencora. Stan: stary (2019/2020), ale GT-King to jedyny sensowny
  „gotowy Android TV" dla tego boxa.
- Instalacja: USB Burning Tool (Amlogic) + obraz `.img`, tryb reset-pin (OTG port).
- Wada: Android 9 na zawsze, brak aktualizacji.
- Linki: film instruktażowy: https://www.youtube.com/watch?v=AVadnwGES1Q

### Ścieżka B — CoreELEC (nie Android, ale media-center „wszystko działa")
- Oficjalnie wspierany w obrazach **Amlogic-ng** (kernel mainline-ish 5.x, S922X OK).
- 4K, HDR, DV (częściowo), passthrough HD audio, Netflix/Kodi addony (L3/WV via inputstream).
- Instalacja na SD (zero ryzyka) albo `ceemmc` do eMMC.
- Wątek urządzenia: https://discourse.coreelec.org/t/s922x-bee-link-gt-king/5334
- Wiki: https://wiki.coreelec.org/coreelec:beelink

### Ścieżka C — własny build AOSP ze źródeł („własny system" dosłownie)
Trudna, ale wykonalna — GT-King dzieli SoC z płytami mającymi publiczne źródła:
- **Odroid N2/N2+** (S922X) — publiczne źródła Android (vendor kernel 4.9) od Hardkernel:
  https://forum.odroid.com/viewforum.php?f=178
- **Khadas VIM3** (A311D, ta sama rodzina G12B) — wspierany **bezpośrednio w AOSP** (codename `yukawa`):
  https://aospandaaos.github.io/device-vim3.html
- Mainline kernel ma DTS dla G12B (meson-g12b-*); port = nowy device tree dla GT-King
  (WiFi/BT moduł, IR, eMMC timing) + bootloader.
- Realistycznie: tygodnie pracy; DRM i tak tylko L3; dekodowanie wideo przez V4L2 stateless.
- Alternatywnie gotowiec: GloDroid (AOSP+mainline, głównie Allwinner/RPi — Amlogic przez własne porty):
  https://github.com/GloDroid

### Czego NIE wgrywać
- Oficjalnych buildów LineageOS 20/22 „for Amlogic" z XDA — **nie obejmują GT-King**
  (tylko urządzenia Google-certified: onn 4K, Dynalink, ADT-3, Chromecast, Odroid C4, BPI M5).
  Wgranie na GT-King = brick.

## Plan minimalny (kolejność)

1. Sprawdź rewizję/bootloader: wersja firmware w Settings → jeśli 0529+ → ostrożnie z flashowaniem Androida.
2. Zrób **pełny backup eMMC** (`ddbr` z CoreELEC/Armbian SD). Schowaj obraz w 2 miejscach.
3. Test CoreELEC z SD (bez ruszania eMMC) — sprawdź, czy box w ogóle Ci wystarczy jako Kodi box.
4. Decyzja: A (ATV 9 pod streaming/DRM) / B (CoreELEC) / C (własny AOSP — wtedy setup build hosta:
   Linux, ~400 GB dysku, 16+ GB RAM, repo/sync, port DT z Odroid N2).

## Linki zbiorcze

- Wątek XDA LOS Amlogic (co jest wspierane): https://xdaforums.com/t/official-lineageos-22-for-amlogic-gxl-gxm-g12a-sm1-ne-family-devices-android-tv-tablet.4649881/
- CoreELEC GT-King: https://discourse.coreelec.org/t/s922x-bee-link-gt-king/5334
- Armbian/Manjaro na GT-King (mainline): https://forum.manjaro.org/t/how-do-i-install-on-my-beelink-gt-king-sa9xhqcf50153/152645
- Review GT-King (Netflix/DRM kontekst): https://xdaforums.com/t/beelink-gt-king-review-the-new-king-of-tv-boxes.3947026/
- Beelink BBS (fw, Widevine): https://bbs.bee-link.com/d/6260-firmware-to-restore-widevine-l1-on-gt-king-pro
