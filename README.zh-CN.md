# Beelink GT-King 的 Android 15 TV — `galilei`

[English](README.md) · [Polski](README.pl.md) · **简体中文**

Beelink GT-King（Amlogic **S922X**，4×Cortex-A73 @2.2 GHz + 2×A53，Mali-G52，4 GB LPDDR4，
64 GB eMMC，AP6275S Wi-Fi 5/蓝牙 5）从未获得过比 Android 9 更新的系统——无论是 Beelink 官方，
还是基于原厂固件的社区 ROM。本仓库是在这台盒子上完整移植 **Android 15（Android TV 版）** 的全部
内容：设备树、内核修复、引导加载链、刷机包、过程中使用的工具，以及每一条走不通的路的记录。

两个版本，相同的引导加载链，相同的刷机步骤：

| | **v1** — LineageOS 22.2 | **v2** — 64 位 |
|---|---|---|
| 用户空间 | 32 位（armeabi-v7a），与原厂固件相同 | **arm64 + arm** |
| 基础 | 使用本设备树从源码编译的 LineageOS 22.2 | voodik 为 ODROID-N2（同为 S922X）制作的 LineageOS 22.1 ATV + GT-King 的内核、DTB 和 vendor 修复 |
| GPU 驱动 | Mali r32p1（32 位） | Mali r51p0，Vulkan 1.3，GLES 3.2 |
| Google 应用 | 已包含（MindTheGapps for Android TV） | 已包含 |
| 适合 | 简洁、轻量的 Android TV | 模拟器（PS2、GameCube/Wii 需要 64 位） |

下载：[GitHub Releases](https://github.com/MKmajster/gt-king-android-tv/releases/latest) ·
刷机说明：[`docs/release/INSTALL.md`](docs/release/INSTALL.md)（英文） ·
更新说明与校验和：[`docs/release/RELEASE-NOTES.md`](docs/release/RELEASE-NOTES.md) ·
讨论与支持：[XDA 帖子](https://xdaforums.com/t/rom-android-15-unofficial-s922x-lineageos-22-2-64-bit-android-tv-for-beelink-gt-king-galilei.4802970/)

## 截图

| | |
|---|---|
| ![Android TV 主屏幕](docs/screenshots/home.png) | ![关于：Android 15，内核 4.9.337](docs/screenshots/about.png) |
| ![PlayStation 2：战神（ARMSX2，16:9）](docs/screenshots/ps2.jpg) | ![PSP：战神：斯巴达之魂（PPSSPP Vulkan 2x）](docs/screenshots/psp.jpg) |
| ![PlayStation：古惑狼 3（SwanStation 5x = 1080p）](docs/screenshots/psx.jpg) | v2 截图，通过 ADB 在盒子上截取（1920×1080） |

## 可用功能

| | |
|---|---|
| 系统 | Android 15 TV 界面，内核 4.9.337（arm64），userdebug；网络 ADB |
| 视频 | H.264 / HEVC / VP9 硬件解码——YouTube 和 SmartTube 播放 4K60 VP9 无丢帧；支持 4K 输出模式（尚未在 4K 电视上测试） |
| 音频 | 通过 Amlogic "auge" 声卡的 HDMI L-PCM（DTS 中的 DAI 配置需要修正） |
| Wi-Fi / 蓝牙 | AP6275S（BCM43752）5 GHz 11ac；蓝牙 5（v2：通过普通 HCI UART，并带内核修复） |
| 遥控器 | 原厂红外遥控器（Beelink 按键表）；USB/蓝牙遥控器、键盘、手柄（v2：待机后也支持热插拔） |
| 电源 | 两个 CPU 簇均有温控（原厂 DTS 从不限制 A53 核心），待机时关闭 HDMI 信号并可即时唤醒（SoC 保持运行） |
| 存储 | eMMC、microSD、USB 主机（2.0 + 3.0，经 Fresco Logic 集线器） |
| 其他 | RTC（HYM8563），HDMI-CEC 驱动/HAL（电视控制尚未测试），Widevine L3 + ClearKey |

已知限制（详见 [`docs/release/INSTALL.md`](docs/release/INSTALL.md)）：仅支持 Widevine L3
（这台盒子没有 L1 密钥，原厂固件也是如此）；Netflix 的 Android TV 应用拒绝未认证设备；内置
Chromecast 接收端无法注册（需要每台设备独有的证书）；待机不进入深度睡眠；USB ADB 不可用
（请使用网络 ADB）；以太网未测试（测试机的 PHY 芯片硬件损坏）。

## v2 上的模拟器（实测，1080p60 电视）

| 平台 | 模拟器 | 结果 |
|---|---|---|
| PlayStation 2 | ARMSX2（Vulkan，原生分辨率，16:9 与去隔行补丁，8x 各向异性过滤，锐化） | 战神（PAL）50/50 fps；古惑狼：Cortex 的愤怒（The Wrath of Cortex）在游戏中 38–50 fps，使用该游戏专用的加速设置（EE cycle rate/skip，GPU 调色板转换）——测试过最吃性能的游戏 |
| PSP | PPSSPP 独立版（Vulkan，2x） | 战神：斯巴达之魂 60/60 fps |
| PlayStation | RetroArch SwanStation（5x = 1080p，PGXP，24 位色，16:9） | 50/50 fps |
| SNES / NES | RetroArch Snes9x / FCEUmm，CRT 着色器与 run-ahead | 全速 |

PS2 全速运行需要把 Mali 频率固定在 800 MHz（v2 在启动时自动设置：bifrost 驱动报告的负载始终为 0，
导致调速器一直停在 399 MHz）。PS2 提升分辨率超出了 Mali-G52 的能力（1.5x/2x = 20–34 fps）。
这些在 v1 上都无法实现：PS2 模拟器需要预留约 8 GB 地址空间，而 Dolphin 只有 arm64 版本。

## 刷机

参见 [`docs/release/INSTALL.md`](docs/release/INSTALL.md)。简要步骤：Amlogic USB Burning Tool
2.2.0，解压后的 `.img`，在 OTG 口插上 USB-A↔A 线后执行 `adb reboot update`，等待 5–8 分钟，
断电重启。`aml_upgrade_package_stock-restore+stockbl` 刷机包可恢复 Beelink 原厂固件。

## 启动方式（以及为何与众不同）

GT-King 使用锁定的 2015 版 Amlogic u-boot，其 BL2 包含这块主板的 LPDDR4 内存训练参数。刷机包
没有替换它，而是**保留原厂引导加载程序**并加入第二级引导：

1. 原厂 BL2 → BL31/BL32 → 原厂 u-boot（`g12b_w400`），
2. 它的 `preboot` 钩子：`if store read bl33 …; then go 0x1000000`——从独立的 `bl33` 分区加载
   **我们的** LineageOS u-boot（BL33 v4，`lineage/uboot/gen_galilei_board.py`）并跳转执行，
3. 我们的 u-boot 使用 GT-King 的 DTB 启动 `boot`。

两个 u-boot 读取同一个 `_aml_dtb`，因此它是一个包含两项的 Amlogic **多 DTB 容器**：原厂
`g12b_w400_b` DTB（移植了新的分区表——否则原厂 u-boot 会卡在以太网初始化）和我们的
`g12b_s922x_galilei` DTB。钩子位于原厂 u-boot **编译进去的默认环境变量**中：原厂 FIP 中的 BL33
被解包（LZ4），其 147 字节的 `preboot=` 字符串被替换，然后用 Amlogic 的 `aml_encrypt_g12b`
重新签名（`lineage/scripts/patch-stock-bl33-env.py`）；BL2/BL30/BL31/BL32 保持逐字节不变。
这使刷机包刷入即可使用：USB Burning Tool 每次刷机结束时都会用默认环境执行 `saveenv`，所以只存在于
已保存环境中的钩子在首次启动前就会消失（此时原厂 u-boot 会自己启动内核，而内核在未设置 A73 簇
时钟的情况下会在 1.8 秒处停住）。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `lineage/device/beelink/galilei/` | v1 的 LineageOS 设备树（继承 `device/amlogic/g12-common`）：主板配置、遥控器按键表、Wi-Fi/蓝牙固件配置、init rc、GApps 集成 |
| `lineage/device/beelink/galilei/v2/` | v2 vendor 辅助程序：`btuart-attach.c`（2 KB 静态程序，为 AP6275S 蓝牙挂接 HCI UART）、`btdiag.c` |
| `lineage/kernel/dts/` | `g12b_s922x_galilei.dts`（v1）和 `v2/`（v2 DTB + 分区表）——原厂 w400 参数 + 修复：音频 DAI、散热映射、CPU 稳压器、Wi-Fi/蓝牙、以太网 |
| `lineage/patches/` | v1 内核补丁（stmmac 重复注册 PM notifier = 无 PHY 时启动卡死；meson_wdt 唤醒后重载）；`v2/` = 基于 voodik 内核的六个补丁（eMMC 分区表、SCPI 超时、stmmac、meson_wdt、hci_bcm 初始化、待机失败后的 USB 设备识别）；`wip/` = hdmitx 唤醒卡死的调查（未启用） |
| `lineage/uboot/gen_galilei_board.py` | 为 LineageOS u-boot 生成 `g12b_galilei_v1` 主板配置（固定启动环境、无以太网、适合二级引导） |
| `lineage/scripts/` | v1：`setup-tree.sh`、`rebuild-final.sh`、`patch-stock-bl33-env.py`、`gen-privapp-allowlist.py`、`make-gapps-vendor.py`、`make-multi-dtb.py`、`make-packages-with-bootloader.sh`、`postflash-check.sh`；v2：`extract-voodik-vendor.sh`、`v2-kernel-patches.sh`、`v2-build-kernel.sh`、`v2-build-dhd.sh`、`v2-build-dtb.sh`、`v2-make-multidtb.sh`、`v2-make-m1.sh`、`v2-adb-flash.py`；发布：`make-release-archives.sh`；串口控制台：`serial-console.py`、`uart-*.py`；测量：`sf-fps.sh`、`ps2-bench.sh` |
| `docs/option1/` | 移植文档：`BRINGUP.md`（从源码编译）、`FLASH.md`（刷机包、控制台操作）、`UART.md`（排针定义）、`EMMC-SHORT.md`、`HDMI-BOOT.md` |
| `docs/release/` | `INSTALL.md`、`RELEASE-NOTES.md`、`XDA-thread.bbcode`、`PUBLISH.md` |
| `tools/` | `hdmiboot/`（基于 Arduino 的 BootROM HDMI 启动加密狗）、`cp210x/`（USB-UART 驱动） |

研究阶段的笔记（波兰语）：[`docs/RESEARCH-NOTES-PL.md`](docs/RESEARCH-NOTES-PL.md)。

## 编译

v1（从源码编译 LineageOS 22.2）：

```
# 首次：同步 LineageOS 22.2 及 Amlogic g12-common 源码树（docs/option1/BRINGUP.md）
TOP=~/android/lineage bash lineage/scripts/setup-tree.sh        # 设备树、DTS、u-boot 主板、GApps
TOP=~/android/lineage bash lineage/scripts/rebuild-final.sh      # bacon + 多 DTB + Burning Tool 刷机包
```

`GAPPS=none` 可编译不含 Google 应用的版本。`setup-tree.sh` 还会把 `lineage/patches/` 中的内核补丁
应用到 `kernel/amlogic/linux-4.9`（可重复执行）。

v2（64 位；需要 voodik 的 ODROID-N2 ATV 22.1 镜像，以及作为引导分区基础的 v1 GApps 刷机包）：

```
bash lineage/scripts/extract-voodik-vendor.sh <他的 OTA zip> vendor system   # -> ~/voodik/*.img
bash lineage/scripts/v2-kernel-patches.sh        # voodik 内核 @660a3bebdf92 + lineage/patches/v2
bash lineage/scripts/v2-build-kernel.sh
bash lineage/scripts/v2-build-dhd.sh             # AP6275S 驱动模块
bash lineage/scripts/v2-build-dtb.sh && bash lineage/scripts/v2-make-multidtb.sh
TAG=final bash lineage/scripts/v2-make-m1.sh     # -> aml_upgrade_package_v2-final.img
```

## 支持

这是一个免费、开源的业余项目。如果它让你的 GT-King 重获新生，欢迎在 [Ko-fi](https://ko-fi.com/mkmajster) 请我喝杯咖啡（信用卡或 PayPal）——完全自愿。

测试反馈同样宝贵：以太网、4K/HDR 电视和 HDMI-CEC 仍未经过测试。

有其他 Android TV 盒子，或需要类似移植工作的项目？我也乐意承接新项目或协助现有项目——请在这里提交
issue，或在 XDA 上私信我。

## 致谢

LineageOS 与 Amlogic g12-common 的维护者（v1 设备树继承了他们的通用设备树和内核）；**voodik**——
他为 ODROID-N2 制作的 LineageOS ATV 及其内核是 v2 的基础
（[GitHub](https://github.com/voodik)，[ODROID-N2 版本](https://oph.mdrjr.net/voodik/S922X/ODROID-N2/Android/)）；
Hardkernel；MindTheGapps；CoreELEC 与 Khadas 社区提供的 S922X/G12B 知识；ARMSX2/PCSX2、PPSSPP、
DuckStation/SwanStation 和 RetroArch 项目；Beelink 的原厂固件——这些版本仍依赖其引导加载程序和
二进制组件。

## 许可证

设备树、脚本和文档：Apache-2.0。内核补丁：GPL-2.0（修改的是 Amlogic 4.9 内核）。专有 vendor
二进制文件和 Google 应用不属于本仓库。
