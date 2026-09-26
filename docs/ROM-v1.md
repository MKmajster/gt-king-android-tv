# ROM v1 — GT-King PRO „Google TV skin" (2026-09-14)

Baza: stock Beelink ATV Android 9 (`galilei-userdebug 9 PPR1.180610.011 20220401 test-keys`), **stock `boot`** (sha1-zweryfikowany, bez Magiska — patrz niżej), `/system` z nakładkami `gtk-identity`, `gtk-identity-fp`, `gtk-look`, `gtk-hosts`, `gtk-launcherx` (Google TV Home jako priv-app — patrz `docs/GOOGLE-TV-HOME.md`) (oryginały plików nadpisanych przez nakładki leżą w `/data/local/gtk-backup/<id>/` na boxie) + apki użytkownika. Root: `adb root` (userdebug) + stock `/system/xbin/su`.

## Dlaczego bez Magiska (wariant B)

U-boot na tym boxie zawsze doklejał `skip_initramfs` do cmdline (ustawione na etapie kompilacji u-boota, nie do zmiany z poziomu Androida), a stock kernel to 32-bitowy skompresowany zImage bez ramdysku w `boot`. Magisk (patch LEGACYSAR) wymaga ramdysku do wstrzyknięcia się w proces bootu — bez niego patch nie ma czego łatać. Backup próby Magiska został zachowany w `backup/20260914-magisk/` (m.in. `boot-magisk.img`), ale nie jest używany.

Zamiast tego: **stock `boot` zostaje przywrócony i zweryfikowany sha1**, a wszystkie modyfikacje idą jako nakładki na `/system` przez `scripts/overlay.sh install|remove|list` (adb root + remount rw, `chcon`/`chmod` na miejscu, oryginały nadpisanych plików kopiowane do `/data/local/gtk-backup/<id>/` zanim cokolwiek zostanie nadpisane). System wraca do read-only po każdej operacji.

## Zainstalowane nakładki (na 2026-09-14)

- `gtk-identity` — property Android 14 identity (`ro.build.version.release` itp.) w `/system/build.prop`.
- `gtk-look` — wygenerowana animacja bootowania w stylu Google TV (bez fontów Google Sans — nie zostały dostarczone, więc nakładka fontów NIE jest częścią `gtk-look`).
- `gtk-hosts` — lista StevenBlack (adblock), 84959 linii w `/system/etc/hosts`.
- `gtk-identity-fp` — istnieje w repo (`overlays/gtk-identity-fp/`), **NIE jest zainstalowana** (opcjonalny certified fingerprint, do rozważenia po sprawdzeniu certyfikacji Play Store — patrz `HANDOFF.md` sekcja 6).

Launcher: **Projectivy** (`com.spocky.projengmenu`) ustawiony jako HOME, stock `com.google.android.tvlauncher` wyłączony (`pm disable-user`). LauncherX nie był testowany — brak APK-ów w `apps/launcherx/`.

Apki sideloadowane: Kodi 21.3 (armeabi-v7a), SmartTube 32.47 (`org.smarttube.stable`), Aerial Views 1.8.4 (ustawiony jako wygaszacz ekranu). Apki tylko-ze-Store (Plex, TiviMate, DRM Info) **nie są jeszcze zainstalowane** — to ręczny krok użytkownika (`scripts/apps.sh store` otwiera strony Play Store, instalacja pilotem).

## Backup ROM v1

`backup/20260914-rom-v1/` — 20 obrazów partycji + `SHA1SUMS` (sha1 każdego pliku zweryfikowany przeciw partycji na boxie w momencie zrzutu), `getprop.txt`, `dmesg.txt`, `packages.txt`, `packages-disabled.txt`, `cmdline.txt`, `partitions.txt`, `by-name.txt`, `config.gz`. `system.img` zawiera już wszystkie nakładki (`gtk-identity`, `gtk-look`, `gtk-hosts`) — to jest pełny, gotowy do przywrócenia obraz ROM v1, nie sam stock.

Użytkownik zrezygnował z kopiowania backupu na drugi nośnik — istnieje wyłącznie na tym Macu w `backup/20260914-rom-v1/` (oraz `backup/20260914-stock/` ze stockiem). To jedyna kopia; do rozważenia w przyszłości.

## Przywrócenie ROM v1 na tym samym boxie (po awarii /data lub eksperymentach)

1. `adb connect 192.168.0.100:5555` (ADB musi działać jako root — stock userdebug; `scripts/lib.sh:require_device` robi to automatycznie).
2. `scripts/restore.sh backup/20260914-rom-v1 boot system vendor product odm` — flashuje tylko partycje różne od tego, co już jest na boxie (porównanie po sha1), z guardem rozmiaru i weryfikacją sha1 po zapisie każdej partycji.
3. `adb -s 192.168.0.100:5555 reboot`. Nakładki siedzą w `system.img`, więc wracają razem z nim — nie trzeba osobno odtwarzać `gtk-identity`/`gtk-look`/`gtk-hosts`.
4. **Jeśli `/data` było czyszczone (factory reset / awaria)**: `/data/local/gtk-backup/` (oryginały plików spod nakładek) przepada razem z resztą `/data`. W takim wypadku:
   - `scripts/apps.sh install` (sideload Kodi/SmartTube/Aerial Views z `apps/*.apk`), potem `scripts/apps.sh store` dla apek tylko-ze-Store,
   - `scripts/launcher.sh projectivy`,
   - `scripts/debloat.sh disable`,
   - `scripts/screensaver.sh`,
   - Ponieważ `/data/local/gtk-backup/` przepadł, nakładek na `/system` **nie da się już zdjąć przez `overlay.sh remove`** (nie ma skąd wziąć oryginałów) — cofnięcie do czystego `/system` wtedy tylko przez pełne przywrócenie partycji `system` ze stocka: `scripts/restore.sh backup/20260914-stock system`.
5. `scripts/verify.sh` → oczekiwane `ALL OK`.

## Powrót do stocka

`scripts/restore.sh backup/20260914-stock system` (zdejmuje wszystkie nakładki, bo cała partycja `system` wraca do stanu ze stocka) — albo pełny powrót: `scripts/restore.sh backup/20260914-stock boot system vendor product odm recovery dtbo logo`.

**Nigdy nie flashować** (i `scripts/restore.sh` odmawia tego programowo — lista `FORBIDDEN` w skrypcie): `bootloader`, `tee`, `rpmb`, `cri_data`, `param`. To partycje bootloadera i strefy zaufanej (TEE) — flashowanie ich niesie realne ryzyko bricka lub utraty kluczy Widevine trzymanych w RPMB. `restore.sh` odmawia flashowania `env` (lista `FORBIDDEN`: bootloader, tee, rpmb, cri_data, param, env).

## Gdy ADB nie działa

Amlogic USB Burning Tool + oficjalny firmware Beelink GT-King PRO (`.img`). **Nie zaznaczać „Erase bootloader" / „Erase all"** — ten sam powód co wyżej (RPMB/keybox Widevine, bootloader).


## ROM v2 (2026-09-14 wieczór)
`backup/20260914-rom-v2/` — jak v1 + Google TV Home (`gtk-launcherx`), katniss 7.55, YouTube/Asystent włączone. Przywracanie identycznie jak v1 (`scripts/restore.sh backup/20260914-rom-v2 boot system vendor product odm`).
