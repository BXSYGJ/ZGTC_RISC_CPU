# AGENTS.md

本仓库当前只有**一条活跃主线**：`instrec_fpga/`（InstRec 8 类乐器识别移植到盘古 100Pro+ / PG2L100H-6IFBG676）。
`cpu/`、`pds_cpu_100h/` 是已交付的 RV32IM SoC 历史工程；`ai_pcb/`、`pcb-aoi/` 已搁置。
`DEV_SNAPSHOT.md`、`CODEBUDDY.md` 已过时，不要作为当前依据；`README.md` 仅顶部“当前活跃主线”说明有效，
其余是 200H 历史记录。

## 恢复开发：先读这些

1. `instrec_fpga/docs/STATUS.md` —— **唯一实时状态源**（当前阻塞、证据、下一步）；变更史见 `docs/CHANGELOG.md`。
2. `instrec_fpga/docs/HANDOFF_SNAPSHOT_20261027.md` —— 资产清单与踩坑记录（其 4.1 节已被 STATUS 更新覆盖）。
3. `instrec_fpga/docs/sdd/{spec,design,tasks}.md` —— 69 条需求 / 17 模块设计 / 44 任务与 DoD。
   （`.codeartsdoer/` 被自身 `*` 规则整体忽略，**不要只依赖那里的副本**。）
4. 记忆目录 `C:\Users\menss\.codeartsdoer\memory\D--0000-111-001-Pango-ZGTC_RISC_CPU`：优先
   `project-multi-phase-workflow-state.md`、`project-instrec-quant-contract-facts.md`、`project-instrec-npu-golden-baseline.md`。

## 当前状态（2026-10-28，详见 `instrec_fpga/docs/STATUS.md`）

- **M0/M1 位流均已产出并归档**：M0 `C517736C…`、M1 `BD40D10A…`，M1 All Constraints Met。
  收敛手段：`db_norm` 4 拍、`standardize` 5 拍流水，位级结果不变。
- **板级已确认 `core_clk` 起振**：`core_probe` 诊断位流在 COM5 收到 13 个 `C`。
  更早的 `done=0`（状态寄存器 `0x00180C80`）已由重新 program 修正为 `0x081FFCA0`。
- **BOOT 乱码已修**：`uart_debug` 的字符串字面量位序假设错误，已改为显式 ASCII case 表
  （位流已构建，待 USB 恢复后验证）。
- **M2 编译闭环**：`wdma`（权重+48 拍契约）、`conv_engine`、`pool_engine`、`gap_unit`、
  `fc_engine`（bias/M/shift 三流）、`softmax_top`、`weight_loader`（写+读回）、`npu_top`
  全链例化；`instrec_top` 已例化 `npu_top`（start/feat 暂置 0），全量构建
  **All Constraints Met，WNS +1.059**，sha256 `07062C4E…`。
- **NPU 资源实测**：LUT 19522/66600 (29.3%)、DRM 34.5/155 (22.3%)、APM 35/240 (14.6%)。
- **M3**：`bars_disp`/`spectrum_disp`/`font_rom`/`ui_overlay`/`bars_data`/
  `ui_coord_delay`/`feat_page_buf`/`feat_copy_engine` 均单编译通过；
  `ui_overlay` 已并入 `ui_renderer`，概率条链路已接顶层（WNS +1.443）；spectrum 顶层接线待做。
- **待接**：spectrum 顶层接线（feat_copy + page_buf + mux）、端到端对拍。
- **板级阻塞**：FTDI 下载器反复掉线（CP2102 正常）；已停止强杀 `cdt_*`，改用 TCL `exit`。

## 下一步（按序）

1. FTDI 恢复后 `python scripts/board_check.py --sbit build/instrec-latest.sbit`：
   确认 `INSTREC BOOT` 可读、`done=1`；再跑 `weight_upload.py` 看 `WOK`。
2. 接 mel feat 读口与 m1 仲裁，然后跑单层 conv1 对拍（契约已由测试向量固定）。
3. M3：`spectrum_disp`/`font_rom` 并入 `ui_renderer`。

## 命令（在 `instrec_fpga/` 下执行）

```powershell
python scripts/check_rtl.py        # SV-2005 词法检查，必须 0 violation（31 个 .v，hdmi demo 默认排除）
python -m pytest -q                # 全量 88 passed，约 34 s
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1
python scripts/board_check.py --sbit build/instrec-latest.sbit   # 一键板级检查
```

- 构建脚本必须 **PowerShell 5.1 兼容**：只用 `[System.IO.File]::WriteAllText` + BOM-less UTF8，不用
  `Set-Content -Encoding UTF8`，不用 PS7 三元 / `??` / `&&`。`Start-Process` 必须带 `-Wait`，否则 ExitCode 不可靠。
- 产物在 `build/pds/<时间戳>-<随机>/`（gitignored）；成功时复制为 `build/instrec-latest.sbit` 并写
  `instrec-latest.json`（含 StageStatus / WNS / SHA-256 / 资源），同时把日志归档到 `reports/`。
  失败或被中断的 run 只留在 `build/pds/` 下，**不会**自动进 `reports/`。
- **脚本不校验 WNS**：只要产出了位流就报成功。判断收敛必须读 `instrec-latest.json` 的 `Wns`
  或 `report_timing/*.rtr` 的 `Design Summary`。
- 环境（用户级变量）：`PDS_ROOT=H:\GG\pango\PDS_2022.2-SP6.4`，
  `PANGO_LICENSE_FILE=E:\License\pango\new_pds_F4A80DA47D72.lic`。
- **一次只能跑一个 `pds_shell.exe`**。`run_pds_full.ps1` 本身不查并发，启动前自己确认。
- **JTAG 侧的 `cdt_js`（jtagserver，会显示成 UI）只允许一个实例**：它持有 FT2232H 的 D2XX 句柄。
  强关它、或再开第二个，都会让下载器从 PnP 消失（`CM_PROB_PHANTOM`），只能物理重插恢复。
  规则：`board_check.py` 一律**复用**已存在的 `cdt_js`（端口没起来就等，绝不新起）；
  任何脚本都不得 `terminate()`/`Stop-Process` `cdt_js`/`cdt_cfg`；TCL 一律以 `exit` 收尾。
  `tests/test_board_flash_safety.py` 锁死这三条，改烧录脚本后必须跑它。
- 本机 **WSL 不可用**（Ubuntu 发行版的 vhdx 缺失，启动报 `ERROR_PATH_NOT_FOUND`），因此没有 iverilog/verilator；
  `cpu/` 的 WSL 仿真与 iverilog 命令在本机跑不了。instrec 的验证只有 Python golden 对拍 + 板级实测。
- CPU 历史工程的 Windows PDS 路径仍可用：`powershell -File pds_cpu_100h/scripts/run_pds_full.ps1`、
  `powershell -File pds_cpu_100h/scripts/run_pds_153.ps1 -ClockHz 120000000`。100H 上 153 MHz 不可达。

## RTL 硬约束（instrec，SV-2005 子集）

- 禁 `always_ff` / `always_comb` / `always_latch`、`logic`、`interface`、`unique` / `priority`、空 `.port()`；
  组合块一律 `@*`。
- 模块名 = 文件名 = 单文件单模块；信号 `snake_case`，参数 `UPPER_SNAKE_CASE`，注释纯 ASCII 英文。
- `check_rtl.py` 只是词法检查，**查不出 PDS 解析器限制**：
  - 不支持参数基数字面量：`19'dPARAM` 要改写成 `PARAM[18:0]`；
  - 不支持 `generate` 内嵌 `generate`：用裸 `if/else` + 条件 assign（嵌套 generate-for 体内同样适用）。
  这两类只在 compile 阶段暴露，lint 全绿不代表能综合。
- 约束加载顺序是语义依赖：`clock_groups_async.fdc` 必须在 `ddr3_100h.fdc` **之后**，否则整条 clock group
  被静默忽略（PDS 逐条执行约束）。`gen_ddr3_fdc.py` 可重生成 DDR3 引脚约束。

## 数值与 DDR3 契约（改 RTL 前必读）

- `scripts/golden_pipeline.py` 是**位级真值**（与浮点精确数学 0 LSB）。本机 torch 2.14.1 的 QEngine 是 oneDNN，
  tile 边界有 21~67 LSB 噪声，**对拍只认 golden，不认 torch**。
- requant 必须 **round-half-even**；截断会经 432-tap 卷积放大到 ±32 LSB/层。GAP 的 `>>6` 同型舍入。
- 量化唯一真源是 `scripts/outputs/layer_contract.json`：`deploy/weights/*_bias_int32.npy` 已被 astype 截断损坏；
  per-channel shift ∈[37,53]，需 ≥6 bit；conv1 padding 填 `zp_in=49`；fc2 `zp_out=57`；feat 是 uint8、`zp_in=49`。
- softmax 单类主导饱和 65535（Q0.16）属预期语义，UI 显示 99% 不是 bug。
- NCO STEP = **3507557**（design.md 的 3509057 是笔误）。
- DDR3 IP 契约：无 `axi_wvalid` / `axi_rready` / `axi_b`；写完成 = `axi_wready && beat_cnt==len`；
  读前必须 dummy-write（已封装在 `ddr3_ctrl_axi`）；R 通道不能反压，控制器每周期都要能接。主口固定：
  m0=audio / m1=NPU 权重 / m2=mel_engine / m3=self_test。

## 工程边界与提交约定

- `instrec_fpga/` 之外目录**零改动**（REQ-BLD-004）；`ai_pcb/`、`pcb-aoi/` 已搁置。
- 分支是 **XSY**（不是 main）；**不要自动 push**，除非用户明确要求。
- 不提交 `build/`、`reports/*.log`、`__pycache__`、`account.txt`、证书/令牌。
- `instrec_fpga/ipcore/` 已用 `!instrec_fpga/ipcore/` 例外纳管：DDR3 `.vp`、PLL `.idf/.v` 是重建必需资产，
  不要新增会把它排除的全局规则。
- `.gitattributes` 对 `cpu/experiments/**`、`cpu/docs/evidence/**` 设 `-text`：逐字节保全证据，禁止格式化或换行重写。
- `cpu/experiments/` 是约 148 个冻结的微架构实验，不要清理、不要跨目录重构。
- 失败构建、被否位流、抓取记录一律保留，不覆盖。

## 交接纪律（每次会话必须执行）

1. 结束前按序更新：`instrec_fpga/docs/STATUS.md`（状态/阻塞/证据/下一步）→ `docs/CHANGELOG.md` 追加一条 →
   记忆 `project-multi-phase-workflow-state.md` → **git commit**（不 push）。
2. **工作区不留未提交的 RTL/约束/脚本改动**。2026-10-27 已发现 4 个未提交改动把已修复的 AXI 端口方向、
   13-bit 超时、读前 dummy-write 回退成旧 bug；原始 diff 留档在 `instrec_fpga/reports/workspace-revert-20261027.diff`。
3. 构建前先 `git status` + `git diff`：确认没有意外的 `M` 文件，确认没有把修复改回旧实现。
4. 试验性代码放 `build/`、临时分支或实验目录，不要混入主线 RTL。
5. 新资产（IP、SDD、权重、golden 数据）必须落在 `instrec_fpga/` 内且能被 git 跟踪；
   不要只留在 `.codeartsdoer/`（自身 `*` 忽略）、本机临时目录或对话里。
6. 关闭 PDS/后台进程再结束会话；被中断的构建要在 STATUS 里写明“无位流”，不要让它看起来成功。

## 历史工程事实（避免误报）

- 200H（PG2L200H）上 153 MHz / 511.318 CoreMark 是历史成绩；100H 上 153 MHz 不可复现，可交付点是
  **120 MHz / 383.0 CoreMark**（`cpu/docs/MIGRATION_100H_20261025.md`）。
- CoreMark 用 `6000 × clock / timed_cycles`（板载 64-bit 计数器）；不要引用 UART 的 `Iterations/Sec` 整数行（如 545）；
  CoreMark、CoreMark/MHz、CoreMark/LUT 三项分开报，不要做 Pareto 宣称。
- 上板跑通 ≠ 认证：电气、CDC、长时稳定性均未做。

## 权威文档

- `instrec_fpga/reports/ddr3_ctrl_checklist.md` —— DDR3 自检失败时的两个回退参数。
- `instrec_fpga/docs/m0_top_integration.md` —— M0 顶层接线。
- `docs/skills/pango-pg2l100h-dev/SKILL.md` —— 100Pro 板卡的 PDS / JTAG / 串口流程与引脚。
- `cpu/docs/AI_HANDOFF_153MHZ.md`、`cpu/docs/PROJECT_HANDOVER_153MHZ.md` —— 仅用于理解 200H 历史。