# InstRec-FPGA 工作快照（交接文档）

> **2026-10-27 11:15 状态更新（先读这段）**：本文第 4.1 节记录的“3 处语法错误”已全部修复
> （含 `fft2048_sdf.v` 嵌套 generate）。最新构建 `20261027-104218-acb7a788` 已走通
> compile→synthesize→dev_map→pnr→report_timing，新阻塞是 `db_norm` 组合时序
> （`ddrphy_sysclk` WNS -4.401 ns）。**实时状态以 `docs/STATUS.md` 为准**，逐次变更见
> `docs/CHANGELOG.md`；以下原文保留为 10:50 交接时刻的历史记录。

**日期**：2026-10-27 10:50
**撰写**：团队长（本会话）
**用途**：跨会话交接——恢复开发时以本文档为起点，配合 `.codeartsdoer/specs/instrec_fpga/{spec,design,tasks}.md` 三份 SDD 文档与团队任务板（12 项）。

---

## 一、项目一页纸

**目标**：将 InstRec 乐器识别系统（8 类 IRMAS，INT8 CNN）移植到紫光同创盘古 100Pro+ 开发板（PG2L100H-6IFBG676），纯 FPGA 硬件管线。

**架构**（已拍板，不再变动）：
```
I2S(FMC 扩展IO: bck=U20, lrck=T20, sd=V16) → i2s_rx(216MHz NCO)
  → audio_cdc_fifo → audio_sink(PCM 环写 DDR3, 波形降采样) →DDR3→ mel_engine(M1)
  → feat(64×258 uint8, zp=49) → NPU(M2: conv1-4+pool+GAP+fc1/fc2) → softmax
  → HDMI UI(M3: 波形/频谱/中文类别/置信度条, 1080p@60) + uart_debug
```

**硬约束**：SV-2005（无 always_ff/logic/interface；`.port()` 空连接禁用）；Windows PDS 2022.2-SP6.4 批处理（`powershell -File scripts/run_pds_full.ps1`，PS5.1 兼容）；本机**无仿真**（验证=Python bit-accurate 金标准对拍 + 板级实测）；英文注释/snake_case/模块名=文件名；工程根 `instrec_fpga/`，仓库其他目录零改动。

**里程碑**：M0 链路贯通 → M1 Mel 引擎 → M2 INT8 NPU → M3 UI 集成演示。

---

## 二、里程碑状态（截至今日）

| 里程碑 | 状态 | 说明 |
|---|---|---|
| Phase A/B/C（SDD 文档） | ✅ 完成 | spec.md 631行69需求 / design.md 945行 / tasks.md 483行44任务 |
| P0 工具链+金标准 | ✅ 完成 | 构建链实跑出位流×4、check_rtl.py（12 单测）、mel_tables/weights_image/layer_contract/golden_pipeline（Mel+NPU 全段）、全仓 pytest 63 passed |
| M0（I2S→DDR3→HDMI 波形） | ✅ 完成 | 18 模块集成、全量构建 All Constraints Met、sbit sha256=c517736c…（2026-10-27 00:06）、**板级冒烟 T-M0-10 未做（待上板）** |
| M1（Mel 特征引擎） | 🔶 RTL 全落盘、构建修复中 | 7 模块+整合层全交付、lint 0 违例；**集成构建报 3 处语法错误，2 处已修复、1 处（fft 嵌套 generate）未修，构建未重跑** |
| M2（INT8 NPU） | 🔶 起步 | requant_unit.v 已交付（严工）；conv_engine/wdma/weight_loader/pool/gap_fc/softmax 未做 |
| M3（UI 集成） | ⬜ 未开始 | spectrum/chars/bars 渲染、端到端联调 |
| 板级验证（T-M0-10 及全部） | ⬜ 未开始 | 100Pro 板卡在线可用，JTAG 烧录待执行 |

---

## 三、已交付资产清单（全部验收状态）

### 3.1 RTL（src/ 全树 25 个 .v，lint 0 违例）

| 模块 | 文件 | 状态 |
|---|---|---|
| audio_pll | src/ip/audio_pll.v（例化 pll_audio IP） | ✅ |
| i2s_clk_gen | src/audio/i2s_clk_gen.v（NCO STEP=3507557 修正值） | ✅ |
| i2s_rx | src/audio/i2s_rx.v（Philips 跨界位流） | ✅ |
| audio_cdc_fifo | src/audio/audio_cdc_fifo.v（帧对齐写） | ✅ |
| audio_sink | src/audio/audio_sink.v（637 行，win_tick 2.9954s） | ✅ |
| ddr3_wrapper | src/ddr3/ddr3_wrapper.v（实例名 I_ips_ddr_top） | ✅ |
| ddr3_arbiter | src/ddr3/ddr3_arbiter.v（4 主+P3 quota） | ✅ |
| ddr3_ctrl_axi | src/ddr3/ddr3_ctrl_axi.v（dummy-write 前置等 IP 契约） | ✅ |
| hdmi_tx_if | src/hdmi/hdmi_tx_if.v（复用 demo pll/sync_vg/ms72xx_ctl+iic_dri） | ✅ |
| ui_renderer + waveform_disp | src/ui/*.v | ✅（M0 版：波形+网格） |
| uart_tx/rx/debug | src/ctrl/*.v（预定义状态行+hex32 格式化） | ✅ |
| sys_ctrl + self_test | src/ctrl/*.v（BOOT→PLL→DDR→RUN 自检链） | ✅ |
| **instrec_top** | src/ctrl/instrec_top.v（587+55 行 M1 集成版） | 🔶 **mel_engine 已例化（m2 主口接线完成）但构建未过** |
| stft_framer + hann_rom | src/mel/*.v（530 行，reflect+加窗位级契约） | ✅ |
| fft2048_sdf | src/mel/fft2048_sdf.v（643 行，DIT-SDF 无缩放 s27/s28） | 🔶 **471 行嵌套 generate 语法错误未修** |
| tw_rom_s + 11 张 twiddle hex | src/mel/ | ✅ |
| mel_filter | src/mel/mel_filter.v（669 行，功率谱 rhu>>10+COO+log2） | ✅ |
| db_norm | src/mel/db_norm.v（249 行，259 帧全局 max+top_db） | ✅ |
| standardize | src/mel/standardize.v（424 行，恢复除法/开方+Q8.24 量化） | ✅ |
| mel_engine | src/mel/mel_engine.v（772 行整合，credit 节流+谱导出） | ✅（RTL 验收过，语法修复中） |
| **requant_unit** | src/npu/requant_unit.v（185 行，round-half-even 位级核心） | ✅（严工，验收质量优） |
| **conv_engine** | src/npu/conv_engine.v（275 行，16-MAC 组广播+tap 串行扫描+zp 中性填充读侧注入，golden 数据流镜像） | 🔶 严工交付于交接冻结时刻、lint 过；**完整性未及深验**——接手后核对 16 lane/层参数/行缓冲控制是否全部实现，若为部分实现需续写 |

### 3.2 Python 工具与测试（全仓 pytest 63 passed）

- `scripts/gen_mel_tables.py` + outputs（Hann Q1.15/COO 1820/log2 LUT/exp LUT，coe+json 双格式）
- `scripts/gen_weight_image.py` + outputs（weights_image.bin 691,040B + layer_contract.json——**量化契约唯一真源**）
- `scripts/golden_pipeline.py`（~1200 行：Mel 段+NPU 段位级金标准；`--stage pcm..probs --ref torch`）
- `scripts/export_twiddle_hex.py`（twiddle 表导出）
- `scripts/check_rtl.py`（SV-2005 lint，**两处工具缺陷已修**：wire 初始化表达式误报、字符串参数空连接误报——均已加回归用例）
- `scripts/build_full.tcl` + `scripts/run_pds_full.ps1` + `scripts/gen_ddr3_fdc.py`（构建链，出过 4 次位流）
- tests/：test_check_rtl 12 / test_mel_tables 5 / test_weight_image 6 / test_golden_mel 23 / test_golden_npu 8 / test_ddr3_arbiter_model 9

### 3.3 约束与 IP

- `constraints/instrec_top.fdc`（46 脚：板载 13+I2S 3+HDMI 30；四时钟声明+异步组）
- `constraints/ddr3_100h.fdc`（73 针，层级前缀 ddr3_wrapper.I_ips_ddr_top，gen_ddr3_fdc.py 可重生成）
- `constraints/clock_groups_async.fdc`（**必须在 ddr3_100h.fdc 之后加载**——SDC-2027 教训：引用未创建时钟的组声明整条被忽略）
- `ipcore/ddr3_test/`（复用 pds_cpu_100h）、`ipcore/pll/`（demo HDMI GPLL）、`ipcore/pll_audio/`（**文本派生** 27M→216M：RATIOM=2/RATIOF=16/RATIO0=4，VCO 864MHz；若 GUI 重开 idf 会覆盖手改参数）

---

## 四、进行中/未完成工作（按优先级）

### 4.1 🔴 最高优先：M1 集成构建的三处语法错误（修复到一半）

构建日志：`reports/build_20261027-101841-e3f7660b.pds.stdout.log`（compile 阶段失败）。

1. **mel_engine.v 参数基数字面量**——✅ 已修复：`19'dFILL_CREDIT` 等改为 `FILL_CREDIT[18:0]`（SV 参数基数字面量 PDS 不支持，词法 lint 查不出）
2. **standardize.v var_q16_u32 重复声明**——✅ 已修复：179 行 reg（快照）与 224 行 wire（组合）冲突，wire 改名 `var_q16_comb`，361 行快照赋值 `var_q16_u32 <= var_q16_comb`
3. **fft2048_sdf.v 471~483 行嵌套 generate**——❌ **未修**：generate 循环体内又写了 `generate if (k==1) ... endgenerate`。PDS 报 `Syntax error near generate`。修复方案：去掉嵌套 generate，改用 `assign` + 条件位选（如 `assign d_hi_re = (k==1) ? {d_re_r[16], d_re_r} : d_re_r[IW-1:k-2];`——注意 else 分支的 part-select `d_re_r[IW-1:k-2]` 在 k=1 时位宽为负会非法，这正是原嵌套 generate 的动机；替代写法：用 localparam 定义各分支的常量位宽 + 两个 assign 用 `(k==1)` 三元选择，part-select 写成 `d_re_r[IW-1 -: (k-1)]` 变位宽形式或拆成 shift：`d_re_r >> (k-1)` 再截 18bit——**择一并验证 PDS 接受**）
4. 修复后重跑：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1`，期望六阶段全 OK（M1 资源预估 +6K LUT/+20 DRM，总 LUT ~13K、DRM ~25）

### 4.2 🟡 M2 NPU 剩余（tasks.md 四、M2 组）

- conv_engine（16 MAC 阵列+行流水）——严工会话中断于 requant_unit 落盘后
- wdma（权重 DDR3 分组流式加载，走 m1 口，shift 按 6bit）
- weight_loader + weight_upload.py（UART 加载 0.69MB，一次性 ~60s）
- pool_engine（2×2 max，floor 几何 258→129→64→32→16）
- gap_fc（GAP>>6 half-even + fc1/fc2 + wsum 修正 + softmax 定点）
- npu_top 整合 + 板级逐层 UART 导出对拍

### 4.3 🟡 板级冒烟（T-M0-10，tasks.md）

位流已就绪（M0 版 c517736c…；M1 版待 4.1 完成后重出）。板卡在线：
1. JTAG 烧 instrec-latest.sbit → 观察 LED（心跳/sys_run/自检阶段码）+ UART 115200 状态行（BOOT/PLL/DDROK）
2. DDR3 自检失败时查 `reports/ddr3_ctrl_checklist.md` §四的两个回退参数（AXI_USER_AP / DUMMY_WSTRB_ALL1）
3. HDMI 显示网格+波形（需音频输入）；CDC FIFO 上电窗口溢出告警属预期

### 4.4 🟡 M3 UI（tasks.md 五、M3 组）

spectrum_disp（消费 0x200000 谱导出区）/font_rom（8 类中文名点阵）/bars_disp（置信度条）/ui_renderer 扩展。

---

## 五、跨会话必须知道的技术事实（血泪教训汇总）

1. **NCO STEP 修正**：design.md 的 3509057 是笔误，正确 3507557（RTL 已用正确值）
2. **golden_pipeline.py = 位级真值**：与浮点精确数学 0 LSB；torch 2.14.1 本机 QEngine 是 **oneDNN**（fbgemm 已移除），oneDNN 量化 conv 在 tile 边界有 21~67 LSB 噪声（x%8∈{0,1,7}/y%4==3 模式）——**RTL 对拍以 golden 为准，不以 torch 为准**
3. **requant 必须 round-half-even**：截断 >>> 会经 432-tap 卷积放大到 ±32 LSB/层；requant_unit.v 已实现（可作 conv_engine 的参照）
4. **InstRec npy bias 损坏**：`deploy/weights/*_bias_int32.npy` 被 astype 截断（conv2 c0 真值 7983→0）；正确 bias 在 layer_contract.json（从 pt packed params 重建）
5. **shift 需 6bit**（实测 37..53）；fc2 zp_out=57（logits=(out−57)×s_out）；conv1 padding 填 zp_in=49
6. **DDR3 IP 契约**：无 axi_wvalid/axi_rready/axi_b；写完成=axi_wready&&beat_cnt==len；读前 dummy-write（ctrl_axi 已封装）；4 主口 m0=audio/m1=NPU权重(悬空)/m2=mel_engine(已接)/m3=self_test
7. **fdc 加载顺序=语义依赖**：clock_groups_async.fdc 必须在 ddr3_100h.fdc 后（否则 SDC-2027 整条忽略）；PDS 逐条执行约束
8. **check_rtl.py 两个已修缺陷**：wire 初始化表达式误报、字符串参数(".TW_FILE("xx.hex")")空连接误报——勿回退
9. **子代理执行纪律**：多次会话因「长思考后单次大输出」被截断——恢复会话时指令必须「先落盘再汇报、每文件一次 Write」
10. **PDS 不支持 SV 参数基数字面量**（`19'dPARAM`）与嵌套 generate——check_rtl.py 词法层查不出，构建 compile 阶段才暴露

---

## 六、团队与会话索引（本会话累计）

孙工(构建/ddr3/ctrl_axi)、郑工(I2S/uart/sys_ctrl)、冯工(HDMI/UI/audio_sink/fdc)、周工(Mel 金标准)、吴工(权重转换+NPU 金标准)、沈工(顶层集成)、褚工(stft/fft)、蒋工(mel_filter/db 谱/mel_engine)、韩工(db_norm/standardize)、严工(requant_unit)。关键 session_id 见团队联系人列表；会话超时（>120min）频繁发生，**恢复用 background-task(session_id=…) + 精确指令**。

---

## 七、恢复开发的操作指引

1. **先读本快照 + tasks.md**（`.codeartsdoer/specs/instrec_fpga/tasks.md`，44 任务含 DoD）
2. **立即修复 4.1 的 fft generate**（唯一阻塞项）→ 重跑构建 → M1 收官
3. 按 tasks.md 顺序推进 M2（conv_engine→wdma→weight_loader→pool→gap_fc→npu_top）与板级冒烟（T-M0-10 可与 M2 并行）
4. 团队任务板：`read-team-task` 查看 12 项（#1~#9 已完成、#10 M2-RTL 进行中、#11/#12 待启动）
5. 每完成一模块：check_rtl.py + pytest 全量回归；每完成一里程碑：全量构建 + 板级验收

**祝交接顺利。工程一切资产均在 `instrec_fpga/` 内，仓库其他目录零污染（git 工作区 4 个 M 文件为历史遗留，与本工程无关）。**