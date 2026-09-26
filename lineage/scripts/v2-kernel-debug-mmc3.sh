#!/usr/bin/env bash
# v2 debug commit 3: M1d showed the eMMC fully attached (mmc_attach_mmc done), no MMC claim/request
# waits, yet mmc_add_host() never returned to meson_mmc_probe and PID 1 never left meson_mmc_init.
# A kthread started from the first meson_mmc_probe dumps PID 1's stack every 4 s (6 times) with
# sched_show_task(), whatever state it is in - the exact place it hangs.
#   bash lineage/scripts/v2-kernel-debug-mmc3.sh
set -euo pipefail
cd "$HOME/v2/kernel-voodik"
git checkout -q galilei-v2
python3 - <<'EOF'
import pathlib
a = pathlib.Path("drivers/amlogic/mmc/aml_sd_emmc.c")
t = a.read_text()
helper = '''
/* galilei v2 debug: dump PID 1 (kernel_init) every 4 s */
#include <linux/kthread.h>
#include <linux/sched.h>
#include <linux/delay.h>
static int galilei_init_watch(void *unused)
{
	int n;
	for (n = 0; n < 6; n++) {
		struct task_struct *t;
		msleep(4000);
		rcu_read_lock();
		t = find_task_by_vpid(1);
		if (t) {
			pr_emerg("galilei: ---- PID 1 (%s) state %ld ----\\n", t->comm, t->state);
			sched_show_task(t);
		}
		rcu_read_unlock();
	}
	return 0;
}
'''
anchor = "static int meson_mmc_probe(struct platform_device *pdev)\n{"
assert t.count(anchor) == 1
t = t.replace(anchor, helper + "\n" + anchor + "\n\tstatic bool galilei_watch_started;\n", 1)
# start the watcher at the top of the probe, after the local declarations: put it right before the
# first mmc_add_host marker (inside the probe, runs once)
m = "\t\tpr_emerg(\"galilei: %s mmc_add_host\\n\", dev_name(&pdev->dev));\n"
assert t.count(m) == 1
t = t.replace(m, "\t\tif (!galilei_watch_started) {\n\t\t\tgalilei_watch_started = true;\n"
              "\t\t\tkthread_run(galilei_init_watch, NULL, \"galilei_watch\");\n\t\t}\n" + m)
a.write_text(t)
print("PID 1 stack watcher added")
EOF
git add -A
git -c user.name=galilei -c user.email=galilei@local commit -q -m "galilei v2 DEBUG 3: dump PID 1 stack every 4 s"
git log --oneline -1
