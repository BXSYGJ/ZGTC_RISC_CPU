---
name: pango-pg2l100h-dev
description: >
  紫光同创 Logos2 PG2L100H（盘古 100Pro+ / MES2L676-100HP 开发板）的 Windows PDS 全流程开发技能。
  覆盖：PDS 环境（PDS_ROOT、PANGO_LICENSE_FILE）、无 WSL 的本地 PDS 批处理综合/实现/生成位流、
  PG2L100H 工程 TCL 流程、板级管脚约束、USB Cable II + J12 的 JTAG 下载/固化、板载 CP2102
  串口（UART）调试，以及 RISC-V CPU SoC 上位（pds_cpu_100h：位流构建 + 烧录 + ZBOOT 串口加载应用）。
  当用户要求用 PDS 开发 PG2L100H / 盘古 100Pro+ 开发板、生成 .sbit 位流、用 JTAG 下载位流、
  固化 Flash、通过串口连接/调试本板、把 CPU/RISC-V SoC 烧到板上跑、或经串口给板子加载应用程序时使用本技能。
  本机仅有 Windows PDS，没有 WSL / Icarus Verilog，不要尝试本地 RTL 仿真。
---

# 紫光同创 PG2L100H · 盘古 100Pro+ PDS 开发

面向 `PG2L100H-6IFBG676`（Logos2 家族）与 `MES2L676-100HP` 开发板，使用 Windows 版
**PDS 2022.2-SP6.4**。链路已在实板验证到：本地 PDS 六阶段成功 → 生成 `blink_top.sbit`
→ JTAG 下载 → **8 个 LED 跑马灯运行**（2026-10-11）；以及 **RISC-V CPU SoC 全链路上板**
（2026-10-24，见 `references/cpu_serial_flash.md`）：`pds_cpu_100h` 位流 → JTAG 烧录 →
ZBOOT 串口控制台 → 串口加载应用 → SoC 自试 `ZSOC PASS`。

## 环境前提（本机已配置，缺失时再设）

| 变量 | 本机值 | 说明 |
| --- | --- | --- |
| `PDS_ROOT` | `H:\GG\pango\PDS_2022.2-SP6.4` | PDS 安装根，脚本读取 `bin/pds_shell.exe` |
| `PANGO_LICENSE_FILE` | `E:\License\pango\new_pds_F4A80DA47D72.lic` | PDS 许可证绝对路径 |

两项已写入**用户级**环境变量，新 PowerShell 进程自动继承。换机器用
`[Environment]::SetEnvironmentVariable('PDS_ROOT','<path>','User')` 重设。

> 本机**没有 WSL，也没有 Icarus Verilog**，不要调用任何本地仿真；仿真请在具备工具的机器上另行构建。

## 工作流

1. 读取用户工程；没有工程时以 `template/` 下的流水灯基线新建（已验证可生成位流并上板）。
2. 确认 `PDS_ROOT/bin/pds_shell.exe` 与 `PANGO_LICENSE_FILE` 存在，否则报错并提示设置。
3. 综合/实现/生成位流走 PDS 批处理（见下）。**不要**启动图形界面 `pds.exe` 做批处理。
4. 位流产出在 `<project>/generate_bitstream/<top>.sbit`，记录 sha256。
5. 下载走 PDS **Configuration** GUI（最稳），或 `cdt_cfg` + jtagserver（脚本化，见 `references/jtag_download.md`）。
6. 串口调试见 `references/serial_console.md`。
7. **CPU SoC 上位**（位流构建/烧录/ZBOOT 串口加载应用/自试）见 `references/cpu_serial_flash.md`。

## PDS 批处理构建（核心命令）

工程入口是 `pds_shell.exe -file build_full.tcl -work_dir <root> -project_name <name>`。
TCL 顺序（完整说明见 `references/pds_tcl_flow.md`）：

```tcl
add_design    "<root>/src/<top>.v"
add_constraint "<root>/constraints/<top>.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -top_module <top>
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
```

位流输出到 `<root>/generate_bitstream/<top>.sbit`。`gen_bit_stream` 会打印
`C: Bitstream-2001: SCBV has not been set` —— 原厂未提供 PCB 参数时的正常提示，**非错误**。

## 新建工程的推荐脚本

`template/scripts/run_pds_full.ps1` 把 TCL 中 `__PROJECT_ROOT__` 令牌展开为当前工程绝对路径，
调 `pds_shell`，并校验 `E:` 错误、位流存在与 sha256：

```powershell
pwsh -NoProfile -File .\scripts\run_pds_full.ps1
```

## 管脚约束要点（`MES2L676-100HP`）

- `clk` D18（27 MHz，`create_clock -period 37.037`）、`rst_n` C22（KEY0 低有效）、
  `key` C23（KEY1 低有效）、`led[0..7]` A20/C18/C19/E18/A17/A18/C17/B17（高有效）。
- 板载串口：`uart_rx` **B24**、`uart_tx` **C24**，115200 8N1。
- 电平统一 `LVCMOS33`、VCCIO 3.3。完整 `.fdc` 见 `template/constraints/blink_top.fdc`，详见 `references/pin_constraints.md`。
- **普通 IO（clk/KEY/LED/UART）与 200Pro+ 一致**；但 **DDR3 引脚/约束不同**，迁移 200H 工程时不能照搬 DDR3。

## JTAG 下载

- 硬件：USB Cable II → 底板 **J12**（10 针，红线对 1 脚）；先接 JTAG/电源线再开 **SW1**；通电勿插拔。
- GUI：PDS → **Tools → Configuration → Scan Device** → 选 `.sbit` → 右键器件 **Program**。
  成功标志：`COMMAND[Program] execute successfully..`。
- 固化：Operations → Convert File 生成 `.sfc` → Scan Outer Flash → Outer Flash 右键 Program。
- 扫不到器件（TDO 恒 `0xffffffff`）排查见 `references/jtag_download.md`（首查上电/压合/排线方向）。

## 串口（UART）

- 板载 **CP2102 + USB Type-C**：USB 线接底板「USB 转串口」Type-C 口（不是 J12）。
- 装 **CP210x VCP 驱动**，设备管理器出现 `Silicon Labs CP210x USB to UART Bridge (COMx)`。
- 参数：**115200 8N1**（官方 `2_8_uart_test` 于 27 MHz 下 `BPS_NUM=234`）。
- ⚠️ 流水灯工程无 UART，插上无输出；验证串口要烧含 UART 的设计。详见 `references/serial_console.md`。

## 参考资源

- `template/`：已验证的 PG2L100H 流水灯工程（src / constraints / sim / scripts）。
- `references/pds_tcl_flow.md`：PDS TCL 批处理各阶段与退出码判定。
- `references/pin_constraints.md`：板级管脚、电平、时钟、串口、与 200H 差异。
- `references/jtag_download.md`：下载/固化流程与「扫不到器件」排查。
- `references/serial_console.md`：串口硬件/驱动/参数/上位机（含 serial_cli.py 用法）。
- `references/cpu_serial_flash.md`：CPU SoC 上板与串口烧录全流程（pds_cpu_100h、ZBOOT R 协议、实测记录）。
- `references/troubleshooting.md`：常见问题速查。

## 交付格式

```text
器件/板卡:
PDS 环境:
综合实现结果:
位流路径与 SHA-256:
时序(setup/hold WNS/WHS):
下载状态(已下载/已固化/未运行):
串口链路验证:
剩余问题:
```

未运行的阶段（如未固化、未做串口）必须明确写"未运行"，不得推断通过。
