# InstRec-FPGA 当前状态（STATUS）

> 本文件是**唯一实时状态源**，优先于任何交接快照与记忆。每次会话结束前必须更新，
> 并在 `CHANGELOG.md` 追加一条。最后更新：2026-10-27 11:15。

## 一句话

InstRec 8 类乐器识别（INT8 CNN）正在移植到盘古 100Pro+（PG2L100H-6IFBG676）纯 FPGA 管线。
**M0 已出位流但未上板；M1（Mel 引擎）RTL 全部落盘、语法已修，当前卡在 `db_norm` 组合时序。**

## 里程碑

| 里程碑 | 状态 | 关键证据 |
|---|---|---|
| P0 工具链 + Python 金标准 | 完成 | `pytest -q` 63 passed；`golden_pipeline.py` 位级真值 |
| M0 I2S→DDR3→HDMI 波形 | 完成（未上板） | run `20261027-000612-a71f1451` 六阶段 OK，sbit sha256 `C517736C7E61937521BC1776DDA4ACAC66F0373DF7E0FACDD86AEC017DD2EDAC`，WNS +1.757 |
| M1 Mel 特征引擎 | **进行中：时序未收敛** | 8 个 RTL 落盘，最差 WNS -4.401 ns，无位流 |
| M2 INT8 NPU | 起步 | `requant_unit.v` 已交付；`conv_engine.v` 待复核；其余未做 |
| M3 UI 集成 | 未开始 | `src/ui/` 仅 M0 的网格 + 波形 |

## 当前阻塞（M1）

- 构建目录：`build/pds/20261027-104218-acb7a788`（尚未归档到 `reports/`）。
- 已通过：compile → synthesize → dev_map → place_route → report_timing。
- 未完成：gen_bit_stream（会话结束时 PDS 进程被终止，无 M1 位流）。
- 失败时钟：`ddrphy_sysclk`（即顶层 `core_clk`，125 MHz）WNS **-4.401 ns**，TNS -487.619，200 failing endpoints / 41356。
- 最差路径：`u_mel_engine/u_db_norm`，DRAM→APM→LUT→APM→LUT→APM，arrival 17.539 ns，仅 5 logic levels
  （Logic 8.121 ns / Route 3.876 ns），required 13.138 ns。
- 其余时钟：`clk_nco` 216 MHz +1.348、`pix_clk` 148.5 MHz +0.486、`rst_clk` 125 MHz +4.727。
- 资源：LUT 15731/66600 (24%)、FF 11855/133200 (9%)、DRM 43.5/155 (29%)、APM 29/240 (13%)、Distributed RAM 996 (6%)。
- **不是 DDR3 IP 固有**：同一 IP 在 `pds_cpu_100h`（DDR3 版）`ddrphy_sysclk` 为 **+2.110 ns**。

## 下一步（按序）

1. `db_norm` 乘加链插流水寄存器，保持 259 帧全局 max 与位级结果不变；重跑到 All Constraints Met。
2. 出 M1 位流 → 板级冒烟 T-M0-10：JTAG 烧录 → UART 115200 看 BOOT/PLL/DDROK → HDMI 网格 + 波形。
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