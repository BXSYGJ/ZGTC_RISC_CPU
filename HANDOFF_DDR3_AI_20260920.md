# ZGTC RISC CPU — DDR3 接入交接快照（2026-09-20，XSY 分支）

> 目的：给「下一个人」一份可立即接手的状态记录。读完本文件应能知道：
> 项目当前做什么、DDR3 接入做到哪一步、最后构建结果是什么、还有哪些事没做、
> 技能与文档放在哪里、下一步 AI 加速怎么规划。
> 上一份快照：仓库根 `DEV_SNAPSHOT.md`（2026-09-07，153MHz/RV32IM 基线）。本文件只记录 DDR3 与 AI 加速相关增量。

---

## 0. 一句话现状

**RV32IM SoC 已以 153MHz/511 CoreMark 验证跑通（历史基线）；当前新工作在 XSY 分支推进「DDR3 接入 → AI 加速单元 → 部署小 YOLO」。**
DDR3 接入的 **RTL 桥接、约束、工程集成、bootloader 自检均已实现**，最新一次完整构建**时序全绿（All Constraints Met）并产出位流**
（`cpu/build/pds/20260920-161710-63f81735/generate_bitstream/pds_soc_top.sbit`，RemoteLab UART）。
**静态审查已修复 `rv32_burst_ddr3.sv` 中 3 个缺陷**（r_last 永零致命 bug + 两处重复声明），**pds_report.py 多时钟/GPLL 审计已修复**。
**尚未做**：远程实验箱上板验证（受阻于 `logicmatrixsemi.com` DNS 不可达——用户侧网络问题）。

---

## 1. DDR3 接入：已完成的工作

### 1.1 新增 RTL（均已落盘、已进构建）

| 文件 | 作用 |
| ---- | ---- |
| `cpu/rtl/rv32_burst_ddr3.sv` | 桥：CPU 27MHz 突发总线 ↔ DDR 125MHz AXI（CDC、16B line→32B 单拍、`cmd_address[4]` 选字高低半区、`wstrb` 按位生成、读回 4 拍） |
| `cpu/fpga/rv32_ddr3_ip_wrapper.sv` | DDR3 IP 顶层 wrapper：GTP_INBUFDS（差分 125MHz ref_clk）→ rst 同步 → `ddr3_test` 例化，APB 配置口接常量 0 |

### 1.2 DDR3 IP（精简拷贝，已进构建）

- 位置：`cpu/fpga/ddr3/ipcore/ddr3_test/`（含 `ddr3_test.v`、`ddr3_test_ddrphy_top.v`、`ddr3_test.idf`、`rtl/`、`sim_lib/`，不含 pnr 目录）
- 来源：`docs/盘古200Pro+开发板.../2_Demo/2_9_ddr3_test/.../ipcore/ddr3_test/`
- **关键事实：此 IP 无 `axi_b` 通道**，写完成判定用 `axi_wready` 握手（与官方 `test_wr_ctrl_v1_0.v` 一致）。

### 1.3 修改的 RTL/脚本

| 文件 | 改动 |
| ---- | ---- |
| `cpu/rtl/rv32_memory_system.sv` | 加 `CACHE_ADDRESS_BITS` 参数、DDR 后端端口、cache `.ADDRESS_BITS(CACHE_ADDRESS_BITS)`、组合路由 `ddr_select = cmd_address >= 32'h0001_0000` + 双后端门控 mux。修复了之前 `cmd_address[15:0]>=16'h0000` 恒真 bug |
| `cpu/rtl/rv32_soc.sv` | `CACHE_ADDRESS_BITS` 透传、DDR 后端端口、core `BTB_ADDRESS_BITS` 改为此参数 |
| `cpu/rtl/rv32_board_top.sv` | `CACHE_ADDRESS_BITS=16`、`ref_clk_p/n` + 全部 `mem_*` 物理端口、例化 `rv32_burst_ddr3` + `rv32_ddr3_ip_wrapper` |
| `cpu/scripts/pds_soc_top.v.in` | 加 ref_clk/mem 端口、`__CACHE_ADDRESS_BITS__` 占位符 |
| `cpu/scripts/build_pds.tcl` | 加 `__DDR3_DESIGN__`（wrapper+idf）、`__DDR3_CONSTRAINT__`（ddr3.fdc）占位符，默认空保持旧构建兼容 |
| `cpu/scripts/run_pds.ps1` | 加 `[int]$CacheAddressBits`（默认 27）、三个占位符替换、fpga 目录**递归复制**；修复 PS5.1 不支持的 `utf8BOM`→`utf8`、`Path.GetRelativePath`→`Substring` 兼容 |
| `cpu/sw/boot/bootloader.c` | 已实现 `D` 命令 DDR 自检：向 `DDR_BASE`（0x0001_0000）窗口写 `DDR_PATTERN+word`，读回比较，UART 打印 `DDROK` 或 `DDRErr @0x...` |

### 1.4 约束文件 `cpu/constraints/ddr3.fdc`（529 行，已写全）

- 6 个 generated clock：`ref_clk`(125M) → `rst_clk`/`ddrphy_sysclk`/`phy_dq_clk_0`/`phy_dq_clk_1` + 派生 `phy_dq_sysclk_0/1`（IP 实例路径前缀 `board.ddr3_wrapper.I_ips_ddr_top.*`，**必须保留此层级**）
- `set_multicycle_path 2 -from ddrphy_sysclk -to phy_dq_sysclk_0/1`、`set_clock_uncertainty 0.4`（官方同款）
- `set_clock_groups -asynchronous`：**每个时钟单独一组**（CPU `clk`、`ref_clk`、`rst_clk`、`ddrphy_sysclk`、`phy_dq_clk_0`、`phy_dq_sysclk_0`、`phy_dq_clk_1`、`phy_dq_sysclk_1`）——官方写法；注意**不要**把所有 DDR 时钟合成一组（会把 DDR PHY 内部异步复位路径当同步路径分析，产生 37 处违规）
- 全部 `mem_*` 物理引脚约束（来自官方 fdc，SSTL15/HSTL15、1.5V、drive 8、SLEW SLOW）

---

## 2. 构建结果（最新三路对比）

| 构建目录 | 时间 | Design Summary | bitstream | 说明 |
| ---- | ---- | ---- | ---- | ---- |
| `cpu/build/pds/20260920-161710-63f81735` | 16:17 | **All Constraints Met** | ✅ 有 | **r_last 修复后构建**，RemoteLab UART，pds_report.py --ddr3 审计通过（WNS +23.105ns, GPLL=2, 7653 LUT） |
| `cpu/build/pds/20260920-150934-da1bd5fa` | 15:22 | **All Constraints Met** | ✅ 有 | r_last 修复前构建（Board UART），pds_report.py 审计未跑通（多时钟匹配缺陷） |
| `cpu/build/pds/20260920-144109-14b8b9a3` | 14:41 | Some Constraints Violated（36 处） | ✅ 有 | 旧式 clock_groups 分组的问题构建 |

**关键踩坑（已解决）**：
- 时钟 pin 路径：PDS 综合报 `Nothing matched` 是因为 fdc 里 get_pins 路径少了 `board.ddr3_wrapper.` 两层前缀（实测实例 `pds_soc_top/board/ddr3_wrapper/I_ips_ddr_top/...`）。
- clock_groups 错误分组曾在 DDR↔CPU 间产生 37 处违规；改成每时钟一组（官方写法）后清零。
- **run_pds.ps1 误报失败根因**：PS 5.1 下 `Start-Process -Wait` 缺省（原先手写 `WaitForExit()`）导致 `$process.ExitCode` 为 `$null`，而 `$null -ne 0` 恒真 → 即使时序全绿也 throw。**已修复为 `-Wait` 并打印 `PDS ExitCode:`，但修复后尚未在 PowerShell 5.1 下完整重跑验证**（见遗留问题）。
- `SCBV has not been set`（Bitstream-2001）是警告非致命，此前 sbit 已成功烧录过。

---

## 3. 遗留问题 / 待办（按优先级）

1. **远程实验箱上板验证 DDR3**（唯一未验证的关键环节）：
   - 用 `tool/fpga_lab/scripts/serial_session.py`（或既有 `remote-lab.cmd` 流程）烧录最新 sbit；
   - 串口发 `ZBOOT` 或复位进入 bootloader，发 `D` 命令触发 DDR 自检 → 期望 `DDROK`。
   - 注意坏箱：实验箱9（id59）复位丢程序、gateway .31（id61）串口静默；好箱 1/2/3/4/5/7、gateway .32。
   - **当前受阻**：`logicmatrixsemi.com` DNS 不可达（用户侧网络问题），需用户处理 DNS/域名/IP 直连后重试。
2. （可选）DDR3 实测通过后，把 `D` 自检结果并入 `?` 帮助、并沉淀到 `cpu/docs/` 一篇 DDR3 接入文档。

---

## 3a. 已修复的缺陷（2026-09-20 静态审查）

### `rv32_burst_ddr3.sv` — 3 个缺陷

| 缺陷 | 严重性 | 修复 |
| ---- | ---- | ---- |
| **`r_last` 永远为 0** | **致命** — 所有 DDR3 读操作挂死 | 重写 CPU_READ_SEND 状态：以 `if(r_valid && r_ready && r_last)` 结束、`else if(!r_valid \|\| r_ready)` 推进 beat，仿照 `rv32_burst_ram.sv` 正确模式 |
| `cpu_req_r` 重复声明（第76行 + 第113行） | 中 — PDS 容忍但应清理 | 删除第113行 |
| `ddr_ack_r` 重复声明（第77行 + 第223行） | 中 — 同上 | 删除第223行 |

**r_last bug 根因**：原第177行 `r_last <= (rbeat==2'd3)` 在 rbeat==3 握手时被第180行 `r_last <= 1'b0` 同拍覆盖。下游 arbiter（第96行 `r_valid && r_ready && r_last`）、cache（第196行 `if(r_last)`）、uncached（第86行）全部依赖 r_last=1 结束读事务。

### `pds_report.py` — 2 个缺陷

| 缺陷 | 修复 |
| ---- | ---- |
| 第28行正则无行首锚定，`clk` 子串误匹配 `rst_clk`/`ddrphy_sysclk`（found 3） | 加 `^\s*` + `re.M`，与第24行一致 |
| GPLL 检查未考虑 DDR3 PHY 的 2 个 PLL（期望 0，实际 2） | 加 `--ddr3` 标志，期望 GPLL += 2；`run_pds.ps1` 已传 `--ddr3` |

---

## 4. 硬性约束（改代码时不可丢）

- **上电地址 0 取指 + BRAM 引导**：DDR3 上电为空，必须保留低 64KiB BRAM boot ROM（bootloader 链接 `APP_BASE=0x1000, APP_MAX=0xf000`），**DDR3 映射到 0x0001_0000 起**。
- **MMIO 旁路限制**：MMIO 条件是 `d_req_address[31:28]` 非 0 → DDR3 只能映射在低 256MB 内，不能放高位。
- **Cache `ADDRESS_BITS` 扩大但 `MEMORY_ADDRESS_BITS` 不动**：DDR 构建 `CACHE_ADDRESS_BITS=16`（board_top 参数），`MEMORY_ADDRESS_BITS` 保持（BRAM/调试用）。
- **DDR3 IP 无 axi_b 通道**：写完成靠 `axi_wready` 握手，不用 `axi_wusero_last`（官方未验证、有挂死风险）。
- **时钟**：`GTP_INBUFDS` 收差分 125MHz（N3/N2）；IP 输出 `core_clk`(125M) 与低有效 `resetn`；**IP 实例名必须为 `I_ips_ddr_top`**（generated clock 路径依赖）；不引入 free_clk（无该端口且 D18 已被 CPU clk 占用）；APB 接常量 0。
- **编码规范**：全部 SystemVerilog-2005（PDS 不支持 SV-2012）：`always @*`、无隐式 `logic`、无 SV-2012 新语法。
- **Pango 流程**：`pds_shell.exe -file build.tcl -work_dir <root> -project_name <name>`，位流 `<root>/generate_bitstream/<top>.sbit`；本机无 WSL/无 Icarus，**本地 RTL 仿真不可行**，验证只能远程。

---

## 5. 技能与文档情况（给下一个人）

### 5.1 技能 `pango-pg2l200h-dev`（三处副本，内容一致）

| 位置 | 说明 |
| ---- | ---- |
| `docs/skills/pango-pg2l200h-dev/`（**工作区内，本次归档**） | 交接用主副本，随仓库走 |
| `C:\Users\menss\.codebuddy\skills\pango-pg2l200h-dev\` | 原工作副本（CodeBuddy 技能目录） |
| `D:\0000\111\001\Pango\pango-pg2l200h-dev\` | 外围工作副本 |

- 内容：`SKILL.md`（PDS 环境/流程/远程调试完整说明）+ `references/`（`bridge_server.md`、`pds_tcl_flow.md`、`pin_constraints.md`、`remote_debug.md`）+ `template/`（blink 工程模板与全套流程产物）。
- 环境前提（本机已配置用户级）：`PDS_ROOT=H:\GG\pango\PDS_2022.2-SP6.4`、`PANGO_LICENSE_FILE=E:\License\pango\new_pds_F4A80DA47D72.lic`。换机器需重设。
- 已备案到记忆索引：`reference-zgtc-risc-cpu.md`（仓库/分支/架构入口）、技能自身记忆条目（含 PDS 流程、设备白名单、坏箱清单等）。

### 5.2 官方参考文档（DDR3 部分）

- 资料根：`D:\0000\111\001\Pango\docs\盘古200Pro+开发板（MES2L676-200HP）配套资料\`
- **DDR3 demo 工程**：`2_Demo\2_9_ddr3_test\2_9_ddr3_test\ddr3_test\`（官方完整工程）
  - 官方约束参考：`...\ddr3_test\ipcore\ddr3_test\pnr\ddr_test.fdc`（1320 行，引脚 + generated clock + multicycle + uncertainty 来源）
  - 官方读/写控制参考：`sim\` 下 `test_rd_ctrl_v1_0.v` / `test_wr_ctrl_v1_0.v`
- 板上 DDR3 位置：U2（1.5V SSTL15，官方 fdc 引脚即本次 ddr3.fdc 所用）。

### 5.3 仓库内既有文档

- `DEV_SNAPSHOT.md`：2026-09-07 基线（153MHz/RV32IM）。
- `cpu/docs/`：大量设计/验证文档（FLASH_BOOT.md、BUS.md、CLOCKING.md 等 100+ 篇），其中 `AI_HANDOFF_153MHZ.md`、`PROJECT_HANDOVER_153MHZ.md` 为交接类。
- `CODEBUDDY.md`：仓库结构说明（mainline RTL vs `cpu/experiments/full_fetch_commit_factored`），新人必读。

---

## 6. 下一步：AI 加速单元规划（当前思路与结论）

用户目标：**AI 加速单元 → 接入 DDR3（已做）→ 部署小 YOLO**。

### 6.1 结论：不需要改指令集，别做 RVV

- **不推荐在自研核内集成 RVV**：RVV 是把向量化指令压进流水线，工作量大（译码/执行/寄存器堆/控制耦合），且对 YOLO 这类典型 CNN 收益不如投 MAC 阵列。
- 独立 **AI 加速单元**挂在总线/Cache 后端（MMIO 或专用端口 + 结果寄存器/DMA 握手），用 **int8 MAC 阵列 + 专用控制状态机**即可覆盖 YOLO 的计算密集部分。

### 6.2 推荐架构（沿用本项目现状）

```
RV32I核 → I/D-Cache(16B行突发) → 总线(MEMORY_SYSTEM)
   ├── BRAM 0x0000_0000..0x0000_FFFF（boot ROM + 常驻）
   ├── DDR3 0x0001_0000..（大数据/权重/图像，桥已就绪）
   └── [下一步] AI 加速器：AXI/突发总线上，int8 MAC 阵列
        ├── 权重/输入：从 DDR3 读（burst）
        ├── 结果：写回 DDR3 或内部 SRAM 输出缓冲
        └── 控制：MMIO 寄存器（启动/完成/中断）
```

- YOLO 的**上采样、concat、sigmoid、NMS、后处理**由 CPU 做（这些非计算瓶颈，且逻辑复杂不适合硬核）。
- 加速器只做 **GEMM/卷积（含 im2col 或直接滑动窗）**，建议起点：单卷积层 3x3/s1，int8，8~32 个乘加单元并行，先跑通再扩。

### 6.3 建议的接续路径

1. 用已就绪的 DDR3 桥把 YOLO 权重/输入图搬到 DDR3（先写 host 侧工具或 bootloader 命令）；
2. 设计 AI 加速器 RTL（`rv32_ai_accel.sv`，SV-2005 规范），挂 memory_system 的第三后端或 MMIO 窗口；
3. 加速器先以「写寄存器→start→轮询 done→读结果」的简单握手接入 CPU；
4. 在 PC 上先用 Python/C 验证卷积参考输出，再对拍 RTL 行为（本机无仿真器，需远程或借用 WSL/iverilog）。
5. 最后做 YOLO tiny（或自训小网络）端到端演示：UART/摄像头输入 → DDR3 → 加速器 → CPU 后处理 → UART/OLED 输出。

---

*本快照生成于 2026-09-20 15:3x（XSY 分支）。交接人：DuMate。*