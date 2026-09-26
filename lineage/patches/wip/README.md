# Work in progress — not applied by setup-tree.sh

## kernel-hdmitx-quiesce-hpd-irq-across-resume.patch (2026-09-25, night)

The LineageOS 4.9.337 `hdmitx` driver locks the whole SoC up on the GT-King when it comes back
from early-suspend with a sink connected (watchdog reboot ~10 s later). The path is exercised by
every screen-off: the Lineage power HAL maps the INTERACTIVE hint to
`/sys/power/early_suspend_trigger`, and the kernel PM notifier runs the same handlers on a real
suspend. Ten iterations (pstore/ramoops after each watchdog reset) narrowed it down but did not
fix it:

| iteration | change | result |
|---|---|---|
| v1 | mask the HPD irq + cancel plug workers from early_suspend to the end of late_resume | still halts at the end of the resume EDID read |
| v2 | skip the EDID re-read in late_resume | late_resume completes ("late_resume: done"), halt follows within ms; no kernel line after it |
| v3 | keep EDID across sleep, clear stale TOP irq status before enable_irq | halt right after `hw_reset_dbg` |
| v4 | drop `hw_reset_dbg()` from HDMITX_LATE_RESUME, HDCP22 register only when hdcp_mode==2 | halt after the hw op |
| v5 | no HDCP2.2 susflag SMC (0x8200008a) into BL31 | halt after the hw op |
| v6 | no HDCP22 register access in the irq handler at all, markers | last line "re-arming hpd irq", no handler entry line |
| — | same with systemcontrol stopped (kernel-only path) | halt at the same place |

Facts: the halt is a hard stop of all CPUs (pstore console stops mid-sequence, no panic), it
happens with a DVI-class sink (ViewSonic VG2239, no HDMI VSDB) — the one run that got past this
point had the EDID cleared and the driver in "HDMI sink" mode at 720p; with no sink at all the
original code died in `hw_reset_dbg` on the pending irq (that part is fixed by v1/v4). Not tested:
a real HDMI TV. Suspects left: the TOP irq unmask / first TOP register access after a DVI-mode
resume, or something asynchronous started by the mode set (vsync path). The device ships with
the early-suspend path disabled instead (galilei `powerhint.json` without the INTERACTIVE action,
`init.galilei.rc` wakelock) — screen-off leaves HDMI up with a black frame, wake is instant.

Tools that made the iterations cheap: `lineage/scripts/kernel-quick.sh` (incremental kernel +
boot.img repack, 3 minutes), pstore (`/sys/fs/pstore/console-ramoops-0` survives the watchdog
reset), `logcat -L` for the last userspace lines, `echo 1/0 > /sys/power/early_suspend_trigger`
with a kernel wakelock held as the reproducer.
