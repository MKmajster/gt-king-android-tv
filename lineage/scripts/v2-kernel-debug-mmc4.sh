#!/usr/bin/env bash
# v2 debug commit 4: M1e showed PID 1 in state R (running - a loop that keeps scheduling, so neither
# the soft-lockup nor the hung-task detector fires); sched_show_task() of a running task is useless.
# The watcher now sends an IPI to the CPU that runs PID 1 and calls dump_stack() there, which
# unwinds through the interrupted code - the loop's function.
#   bash lineage/scripts/v2-kernel-debug-mmc4.sh
set -euo pipefail
cd "$HOME/v2/kernel-voodik"
git checkout -q galilei-v2
python3 - <<'EOF'
import pathlib
a = pathlib.Path("drivers/amlogic/mmc/aml_sd_emmc.c")
t = a.read_text()
old = ('\t\tif (t) {\n'
       '\t\t\tpr_emerg("galilei: ---- PID 1 (%s) state %ld ----\\n", t->comm, t->state);\n'
       '\t\t\tsched_show_task(t);\n'
       '\t\t}\n'
       '\t\trcu_read_unlock();')
assert t.count(old) == 1, "watcher body"
new = ('\t\tif (t) {\n'
       '\t\t\tint cpu = task_cpu(t);\n'
       '\t\t\tlong st = t->state;\n'
       '\t\t\tpr_emerg("galilei: ---- PID 1 (%s) state %ld on CPU%d ----\\n", t->comm, st, cpu);\n'
       '\t\t\trcu_read_unlock();\n'
       '\t\t\tif (st == TASK_RUNNING && cpu != raw_smp_processor_id())\n'
       '\t\t\t\tsmp_call_function_single(cpu, galilei_dump_here, NULL, 1);\n'
       '\t\t\tcontinue;\n'
       '\t\t}\n'
       '\t\trcu_read_unlock();')
t = t.replace(old, new)
anchor = "static int galilei_init_watch(void *unused)"
assert t.count(anchor) == 1
t = t.replace(anchor, ('static void galilei_dump_here(void *unused)\n{\n'
                       '\tpr_emerg("galilei: stack on CPU%d (current %s):\\n", raw_smp_processor_id(), current->comm);\n'
                       '\tdump_stack();\n}\n\n') + anchor)
t = t.replace("for (n = 0; n < 6; n++)", "for (n = 0; n < 5; n++)")
a.write_text(t)
print("IPI stack dump added")
EOF
git add -A
git -c user.name=galilei -c user.email=galilei@local commit -q -m "galilei v2 DEBUG 4: IPI dump_stack on the CPU running PID 1"
git log --oneline -1
