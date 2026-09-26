# Publishing checklist (GitHub + XDA)

Everything below is run by the maintainer; nothing here is automated on purpose.

## 1. Repository

The public repository is a clean export (no working notes, local paths or build-host names), not
this working tree:

```
py -3 lineage/scripts/export-public-repo.py ..\gt-king-android-tv     # must end with "scan clean"
cd ..\gt-king-android-tv
git init -b main
git config user.name  MKmajster
git config user.email 72458200+MKmajster@users.noreply.github.com
git add -A
git commit -m "LineageOS 22.2 (v1) and 64-bit Android 15 TV (v2) for the Beelink GT-King"
git remote add origin https://github.com/MKmajster/gt-king-android-tv.git
git push -u origin main
```

Check on GitHub that `README.md` renders, `LICENSE` is Apache-2.0 and `docs/release/INSTALL.md` is
linked from the README.

## 2. GitHub release

1. `bash lineage/scripts/make-release-archives.sh` → `lineage/out/release/`.
2. Releases → *Draft a new release* → tag `2026-09-26`, title "Android 15 TV for Beelink GT-King —
   v1 (LineageOS 22.2) + v2 (64-bit)".
3. Body: `docs/release/RELEASE-NOTES.md`.
4. Attach the three `.7z` files from `v1/` (GApps), `v2/`, `stock/` plus `SHA256SUMS.txt` and `INSTALL.md`.
   Every archive is under GitHub's 2 GiB per-asset limit (the sparse images compress to 28–35 %);
   anything bigger would be split into `.7z.001`, `.7z.002` by the script.
5. Publish.

## 3. XDA thread

1. Forum: Android TV → *Android Stick & Console AMLogic based Computers*.
2. Prefix `ROM` (if the forum offers prefixes), title:
   `[ROM][Android 15][UNOFFICIAL][S922X] LineageOS 22.2 & 64-bit Android TV for Beelink GT-King (galilei)`
3. Body: `docs/release/XDA-thread.bbcode` — switch the editor to BBCode mode (the `[ ]` button)
   before pasting. The links point to `github.com/MKmajster/gt-king-android-tv`; change them if
   the repository lives elsewhere.
4. Screenshots: Android TV home, Settings → About, a PS2/PSP game.
5. Tags: `beelink`, `gt-king`, `s922x`, `amlogic`, `lineageos`, `android tv`, `android 15`.
6. Subscribe to the thread; the first questions will be about Ethernet (untested) and the UART
   fallback — both are covered in INSTALL.md.

XDA requires the kernel source for every ROM (GPL): the thread links LineageOS's
`android_kernel_amlogic_linux-4.9` (lineage-22.2) and voodik's `android_kernel_voodik_odroidg12`
(commit 660a3bebdf92) plus `lineage/patches/` of this repository — keep those links working.

## voodik (v2 base)

His sources are public on GitHub (github.com/voodik — kernel `android_kernel_voodik_odroidg12`
GPL-2.0, framework/HAL forks Apache-2.0), so the open-source part of v2 may be redistributed with
credit, links and license notices. The images also carry closed binaries (Mali r51p0 userspace,
Amlogic HALs, Google apps) — same status as the ADT-3 blobs and MindTheGapps in v1 and as his own
public downloads. Credit him prominently and link his download page; a courtesy note to him (ODROID
forum) is good form, not a requirement.

## After publishing

- Phase 2 ideas: deep sleep with a fixed hdmitx resume (v2: deep sleep is aborted by Wi-Fi
  wakeups, no hang), Ethernet report from a box with a working PHY.
