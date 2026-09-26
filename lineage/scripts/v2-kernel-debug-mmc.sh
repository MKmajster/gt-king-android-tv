#!/usr/bin/env bash
# v2 debug commit on top of galilei-v2 (~/v2/kernel-voodik): the kernel hangs inside meson_mmc_init
# after the eMMC partition table was read (all DT variants: without SDIO, without SD, both).
#  * mmc_blk_probe: do not add the boot0/boot1/rpmb disks (Android does not use them; adding them
#    scans their partitions = eMMC partition switch + reads) - likely fix;
#  * pr_emerg markers around every step that follows, so a single boot shows where it stops.
#   bash lineage/scripts/v2-kernel-debug-mmc.sh
set -euo pipefail
cd "$HOME/v2/kernel-voodik"
git checkout -q galilei-v2
python3 - <<'EOF'
import pathlib
b = pathlib.Path("drivers/mmc/card/block.c")
s = b.read_text()
old = "\tlist_for_each_entry(part_md, &md->part, part) {\n\t\tif (mmc_add_disk(part_md))\n\t\t\tgoto out;\n\t}\n\n\tpm_runtime_set_autosuspend_delay(&card->dev, 3000);"
new = ("\tlist_for_each_entry(part_md, &md->part, part) {\n"
       "\t\tpr_emerg(\"galilei: %s area 0x%x\\n\", part_md->disk->disk_name, part_md->area_type);\n"
       "\t\t/* galilei v2: boot0/boot1/rpmb are not used by Android; adding them hung the probe */\n"
       "\t\tif (part_md->area_type & (MMC_BLK_DATA_AREA_BOOT | MMC_BLK_DATA_AREA_RPMB))\n"
       "\t\t\tcontinue;\n"
       "\t\tif (mmc_add_disk(part_md))\n\t\t\tgoto out;\n\t}\n"
       "\tpr_emerg(\"galilei: mmc_blk_probe %s done\\n\", md->disk->disk_name);\n\n"
       "\tpm_runtime_set_autosuspend_delay(&card->dev, 3000);")
assert s.count(old) == 1, "block.c loop"
s = s.replace(old, new)
old2 = "#ifdef CONFIG_AMLOGIC_MMC\n\t/* galilei: Amlogic reserved-area partition table (as the stock kernel does) */\n\taml_emmc_partition_ops(card, md->disk);\n#endif\n"
new2 = old2 + "\tpr_emerg(\"galilei: after aml_emmc_partition_ops\\n\");\n"
assert s.count(old2) == 1
s = s.replace(old2, new2)
b.write_text(s)

a = pathlib.Path("drivers/amlogic/mmc/aml_sd_emmc.c")
t = a.read_text()
old3 = "\t\tret = mmc_add_host(mmc);\n"
assert t.count(old3) == 1, "mmc_add_host"
t = t.replace(old3, "\t\tpr_emerg(\"galilei: %s mmc_add_host\\n\", dev_name(&pdev->dev));\n" + old3 +
              "\t\tpr_emerg(\"galilei: %s mmc_add_host returned %d\\n\", dev_name(&pdev->dev), ret);\n")
old4 = '\tpr_info("%s() : success!\\n", __func__);\n'
assert t.count(old4) == 1, "success"
t = t.replace(old4, '\tpr_emerg("galilei: %s probe success\\n", dev_name(&pdev->dev));\n' + old4)
a.write_text(t)
print("debug markers + boot/rpmb skip added")
EOF
git add -A
git -c user.name=galilei -c user.email=galilei@local commit -q -m "galilei v2 DEBUG: skip boot0/boot1/rpmb disks; pr_emerg markers in mmc probe"
git log --oneline -3
