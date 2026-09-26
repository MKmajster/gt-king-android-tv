#!/usr/bin/env bash
# v2 debug commit 2 (on top of the first debug commit): M1c showed mmc_blk_probe of the eMMC finishing,
# then silence - mmc_add_host() never returns. Instrument the MMC core where it can block forever:
#  * __mmc_claim_host: every 2 s of waiting print who holds the host; mark the first runtime-PM gets;
#  * mmc_wait_for_req_done / mmc_wait_for_data_req_done: every 2 s of waiting print the command;
#  * mmc_attach_mmc: markers after mmc_add_card and after re-claiming the host.
# Behaviour is unchanged (waits still wait), only messages are added.
#   bash lineage/scripts/v2-kernel-debug-mmc2.sh
set -euo pipefail
cd "$HOME/v2/kernel-voodik"
git checkout -q galilei-v2
python3 - <<'EOF'
import pathlib
c = pathlib.Path("drivers/mmc/core/core.c")
s = c.read_text()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:60]
    s = s.replace(old, new)
rep("\t\tspin_unlock_irqrestore(&host->lock, flags);\n\t\tschedule();\n\t\tspin_lock_irqsave(&host->lock, flags);\n",
    "\t\tspin_unlock_irqrestore(&host->lock, flags);\n"
    "\t\tif (!schedule_timeout(2 * HZ))\n"
    "\t\t\tpr_emerg(\"galilei: %s claim by %s waits, held by %s (cnt %d)\\n\", mmc_hostname(host),\n"
    "\t\t\t\t current->comm, host->claimer ? host->claimer->comm : \"?\", host->claim_cnt);\n"
    "\t\tspin_lock_irqsave(&host->lock, flags);\n")
rep("\tif (pm)\n\t\tpm_runtime_get_sync(mmc_dev(host));\n\n\treturn stop;\n}\nEXPORT_SYMBOL(__mmc_claim_host);",
    "\tif (pm) {\n\t\tstatic int galilei_pm_marks;\n\t\tunsigned long t0 = jiffies;\n"
    "\t\tif (galilei_pm_marks < 12) {\n\t\t\tgalilei_pm_marks++;\n"
    "\t\t\tpr_emerg(\"galilei: %s pm get (%s)\\n\", mmc_hostname(host), current->comm);\n\t\t}\n"
    "\t\tpm_runtime_get_sync(mmc_dev(host));\n"
    "\t\tif (time_after(jiffies, t0 + HZ))\n"
    "\t\t\tpr_emerg(\"galilei: %s pm get took %u ms\\n\", mmc_hostname(host), jiffies_to_msecs(jiffies - t0));\n\t}\n\n"
    "\treturn stop;\n}\nEXPORT_SYMBOL(__mmc_claim_host);")
rep("\t\twait_event_interruptible(context_info->wait,\n\t\t\t\t(context_info->is_done_rcv ||\n\t\t\t\t context_info->is_new_req));\n",
    "\t\twhile (!wait_event_interruptible_timeout(context_info->wait,\n\t\t\t\t(context_info->is_done_rcv ||\n\t\t\t\t context_info->is_new_req), 2 * HZ))\n"
    "\t\t\tpr_emerg(\"galilei: %s async CMD%u arg 0x%x waiting > 2 s\\n\", mmc_hostname(host),\n"
    "\t\t\t\t mrq->cmd ? mrq->cmd->opcode : 0, mrq->cmd ? mrq->cmd->arg : 0);\n")
rep("\twhile (1) {\n\t\twait_for_completion(&mrq->completion);\n",
    "\twhile (1) {\n\t\twhile (!wait_for_completion_timeout(&mrq->completion, 2 * HZ))\n"
    "\t\t\tpr_emerg(\"galilei: %s CMD%u arg 0x%x waiting > 2 s\\n\", mmc_hostname(host),\n"
    "\t\t\t\t mrq->cmd ? mrq->cmd->opcode : 0, mrq->cmd ? mrq->cmd->arg : 0);\n")
c.write_text(s)
m = pathlib.Path("drivers/mmc/core/mmc.c")
t = m.read_text()
old = "\terr = mmc_add_card(host->card);\n\tif (err)\n\t\tgoto remove_card;\n\n\tmmc_claim_host(host);\n\treturn 0;\n"
assert t.count(old) == 1, "attach_mmc"
t = t.replace(old, "\terr = mmc_add_card(host->card);\n\tpr_emerg(\"galilei: %s mmc_add_card %d, re-claiming\\n\", mmc_hostname(host), err);\n"
              "\tif (err)\n\t\tgoto remove_card;\n\n\tmmc_claim_host(host);\n"
              "\tpr_emerg(\"galilei: %s re-claimed, attach done\\n\", mmc_hostname(host));\n\treturn 0;\n")
m.write_text(t)
print("mmc core instrumented")
EOF
git add -A
git -c user.name=galilei -c user.email=galilei@local commit -q -m "galilei v2 DEBUG 2: mmc core wait/claim markers"
git log --oneline -2
