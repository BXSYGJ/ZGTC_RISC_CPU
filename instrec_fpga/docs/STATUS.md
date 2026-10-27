# InstRec-FPGA 当前状态（STATUS）

> 本文件是**唯一实时状态源**，优先于任何交接快照与记忆。每次会话结束前必须更新，
> 并在 `CHANGELOG.md` 追加一条。最后更新：2026-10-27 12:30。

## 一句话

InstRec 8 类乐器识别（INT8 CNN）正在移植到盘古 100Pro+（PG2L100H-6IFBG676）纯 FPGA 管线。
**M0/M1 位流均已产出且时序收敛；M1 已归档待板级对拍，下一步是上板与 M2 NPU。**

## 里程碑

| 里程碑 | 状态 | 关键证据 |
|---|---|---|
| P0 工具链 + Python 金标准 | 完成 | `pytest -q` 63 passed；`golden_pipeline.py` 位级真值 |
| M0 I2S→DDR3→HDMI 波形 | 完成（未上板） | run `20261027-000612-a71f1451`，sha256 `C517736C…`，WNS +1.757 |
| M1 Mel 特征引擎 | **构建完成、时序收敛、待板级对拍** | run `20261027-121101-5c24a968`，sha256 `BD40D10A…`，WNS +1.438 / All Constraints Met |
| M2 INT8 NPU | 起步 | `requant_unit.v` 已交付；`conv_engine.v` 待复核；其余未做 |
| M3 UI 集成 | 未开始 | `src/ui/` 仅 M0 的网格 + 波形 |

## 当前状态

- 最新构建：`build/pds/20261027-121101-5c24a968`，六阶段全 OK，已归档到 `releases/m1-20261027/`。
- 时序：**All Constraints Met**；WNS +1.438（clk_nco）、WHS +0.224；
  `ddrphy_sysclk`（core_clk 125 MHz）+0.837（修复前 -4.401）。
- 资源：LUT 15740/66600 (24%)、FF 11915/133200 (9%)、APM 29/240 (13%)、DRAM 43.5/155 (29%)、BKCL 6/6。
- 修复方式：`db_norm` scan 2 改 4 拍流水、`standardize` 量化扫描改 5 拍流水；算术顺序不变，位级结果不变。
- 构建脚本：`Get-FileHash` 在本机 PS 5.1 缺失，已改用 .NET SHA-256（`run_pds_full.ps1`）。
- **板级阻塞**：板子已上电（CP2102 串口 `COM5` 在线），但 **USB Cable II 下载器未被识别**
  （`cdt_js` 的 cable 列表为空，系统无 FTDI 设备），JTAG 扫描报 `No devices detected`。
  JTAG 脚本已就绪：`scripts/jtag_scan.tcl`、`scripts/jtag_program_m1.tcl`。

## 下一步（按序）

1. 插好 USB Cable II（J12，红线对 1 脚）→ `jtag_scan.tcl` 确认扫到器件 → `jtag_program_m1.tcl` 烧 M1。
2. 串口 115200 看 BOOT/PLL/DDROK 状态行；HDMI 看网格 + 波形；再验 Mel 段（T-M1-07，需补 `uart_capture.py`）。
3. M2：先复核 `conv_engine.v` 的 16 lane / 行缓冲 / 层参数，再 `wdma → weight_loader → pool → gap_fc → npu_top`。

## 验证基线

- `python -m pytest -q` → **63 passed**（约 60 s）。
- `python scripts/check_rtl.py` → **26 个 .v，0 violation**（hdmi demo 默认排除）。
- 数值对拍只认 `scripts/golden_pipeline.py`；torch 2.14.1 的 oneDNN 有 21~67 LSB tile 噪声。
- 本机无 WSL 仿真（Ubuntu 发行版 vhdx 缺失），RTL 行为只能靠 Python 对拍 + 板级实测。

## 资产位置

| 类别 | 路径 |
|---|---|
| RTL | `src/{audio,ddr3,mel,npu,ui,ctrl,ip,hdmi}/*.v` |
| 顶层 | `src/ctrl/instrec_top.v`（mel_engine 接 DDR3 m2 口） |
| 约束 | `constraints/instrec_top.fdc`、`ddr3_100h.fdc`、`clock_groups_async.fdc`（顺序敏感） |
| IP | `ipcore/{ddr3_test,pll,pll_audio}/`（重建必需，已入库） |
| 数值真源 | `scripts/outputs/layer_contract.json`、`weights_image.bin`、`mel_tables.*` |
| 金标准 | `scripts/golden_pipeline.py` + `scripts/outputs/golden/*.npy` |
| SDD | `docs/sdd/{spec,design,tasks}.md`（从 `.codeartsdoer` 复制的可交接副本） |
| 证据 | `reports/m0-manifest-20261027.json`、`reports/m1-timing-20261027-104218.txt`（修复前时序） |
| 位流归档 | `releases/m0-20261027/`、`releases/m1-20261027/`（sbit + manifest + SHA256SUMS + 时序报告） |
| 交接 | `docs/HANDOFF_SNAPSHOT_20261027.md` + 本文件 |
| Agent 规则 | 仓库根 `AGENTS.md` |

## 未纳管 / 已搁置资产（勿误删，也不必入库）

- `ai_pcb/`（67 MB，PCB 缺陷识别视觉，含 ONNX）、`pcb-aoi/`（202 MB）—— 2026-10-26 已停止移植。
- `cpu/rtl/rv32_ai_{accel,conv,dma,silu}.sv`、`cpu/rtl/rv32_axi_arbiter.sv`、`cpu/docs/AI_ACCEL_PCB_100H_PLAN.md` ——
  搁置路线的 WIP，未验证。
- 根目录 `1571364599 paper.pdf`、`account.txt`（凭据，禁止入库）。

## 环境

- PDS 2022.2-SP6.4：`PDS_ROOT=H:\GG\pango\PDS_2022.2-SP6.4`
- License：`PANGO_LICENSE_FILE=E:\License\pango\new_pds_F4A80DA47D72.lic`
- 构建脚本必须 PS 5.1 兼容；一次只能跑一个 `pds_shell.exe`（脚本不查并发）。
- 构建成功 ≠ 时序收敛：脚本只校验位流存在与新鲜度，**不校验 WNS**，必须看 `manifest.json` / `.rtr`。

## 版本基线（git，分支 XSY，未 push）

- `1298395` feat(instrec): 首次纳管 InstRec-FPGA 工程并建立可交接文档（182 文件，含 IP 源文件与 SDD）
- `2abf5ed` wip(cpu): 存档已搁置的 PCB 视觉 AI 加速 RTL（未验证）
- 工作区有意保留未纳管：`ai_pcb/`、`pcb-aoi/`（含大 ONNX，已搁置）、`1571364599 paper.pdf`。
- 位流本体不入库（`*.sbit` 全局忽略）；**例外**：`instrec_fpga/releases/**` 与 `pds_cpu_100h/releases/**`
  的里程碑位流已入库并附 `SHA256SUMS`，`.gitattributes` 设 `-text` 防止二进制被换行改写。
- 里程碑位流：`instrec_fpga/releases/m0-20261027/`（M0）、`instrec_fpga/releases/m1-20261027/`（M1，时序收敛）、
  `pds_cpu_100h/releases/120mhz-20261025/`（100H 120 MHz 交付）。