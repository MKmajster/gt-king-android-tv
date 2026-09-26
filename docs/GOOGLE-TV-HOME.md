# Google TV Home (LauncherX) na GT-King PRO — co działa, co nie (stan 2026-09-14)

## Co zainstalowane
| Element | Wersja | Jak | Uwagi |
|---|---|---|---|
| Google TV Home `com.google.android.apps.tv.launcherx` | **1.0.436578635** (23.03.2022) | nakładka `gtk-launcherx` → `/system/priv-app/GoogleTVHome/` (APK + `lib/arm/*.so`) | ostatnia wersja z min API 28; nowsze wymagają Android 10 / 12L+. Jako priv-app dostaje `ACCESS_ALL_EPG_DATA` (bez tego zakładka Dom = „Błąd ładowania”). Odtworzenie: `scripts/build_launcherx.sh && scripts/overlay.sh install gtk-launcherx` |
| Google app for Android TV `com.google.android.katniss` | 7.55.87 (bundle: base + armeabi_v7a + en) | user-app (`adb install-multiple`) | Asystent/wyszukiwanie głosowe z pilota. W zakładce „Wyszukiwanie” launchera pokazuje „zaktualizuj Google TV Home” (niezgodność wersji) |
| HOME | `launcherx/.home.HomeActivity` | `scripts/launcher.sh launcherx` (stock `tvlauncher` wyłączony) | Projectivy zostaje jako zapas: `scripts/launcher.sh projectivy` |

## Co działa
Zakładki **Dom** (rząd „Twoje aplikacje”), **Aplikacje** (kategorie z Play), **Biblioteka**; profil/konto; uruchamianie apek; wygląd 1:1 Google TV.

## Co NIE działa i dlaczego (zweryfikowane)
- **Rekomendacje „Dla Ciebie” / rzędy treści na Dom** — puste (`EMPTY_TAB_LAYOUT`). Backend Google nie serwuje już klientów z 2022 (katniss 6.3 z tej epoki dostaje gRPC `UNAVAILABLE` z `AndroidTvChannelServer`). Nowsze klienty = min Android 10/12L+. Nie do obejścia na Androidzie 9.
- **Zakładka Wyszukiwanie w launcherze** — j.w. (katniss 7.55 żąda nowszego launchera; katniss 6.3 kręci spinner bez końca).
- **YouTube (oficjalny)** — „To urządzenie nie spełnia wymagań technicznych”: od 23.10.2025 Google blokuje YouTube na niecertyfikowanych boxach (polityka serwerowa; spoof fingerprintu nie pomaga). Używać **SmartTube** (zainstalowany).
- **TV Setup (`com.google.android.tungsten.setupwraith`)** — próbowane jako priv-app: przejmuje HOME (priority 4) i odpala OOBE Chromecasta (czarny ekran). Wycofane, nie instalować.
- Tryb „Tylko aplikacje” jest **wyłączony** (`AppsOnlyModeConfirmActivity` proponuje włączenie) — pusty Dom nie wynika z tego trybu.

## Diagnostyka
```bash
adb -s 192.168.0.100:5555 exec-out screencap -p > /tmp/tv.png        # podgląd ekranu TV
adb -s 192.168.0.100:5555 shell uiautomator dump /sdcard/ui.xml       # drzewo UI (teksty/przyciski)
adb -s 192.168.0.100:5555 shell "logcat -d | grep -E ' $(adb -s 192.168.0.100:5555 shell pidof com.google.android.apps.tv.launcherx) '"
```
