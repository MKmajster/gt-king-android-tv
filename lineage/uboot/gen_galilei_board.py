#!/usr/bin/env python3
"""
Create the u-boot board "g12b_galilei_v1" (Beelink GT-King; the stock ROM calls itself "GTKing PRO") inside a
LineageOS hardware/amlogic/u-boot tree, as a derivative of the Amlogic W400
reference board (g12b_w400_v1) that the stock Beelink bootloader is based on.

Usage: gen_galilei_board.py <path/to/hardware/amlogic/u-boot>

Idempotent: re-running regenerates the galilei files from the w400 ones and
leaves an already-patched board/amlogic/Kconfig alone.

Changes vs. w400 (mirroring what LineageOS did for radxa02pro):
  * HDMI box, no LCD panel: outputmode=1080p60hz, CONFIG_AML_LCD* off,
    no vout2/dual-logo/Dolby-Vision logo path in init_display
  * CEC OSD name "GT-King"
  * aml_dt=g12b_s922x_galilei (single DTB, checkhw returns the same name)
  * 'forceupdate' (ADC pinhole key held ~4 s at power-on -> USB burn mode) stays in
    CONFIG_PREBOOT: the GTKing-D4X16 board has no switch on GPIOAO_3, the pinhole is the
    only physical escape hatch, so it must work here as well as in the stock u-boot
    (recovery_key on GPIOAO_3 is only defined as an env var, never run)
  * BL33 v4 (2026-09-24): CONFIG_GALILEI_FIXED_BOOTENV - common/main.c runs the compiled
    CONFIG_PREBOOT and common/autoboot.c the compiled CONFIG_BOOTCOMMAND ("run storeboot")
    instead of the env variables. The eMMC env is SHARED with the stock u-boot: its 'preboot'
    is the stock->galilei chainload hook (must never run here and must never be replaced,
    because this u-boot does saveenv on its own, e.g. cmd_hdmitx do_hpd_detect with no sink,
    which with v3's RAM setenv("preboot", CONFIG_PREBOOT) wiped the hook from the eMMC), and
    its 'bootcmd' starts with ddr_auto_fast_boot_check, which in this u-boot rewrites the DDR
    parameters and resets the box every boot (never reaching the kernel).
  * no ethernet in u-boot (CONFIG_ETHERNET_NONE)
  * CONFIG_AML_SIGNED_UBOOT 0 + CONFIG_SKIP_KERNEL_DTB_SECBOOT_CHECK
"""
import os
import re
import shutil
import sys

W400 = "g12b_w400_v1"
GAL = "g12b_galilei_v1"
DT_ID = "g12b_s922x_galilei"


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def replace_once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        die("%s: expected exactly one match for %r, found %d" % (what, old[:60], n))
    return text.replace(old, new)


def gen_header(src, dst):
    t = open(src, encoding="utf-8", errors="surrogateescape").read()
    t = replace_once(t, "#ifndef __G12B_W400_V1_H__\n#define __G12B_W400_V1_H__",
                     "#ifndef __G12B_GALILEI_V1_H__\n#define __G12B_GALILEI_V1_H__", "guard")
    t = replace_once(t, '#define CONFIG_CEC_OSD_NAME\t\t"AML_TV"',
                     '#define CONFIG_CEC_OSD_NAME\t\t"GT-King"', "cec name")
    t = replace_once(t, '"panel_type=lcd_2\\0"', '"panel_type=lcd_1\\0"', "panel_type")
    t = replace_once(t, '"outputmode=panel\\0"', '"outputmode=1080p60hz\\0"', "outputmode")
    t = replace_once(t, '"fs_type=""rootfstype=ramfs""\\0"\\\n',
                     '"fs_type=""rootfstype=ramfs""\\0"\\\n'
                     '        "aml_dt=' + DT_ID + '\\0"\\\n', "aml_dt env")
    t = replace_once(t, " vout2=${outputmode2},enable", "", "vout2 in storeargs")
    t = replace_once(t,
                     '"hdmitx hpd;hdmitx get_preferred_mode;hdmitx get_parse_edid;dovi process;osd dual_logo;dovi set;dovi pkg;vpp hdrpkt;"',
                     '"hdmitx hpd;hdmitx get_preferred_mode;hdmitx get_parse_edid;setenv dolby_status 0;setenv dolby_vision_on 0;osd open;osd clear;imgread pic logo bootup $loadaddr;bmp display $bootup_offset;bmp scale;vout output ${outputmode};vpp hdrpkt;"',
                     "init_display")
    t = replace_once(t, '\t"irremote_update="\\\n',
                     '        "recovery_key="\\\n'
                     '            "if gpio input GPIOAO_3; then "\\\n'
                     '                "echo detect recovery key; run recovery_from_flash;"\\\n'
                     '            "fi;"\\\n'
                     '            "\\0"\\\n'
                     '\t"irremote_update="\\\n', "recovery_key env")
    # 'forceupdate;' (pinhole ADC key) is deliberately kept in CONFIG_PREBOOT, see the module docstring
    t = replace_once(t, "#if defined(CONFIG_AML_HDMITX20)\n#define CONFIG_AML_DOLBY 1\n#endif\n", "", "dolby")
    t = replace_once(t, "#define CONFIG_AML_LCD    1\n#define CONFIG_AML_LCD_TABLET 1\n#define CONFIG_AML_LCD_EXTERN 1\n",
                     "// #define CONFIG_AML_LCD    1\n// #define CONFIG_AML_LCD_TABLET 1\n// #define CONFIG_AML_LCD_EXTERN 1\n", "lcd")
    t = replace_once(t, "#define CONFIG_AML_CRYPTO_UBOOT   1\n",
                     "#define CONFIG_AML_CRYPTO_UBOOT   1\n\n#define CONFIG_AML_SIGNED_UBOOT   0\n", "signed uboot")
    t = replace_once(t, '#define CONFIG_BOOTCOMMAND "run storeboot"\n',
                     '#define CONFIG_BOOTCOMMAND "run storeboot"\n'
                     '/* galilei BL33 v4: run the compiled CONFIG_PREBOOT/CONFIG_BOOTCOMMAND, never the shared-env ones */\n'
                     '#define CONFIG_GALILEI_FIXED_BOOTENV 1\n', "fixed bootenv switch")
    t = replace_once(t, "//#define CONFIG_AML_CRYPTO_IMG       1\n",
                     "//#define CONFIG_AML_CRYPTO_IMG       1\n#define CONFIG_SKIP_KERNEL_DTB_SECBOOT_CHECK\n", "secboot check")
    t = replace_once(t, "#undef CONFIG_ETHERNET_NONE\n#define ETHERNET_INTERNAL_PHY\n#undef ETHERNET_EXTERNAL_PHY\n",
                     "#define CONFIG_ETHERNET_NONE\n#undef ETHERNET_INTERNAL_PHY\n#undef ETHERNET_EXTERNAL_PHY\n", "ethernet")
    t = t.replace("board/amlogic/g12b_w400_v1", "board/amlogic/" + GAL)
    open(dst, "w", encoding="utf-8", errors="surrogateescape").write(t)


def gen_board_c(src, dst):
    t = open(src, encoding="utf-8", errors="surrogateescape").read()
    t = t.replace("board/amlogic/g12b_w400_v1/g12b_w400_v1.c", "board/amlogic/%s/%s.c" % (GAL, GAL))
    t = replace_once(t, 'strcpy(loc_name, "g12b_w400_a\\0");', 'strcpy(loc_name, "%s\\0");' % DT_ID, "checkhw revA")
    t = replace_once(t, 'strcpy(loc_name, "g12b_w400_b\\0");', 'strcpy(loc_name, "%s\\0");' % DT_ID, "checkhw revB")
    t = replace_once(t, 'strcpy(loc_name, "g12b_w400_unsupport\\0");', 'strcpy(loc_name, "%s\\0");' % DT_ID, "checkhw default")
    # GPIOZ_8 is not an LCD power enable on this box; do not touch it
    t = replace_once(t, "//enable Lcd VCC\nenableLcdVcc();\n", "", "enableLcdVcc call")
    # BL33 v4: the env 'preboot' (chainload hook in the shared eMMC env) is left untouched; common/main.c
    # and common/autoboot.c run the compiled CONFIG_PREBOOT / CONFIG_BOOTCOMMAND instead (patch_common).
    # v3 did setenv("preboot", CONFIG_PREBOOT) here (RAM), and the first saveenv of this u-boot wrote
    # that over the hook in the eMMC.
    t = replace_once(t, "int board_late_init(void)\n{\n\tTE(__func__);\n",
                     "int board_late_init(void)\n{\n\tTE(__func__);\n"
                     "\t/* galilei BL33 v4: env preboot/bootcmd are ignored (CONFIG_GALILEI_FIXED_BOOTENV), nothing to replace here */\n",
                     "board_late_init v4 marker")
    open(dst, "w", encoding="utf-8", errors="surrogateescape").write(t)


def gen_board_dir(uboot):
    src = os.path.join(uboot, "board/amlogic", W400)
    dst = os.path.join(uboot, "board/amlogic", GAL)
    if not os.path.isdir(src):
        die("missing " + src)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    os.remove(os.path.join(dst, W400 + ".c"))
    gen_board_c(os.path.join(src, W400 + ".c"), os.path.join(dst, GAL + ".c"))
    k = os.path.join(dst, "Kconfig")
    t = open(k).read()
    t = replace_once(t, 'default "g12b_w400_v1"\n\nconfig SYS_VENDOR', 'default "%s"\n\nconfig SYS_VENDOR' % GAL, "SYS_BOARD")
    t = replace_once(t, 'config SYS_CONFIG_NAME\n\tdefault "g12b_w400_v1"', 'config SYS_CONFIG_NAME\n\tdefault "%s"' % GAL, "SYS_CONFIG_NAME")
    open(k, "w").write(t)
    for f in os.listdir(dst):
        p = os.path.join(dst, f)
        if os.path.isfile(p) and f.endswith((".c", ".h")):
            t = open(p, encoding="utf-8", errors="surrogateescape").read()
            t2 = t.replace("board/amlogic/g12b_w400_v1/", "board/amlogic/%s/" % GAL)
            if t2 != t:
                open(p, "w", encoding="utf-8", errors="surrogateescape").write(t2)


def gen_configs(uboot):
    gen_header(os.path.join(uboot, "board/amlogic/configs", W400 + ".h"),
               os.path.join(uboot, "board/amlogic/configs", GAL + ".h"))
    src = os.path.join(uboot, "board/amlogic/defconfigs", W400 + "_defconfig")
    dst = os.path.join(uboot, "board/amlogic/defconfigs", GAL + "_defconfig")
    t = open(src).read()
    t = replace_once(t, "CONFIG_G12B_W400_V1=y", "CONFIG_G12B_GALILEI_V1=y", "defconfig")
    open(dst, "w").write(t)


def patch_kconfig(uboot):
    k = os.path.join(uboot, "board/amlogic/Kconfig")
    t = open(k).read()
    if "G12B_GALILEI_V1" in t:
        print("board/amlogic/Kconfig already patched")
        return
    t = replace_once(t,
                     'config G12B_W400_V1\n\tbool "Support amlogic g12b w400 v1 board"\n\tdefault n\n',
                     'config G12B_W400_V1\n\tbool "Support amlogic g12b w400 v1 board"\n\tdefault n\n\n'
                     'config G12B_GALILEI_V1\n\tbool "Support Beelink GT-King (galilei, g12b/s922x) board"\n\tdefault n\n',
                     "Kconfig choice")
    t = replace_once(t,
                     'if G12B_W400_V1\nsource "board/amlogic/g12b_w400_v1/Kconfig"\nendif\n',
                     'if G12B_W400_V1\nsource "board/amlogic/g12b_w400_v1/Kconfig"\nendif\n\n'
                     'if G12B_GALILEI_V1\nsource "board/amlogic/g12b_galilei_v1/Kconfig"\nendif\n',
                     "Kconfig source")
    open(k, "w").write(t)


def patch_common(uboot):
    """BL33 v4: common/main.c and common/autoboot.c use the compiled CONFIG_PREBOOT / CONFIG_BOOTCOMMAND
    when CONFIG_GALILEI_FIXED_BOOTENV is defined (galilei config header). Idempotent."""
    for rel, old, new in (
        ("common/main.c",
         '\tp = getenv("preboot");\n',
         '#ifdef CONFIG_GALILEI_FIXED_BOOTENV\n'
         '\tp = CONFIG_PREBOOT;\t/* galilei: the shared eMMC env preboot is the stock->galilei chainload hook; never run it here */\n'
         '#else\n'
         '\tp = getenv("preboot");\n'
         '#endif\n'),
        ("common/autoboot.c",
         '#endif /* CONFIG_BOOTCOUNT_LIMIT */\n\t\ts = getenv("bootcmd");\n',
         '#endif /* CONFIG_BOOTCOUNT_LIMIT */\n'
         '#ifdef CONFIG_GALILEI_FIXED_BOOTENV\n'
         '\t\ts = CONFIG_BOOTCOMMAND;\t/* galilei: the shared env bootcmd starts with ddr_auto_fast_boot_check (DDR rewrite + reset here) */\n'
         '#else\n'
         '\t\ts = getenv("bootcmd");\n'
         '#endif\n'),
    ):
        path = os.path.join(uboot, rel)
        t = open(path, encoding="utf-8", errors="surrogateescape").read()
        if "CONFIG_GALILEI_FIXED_BOOTENV" in t:
            print(rel + " already patched")
            continue
        t = replace_once(t, old, new, rel)
        open(path, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("patched " + rel)


def main():
    if len(sys.argv) != 2:
        die("usage: gen_galilei_board.py <u-boot dir>")
    uboot = sys.argv[1]
    if not os.path.isfile(os.path.join(uboot, "board/amlogic/Kconfig")):
        die("not an amlogic u-boot tree: " + uboot)
    gen_board_dir(uboot)
    gen_configs(uboot)
    patch_kconfig(uboot)
    patch_common(uboot)
    print("generated board %s in %s" % (GAL, uboot))


if __name__ == "__main__":
    main()
