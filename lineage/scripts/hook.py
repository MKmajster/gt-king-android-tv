"""The stock->galilei chainload hook for the SHARED eMMC u-boot env ('preboot' overrides the compiled
CONFIG_PREBOOT). One definition for catch-burn.py, chainload-env.py, serial-console.py, esp32-bridge.py.

    run upgrade_check; forceupdate; if store read bl33 0x1000000 0 0x140000; then dcache off; icache off; go 0x1000000; fi; run update

Design (2026-09-22, after the two failed flash attempts):
  * NO condition on ${aml_dt}: u-boot sets aml_dt only for a MULTI dtb in _aml_dtb (common/aml_dt.c ->
    checkhw); our package writes a SINGLE galilei dtb there, so ${aml_dt} expands to nothing and
    'test != x' (argc 3 < 4, common/cmd_test.c) is always false -> the 21.09 hook never chainloaded.
    The loop protection lives in the galilei u-boot instead: BL33 v3 board_late_init does
    setenv("preboot", CONFIG_PREBOOT) before main_loop, so it never runs this hook.
  * 'forceupdate' FIRST: the ADC pinhole key (SARADC ch2, held ~4 s at power-on) -> 'run update' ->
    USB burn mode in the STOCK u-boot, before anything of ours runs. This is the only physical way
    back into the box without UART: GPIOAO_3 has no switch on the GTKing-D4X16 V4.0 board, so the
    stock 'run upgrade_key' is useless and is not included.
  * 'run upgrade_check': upgrade_step=3 -> update (what 'adb reboot update' sets on stock).
  * 'run update' at the END is the fallback when 'store read bl33' fails (no bl33 partition / bad
    read): straight into a USB burn window (catch-burn.py), never a silent storeboot of our
    boot.img by the stock u-boot.
Every 'setenv pN ...' must stay < 64 bytes: the burn-mode TPL_CMD goes through EP0 in 64-byte packets.
2026-09-25: the hook is ALSO the compiled-in default `preboot` of the stock u-boot shipped in the
packages (patch-stock-bl33-env.py imports HOOK and pads it to the stock string's 147 bytes). The
USB Burning Tool ends every burn with a saveenv of the default env, so only a default hook survives
a flash. Observed: an SD card with aml_autoscript makes `forceupdate` report "press update key!"
and boot the card (CoreELEC dual boot as on stock); the card's own saveenv keeps the hook.
"""

PIECES = [
    "run upgrade_check; forceupdate;",
    "if store read bl33 0x1000000 0 0x140000; then",
    "dcache off; icache off; go 0x1000000; fi;",
    "run update",
]
HOOK = " ".join(PIECES)

# commands that build the hook from the pieces (hush expands $p1.. inside double quotes at setenv time)
SETENV_CMDS = [f"setenv p{i} '{p}'" for i, p in enumerate(PIECES, 1)] + [
    'setenv preboot "' + " ".join(f"$p{i}" for i in range(1, len(PIECES) + 1)) + '"',
] + [f"setenv p{i}" for i in range(1, len(PIECES) + 1)]

for _c in SETENV_CMDS:
    assert len(_c) + 1 <= 64, _c

if __name__ == "__main__":
    print(HOOK)
    for c in SETENV_CMDS:
        print(f"{len(c)+1:3d}  {c}")
