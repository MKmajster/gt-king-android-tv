#!/usr/bin/env bash
# v2: galilei changes on top of voodik's kernel (commit 660a3bebdf92), as git branch "galilei-v2" in
# ~/v2/kernel-voodik. Only function bodies change - no exported prototypes - so the symbol CRCs stay
# identical and voodik's prebuilt modules (mali.ko r51p0, media) keep loading.
#   bash lineage/scripts/v2-kernel-patches.sh
#  1. eMMC partitions the Amlogic way. His ODROID build finds partitions with Hardkernel's MPT at
#     sector 1928 (block/partitions/mpt.c; `oem fdisk` layout); on the GT-King that sector is inside
#     the stock bootloader. Here, as in the v1 kernel: mmc_blk_probe calls aml_emmc_partition_ops(),
#     which reads the MPT the Burning Tool wrote to the reserved area from our DTB's partition table
#     (names -> /dev/block/<name>), and emmc_partitions.c takes its stock-Amlogic branches instead of
#     the CONFIG_ARCH_MESON64_ODROID_COMMON ones (reserved-area offset, byte sizes, emmc-only).
#  2. lineage/patches/kernel-meson-wdt-reload-before-reenable.patch (v1 fix).
#  3. SCPI: 2 s timeout on BL30 answers (his send_scpi_cmd waits forever; v1 has a timeout) - safety.
#  4. stmmac: unregister the static suspend_pm_nb before registering it again. THE boot hang of
#     M1..M1f (found 2026-09-26 with an IPI dump_stack of PID 1): dwmac-meson fails without a PHY,
#     dwmac-generic re-probes, the 2nd register_pm_notifier() self-loops the chain and the next
#     caller (mmc_add_host -> mmc_register_pm_notifier) spins forever in
#     blocking_notifier_chain_register. Same bug and fix as v1
#     (lineage/patches/kernel-stmmac-pm-notifier-double-register.patch; the context differs here).
#  5. hci_bcm: bcm_setup() returned bcm_request_irq()'s -ENODEV (no bcm platform device on a plain
#     HCI UART line discipline) -> hci0 stayed in HCI_SETUP, never initialised or announced to mgmt,
#     and the btlinux HAL waited forever (2026-09-26, AP6275S Bluetooth via btuart-attach).
#  6. suspend: Amlogic's suspend_prepare() blocks device probing before freezing tasks but only
#     suspend_finish()/dpm_complete() unblock it; an attempt aborted while freezing (pending wakeup,
#     i.e. every screen-off with Wi-Fi up) left all probing deferred until reboot - a USB gamepad
#     plugged in after the first standby never got a driver (2026-09-26).
set -euo pipefail
K=$HOME/v2/kernel-voodik
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/../patches" && pwd)"
cd "$K"
git -c advice.detachedHead=false checkout -q -B galilei-v2 660a3bebdf92
python3 - <<'EOF'
import pathlib
b = pathlib.Path("drivers/mmc/card/block.c")
s = b.read_text()
anchor = "\tif (mmc_add_disk(md))\n\t\tgoto out;\n\n\tlist_for_each_entry(part_md, &md->part, part) {"
assert s.count(anchor) == 1
s = s.replace(anchor, "\tif (mmc_add_disk(md))\n\t\tgoto out;\n\n#ifdef CONFIG_AMLOGIC_MMC\n"
              "\t/* galilei: Amlogic reserved-area partition table (as the stock kernel does) */\n"
              "\taml_emmc_partition_ops(card, md->disk);\n#endif\n\n"
              "\tlist_for_each_entry(part_md, &md->part, part) {")
b.write_text(s)
e = pathlib.Path("drivers/amlogic/mmc/emmc_partitions.c")
t = e.read_text()
n = t.count("CONFIG_ARCH_MESON64_ODROID_COMMON")
t = t.replace("CONFIG_ARCH_MESON64_ODROID_COMMON", "GALILEI_HARDKERNEL_PARTITIONS_DISABLED")
e.write_text(t)
print("block.c: aml_emmc_partition_ops call added; emmc_partitions.c:", n, "ODROID branches off")
EOF
python3 - <<'EOF'
import pathlib
# 3. SCPI (BL30 mailbox): his send_scpi_cmd() waits for BL30's answer forever; our v1 kernel uses a
#    timeout. Time out instead, like v1, and log the command (a BL30 that does not answer must not
#    hang the caller).
p = pathlib.Path("drivers/amlogic/mailbox/scpi_protocol.c")
s = p.read_text()
old = "\twait_for_completion(&scpi_buf->complete);\n\tstatus = *(u32 *)(data->rx_buf); /* read first word */\n"
new = ("\tif (!wait_for_completion_timeout(&scpi_buf->complete, msecs_to_jiffies(2000))) {\n"
       "\t\tpr_err(\"scpi: cmd 0x%x: no answer from BL30 in 2 s (galilei)\\n\", data->cmd);\n"
       "\t\tstatus = SCPI_ERR_TIMEOUT;\n\t\tgoto free_channel;\n\t}\n"
       "\tstatus = *(u32 *)(data->rx_buf); /* read first word */\n")
assert s.count(old) == 1, "scpi wait not found"
p.write_text(s.replace(old, new))
print("scpi_protocol.c: 2 s timeout on BL30 answers")
p = pathlib.Path("drivers/net/ethernet/stmicro/stmmac/stmmac_main.c")
s = p.read_text()
old = "\tresult = register_pm_notifier(&suspend_pm_nb);\n"
assert s.count(old) == 1, "stmmac register_pm_notifier"
s = s.replace(old, "\t/* galilei: a re-probe (dwmac-generic after dwmac-meson failed with no PHY) must not register\n"
              "\t * this static block twice - that self-loops the pm notifier chain and every later\n"
              "\t * register_pm_notifier() spins forever (PID 1 stuck in mmc_add_host at boot). */\n"
              "\tunregister_pm_notifier(&suspend_pm_nb);\n" + old)
p.write_text(s)
print("stmmac: unregister suspend_pm_nb before registering it")
p = pathlib.Path("drivers/bluetooth/hci_bcm.c")
s = p.read_text()
old = "\terr = bcm_request_irq(bcm);\n\tif (!err)\n\t\terr = bcm_setup_sleep(hu);\n\n\treturn err;\n"
assert s.count(old) == 1, "hci_bcm bcm_request_irq"
s = s.replace(old, "\t/* galilei: a plain HCI UART line discipline (btuart-attach) has no bcm platform device ->\n"
              "\t * bcm_request_irq() = -ENODEV. That only means no host-wake irq / sleep setup, not a failed\n"
              "\t * setup (upstream ignores it); returning it left hci0 in HCI_SETUP forever, never\n"
              "\t * initialised nor announced to mgmt, and the btlinux HAL waited for it endlessly. */\n"
              "\tif (!bcm_request_irq(bcm))\n\t\terr = bcm_setup_sleep(hu);\n\n\treturn err;\n")
p.write_text(s)
print("hci_bcm: bcm_request_irq() failure is not a setup failure")
p = pathlib.Path("kernel/power/suspend.c")
s = p.read_text()
old = "\tsuspend_stats.failed_freeze++;\n\tdpm_save_failed_step(SUSPEND_FREEZE);\n Finish:\n"
assert s.count(old) == 1, "suspend_prepare failed_freeze path"
s = s.replace(old, "\tsuspend_stats.failed_freeze++;\n\tdpm_save_failed_step(SUSPEND_FREEZE);\n"
              "#ifdef CONFIG_AMLOGIC_MODIFY\n"
              "\t/* galilei: device_block_probing() above is undone only by suspend_finish()/dpm_complete();\n"
              "\t * a suspend aborted while freezing tasks (pending wakeup - every attempt with Wi-Fi up)\n"
              "\t * left defer_all_probes set, so no device probed again until reboot (USB gamepads,\n"
              "\t * sticks, re-bound hubs: 'Unsupported device', bind -ENODEV). */\n"
              "\tdevice_unblock_probing();\n#endif\n Finish:\n")
p.write_text(s)
print("suspend: unblock probing when freezing tasks fails")
EOF
git apply --check "$P/kernel-meson-wdt-reload-before-reenable.patch" && git apply "$P/kernel-meson-wdt-reload-before-reenable.patch" \
    && echo "meson_wdt patch applied" || echo "meson_wdt patch does NOT apply - skipped"
git add -A
git -c user.name=MKmajster -c user.email=72458200+MKmajster@users.noreply.github.com commit -q -m "galilei v2: Amlogic eMMC partition table; SCPI timeout; stmmac pm notifier; meson_wdt; hci_bcm setup; suspend unblock probing"
git log --oneline -2
