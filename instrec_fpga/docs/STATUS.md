# InstRec-FPGA 当前状态（STATUS）

> 本文件是**唯一实时状态源**，优先于任何交接快照与记忆。每次会话结束前必须更新，
> 并在 `CHANGELOG.md` 追加一条。最后更新：2026-10-28 23:40。

## 一句话

InstRec 8 类乐器识别（INT8 CNN）正在移植到盘古 100Pro+（PG2L100H-6IFBG676）纯 FPGA 管线。
**M1 时序收敛并归档；板级已定位到 `done=0` 配置问题并用探针验证了 27 MHz/UART 链路；M2 已交付 conv_engine 修复、weight_loader、pool_engine 与上位机上传协议。**

## 里程碑

| 里程碑 | 状态 | 关键证据 |
|---|---|---|
| P0 工具链 + Python 金标准 | 完成 | `pytest -q` 63 passed；`golden_pipeline.py` 位级真值 |
| M0 I2S→DDR3→HDMI 波形 | 完成（未上板） | run `20261027-000612-a71f1451`，sha256 `C517736C…`，WNS +1.757 |
| M1 Mel 特征引擎 | **构建完成、时序收敛、待板级对拍** | run `20261027-121101-5c24a968`，sha256 `BD40D10A…`，WNS +1.438 / All Constraints Met |
| M2 INT8 NPU | 约 45% | `requant_unit`/`conv_engine`（编译通过）+ `weight_loader`（写+读回）+ `pool_engine` + `weight_upload.py`；wdma/gap_fc/npu_top 未做 |
| M3 UI 集成 | 未开始 | `src/ui/` 仅 M0 的网格 + 波形 |

## 当前状态

### 板级（2026-10-27 深夜，关键突破）

- 用 `cfg_read_device_property -device_index 0 -mode 3` 直接读状态寄存器：早期读数为 `0x00180C80`，
  其中 **`done=0`、`done_i=0`**（`pll_lock=1`、`init_complete=1`）→ 说明此前所有“烧录成功”后
  FPGA 内根本没有有效配置，这解释了 M0/M1/探针全部无输出。
- 重新 `program` 后复读为 `0x081FFCA0`：**`done=1`、`done_i=1`、`crc_err=0`**，配置确实生效。
- 无复位探针（27 MHz 发 `P` + `rst_n` 电平编码）烧录后，COM5 **收到 46 个 `P`** →
  27 MHz 时钟、UART 位层、C18/C24 引脚与 CP2102 链路全部正常。
- 但 M1 位流烧录后 `done=1` 而串口仍 0 字节 → 问题已收窄到 **core_clk（DDR3 IP 125 MHz）或 sys_ctrl**。
- 随后 FTDI 下载器再次从系统掉线（CP2102 仍在线），板级工作暂停；恢复后直接做 `core_clk` 探针。

### M1 构建

- 最新构建 `20261027-121101-5c24a968` 已归档 `releases/m1-20261027/`，All Constraints Met，
  WNS +1.438 / WHS +0.224；复位链已改为 `.resetn(rst_n)` 直连，后续重建 WNS +1.603。
- 构建脚本：`Get-FileHash` 在本机 PS 5.1 缺失，已改用 .NET SHA-256；PDS 对该器件不支持多线程
  （`-max_parallel_jobs`/`-number_of_router_thread` 均报 Flow-0182），单线程约 11~13 分钟。

### M2

- `conv_engine.v`：修正两处“先使用后声明”，PDS 单独编译通过；组契约注释明确为
  “每拍一个 valid、16 bias → 16 M → 16 shift”。
- `weight_loader.v`：UART 帧解析 + CRC16 + 按帧写 m1 + ACK/NAK 重传 + 全镜像读回摘要比对（WOK/WERR），编译通过。
- `pool_engine.v`：2×2 floor、奇偶列分 bank、同步读两拍流水，编译通过。
- `scripts/weight_upload.py` + 测试：2701 帧，CRC-16/CCITT-FALSE，8 项测试通过。
- `tests/test_pool_gap_model.py`：形状链 / floor / channel-local / GAP 语义，6 项通过。
- `gap_unit.v`：256 通道 × 64 值累加 + round-half-even >>6，编译通过。
- `uart_frames.py` + `uart_capture.py --frames`：design 9.2 帧解析/重组/对拍，6 项测试通过。
- `core_probe.v`（诊断）：core_clk 域复位后发 16 个 `C`，已集成顶层并构建 run `20261028-002353-43f24360`，
  **尚未烧录**（FTDI 仍掉线）。这是诊断版，验证后决定保留或移除。
- `fc_engine.v`：16 并行输出、组数为上取整（fc2 8 通道 pad 到 1 组）、复用 requant_unit，编译通过。
- `tests/test_conv_model.py`（流式扫描顺序 vs 向量化，2 项）与 `tests/test_fc_model.py`（3 项）通过。
- `npu_top.v`：层序控制壳（conv1→…→fc2）、busy/done、npu_cycles、timeout_flag 已编译通过；
  数据通路与 wdma 尚未接入（`layer_start/layer_done` 为接入点）。
- `scripts/board_check.py`：一键设备检查→烧录→读 done→抓串口。
- `softmax_top.v`：8 路定点 softmax（Q16.15 预缩放、Q6.9 饱和、512 项 exp LUT、
  组合 round-half-up 除法、top1/percent），单编译通过；`tests/test_softmax_model.py` 5 项通过。
- `wdma.v` 初版落盘：整层权重按 32B beat 连续读（AXI burst ≤16）、16 深 FIFO 吸收
  2:1 速率差、16B/8B tap 切分、`w_ready` 反压握手、组边界脉冲；PDS 单编译通过。
  **尚未仿真/板级验证**。
- `npu_top.v` 整合骨架：conv1→pool1→conv2→pool2→conv3→pool3→conv4→pool4→gap→fc1→fc2→softmax
  全链例化，层序列、GAP 结果缓存与 fc1 回放、fc2→logits 总线已接；PDS 编译通过。
- `tests/test_contract_stream.py`（4 项）固定了契约地址与内容：conv 层每组 48 拍
  （16 bias + 16 M + 16 shift），fc 层为 3×COUT 拍；与 layer_contract.json 逐值一致。
- `fc_engine` 接口已补齐：bias/M/shift 拆成 b_valid/m_valid/s_valid 三条独立流，bias RAM
  在每组首拍初始化累加器；`npu_top` 随之重新编译通过。契约流的生产者（wdma）仍是唯一缺口。
- `sys_ctrl` 增加 `ST_WEIGHT` 自检环（REQ-REL-001 第 4 环）：`weight_ok` 放行 RUN，
  `weight_err` 进 SAFE_ERR；参数 `REQUIRE_WEIGHT` 默认 0，接入 weight_loader 后置 1。
- `docs/m2_top_integration.md`：m1 仲裁、自检链、接线与验证顺序。
- `tests/test_requant_model.py`（5 项）：round-half-even 正/负半值、截断反例、u8 饱和、随机向量逐值对拍。
- `bars_disp.v`（M3）：8 条概率条，pct×4 定长、按槽位取色，单编译通过；尚未接入 `ui_renderer`。
- `tests/test_wdma_group_model.py`（3 项）：固定每组「48 拍契约 + 组内 tap」顺序与内容，
  fc2 的 8 通道 pad 到 16 lane。
- `wdma` 契约流已实现：层启动读 bias/M/shift 到片上 RAM，每组先发 48 拍再发 tap。
- `npu_top` 已按层门控把契约送给对应 conv（cb1/cm1/cs1 … cb4/cm4/cs4），四个 conv 共享数据总线。
- `wdma` 增加 fc 模式（3×COUT 拍）；fc1/fc2 的 b/m/s 已按层门控接入，`npu_top` 编译通过。
- **M2 编译闭环**：权重/契约流、conv/pool/gap/fc/softmax 全链、weight_loader、sys_ctrl 自检环均已落地并编译。
- **NPU 资源实测（wrapper 综合，2026-10-28）**：LUT **19522/66600 (29.3%)**、
  DRM **34.5/155 (22.3%)**、APM **35/240 (14.6%)** → 4 个 conv 实例方案资源可控。
  叠加 M0/M1 现有约 16K LUT，整机预计 ≈55% LUT、≈50% DRM。
- `instrec_top` 已例化 `npu_top`（`start/feat` 暂置 0，不改变 M1 行为），全量构建
  **All Constraints Met，WNS +1.059 / WHS +0.248**，sha256 `07062C4E…`。
- mel feat 读口已接：`npu_top` 输出 `feat_rd_addr`、消费 `feat_rd_data`（1 拍同步读），
  顶层删除原 tie-off；全量构建 **WNS +1.361 / WHS +0.157**，sha256 `895E4F43…`。
- 仍缺：m1 在 `weight_loader` 与 `npu` 间的仲裁、`sys_ctrl` 触发 `npu.start`、端到端对拍。
- **weight_loader 已接入 `instrec_top`**：UART 字节共用、TX 仲裁（加载优先）、m1 写/读通道、
  `weight_ok/weight_err` 接 `sys_ctrl`；`REQUIRE_WEIGHT=0` 保持 M1 链路不被阻塞。
  全量构建成功（15 分钟，比 M1 多约 3 分钟，资源增加）。
- 布局事实（`tests/test_wdma_layout.py`、`test_wdma_stream_model.py`，9 项通过）：
  所有层权重区 32B 对齐；conv1 每组 144B（27 tap）尾部仅 1 tap；fc2 tap 为 8B/4 个每 beat。

## 下一步（按序）

1. FTDI 恢复后：烧 M1 → 读 `done` → 若仍 0 字节，做 `core_clk` 探针（DDR3 IP 的 core_clk 驱动 uart_tx 发 `C`）。
2. 若 `core_clk` 起振则查 `sys_ctrl`/`uart_debug`；若不起振则查 125 MHz 差分 `ref_clk` 与 IP 时钟配置。
3. M2：`wdma` → `gap_fc` → `npu_top` → T-M2-07 逐层导出。

## 验证基线

- `python -m pytest -q` → **114 passed**（约 38 s）。
- `python scripts/check_rtl.py` → **34 个 .v，0 violation**（hdmi demo 默认排除）。
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