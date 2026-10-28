# InstRec-FPGA 变更日志

> 每次会话结束前追加一条：时间、做了什么、结论、证据路径。倒序，最新在上。
> 状态汇总见 `docs/STATUS.md`。

## 2026-10-29 06:15 — 概率条链路接入顶层

- `instrec_top` 串联 `ui_coord_delay`（3 拍坐标）→ `bars_data`（8 类 pct）→
  `bars_disp` → `ui_renderer.bars_*`；spectrum 仍 tie-off。
- 全量构建 All Constraints Met，WNS +1.443 / WHS +0.201。

## 2026-10-29 05:00 — 概率数据跨域

- 新增 `bars_data.v`：core 域锁存 8 类百分比，pix 域两级同步，
  3 s 窗口更新率下允许瞬时混值。单编译通过。

## 2026-10-29 04:25 — ui_overlay 并回 ui_renderer

- `ui_renderer` 例化 `ui_overlay`，de/hs/vs 延迟由 3 拍改为 4 拍；顶层 spec/bars 暂 tie-off。
- 全量构建 All Constraints Met，WNS +1.357 / WHS +0.184。

## 2026-10-29 03:20 — M3 图层合并

- 新增 `ui_overlay.v`：bars > spectrum > base 的优先级合成，1 拍寄存输出。
- 单编译通过；尚未并回 `ui_renderer`。

## 2026-10-29 03:00 — M3 字库

- `scripts/gen_font_hex.py` 用 Consolas 渲染 95 个 ASCII 字符为 8×16 点阵
  （1520 字节），输出 `src/ui/font8x16.hex`。
- 新增 `font_rom.v`（同步读），单编译通过；`build_full.tcl` 增加 `src/ui/*.hex` 的
  work_dir 复制。

## 2026-10-29 02:25 — M3 谱图模块

- 新增 `spectrum_disp.v`：258x64 Mel 页映射到 512x256 窗口（col=x*258>>9、
  row=y>>2），5 档伪彩，同步读地址 + 1 拍对齐。
- 单编译通过，尚未并入 `ui_renderer`。

## 2026-10-29 01:40 — npu.start 触发

- `instrec_top` 用 mel_engine 的 `mel_npu_start` 触发 NPU，`NPU_ENABLE` 参数默认 0。
- 全量构建 All Constraints Met，WNS +1.406 / WHS +0.270；M2 顶层接入完成。
- 剩余：端到端仿真/板级对拍。

## 2026-10-29 00:55 — m1 仲裁接通

- `instrec_top` m1 仲裁：`weight_loader` busy 时独占，空闲时交给 NPU wdma；
  `rd_data_1/rd_valid/done` 按 `wl_busy` 门控。
- 全量构建 All Constraints Met，WNS +1.406 / WHS +0.270，sha256 `90F531C0…`。
- 待接：sys_ctrl 触发 npu.start。

## 2026-10-28 23:40 — mel feat 读口接通

- `npu_top` 改为 feat 地址/数据接口（地址 0..16511，数据 1 拍后有效）；
  `instrec_top` 删除 `mel_feat_rd_addr` 的 tie-off 并连接 mel_engine。
- 全量构建 All Constraints Met，WNS +1.361 / WHS +0.157，sha256 `895E4F43…`。
- 待接：m1 在 weight_loader 与 npu 间的仲裁、sys_ctrl 触发 npu.start。

## 2026-10-28 21:45 — npu_top 顶层例化

- `instrec_top` 例化 `npu_top`（start/feat 置 0），顶层拓扑定型。
- 全量构建 All Constraints Met，WNS +1.059 / WHS +0.248，sha256 `07062C4E…`；耗时 19 分钟。
- 待接：mel feat 读口、m1 在 weight_loader/npu 间的仲裁。

## 2026-10-28 20:35 — NPU 资源实测

- 用只暴露 clk/rst/start/din 的 wrapper 对 `npu_top` 做 synthesize+dev_map（避免 DRC-0018 全端口绑定）：
  LUT 19522/66600 (29.3%)、DRM 34.5/155 (22.3%)、APM 35/240 (14.6%)。
- 结论：4 个 conv 实例 + pool/gap/fc/softmax/wdma 的资源可控，顶层例化可行。

## 2026-10-28 19:35 — fc 契约接入，M2 编译闭环

- `wdma` 增加 fc 模式：3×COUT 拍（bias/M/shift 各 COUT），start 放宽到 fc2。
- `npu_top` 将 fc1/fc2 的 b/m/s 按层门控接入；编译通过。
- M2 各模块与契约流在编译层面闭环；端到端仿真/板级对拍与 instrec_top 例化仍待做。

## 2026-10-28 18:50 — npu_top 契约门控

- wdma 的 48 拍契约按 `layer` 门控分发给 conv1..conv4，共享数据总线；编译通过。
- fc1/fc2 契约仍 tie-off：fc 需要 3×COUT 拍，与 conv 的 48 拍/组不同。

## 2026-10-28 18:15 — wdma 契约流实现

- `wdma` 新增契约读入（层启动读 bias/M/shift 到片上 RAM）与每组 48 拍输出；
  fc2 8 通道 pad 到 16 lane；单编译通过。
- 未接 `npu_top`：4 个 conv 需按层门控契约 valid，避免同时写 shadow bank。
- check_rtl 35 个 .v、0 violation。

## 2026-10-28 17:15 — wdma 组流模型

- 新增 `tests/test_wdma_group_model.py`（3 项）：每组 48 拍契约 + 组内 tap 顺序与内容、
  fc2 8 通道 pad、conv1 144B 组距。
- 全量 114 passed。

## 2026-10-28 16:50 — weight_loader 接入顶层

- `instrec_top` 例化 `weight_loader`：UART 字节共用、TX 仲裁（加载期优先）、
  m1 写/读通道、`weight_ok/weight_err` 接 `sys_ctrl`。
- `REQUIRE_WEIGHT` 仍为 0，M1 启动链不被加载阻塞；加载链已可板级验证。
- 全量构建成功，耗时 15 分钟。

## 2026-10-28 15:30 — M3 概率条模块

- 新增 `src/ui/bars_disp.v`：8 类概率条，pct*4 定长、slot 内偏移、按类取色；
  单编译通过，尚未并入 `ui_renderer` 的 3 拍流水。

## 2026-10-28 14:40 — requant 位级判据

- 新增 `tests/test_requant_model.py`（5 项）：正/负 exact-half 归偶、截断反例、
  u8 双端饱和、随机 512 向量与独立标量实现逐值一致。
- 全量 111 passed。

## 2026-10-28 13:55 — sys_ctrl 权重自检环与 M2 接入蓝图

- `sys_ctrl` 新增 `ST_WEIGHT`：等 `weight_ok` 后放行 `sys_run`，`weight_err` 进 SAFE_ERR；
  `REQUIRE_WEIGHT` 默认 0（保持当前 M1 链路），接入 weight_loader 后置 1。
- 新增 `docs/m2_top_integration.md`：m1 口仲裁、自检链、weight_loader/npu_top 接线与验证顺序。
- sys_ctrl 单编译通过；check_rtl 34 个 .v、0 violation。

## 2026-10-28 12:30 — fc_engine 契约接口补齐

- `fc_engine` 新增 bias 输入与独立 b_valid/m_valid/s_valid 三条加载流，
  bias RAM 在每组首拍（k_cnt==0）初始化累加器，替代原先的“归零后累加”。
- `npu_top` 例化同步更新，PDS 编译通过；契约流生产者（wdma）仍是唯一缺口。
- check_rtl 34 个 .v、0 violation。

## 2026-10-28 12:00 — core_clk 确认与 BOOT 乱码修复

- 烧 `core_probe` 后 COM5 收到 13 个 `C`：**core_clk 已起振，core 域退出复位**。
- BOOT 行乱码定位：`uart_debug` 的字符串字面量位序假设错误，板级收到 `00 00 00 00 4e ...`；
  改为显式 ASCII case 表，并修正 `DDR3 SELFTEST...` 长度为 17 字节。位流已构建，待验证。
- 移除 `core_probe` 的 UART 仲裁（避免干扰 BOOT），文件保留作诊断资产。
- FTDI 再次掉线；`terminate()` 后仍发生，下一步用 TCL `exit` 自然退出。

## 2026-10-28 07:40 — 契约流事实与 fc_engine 缺口

- 新增 `tests/test_contract_stream.py`（4 项）：conv 组契约 48 拍、fc 契约 3×COUT 拍，
  逐值与 `layer_contract.json` 一致；shift 全域落在 37..53。
- 记录 `fc_engine` 接口缺口：无 bias 输入、M/shift 共用 `c_valid`，需拆分后才能真正接契约。
- 全量 106 passed。

## 2026-10-28 06:30 — npu_top 数据通路整合

- `npu_top.v` 全链例化：conv1→pool1→…→conv4→pool4→gap→fc1→fc2→softmax，
  层序列、GAP 结果缓存/回放、fc2→logits 总线完成；PDS 编译通过。
- 唯一缺口：48 拍 bias/M/shift 契约流（conv/fc 均 tie-off），端到端功能尚未成立。
- 修正空端口 `.port()` 与 output reg 连实例输出的两处 SV-2012/PDS 报错。
- 全量 102 passed；check_rtl 34 个 .v、0 violation。

## 2026-10-28 05:15 — wdma 初版与镜像布局验证

- 新增 `tests/test_wdma_layout.py`（4 项）与 `tests/test_wdma_stream_model.py`（5 项）：
  确认所有层权重区 32B 对齐、conv1 每组 144B/27 tap 尾部单 tap、fc2 tap=8B。
- `wdma.v` 初版：整层 32B beat 连续读（burst≤16）、16 深 FIFO、16B/8B tap 切分、
  `w_ready` 反压握手、组边界脉冲；PDS 单编译通过，**未仿真/未上板**。
- 全量 102 passed；check_rtl 34 个 .v、0 violation。

## 2026-10-28 03:40 — softmax 定点单元

- 新增 `softmax_top.v`：Q16.15 预缩放、减 max、Q6.9 饱和、512 项 exp LUT、
  组合 round-half-up 除法、top1/percent；S_Q15 按实测 fc2 契约修正为 9197。
- 导出 `src/mel/exp_lut.hex`（512×Q0.16）。
- `tests/test_softmax_model.py` 5 项（Q15 常量、LUT、归一、单类饱和、percent）。
- wdma 草稿因「DDR3 2 tap/beat vs conv 1 tap/cycle + burst≤16 + 读侧不可反压」
  需读 FIFO，未入库。
- 全量 93 passed；check_rtl 33 个 .v、0 violation。

## 2026-10-28 02:10 — npu_top 控制壳与一键板级脚本

- 新增 `npu_top.v`：11 层序列（conv1→pool1→…→fc2）、busy/done、npu_cycles、
  REQ-REL-002 超时标志；编译通过，数据通路与 wdma 留待接入。
- 新增 `scripts/board_check.py`：FTDI 检查→烧录→读状态寄存器→抓串口，一条命令完成。
- check_rtl 32 个 .v、0 violation。

## 2026-10-28 01:35 — FC 引擎与流式模型测试

- 新增 `fc_engine.v`：16 并行输出、CIN 拍/组、复用 requant_unit；
  fc2 的 8 通道按上取整 pad 到 1 组（GRP_NUM=(COUT+15)/16），编译通过。
- 新增 `tests/test_conv_model.py`（流式扫描顺序与向量化数学逐位一致，2 项）
  与 `tests/test_fc_model.py`（ReLU rail / fc2 logits 容器，3 项）。
- 全量回归 88 passed；check_rtl 31 个 .v、0 violation。

## 2026-10-28 00:55 — GAP/帧解析落地 + core_clk 诊断位流

- 新增 `gap_unit.v`（256 通道 GAP + round-half-even >>6），单编译通过；
  `tests/test_pool_gap_model.py` 增补全通道路径，6 项通过。
- 新增 `scripts/uart_frames.py`（design 9.2 帧解析/重组/对拍）与
  `uart_capture.py --frames`；`tests/test_uart_frames.py` 6 项通过。
- 新增 `core_probe.v` 并集成顶层：core_clk 域复位后发 16 个 `C`，用于判断
  DDR3 IP 的 core_clk 是否起振；诊断位流 run `20261028-002353-43f24360` 已构建，
  FTDI 掉线未能烧录。诊断版验证后决定保留或移除。
- 全量回归 83 passed；check_rtl 30 个 .v、0 violation。

## 2026-10-27 23:55 — 板级根因收窄 + M2 三模块落地

- 板级突破：`cfg_read_device_property -mode 3` 直读状态寄存器，早期 `0x00180C80` 中 **done=0**，
  说明此前“烧录成功”后 FPGA 没有有效配置；重新 program 后 `0x081FFCA0`，done=1、crc_err=0。
- 无复位探针（27 MHz 发 `P`）烧录后 COM5 收到 46 个 `P`，证明 27 MHz/UART/CP2102 链路正常；
  M1 烧录后 done=1 但串口 0 字节，问题收窄到 core_clk / sys_ctrl。
- 随后 FTDI 再次掉线，板级暂停；恢复后直接做 core_clk 探针。
- M2：`conv_engine.v` 修复两处先使用后声明并单独编译通过；新增 `weight_loader.v`（帧解析+CRC16+
  写 m1+读回摘要）、`pool_engine.v`（2×2 floor、奇偶列分 bank、同步读）；
  `scripts/weight_upload.py` + 8 项测试；`tests/test_pool_gap_model.py` 5 项。
- 全量回归：76 passed；check_rtl 28 个 .v、0 violation。

## 2026-10-27 12:23 — M1 时序收敛、位流归档

- `db_norm` scan 2 改 4 拍流水（DIFF/MUL/SQ/ACC），`standardize` 量化扫描改 5 拍流水
  （DIFF/MUL/QPROD/Q）；算术顺序不变，位级结果不变。
- 第一轮 run `20261027-115358-d5a76b9d`：WNS 由 -4.401 改善到 -1.316（db_norm 路径消失，
  剩余违例转到 `u_standardize`）。
- 第二轮 run `20261027-121101-5c24a968`：**All Constraints Met**，WNS +1.438、WHS +0.224，
  `ddrphy_sysclk` +0.837；sha256 `BD40D10A…`；六阶段 OK。
- 归档 `releases/m1-20261027/`（sbit + manifest + timing.rtr + SHA256SUMS + README）。
- 修复 `run_pds_full.ps1` 的 `Get-FileHash` 依赖（本机 PS 5.1 该 cmdlet 缺失），改用 .NET SHA-256。
- 新增 `scripts/jtag_scan.tcl`、`scripts/jtag_program_m1.tcl`。
- 板级：CP2102 串口 COM5 在线；USB Cable II 未被识别（cable 列表空），JTAG 扫描 `No devices detected`，
  待接入下载器后继续。

## 2026-10-27 11:25 — 里程碑位流归档入库

- `releases/m0-20261027/`：InstRec M0 位流 + manifest + SHA256SUMS（sha256 校验与 manifest 一致）。
- `pds_cpu_100h/releases/120mhz-20261025/`：100H 120 MHz 交付位流 + manifest + CoreMark 记录 + SHA256SUMS。
- `.gitignore` 仅对两个 `releases/**` 放开 `*.sbit`；`.gitattributes` 对这些目录设 `-text`，防止二进制被换行改写。
- 其余位流仍视为可重建产物，不入库；失败构建日志保留在 `build/` 磁盘。

## 2026-10-27 11:15 — 工作区/文档/版本整理

- 恢复 4 个被误回退的已跟踪文件（`.gitignore`、`DEV_SNAPSHOT.md`、`cpu/fpga/rv32_ddr3_ip_wrapper.sv`、
  `cpu/rtl/rv32_burst_ddr3.sv`）。原 diff 留档：`reports/workspace-revert-20261027.diff`。
  其中 2 个 RTL 的改动会把已修复的 AXI 端口方向、13-bit 超时、读前 dummy-write 回退成旧 bug。
- `.gitignore` 增加 `!instrec_fpga/ipcore/`：DDR3 / GPLL IP 源文件是重建必需资产，此前被全局 `ipcore/` 忽略。
- SDD 三份文档复制到 `docs/sdd/`（`.codeartsdoer/` 被自身 `*` 规则整体忽略，交接会丢）。
- 新增 `docs/STATUS.md`（唯一实时状态源）与本文件。
- `instrec_fpga/` 首次纳入 git（此前 0 个文件被跟踪）：commit `1298395`，180 个文件。
- 搁置路线的 AI RTL 单独存档：commit `2abf5ed`。
- 证据从 `build/` 提取到可追踪位置：`reports/m0-manifest-20261027.json`、
  `reports/m1-timing-20261027-104218.txt`。
- 核对基线：pytest 63 passed；check_rtl 26 文件 0 violation。

## 2026-10-27 10:56 — M1 语法修复后的首次完整构建

- run `20261027-104218-acb7a788`：compile/synthesize/dev_map/pnr/report_timing 全过，
  gen_bit_stream 被会话结束中断，无 M1 位流。
- 新阻塞：`ddrphy_sysclk`（core_clk，125 MHz）WNS -4.401 ns / TNS -487.619 / 200 endpoints。
- 根因定位：最差路径在 `u_mel_engine/u_db_norm` 乘加组合链（17.539 ns，5 levels），非 DDR3 IP。
- 对照：`pds_cpu_100h` 同 IP `ddrphy_sysclk` = +2.110 ns。

## 2026-10-27 10:19 — 交接快照记录的语法错误全部修复

- `mel_engine.v`：参数基数字面量 `19'dPARAM` → `PARAM[18:0]`。
- `standardize.v`：`var_q16_u32` reg/wire 重复声明 → `var_q16_comb` 组合 + 快照。
- `fft2048_sdf.v`：去掉 generate 内嵌 generate，改裸 `if/else` + 条件 assign。
- `HANDOFF_SNAPSHOT_20261027.md` 第 4.1 节“fft 未修”的结论已过时。

## 2026-10-27 00:06 — M0 位流产出

- run `20261027-000612-a71f1451`，六阶段 OK，All Constraints Met，WNS +1.757。
- sbit sha256 `C517736C7E61937521BC1776DDA4ACAC66F0373DF7E0FACDD86AEC017DD2EDAC`。
- 资源 LUT 6201 (9%) / FF 6743 (5%) / BKCL 6/6。尚未上板。