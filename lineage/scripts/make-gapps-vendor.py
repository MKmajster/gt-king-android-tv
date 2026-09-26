#!/usr/bin/env python3
"""Turn a MindTheGapps *-ATV zip into an inline vendor tree the LineageOS build can inherit.

    python3 make-gapps-vendor.py <MindTheGapps-15.0.0-arm-ATV-full-*.zip> <TOP>/vendor/mindthegapps-atv [<TOP>]

With <TOP> (or $TOP) given, soong's check_prebuilt_presigned_apk.py decides per APK whether
`skip_preprocessed_apk_checks` is needed (soong rejects the flag on clean APKs and the APK without it
otherwise).

Why: the box has no working USB gadget, so `adb sideload` in recovery is not an option and the
GApps have to be part of the image. The zip is just a `system/` tree (product/, system/,
system_ext/) plus an update-binary that copies it and, for the "full" variant, deletes the
no-GMS launcher/recommendations. We reproduce that with build modules:
  * every APK -> android_app_import (presigned, privileged for priv-app, product/system_ext
    placement, dex-preopt off, uses-libs checks off); TVLauncher overrides Catapult (the
    LineageOS TV launcher) so Home goes to Google's launcher, like the zip does;
  * runtime resource overlays (*/overlay/*.apk) -> BUILD_PREBUILT in overlay/Android.mk with
    LOCAL_MODULE_PATH=<partition>/overlay (android_app_import cannot install there and
    PRODUCT_COPY_FILES refuses APKs);
  * everything else (permissions/sysconfig xml, init rc) -> PRODUCT_COPY_FILES, plus generated
    privapp allowlists (gen-privapp-allowlist.py) because the zip's XMLs are incomplete.
The output dir is regenerated from scratch on every run; `gapps.mk` is what
lineage_galilei.mk includes (`-include vendor/mindthegapps-atv/gapps.mk`).
"""
import os
import shutil
import subprocess
import sys
import zipfile

PARTITION_FLAG = {"product": "product_specific: true", "system_ext": "system_ext_specific: true", "system": None}
COPY_OUT = {"product": "$(TARGET_COPY_OUT_PRODUCT)", "system_ext": "$(TARGET_COPY_OUT_SYSTEM_EXT)",
            "system": "$(TARGET_COPY_OUT_SYSTEM)"}
TARGET_OUT = {"product": "$(TARGET_OUT_PRODUCT)", "system_ext": "$(TARGET_OUT_SYSTEM_EXT)", "system": "$(TARGET_OUT)"}
OVERRIDES = {"TVLauncher": ["Catapult", "TVLauncherNoGMS"], "TVRecommendations": ["TVRecommendationsNoGMS"]}
NL = chr(10)


def needs_skip(top, apk, privileged):
    """soong refuses `skip_preprocessed_apk_checks` on an APK that passes its presigned checks and
    refuses the APK without it when it does not (compressed dex, alignment): ask the checker."""
    if not top:
        return True
    script = os.path.join(top, "build/soong/scripts/check_prebuilt_presigned_apk.py")
    aapt2 = os.path.join(top, "out/host/linux-x86/bin/aapt2")
    zipalign = os.path.join(top, "out/host/linux-x86/bin/zipalign")
    if not all(os.path.exists(x) for x in (script, aapt2, zipalign)):
        return True
    cmd = ["python3", script, "--aapt2", aapt2, "--zipalign", zipalign, "--preprocessed"]
    if privileged:
        cmd += ["--privileged", "--uncompress-priv-app-dex"]
    cmd += [apk, "/tmp/make-gapps-vendor-check.stamp"]
    return subprocess.run(cmd, capture_output=True).returncode != 0


def main():
    src, out = sys.argv[1], sys.argv[2]
    top = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("TOP", "")
    z = zipfile.ZipFile(src)
    if os.path.isdir(out):
        shutil.rmtree(out)
    prop = os.path.join(out, "proprietary")
    os.makedirs(prop)
    apks, overlays, copies = [], [], []
    for name in z.namelist():
        if not name.startswith("system/") or name.endswith("/") or "/addon.d/" in name:
            continue
        rel = name[len("system/"):]                     # product/priv-app/X/X.apk | system/app/... | system_ext/...
        # GoogleServicesFramework goes to /system/priv-app instead of /system_ext: the PackageManager
        # scans system before product, and the first package to declare an authority keeps it. GmsCore
        # Pano 23.48 enables its own GservicesProvider on API 35 (bool/platformIsAtLeastV) with GSF's
        # authority com.google.android.gsf.gservices; when it owns that authority its persistent process
        # queries itself from GmsApplication.attachBaseContext before the Chimera context exists and
        # dies with a NullPointerException in a loop (2026-09-25). With GSF scanned first, GmsCore's
        # provider is skipped ("name already used by com.google.android.gsf") and it reads Gservices
        # from GSF's process, as it does on Android 14.
        if rel.startswith("system_ext/priv-app/GoogleServicesFramework/"):
            rel = "system/" + rel[len("system_ext/"):]
        part, path = rel.split("/", 1)
        dst = os.path.join(prop, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(z.read(name))
        if rel.endswith(".apk") and "/overlay/" in rel:
            overlays.append((part, rel))
        elif rel.endswith(".apk"):
            apks.append((part, rel))
        else:
            copies.append((part, path, rel))
            # hidden-API allowlisting is only honoured from /system/etc/sysconfig on this platform
            # (product gets ALLOW_ALL only on older first-API devices) - GmsCore ran with policy
            # "enforced" and hundreds of reflection denials otherwise.
            if rel.endswith("sysconfig/google-hiddenapi-package-whitelist.xml") and part != "system":
                copies.append(("system", path, rel))

    # privapp allowlists: the MindTheGapps XMLs miss several signature|privileged permissions the
    # ATV apps request (READ_LOGS, DUMP, MANAGE_LOW_POWER_STANDBY, TURN_SCREEN_ON, ...); with
    # ro.control_privapp_permissions=enforce system_server then throws and reboots in a loop.
    # gen-privapp-allowlist.py writes complete per-partition XMLs into the proprietary tree.
    if top:
        gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen-privapp-allowlist.py")
        r = subprocess.run(["python3", gen, top, prop, prop], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            raise SystemExit("gen-privapp-allowlist.py failed: " + r.stderr)
        for part in ("product", "system_ext", "system"):
            rel = "%s/etc/permissions/privapp-permissions-galilei-%s.xml" % (part, part)
            if os.path.exists(os.path.join(prop, rel)):
                copies.append((part, rel.split("/", 1)[1], rel))

    names = []
    bp = ['// Generated by lineage/scripts/make-gapps-vendor.py from %s - do not edit.' % os.path.basename(src), '',
          'soong_namespace {', '}', '']
    for part, rel in apks:
        mod = rel.split("/")[-2]
        names.append(mod)
        lines = ['android_app_import {', '    name: "%s",' % mod, '    owner: "mindthegapps",',
                 '    apk: "proprietary/%s",' % rel, '    presigned: true,', '    preprocessed: true,']
        if needs_skip(top, os.path.join(prop, rel), "/priv-app/" in rel):
            lines.append('    skip_preprocessed_apk_checks: true,')
        lines += ['    enforce_uses_libs: false,', '    dex_preopt: {', '        enabled: false,', '    },']
        if "/priv-app/" in rel:
            lines.append('    privileged: true,')
        if PARTITION_FLAG[part]:
            lines.append('    %s,' % PARTITION_FLAG[part])
        if mod in OVERRIDES:
            lines.append('    overrides: [%s],' % ", ".join('"%s"' % o for o in OVERRIDES[mod]))
        lines.append('}')
        lines.append('')
        bp += lines
    open(os.path.join(out, "Android.bp"), "w").write(NL.join(bp))

    if overlays:
        ov = ['# Generated by lineage/scripts/make-gapps-vendor.py - runtime resource overlays.',
              'LOCAL_PATH := $(call my-dir)', '']
        for part, rel in overlays:
            mod = os.path.splitext(os.path.basename(rel))[0]
            names.append(mod)
            ov += ['include $(CLEAR_VARS)', 'LOCAL_MODULE := %s' % mod, 'LOCAL_MODULE_OWNER := mindthegapps',
                   'LOCAL_SRC_FILES := ../proprietary/%s' % rel, 'LOCAL_MODULE_CLASS := APPS',
                   'LOCAL_MODULE_SUFFIX := .apk', 'LOCAL_MODULE_TAGS := optional',
                   'LOCAL_CERTIFICATE := PRESIGNED', 'LOCAL_DEX_PREOPT := false',
                   'LOCAL_MODULE_PATH := %s/overlay' % TARGET_OUT[part], 'include $(BUILD_PREBUILT)', '']
        os.makedirs(os.path.join(out, "overlay"))
        open(os.path.join(out, "overlay", "Android.mk"), "w").write(NL.join(ov))

    mk = ['# Generated by lineage/scripts/make-gapps-vendor.py from %s - do not edit.' % os.path.basename(src),
          'PRODUCT_SOONG_NAMESPACES += vendor/mindthegapps-atv', '',
          'PRODUCT_PACKAGES += \\']
    mk += ['    %s \\' % n for n in names[:-1]] + ['    %s' % names[-1], '', 'PRODUCT_COPY_FILES += \\']
    entries = ['    vendor/mindthegapps-atv/proprietary/%s:%s/%s' % (rel, COPY_OUT[part], path) for part, path, rel in copies]
    mk += [e + ' \\' for e in entries[:-1]] + [entries[-1], '']
    open(os.path.join(out, "gapps.mk"), "w").write(NL.join(mk))
    print("gapps vendor tree: %d apks, %d overlays, %d copied files -> %s" % (len(apks), len(overlays), len(copies), out))


if __name__ == "__main__":
    main()
