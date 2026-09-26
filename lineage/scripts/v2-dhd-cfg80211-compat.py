#!/usr/bin/env python3
"""v2: make bcmdhd.101.10.591.x build against voodik's ODROID kernel, whose core is Linux 4.9 but whose
cfg80211/nl80211 is backported to the 4.17 level (cfg80211_roam_info, sched-scan reqid, timeout
reason, external_auth; no 4.18 bss_iter). The driver picks cfg80211 APIs with LINUX_VERSION_CODE
(= 4.9 here), which selects the old ones and does not compile.

In the driver's cfg80211 files every #if/#elif that compares LINUX_VERSION_CODE with a 4.10..4.17
version gets WL_CFG80211_VERSION_CODE instead (defined as 4.17 on the command line), UNLESS the
guarded code is a core-kernel API that the backport does not cover (netlink parsing, netdev
destructors, timers, kernel_read/write, ktime ...). Those keep LINUX_VERSION_CODE.
    python3 v2-dhd-cfg80211-compat.py <dhd source dir>
"""
import pathlib
import re
import sys

FILES = ["wl_cfg80211.c", "wl_cfg80211.h", "wl_cfgscan.c", "wl_cfgscan.h", "wl_cfgvif.c", "wl_cfgvif.h",
         "wl_cfgp2p.c", "wl_cfgp2p.h", "wl_cfgvendor.c", "wl_cfgvendor.h", "wl_cfgnan.c", "wl_android.c",
         "wldev_common.c", "dhd_cfg80211.c", "wl_cfg_btcoex.c"]
CORE = re.compile(r"nla_parse|nla_put|genl|netlink|needs_free_netdev|priv_destructor|destructor|"
                  r"timer_setup|from_timer|setup_timer|kernel_read|kernel_write|ktime|get_ds|access_ok|"
                  r"sched/signal|vfs_|skb_put_data|wakeup_source|rtnl_|dev_open|dev_close|__vfs")
VER = re.compile(r"LINUX_VERSION_CODE\s*(>=|<=|>|<|==)\s*KERNEL_VERSION\s*\(\s*4\s*,\s*(\d+)\s*,")


def main():
    root = pathlib.Path(sys.argv[1])
    total = kept = 0
    for name in FILES:
        p = root / name
        if not p.exists():
            continue
        lines = p.read_text(errors="surrogateescape").split("\n")
        changed = 0
        cont = False     # inside a backslash-continued #if/#elif
        for i, l in enumerate(lines):
            s = l.lstrip()
            is_cond = s.startswith("#if") or s.startswith("#elif") or cont
            cont = is_cond and l.rstrip().endswith("\\")
            if not is_cond or "LINUX_VERSION_CODE" not in l:
                continue
            m = VER.search(l)
            if not m or not 10 <= int(m.group(2)) <= 17:
                continue
            window = "\n".join(lines[i:i + 8])
            if CORE.search(window):
                kept += 1
                continue
            lines[i] = l.replace("LINUX_VERSION_CODE", "WL_CFG80211_VERSION_CODE")
            changed += 1
        if changed:
            p.write_text("\n".join(lines), errors="surrogateescape")
        total += changed
        print(f"{name}: {changed} guards -> WL_CFG80211_VERSION_CODE")
    print(f"total {total}, kept as core-kernel {kept}")


if __name__ == "__main__":
    main()
