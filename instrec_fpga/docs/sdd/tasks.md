# InstRec-FPGA 实施任务分解清单

| 项目 | 内容 |
| ---- | ---- |
| 文档标识 | tasks.md / instrec_fpga |
| 版本 | v1.0 |
| 日期 | 2026-10-26 |
| 作者 | 规划工程师（陈工） |
| 上游输入 | `.codeartsdoer/specs/instrec_fpga/spec.md` v1.0（69 条 EARS 需求）、`.codeartsdoer/specs/instrec_fpga/design.md` v1.0（17 模块技术设计） |
| 工程根目录 | `D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga\` |

> **术语对照说明**：权重转换工具统一采用 design.md §6.1/§12.1 的正式命名 `scripts/gen_weight_image.py`（规划沟通过程中曾称 `export_weights.py`，两者为同一工具，以本文档命名为准）。

---

## 〇、任务组织与依赖总则

1. **双轨并行**：P0（Python 金标准与工具链）与 M0（RTL 链路）可并行开工；P0 的对拍脚本是唯一数值验证手段（本机无仿真，R-07），必须在 M1/M2 RTL 之前或期间尽早可用。
2. **任务粒度**：每任务 2~4 小时（一名工程师一次专注可完成），原子化、可独立验收。
3. **顺序约束**：M0 内部 i2s_clk_gen/i2s_rx → audio_cdc_fifo → ddr3_wrapper/ddr3_ctrl_axi → audio_sink → hdmi_tx_if/ui_renderer 波形 → instrec_top M0 版 → fdc/构建 → 板级冒烟；M1 拆 hann_rom/stft_framer/fft2048_sdf/mel_filter/log2_lut/db_norm/standardize 后 mel_engine 整合；M2 拆 export 工具 → weight_loader/wdma → conv_engine → pool/gap_fc → npu_top 整合 → 板级逐层对拍；M3 UI 完整 → softmax → 端到端 → 演示。
4. **角色缩写**：RTL = RTL 工程师；MDL = 模型工程师；BLD = 构建工程师；VER = 验证工程师。
5. **风险预案**：CT 组为可选 contingency 任务，触发条件在各自 DoD 中声明。
6. **板级用例编号**（T0.x/T1.x/T2.x/T3.x）引用 design.md §9.3，对应 REQ-VER-001~004 验收。

---

## 一、P0：工具链与 Python 金标准先行线（6 个任务）

> 对拍是唯一验证手段（R-07）。本组任务与 M0 并行启动，必须在 M1 RTL 开始前完成 T-GP-02/03/04，在 M2 RTL 开始前完成 T-GP-05。

### T-GP-01 搭建工程目录骨架与 PDS 批处理构建脚本
- **前置依赖**：无（可立即开工）
- **涉及文件**：`instrec_fpga/`（src/audio、src/ddr3、src/mel、src/npu、src/ui、src/hdmi、src/ctrl、src/ip、ipcore/、constraints/、scripts/、tests/、reports/、docs/）、`scripts/build_full.tcl`、`scripts/run_pds_full.ps1`
- **任务描述**：按 design.md §12.1 创建全部目录；以 `pds_cpu_100h/scripts/build_full.tcl` 与 `.skills/pango-pg2l100h-dev/template` 为模板编写六阶段批处理（compile → synthesize → dev_map → pnr → report_timing → gen_bit_stream，含 `__PROJECT_ROOT__` 令牌展开、SCBV 警告豁免、sbit sha256 记录）；编写 `run_pds_full.ps1`（PDS_ROOT=H:\GG\pango\PDS_2022.2-SP6.4、PANGO_LICENSE_FILE 指向 E:\License\pango\new_pds_F4A80DA47D72.lic）；建立 `.gitignore`（build/ 时间戳输出）。
- **完成判据（DoD）**：目录树与 §12.1 一致；`run_pds_full.ps1` 在空 RTL（仅含顶层骨架文件）下可走通 compile/synthesize 无 Error（允许因无实质逻辑提前终止于 map）；日志落盘 `reports/`；既有 `cpu/`、`pds_cpu_100h/` 目录 `git diff` 零改动（REQ-BLD-004）。
- **建议负责角色**：BLD

### T-GP-02 实现 gen_mel_tables.py：Hann/Mel COO/log2 LUT 系数表生成
- **前置依赖**：T-GP-01
- **涉及文件**：`scripts/gen_mel_tables.py`、`scripts/outputs/mel_tables.coe`、`scripts/outputs/mel_tables.json`、`tests/test_mel_tables.py`
- **任务描述**：用 librosa `get_window("hann", 2048, fftbins=True)` 生成 2048×Q1.15 Hann 表；用 `mel(sr=44100, n_fft=2048, n_mels=64, fmin=0, fmax=22050, htk=False, norm="slaney")` 生成 64×1025 稠密矩阵并抽 COO 稀疏（weight>1/8192，约 4.0k 条 `{bin_idx s11, weight Q1.15 s16}` + 64 通道偏移头）；生成 log2 LUT 256 项×Q0.8 与 softmax exp LUT 512 项×Q0.16；全部参数从 `InstRec/deploy/feature_params.json` 读取并与 REQ-FTR-001 逐项断言（SR/N_FFT/HOP/N_MELS/N_FRAMES/f_min/f_max/power/top_db/normalization）；输出 coe/json 双格式 + sha256 清单。
- **完成判据（DoD）**：`pytest tests/test_mel_tables.py` 通过：① 参数 10 项与 feature_params.json 逐项一致；② COO 重建的稠密 Mel 矩阵与 librosa 直接计算矩阵逐元素误差 ≤ 1/8192；③ Hann 表首/中/末值与 librosa 一致（Q1.15 量化 ±1 LSB 内）；④ 重复执行 sha256 逐位一致（确定性）；⑤ LUT 项数 256/512 正确。
- **建议负责角色**：MDL

### T-GP-03 实现 gen_weight_image.py：双源权重转换与层契约生成
- **前置依赖**：T-GP-01
- **涉及文件**：`scripts/gen_weight_image.py`、`scripts/outputs/weights_image.bin`、`scripts/outputs/layer_contract.json`、`tests/test_weight_image.py`
- **任务描述**：实现 design.md §6.1 双源转换：① 从 `InstRec/deploy/weights/*.npy`（24 个文件）读取 per-channel 权重 scale（F-01：`*_scale.npy` 是权重 s_w 而非激活 scale）、int8 权重、int32 bias；② 从 `InstRec/deploy/quantized_model.pt`（TorchScript fbgemm）遍历量化模块提取 activation_post_process 的 s_in/s_out/zp_in/zp_out；③ 计算逐层逐 16 通道组 `M[c]=round(s_w[c]×s_in/s_out×2^shift)`（Q0.31，shift 使 M∈[2^30,2^31)）；④ 按 §5.2 布局（镜像头 IRW1/层契约表/逐层权重，16 通道交错重排）输出 `weights_image.bin` 与 `layer_contract.json`；⑤ 加载 `class_names.json` 与 `src/dataset.py` 的 INSTRUMENT_NAMES 比对断言（R-06 类别顺序防线）；⑥ 对 6 层逐一断言 s∈(1e-4,1)、zp∈[-128,127]（R-12）。
- **完成判据（DoD）**：`pytest tests/test_weight_image.py` 通过：① bin 总长 ≈ 690KB 且各区偏移与 §5.2 表一致；② layer_contract.json 含 6 层完整 {s_in,s_out,zp_in,zp_out,M[16],shift,组数,地址偏移,形状}；③ 类别顺序断言通过（0=单簧管…7=小提琴）；④ 重复执行输出 sha256 逐位一致；⑤ inv_s_in 的 Q 格式选择逻辑（16bit 容器溢出升 Q8.24）有单测覆盖。
- **建议负责角色**：MDL

### T-GP-04 实现 golden_pipeline.py Mel 段：bit-accurate 定点金标准（前半）
- **前置依赖**：T-GP-02
- **涉及文件**：`scripts/golden_pipeline.py`、`tests/test_golden_mel.py`
- **任务描述**：用 NumPy int64/int32 显式实现 design.md §3 全链（禁 float 捷径）：PCM s16 → Hann Q1.15 乘 >>15 round-half-up → FFT s18 11 级每级 ÷2（round-half-up）→ 功率 s37 精确 → Mel COO（读同一 mel_tables.coe）s56 累加 → log2（前导 1 规格化 + 256 LUT，Q8.8 int16）→ 第二遍 dB（×775/256、top_db=80 截断、±1LSB 防护）→ μ/σ（s48 累加、16 周期除法语义、NR 开方/求逆）→ z Q4.12 → int8 量化（round-half-to-even 位级实现 + zp + 饱和）。支持 `--stage pcm|log2spec|dbspec|feat` 逐级输出 .npy；支持 `--ref librosa` 模式调用 `InstRec/src/features.py` 的 `extract_mel` 浮点参考。
- **完成判据（DoD）**：`pytest tests/test_golden_mel.py` 通过（≥3 条代表音频含全静音/满幅/两段响度拼接）：① golden vs librosa per_sample 归一化谱 max|Δ|≤0.05 且 Pearson r≥0.999（REQ-ACC-001 指标在 Python 域先闭环）；② 全静音样本无 NaN/溢出（amin/eps 路径）；③ 首/末帧边界（reflect 填充）与参考一致；④ 各 stage .npy 输出形状正确（log2spec/dbspec 64×258、feat 64×258 int8）。
- **建议负责角色**：MDL

### T-GP-05 实现 golden_pipeline.py NPU 段：INT8 前向金标准（后半）
- **前置依赖**：T-GP-03、T-GP-04
- **涉及文件**：`scripts/golden_pipeline.py`（扩展）、`tests/test_golden_npu.py`
- **任务描述**：按 layer_contract.json 实现 INT8 前向：conv1~4（3×3 pad1，acc s32 = Σ x_s8×w_s8 + bias_s32）→ requant（`sat_int8((acc×M)>>>shift+zp)`，M 高 24bit Q0.23 截取与 RTL 一致）→ pool 2×2 floor（`W[10:1]` 语义）→ GAP（s32 直加后 requant）→ fc1+ReLU（requant 后 clamp min 0）→ fc2（logits int32 原值保留）→ softmax（Q6.9 + 512 exp LUT + 定点除法，与 §4.5 位级一致）。支持 `--stage conv1..conv4|fc1|fc2|logits|probs` 逐层 .npy 输出；`--ref torch` 模式调用 `InstRec/deploy/inference_reference.py` 参考对拍。
- **完成判据（DoD）**：`pytest tests/test_golden_npu.py` 通过（≥5 条音频特征样本）：① 逐层 int8 输出与 TorchScript 量化参考 100% 元素 ±1 LSB（REQ-ACC-002 指标 Python 域闭环）；② max|Δlogit|≤0.25、softmax max|Δp|≤0.02、top-1 一致率 100%（REQ-ACC-003）；③ conv1 输出形状 48×64×258、pool1 后 48×32×129（R-10 形状首检）；④ 满幅样本饱和路径无翻转（REQ-INF-007）。
- **建议负责角色**：MDL

### T-GP-06 实现 check_rtl.py：SV-2005 静态检查清单
- **前置依赖**：T-GP-01
- **涉及文件**：`scripts/check_rtl.py`、`tests/test_check_rtl.py`
- **任务描述**：实现 REQ-BLD-003 lint 清单：① SV-2012 语法黑名单（`always_ff/always_comb/logic 隐式/.port() 空连接/interface`）；② 标识符 snake_case、参数名全大写；③ 注释非英文字符检测；④ `always @*` 使用规范；⑤ 文件头部模板（模块名=文件名）。扫描 `src/**/*.v` 输出违例清单，退出码非零表示有违例。
- **完成判据（DoD）**：`python scripts/check_rtl.py` 在含已知违例的样例文件上正确检出（单测覆盖 5 类违例各 ≥1）；对当前空 src/ 退出码 0；后续所有 RTL 任务 DoD 引用「check_rtl.py 通过」。
- **建议负责角色**：VER

---

## 二、M0：链路贯通——I2S → DDR3 → HDMI 波形（10 个任务）

> 里程碑目标（REQ-VER-001）：I2S 时钟正确（±500ppm）、DDR3 自检通过、HDMI 1080p@60 显示实时波形。R-05 缓解策略：先原样复用 demo 显示通路，再叠加数据通路。

### T-M0-01 实现 i2s_clk_gen：GPLL 整数倍频 + 28bit NCO 合成 I2S 时钟
- **前置依赖**：T-GP-01
- **涉及文件**：`src/audio/i2s_clk_gen.v`、`src/ip/audio_pll.v`
- **任务描述**：按 design.md §1.2 方案 B 实现：audio_pll（GPLL_D，27MHz→216MHz 整数倍频 M=8/D=1）；28bit 相位累加器 STEP=3509057 产生 BCK 翻转 tick（bck_tick 单周期使能 + bck_phase[4:0] 帧相位）；LRCK 在 bck_phase==31 边界翻转（低=左声道，Philips）；输出 i2s_bck/i2s_lrck 引脚寄存器。累加器进位链若时序紧张预留 14+14 两级流水注释。两级同步器消费 rst（GPLL lock 门控）。
- **完成判据（DoD）**：① 文件存在且 check_rtl.py 通过；② PDS 综合（并入任意构建）无 Error；③ 板级（T0.1，若提前接板）示波器实测 BCK=1.4112MHz、LRCK=44.1kHz、占空比 50%、误差 ≤±500ppm（REQ-AUD-002/003）；④ bck_tick/bck_phase 波形与 §2.2.2 契约一致（UART 逻辑分析仪辅助或 LED 分频观测）。
- **建议负责角色**：RTL

### T-M0-02 实现 i2s_rx：Philips I2S 帧解码与静音检测
- **前置依赖**：T-M0-01
- **涉及文件**：`src/audio/i2s_rx.v`
- **任务描述**：按 §2.2.3 契约实现：i2s_sd 两级同步器（216M 域，REQ-AUD-007）；按 bck_tick 使能在数据位中心采样移位合成 16bit 字（MSB 前、延迟 1 BCK 对齐）；LRCK 低半帧 → pcm_l、高半帧 → pcm_r；pcm_valid 每完整字一个脉冲；sd_idle 检测（SD 电平静止 >1 LRCK 周期置位，恢复后清除，REQ-REL-003）；异常样本按静音处理。全部逻辑运行于 clk_nco、bck_tick 使能推进。
- **完成判据（DoD）**：① check_rtl.py 通过；② 综合无 Error；③ 逻辑分析仪解码回放已知正弦源时左右声道 16bit 样本值一致（REQ-AUD-004，板级并入 T-M0-10 验收）；④ 仅左声道含内容时识别通路仅响应左声道（REQ-AUD-005，与 audio_sink 联测）。
- **建议负责角色**：RTL

### T-M0-03 实现 audio_cdc_fifo：216M→125M 双时钟样本 FIFO
- **前置依赖**：T-M0-02
- **涉及文件**：`src/audio/audio_cdc_fifo.v`
- **任务描述**：按 §1.4 CDC 表实现深度 512×32bit 双时钟 DRM FIFO（左右声道 s16×2 打包）；写侧 clk_nco、读侧 core_clk；空满标志格雷码指针；音频速率 88.2k 样本/s 水位 <2%，断言无溢出条件（水位 11.6ms 缓冲）。reset 跨域处理按复位树（rst_sync_nco / rst_sync_core）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 综合无 Error 且 DRM 推断为 1 块（映射报告核对）；③ 板级长稳运行（并入 T-M0-10）UART 无 FIFO 溢出告警；④ fdc 中该跨域路径被 `set_clock_groups -asynchronous` 覆盖（T-M0-09 约束核对项）。
- **建议负责角色**：RTL

### T-M0-04 复制 DDR3 IP 资产并实现 ddr3_wrapper
- **前置依赖**：T-GP-01
- **涉及文件**：`ipcore/ddr3_test/`（整目录复制自 `pds_cpu_100h/ipcore/ddr3_test`）、`src/ddr3/ddr3_wrapper.v`、`constraints/ddr3_100h.fdc`（复制）、`constraints/gen_ddr3_fdc.py`（复制）、`reports/asset_trace.md`
- **任务描述**：按 REQ-MEM-001/REQ-BLD-004：整目录复制 DDR3 IP 与约束脚本（溯源清单登记源路径+sha256）；编写 wrapper 例化 IP，**实例名硬性保持 `I_ips_ddr_top`**，wrapper 实例在顶层命名为 `ddr3_wrapper` 使层级前缀与原工程零语义改动（§12.3）；dbg 信号常量绑定；`gen_ddr3_fdc.py` 校验 73 针表一致性；IP `resetn` 接核心域同步复位、消费 IP 输出 `core_clk`（125MHz）与 `core_clk_rst_n`。
- **完成判据（DoD）**：① `git status` 显示 `pds_cpu_100h/` 零改动；② gen_ddr3_fdc.py 校验 73 针全一致（529 行约束）；③ 溯源清单归档 `reports/asset_trace.md`；④ 包含 wrapper 的综合构建通过（IP 正常加载，实例名在层级报告中为 `ddr3_wrapper.I_ips_ddr_top`）。
- **建议负责角色**：BLD（RTL 协助）

### T-M0-05 实现 ddr3_ctrl_axi + ddr3_arbiter：四主仲裁与 IP 契约适配
- **前置依赖**：T-M0-04
- **涉及文件**：`src/ddr3/ddr3_ctrl_axi.v`、`src/ddr3/ddr3_arbiter.v`、`tests/test_ddr3_arbiter_model.py`
- **任务描述**：按 §2.2.5 实现：4 主设备统一请求口（{wr,addr[27:0],len[7:0]}，256bit 数据）；**IP 特例适配（REQ-MEM-003 硬性规则）**——写完成以 axi_wready 握手判定（无 axi_wvalid）、beat 计数满+wusero_last 旁证；读前同地址 dummy-write（wstrb 全 0 屏蔽）；rvalid 期间逐周期收数（16 深弹性读缓冲反压上游）；axi_awuser_ap=1、user_id 固定主设备号；固定优先级 P0 音频写 > P1 权重读 > P2 Mel 读 > P3 UI 读 + P3 每 1ms 保底配额；每主 32bit wait_cnt 计数器导出（REQ-MEM-004）；全部长突发 len=15、32B 对齐；地址映射按 §5.1（PCM 左 0x0/右 0x84000/权重 0x100000/谱导出 0x200000/自检 0x300000，REQ-RSC-006）。用 Python 状态机模型对拍仲裁行为（无仿真环境，1:1 建模）。
- **完成判据（DoD）**：① check_rtl.py 通过；② `pytest tests/test_ddr3_arbiter_model.py`：Python 仲裁模型在 4 主并发随机负载下任何主等待 ≤ 预算 10%、P3 配额不饿死、地址无重叠冲突；③ dummy-write 前置路径在 checklist 归档；④ 板级（并入 T-M0-10）自含 dummy-write 验证项通过。
- **建议负责角色**：RTL

### T-M0-06 实现 audio_sink：PCM 环形缓冲写管理与波形降采样
- **前置依赖**：T-M0-03、T-M0-05
- **涉及文件**：`src/audio/audio_sink.v`
- **任务描述**：按 §2.2.4 实现：CDC FIFO 出口样本聚合 4 样本/拍 64bit 写 DDR3（主口 0）；写指针模 2 窗口（264KB×2 左声道区，右声道区镜像写入仅存档，REQ-AUD-005/REQ-MEM-002）；每 132096 左声道样本产 win_tick + win_id（REQ-PRF-001 节拍源）；mute_flag（sd_idle 或全零持续 → 注入静音样本保持管线运转，REQ-REL-003）；UI 波形列降采样器（132096 样本 → 1920 列 min/max 包络，O(1) 滚动更新，列缓冲 ping-pong，§7.4）；写指针越界计数器告警（§5.2.3 场景 2）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级（并入 T-M0-10）连续 ≥60s UART 无回卷错误、win_tick 相邻间隔 ∈[2.9,3.1]s（REQ-MEM-002/REQ-PRF-001）；③ 波形列缓冲 1920×2×16bit 双页映射报告核对（≈7 DRM，修正后单页 3.5）。
- **建议负责角色**：RTL

### T-M0-07 复制 HDMI demo 资产并实现 hdmi_tx_if
- **前置依赖**：T-GP-01
- **涉及文件**：`src/hdmi/`（hdmi_tx_if.v + 整文件复制 sync_vg.v/iic_dri.v/ms7200_ctl.v/ms7210_ctl.v/ms72xx_ctl.v，源：`D:\0000\111\001\Pango\docs\盘古100Pro+开发板（MES2L676-100HP）配套资料\7_FMC扩展子卡\2_Demo\da_ad_HDMI\ad9280_ad9708_HDMI\`）、`reports/asset_trace.md`（追加）
- **任务描述**：按 §7.1/R-05：整文件复制 demo 5 个模块（保留原模块名与端口，删除 demo 顶层/pattern_vg/grid_display 接线，功能由 ui_renderer 接管）；hdmi_tx_if 例化 GPLL_B（27MHz→148.5MHz pix_clk + 10MHz cfg_clk，demo pll 原样）、ms72xx_ctl（I2C K22/K23 配置 HDMI 发送芯片）、sync_vg（1080p@60：H_TOTAL=2200/V_TOTAL=1125/H_ACT=1920/V_ACT=1080）；输出 vout_data[23:0]/de/hs/vs/clk；init_over 信号引出（sys_ctrl 自检链消费）；I2C init_over 超时重试逻辑（§5.5.3 场景 1）。
- **完成判据（DoD）**：① 5 个 demo 文件 sha256 与源一致（除删除的顶层外零改动）记录于 asset_trace.md；② 板级（并入 T-M0-10 首步）显示器识别 1080p@60 且 demo 网格四角无撕裂（REQ-UI-001，R-05 第一步验证）；③ HDMI 37 脚约束与 demo fdc 逐针一致（T-M0-09 核对项）。
- **建议负责角色**：RTL（BLD 协助复制）

### T-M0-08 实现 ui_renderer M0 版：波形区 + 网格显示
- **前置依赖**：T-M0-07
- **涉及文件**：`src/ui/ui_renderer.v`、`src/ui/waveform_disp.v`
- **任务描述**：按 §7.2/§7.4 实现 M0 子集：① 波形区（y∈[0,300)，深蓝背景+网格线复刻 grid_display 视觉，绿色 min/max 包络竖线对，1920 列 ← 波形列缓冲双时钟 FIFO 读）；② 其余区域暂为纯色/网格占位；③ 像素流水 3 级（查表+选择器+寄存器）对 de/hs/vs 补偿 3 拍（§7.7）；④ vsync 消隐期列页切换（REQ-UI-007 波形部分语义）；⑤ mute_flag_sync 静音平线提示占位。后续 M3 在同文件扩展四要素。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级（并入 T-M0-10 用例 T0.3）：已知正弦源输入时波形随频率/幅度目视变化（REQ-VER-001 波形部分、REQ-UI-003）；③ 148.5MHz 时序收敛（构建报告 WNS≥0）。
- **建议负责角色**：RTL

### T-M0-09 实现 instrec_top M0 版 + 全量约束 + 基础调试/自检通路
- **前置依赖**：T-M0-01~T-M0-08
- **涉及文件**：`src/instrec_top.v`、`src/ctrl/uart_debug.v`、`src/ctrl/uart_tx.v`、`src/ctrl/uart_rx.v`、`src/ctrl/self_test.v`、`src/ctrl/sys_ctrl.v`（M0 简化版）、`constraints/instrec_top.fdc`（含 i2s_audio 约束项）
- **任务描述**：顶层集成：三域复位树（§1.3：rst_sync_core/nco/pix/cfg，异步断言同步释放+GPLL lock 门控，REQ-SYS-002）；§2.2.1 全部引脚汇聚（i2s_bck U20/i2s_lrck T20/i2s_sd V16 LVCMOS33 DRIVE 8 SLEW SLOW；HDMI 37 脚 demo 抄录；板载 clk D18/rst C22/key1 C23/led×8/uart B24/C24）；fdc：create_clock 27MHz、pix_clk/clk_nco 时钟声明、每时钟独立 async group（§12.3）；uart_debug 115200 8N1 行式输出（BOOT/PLL/DDROK/ERR 行类型，REQ-MNT-001 子集）；self_test DDR3 图案写读自检（主口 3 低优先级，覆盖 §5.1 全部占用区间阶梯图案，REQ-MEM-005）；sys_ctrl M0 版自检链（PLL→DDR3→HDMI_I2C→RUN，失败 SAFE_ERR + LED 错误码，REQ-REL-001 骨架）；KEY0 复位、KEY1 两级同步+消抖预留。
- **完成判据（DoD）**：① check_rtl.py 通过；② 全量构建 `run_pds_full.ps1` 六阶段无 Error（SCBV 豁免）、All Constraints Met（REQ-BLD-001/002 首次闭环）、产出 instrec_top.sbit + sha256；③ 资源初查 LUT ≤53k/GPLL=4（REQ-RSC-001/002 首核）；④ DDR3 自检覆盖 5 区间地址（REQ-RSC-006 验收路径）。
- **建议负责角色**：RTL + BLD

### T-M0-10 M0 板级冒烟验收（REQ-VER-001）
- **前置依赖**：T-M0-09
- **涉及文件**：`reports/m0_board_test.md`、`docs/m0_photos/`（示波器照片/频率读数/UART 日志/HDMI 拍照）
- **任务描述**：执行 design.md §9.3 M0 用例：T0.1 示波器实测 BCK/LRCK 频率/占空比（±500ppm）；T0.2 UART 观测 DDROK + 自检首错注入（强制复位序列模拟 DDR3 失败，LED 错误码+首错地址）；T0.3 HDMI 网格+实时波形（已知正弦源）；JTAG RAM 下载三步流程验证（下载位流→复位→运行可重复，REQ-BLD-005）。全部证据归档。
- **完成判据（DoD）：REQ-VER-001 全项通过**：① BCK=1.4112MHz、LRCK=44.1kHz 误差 ≤±500ppm（频率读数照片）；② DDROK 日志 + 首错注入正确报错；③ 1080p@60 显示且波形随输入目视变化（拍照前后对比 ≥2 组）；④ PDS 构建时序收敛报告归档；⑤ 三步流程重复执行 3 次成功。**里程碑 M0 达成**。

---

## 三、M1：Mel 特征引擎（7 个任务）

> 里程碑目标（REQ-VER-002）：板上 Mel 谱与 Python 定点模型一致、对 librosa 满足 REQ-ACC-001、HDMI 显示频谱图、单窗 ≤150ms。每个子模块有对应 Python 对拍点（golden_pipeline.py --stage）。

### T-M1-01 实现 stft_framer：帧供给器与 reflect 边界语义
- **前置依赖**：T-M0-06（PCM 读主口 2 可用）、T-GP-04（对拍基线）
- **涉及文件**：`src/mel/stft_framer.v`、`src/mel/hann_rom.v`、`tests/test_stage_framer.py`
- **任务描述**：按 §2.2.6 实现：从 DDR3 PCM 流（窗口基址+512×t−1024）生成 258 帧×2048 点序列；**边界语义硬件化（F-05/REQ-FTR-002）**：帧 0 样本 [0..1023] 来自 reflect 翻转 y[1024..1]；帧 257 尾部越界读钳制到窗口末端后 reflect 翻转索引（与 librosa center=True 语义一致）；hann_rom：2048×Q1.15 periodic Hann（$readmemh 加载 mel_tables.coe 段，2 DRM）；加窗乘法 s16×Q1.15→s32 >>15 round-half-up → s17（§3.1 S1）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级 KEY1 导出（或 UART 抽样导出）加窗后帧 0/帧 128/帧 257 数据 vs golden `--stage pcm`（扩展加窗级输出）逐元素 ±1 LSB；③ reflect 边界：帧 0 首 16 样本与 golden 反射序列一致（对拍 checklist 项）；④ 帧计数 258、每帧 2048 周期节拍正确。
- **建议负责角色**：RTL

### T-M1-02 实现 fft2048_sdf：2048 点 SDF 流水 FFT
- **前置依赖**：T-M1-01
- **涉及文件**：`src/mel/fft2048_sdf.v`、`tests/test_stage_fft.py`
- **任务描述**：按 §3.2 实现：SDF radix-2 串行蝶形流水 11 级、每级 ÷2（算术右移+round-half-up 进位）；数据通路 s18（符号扩展 1bit）；twiddle Q1.15 ROM（re/im 各 s16）；每周期吞 1 复样本；级间 2047×36bit 延迟线（DRM 或 LUTRAM，见 T-CT-01 降级开关）；输出实/虚 s18。溢出安全性依据 §3.2 归纳证明（每级 ÷2 恒有界）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级导出 FFT 输出（借 UART 抽样导出调试口）vs golden `--stage`（FFT 级扩展）单频满幅样本逐 bin ±2 LSB（11 级噪声 √11/2≈1.66 LSB 预算内）；③ 吞吐实测 258 帧总周期 ≈528k@125MHz ≈4.2ms（UART 时间戳）；④ PDS 时序收敛（125MHz 域 WNS≥0）。
- **建议负责角色**：RTL

### T-M1-03 实现 mel_filter：COO 稀疏滤波与功率谱
- **前置依赖**：T-M1-02
- **涉及文件**：`src/mel/mel_filter.v`、`tests/test_stage_mel.py`
- **任务描述**：按 §3.1 S4/S5 与 §3.4 实现：功率谱 re²+im²（s18→s36 乘积 s37 精确整数累加，无舍入）；COO 系数表（4096×27bit ≈7 DRM + 64×13bit 通道偏移头，$readmemh 加载）；帧内按 bin 升序流过功率谱，每 bin 查 COO 区间（平均 2.6 通道命中）`s37×Q1.15→累加 s56`；每帧输出 64 通道 Mel 功率 s56；APM 用量 ≤2（§4.2 总账）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级导出 Mel 功率（log2 前一级，调试口抽样）vs golden：定点域逐通道相对误差 ≤0.01%（精确整数乘加链）；③ COO 表 sha256 与 gen_mel_tables.py 输出一致（REQ-FTR-003 验收）；④ 帧滤波周期 ≈1025×2.6+开销，258 帧总 ≤5.5ms。
- **建议负责角色**：RTL

### T-M1-04 实现 log2_lut 与 db_norm：log2 域转换与 dB 归一
- **前置依赖**：T-M1-03
- **涉及文件**：`src/mel/log2_lut.v`（可并入 db_norm）、`src/mel/db_norm.v`、`tests/test_stage_log2.py`
- **任务描述**：按 §3.3/§3.5 实现：log2（前导 1 优先编码 → 指数 e−56 偏置 + 尾数高 8bit 查 256×Q0.8 LUT → `log2_q88=((e−56)<<8)+lut_out` int16）；写入 log2 谱整谱缓冲（64×258×16bit，15 DRM，§3.1 S6）；第二遍第一扫求 max_log2；第二扫 `dB_q88=sat16((log2_q88−max_log2)×775/256)`、`<−20480` 钳 −20480（top_db=80 截断，REQ-FTR-004）、`>0` 钳 0（±1 LSB 抖动防护）；同扫累加 ΣdB、ΣdB²（s48×2，§3.1 S8）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级导出 dB 谱 vs golden `--stage dbspec`：深静音段样本 top_db 截断路径逐元素一致（±1 LSB，REQ-FTR-004 专测）；③ 满幅样本 dB 上界钳 0 正确；④ log2 谱缓冲推断 15 DRM（映射报告）。
- **建议负责角色**：RTL

### T-M1-05 实现 standardize：per-sample 标准化与 int8 量化输出
- **前置依赖**：T-M1-04
- **涉及文件**：`src/mel/standardize.v`（可并入 mel_engine 或 db_norm）、`tests/test_stage_feat.py`
- **任务描述**：按 §3.6/§3.7 实现：μ_q88=ΣdB/16512（时复用 48/16 恢复除法器 16 周期，全设计共用）；var_q16=ΣdB²/16512−μ²；σ_q88=NR 开方（16 次迭代或 8bit 查表+NR 精化，误差<2^-10）；σ+1e-6 下限（Q8.8 域 +1 LSB，防除零）；inv_σ NR 除法 2 次迭代；`z_q412=sat16(((dB−μ)×inv_σ)>>8)`；int8 量化 `sat_int8(round_even(z×inv_s_in)+zp_in)`（round-half-to-even 位级实现，inv_s_in/zp_in 来自 layer_contract.json 常量固化）；特征双页缓冲（2×64×258×8bit，与 log2 谱时分复用同一 DRM bank，乒乓分页）；mel_cycles 耗时计数器（REQ-PRF-003）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级导出特征 vs golden `--stage feat`：int8 域 ±1 LSB 100%；③ 两段不同响度拼接音频跨窗统计行为与 golden 一致（REQ-FTR-005 验收用例）；④ 全静音窗口无除零/NaN、输出有界（§5.3.3 场景 1）。
- **建议负责角色**：RTL

### T-M1-06 mel_engine 整合：两遍管线与谱导出口
- **前置依赖**：T-M1-01~T-M1-05
- **涉及文件**：`src/mel/mel_engine.v`、`src/instrec_top.v`（M1 版接线）、`tests/test_mel_integration.py`
- **任务描述**：按 §2.2.6 契约整合：start（sys_ctrl win_tick 触发）→ PCM 读（主口 2，132096+2048 样本含 reflect 区）→ 第一遍（加窗+FFT+功率+Mel+log2 写谱）→ 第二遍（max→dB/统计→标准化→量化）→ mel_done + feat_page 交替；spec_rd_* 导出口（dB 谱 int16 Q8.8 供 spectrum_disp 与 uart_debug 复用）；mel_cycles 32bit 计数；窗口未齐节拍竞争处理（新窗缓存待取，§5.3.3 场景 2）。与 golden_pipeline 全 stage 对拍点清单归档。
- **完成判据（DoD）**：① check_rtl.py 通过、全量构建时序收敛；② 板级 mel_cycles 时间戳 ≤150ms（实测预期 ≈7ms@125MHz，REQ-FTR-007/REQ-PRF-003 分项）；③ feat 双页交替无撕裂（连续 2 窗口导出对比）；④ DRM 总量较 M0 增量 ≤28 块（Mel 引擎预算 §10 表）。
- **建议负责角色**：RTL

### T-M1-07 M1 板级验收：三方对拍与谱图上屏（REQ-VER-002）
- **前置依赖**：T-M1-06、T-GP-04
- **涉及文件**：`scripts/uart_capture.py`（Mel 段）、`reports/m1_bitmatch.md`、`reports/m1_audio_list.md`
- **任务描述**：执行 design.md §9.3 M1 用例：T1.1 KEY1 导出 Mel 谱 ↔ golden ↔ librosa 三方对拍（≥20 条覆盖 8 类音频，含 REQ-ACC-001 边界样本：首/末帧边界、深静音段、两段响度拼接）；T1.2 耗时时间戳 ≤150ms；T1.3 全静音窗口对拍（amin/eps 路径）；T1.4 跨窗统计验证。HDMI 显示 Mel 频谱图（M0 波形 + 本阶段 spectrum 简版或等待 M3 完整版，此处至少 UART 导出闭环）。
- **完成判据（DoD）：REQ-VER-002 全项通过**：① 板级 vs golden：Mel 谱逐元素一致（int16 Q8.8 域 ±1 LSB）；② golden vs librosa（板级导出间接闭环）：max|Δ|≤0.05 且 r≥0.999，20/20 条全达标（REQ-ACC-001，报告含样本清单+误差统计）；③ mel 时间戳连续 10 窗口 max ≤150ms；④ 静音/拼接专项通过。**里程碑 M1 达成**。
- **建议负责角色**：VER

---

## 四、M2：INT8 CNN NPU（8 个任务）

> 里程碑目标（REQ-VER-003）：板级逐层导出满足 REQ-ACC-002/003，≥10 条已知类别音频 top-1 ≥80% 且与 Python 一致 ≥90%。顺序：转换工具 → weight_loader/wdma → conv_engine → pool/gap_fc → 整合 → 板级逐层对拍。

### T-M2-01 实现 weight_loader 与上位机加载脚本
- **前置依赖**：T-GP-03（weights_image.bin/layer_contract.json 就绪）、T-M0-05
- **涉及文件**：`src/ctrl/weight_loader.v`、`scripts/weight_upload.py`、`tests/test_weight_upload.py`
- **任务描述**：按 §6.2 实现：PC 端 weight_upload.py 经 UART 115200 发分块帧（256B 数据 + CRC16 + 序号 + 进度百分比回显，失败块自动重传，R-13）；板级 weight_loader（uart_rx 命令流 → ddr3_ctrl_axi 主口写权重区 0x0010_0000）+ 回读校验（128bit 分段累加校验和，等效弱 sha256，§6.4）+ 与镜像头比对 → 置 WEIGHT_OK，UART 打印 `WOK <校验和hex>`；失败打印 `WERR @<addr> want <x> got <y>`（REQ-REL-001 错误链）。self_test 扩展权重回读比对。
- **完成判据（DoD）**：① 板级 T2.1（§9.3）：0.69MB 加载 ≤90s（预算 60s+重传余量）且 WOK 报文出现；② 注入坏块（上位机人为翻转）自动重传成功；③ 加载后读回校验和与上位机侧独立计算一致（双保险，REQ-INF-003 验收）；④ 权重镜像 sha256 归档 reports/。
- **建议负责角色**：RTL（上位机脚本 MDL 协助）

### T-M2-02 实现 wdma：权重 16 通道组流式加载
- **前置依赖**：T-M2-01
- **涉及文件**：`src/npu/wdma.v`、`src/npu/npu_top.v`（骨架）
- **任务描述**：按 §4.1/§2.2.7 实现：前向启动时按层按组从 DDR3 权重区预取（主口 1）：conv1 3 组/conv2 6 组/conv3 12 组/conv4 16 组/fc1 8 组/fc2 1 组（§4.1 分块表）；单组 ≤27,648B ≤32KB/层（REQ-RSC-005 验收）；wbuf 片上缓冲（峰值 27.6KB，与 conv 行缓冲 bank 错峰复用，§10 修正 8 块）；组契约装载（16×(32bit M + 5bit shift) + 层级 zp 常量，读自镜像层契约表）；组间顺序预取。npu_top 骨架：状态机（层序列 conv1→pool1→…→fc2）、busy/done、npu_cycles 计数、timeout_flag（>2× 预算，REQ-REL-002）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级前向期间 DDR3 权重读流量非零（wait_cnt/读计数器观测，REQ-RSC-005）；③ wbuf 映射报告 ≤8 DRM 净增；④ 权重加载总突发 ≈690KB → 1.6ms（UART 时间戳，§4.6 预算核对）。
- **建议负责角色**：RTL

### T-M2-03 实现 conv_engine：16 INT8 MAC 阵列与 3×3 行流水
- **前置依赖**：T-M2-02
- **涉及文件**：`src/npu/conv_engine.v`、`tests/test_conv_model.py`
- **任务描述**：按 §4.2 实现：16 MAC/周期（8 APM 18×18 拆 9×9，每 APM 2 路 int8 乘法），每周期完成同一输入分块 16 输出通道部分积（cin/dy/dx 串行 9×Cin 拍）；16×s32 累加器；3×3 行缓冲滑窗（pad=1 零行预填+列相位零注入，激活行缓冲 4 级合计 ≈66.7KB ≈30 DRM，§4.1 表）；逐层形状参数化（§4.4 对照表：conv1 48×64×258→conv4 256×8×32）；层内全行流水激活零 DDR3 回写（架构原则 1）。
- **完成判据（DoD）**：① check_rtl.py 通过；② Python 结构模型 `pytest tests/test_conv_model.py`（1:1 建模）：conv1 输出形状 48×64×258（R-10 checklist 首项）、各层输出 int8 域与 golden `--stage conv1..conv4` ±1 LSB；③ 前向计算 57.5ms 等效吞吐验证（UART 层时间戳：conv4 14.2ms±20%）；④ APM 占用合计 ≤30（§10 表含 requant/FFT/Mel 分配）。
- **建议负责角色**：RTL

### T-M2-04 实现 requant 通路：M/shift 定点重标定
- **前置依赖**：T-M2-03
- **涉及文件**：`src/npu/conv_engine.v`（requant 段，或独立 `src/npu/requant.v`）、`tests/test_requant_model.py`
- **任务描述**：按 §4.3 实现：`y_s8[c]=sat_int8((acc_s32[c]×M_s32)>>>shift+zp_out)`；M 取高 24bit Q0.23（APM 32×24 拼位，误差<2^-23）；barrel shifter；饱和 [-128,127] 与 PyTorch clamp 逐位一致（先 requant 饱和再入行缓冲，REQ-INF-007）；16 通道时复用 16 周期逐通道处理（1 乘法/周期，隐藏于 9×Cin≥432 周期产出间隙）；zp_out 不做 0 假设（fc1 输入 zp 通道可能非 0）。
- **完成判据（DoD）**：① check_rtl.py 通过；② Python requant 模型单测：与 golden 全链对拍满幅/过响度样本饱和路径无溢出翻转（REQ-INF-007 专测）；③ 板级逐层导出（并入 T-M2-08）conv1..4/fc1 输出 ±1 LSB 100%；④ APM 增量 ≤4（§4.2 总账）。
- **建议负责角色**：RTL

### T-M2-05 实现 pool_engine 与 gap_fc：floor 池化 + GAP + 全连接
- **前置依赖**：T-M2-04
- **涉及文件**：`src/npu/pool_engine.v`、`src/npu/gap_fc.v`、`tests/test_pool_gap_model.py`
- **任务描述**：按 §4.4 实现：pool 2×2 stride2 `out_w=W[10:1]` floor 语义（奇数宽 258/129 时末列/行不消费直接丢弃，R-10）；GAP：256 通道×4×16 每通道 64 值 s32 累加 → `fc_in_s8=sat((gap_s32×M_gap)>>>shift+zp_gap)`（256 个 s32 累加器）；fc1 256×128 向量机模式（x 广播 w 流式，16 MAC 并行 16 输出神经元，2048 周期）+ ReLU 融合（requant 后 clamp min 0）；fc2 128×8（64 周期）；logits int32 原值保留输出（dequant 不在片上做，§4.4）。
- **完成判据（DoD）**：① check_rtl.py 通过；② Python 模型单测：pool 形状链 258→129→64→32→16（时间轴）/64→32→16→8→4（Mel 轴）与 §4.4 对照表逐层一致（REQ-INF-001 验收：结构对照表归档）；③ golden `--stage fc1|fc2|logits` 对拍 ±1 LSB（fc1/fc2 int8 域）/ int32 域 ±1（logits）；④ GAP+fc 总周期 ≈2.1k+64。
- **建议负责角色**：RTL

### T-M2-06 npu_top 整合与 instrec_top M2 版集成
- **前置依赖**：T-M2-02~T-M2-05
- **涉及文件**：`src/npu/npu_top.v`（完整版）、`src/instrec_top.v`（M2 版：mel→npu 串行链接线）、`tests/test_npu_integration.py`
- **任务描述**：按 §2.2.7 契约整合：feat_page 消费（mel 完成页）→ 层序列执行（逐层 wdma 预取+行流水）→ logits int32×8 输出；layer_export_* 逐层导出口（conv1..4/fc1/fc2 输出经导出 FIFO 到 uart_debug，REQ-INF-006）；npu_cycles（含权重加载，REQ-PRF-003）；timeout_flag 接 sys_ctrl 看门狗；sys_ctrl 扩展自检链第 4 环（WEIGHT_LOAD_SHA → 放行推理循环）。全量构建 + 资源中期核对。
- **完成判据（DoD）**：① check_rtl.py 通过、全量构建时序收敛（REQ-BLD-002）；② 板级 npu_cycles ≤200ms（实测预期 ≈57.5ms，REQ-INF-004 ≥8 MAC/周期等效性：16 MAC=2× 下限）；③ 前向期间激活零 DDR3 回写（主口 2/3 读计数器仅 PCM/权重/UI 流量，架构原则 1 验证）；④ 资源中期核对：LUT ≤53k、APM ≤144、DRM ≤108（贴边预警则触发 T-CT-01）。
- **建议负责角色**：RTL

### T-M2-07 实现 UART 逐层导出协议与采集对拍脚本
- **前置依赖**：T-M2-06、T-GP-05
- **涉及文件**：`src/ctrl/uart_debug.v`（扩展）、`scripts/uart_capture.py`、`tests/test_uart_capture.py`
- **任务描述**：按 §9.2 实现板级协议：KEY1（或 UART 命令 X）触发后帧序列 `AA <layer_id:1> <seq:2> <len:2> <payload> <crc16:2>`；layer_id 0=MEL_Q8.8(64×258 s16,33KB)/1=CONV1/2=CONV2/3=CONV3/4=CONV4/5=FC1/6=FC2_LOGITS(8×s32)/7=PROBS(8×u8)/8=STATS(时间戳/等待计数)；`layer_id|0x80` 抽样模式（每 16 元素取 1，~8s）vs 全量模式（~400KB@115200≈60s）；PC 端 uart_capture.py 收帧重组 .npy → 与 golden_pipeline 对应 stage 比对 → 报告（±1 LSB 命中率/max|Δ|/r）。STATS 帧含 mel_cycles/npu_cycles/各主 wait_cnt（REQ-MNT-001 行式 + REQ-MEM-004 导出）。
- **完成判据（DoD）**：① 板级 KEY1 导出完整逐层数据包且 uart_capture.py 可解析（REQ-MNT-002/REQ-SYS-003）；② 抽样与全量模式均可跑通（抽样对拍命中率统计一致性验证）；③ CRC16 坏帧注入（人为干扰）正确丢弃重传；④ 对拍报告自动生成 reports/（含 ±1 LSB 命中率列）。
- **建议负责角色**：RTL（协议）+ VER（脚本）

### T-M2-08 M2 板级验收：逐层对拍与识别正确性（REQ-VER-003）
- **前置依赖**：T-M2-07
- **涉及文件**：`reports/m2_bitmatch.md`、`reports/m2_recog_matrix.md`
- **任务描述**：执行 design.md §9.3 M2 用例：T2.1 权重加载 WOK（已并入 T-M2-01 复验）；T2.2 逐层导出对拍 ≥100 个特征样本（8 类均衡抽样）；T2.3 logits/softmax/top-1 指标统计；T2.4 同音频回放 10 次 logits 位级一致；T2.5 已知类别 ≥10 条板级 top-1 正确率与 Python 一致率对照表。
- **完成判据（DoD）：REQ-VER-003 全项通过**：① 逐层 int8 输出 100% 元素 ±1 LSB（REQ-ACC-002，≥100 样本报告归档）；② max|Δlogit|≤0.25、softmax max|Δp|≤0.02、top-1 一致率 ≥99%（REQ-ACC-003）；③ 10 次回放 logits 十六进制完全相同（REQ-ACC-004）；④ ≥10 条已知类别板级 top-1 ≥80% 且与 Python 端到端一致 ≥90%（板级/Python 对照表归档）。**里程碑 M2 达成**。
- **建议负责角色**：VER

---

## 五、M3：UI 集成与端到端演示（6 个任务）

> 里程碑目标（REQ-VER-004）：四要素 UI 齐备、≥10fps、推理周期 ≤3.0s、端到端 ≤3.5s、60s 稳定、资源/时序全达标。

### T-M3-01 实现 gen_font.py 与 font_rom：中文字库
- **前置依赖**：T-GP-01（可与 M2 并行）
- **涉及文件**：`scripts/gen_font.py`、`scripts/outputs/font_16x16.hex`、`src/ui/font_rom.v`、`tests/test_font.py`
- **任务描述**：按 §7.3 实现：字符集合（去重）≈30 汉字（单簧管失真电吉他女声长笛钢琴次中音萨克斯小号小琴别结识别静音无输入）+ ASCII（0-9%: 空格）；16×16 点阵 ROM（$readmemh，≈9.5Kb≈1 DRM）；gen_font.py 从点阵字库生成 hex + sha256 归档；**与 class_names.json 的 name_zh 逐字核对断言（REQ-UI-005 用字验收、R-06 二次防线）**；大字渲染 3×3 像素复制放大（48×48 有效字高）由渲染侧实现。
- **完成判据（DoD）**：① `pytest tests/test_font.py`：8 类 name_zh（单簧管/失真电吉他/女声/长笛/钢琴/次中音萨克斯/小号/小提琴）全部字符在字库内命中（逐字断言）；② ROM 映射 1 DRM；③ hex sha256 归档；④ 重复生成逐位一致。
- **建议负责角色**：MDL（RTL 集成 font_rom）

### T-M3-02 实现 spectrum_disp：Mel 频谱图渲染
- **前置依赖**：T-M1-06（spec_rd_* 导出口）、T-M0-08
- **涉及文件**：`src/ui/spectrum_disp.v`、`src/ui/ui_renderer.v`（扩展）
- **任务描述**：按 §7.5 实现：dB 谱（Q8.8 int16）8bit 灰度压缩 `g=(dB+80)×255/80`；谱图页缓冲 64×258×8bit（单页 4 DRM + vsync 写闭锁，§10 修正项）；伪彩映射 5 段线性插值（蓝→青→绿→黄→红，组合逻辑常数乘法）；最近邻缩放（`frame×1920/258≈7.44`、`mel×440/64≈6.875` 定点乘常数）；显示区 y∈[320,760) 440 行；推理完成时刻写入、更新率 0.33Hz（3s 周期，REQ-UI-004/REQ-UI-007 保持最近结果语义）。
- **完成判据（DoD）**：① check_rtl.py 通过；② 板级目视：高音/低音曲目谱带位置随输入移动（REQ-UI-004 验收）；③ 无推理新结果时谱图保持不变（30s 静音观察，REQ-UI-007）；④ 谱图页缓冲 4 DRM 映射核对。
- **建议负责角色**：RTL

### T-M3-03 实现 bars_disp 与 ui_renderer 四要素完整集成
- **前置依赖**：T-M3-01、T-M3-02、T-M2-06
- **涉及文件**：`src/ui/bars_disp.v`、`src/ui/ui_renderer.v`（完整版）
- **任务描述**：按 §7.2/§7.6 实现：置信度条区 y∈[950,1080) 8 行——每行中文名标签（16×16 字库）+ 水平条（条长=`probs_q(u8,0..100)×1400/100` 整数乘 14，0.7px 精度 ≤ 验收 1px 容差）+ 百分比；top-1 行高亮描边 + 8 类固定 8 色；类别文本区 y∈[780,930)「识别结果：<name_zh> <pct>%」16×16 字库 3 倍放大；静音时③区叠加「静音/无输入」提示（REQ-REL-003 UI 语义）；125M→148.5M 结果经 vsync 握手双缓冲（§1.4 CDC 表，消隐期生效防撕裂）；四要素单屏合成（REQ-UI-002）。
- **完成判据（DoD）**：① check_rtl.py 通过、时序收敛；② 板级 T3.1：四要素同屏齐备且截图归档（REQ-UI-002/REQ-VER-004 项①）；③ 三条不同分布测试音频核对条长比例与 UART 概率一致（误差 ≤1 像素级，REQ-UI-006）；④ 中文名用字与 §6.4 表逐字核对（REQ-UI-005）；⑤ 拔 SD 线静音 30s：波形平线+静音提示+置信度保持、系统不复位（REQ-REL-003）。
- **建议负责角色**：RTL

### T-M3-04 实现 softmax_top：定点 softmax 与 top-1
- **前置依赖**：T-M2-06
- **涉及文件**：`src/ctrl/softmax_top.v`、`tests/test_softmax_model.py`
- **任务描述**：按 §4.5 实现：8 路 int32 logits → 减 max → 差值 Q6.9 缩放（截高 15bit）→ exp 查表 512 项×Q0.16 → 8 值求和 s48 → 时复用除法得 p_i Q0.16 → ×100 取整 → u8 百分比；top-1 类别 ID 提取；类别 ID→name_zh 映射以 class_names.json 唯一真源（REQ-INF-005）；输出 probs_q 8×u8 + top1_id 3bit（经结果双缓冲提交 UI）。
- **完成判据（DoD）**：① check_rtl.py 通过；② Python 模型单测：vs golden `--stage probs`，max|Δp|≤0.02、top-1 一致 100%（≥20 样本）；③ 板级 UART 导出 PROBS（layer_id 7）与 Python 概率比对一致（REQ-ACC-003 板级闭环）；④ exp LUT 1 DRM + 2 APM 映射核对（§10 表）。
- **建议负责角色**：RTL

### T-M3-05 实现 sys_ctrl 完整版与结果原子提交
- **前置依赖**：T-M2-06、T-M3-04
- **涉及文件**：`src/ctrl/sys_ctrl.v`（完整版）、`src/instrec_top.v`（最终版接线）
- **任务描述**：按 §2.2.9/§1.3 实现：完整自检链状态机 `PLL_LOCK_WAIT→DDR3_INIT→DDR3_PATTERN→WEIGHT_LOAD_SHA→HDMI_I2C_CFG→RUN`，任一失败 SAFE_ERR（LED 错误码+UART 报文+禁止 npu 结果提交 UI，REQ-REL-001）；各阶段 2× 预算看门狗（超时置标志+UART 告警+该阶段状态机复位重入不挂死，REQ-REL-002）；LED 编码（led[0] 心跳 1Hz/led[1] DDR OK/led[2] 推理进行/led[3] 结果有效/led[7:4] 错误码，REQ-MNT-003）；KEY0 异步复位同步释放（REQ-SYS-002）+ KEY1 两级同步+20ms 消抖触发导出（REQ-SYS-003/REQ-AUD-007）；窗口节拍→mel→npu→softmax 串行链调度；**结果双缓冲/握手原子提交**（窗口推理完成才切换，非新窗口时刻不更新，REQ-INF-008）；系统级状态（初始化/运行/静音/超时/错误）LED 与 UART 一致呈现（REQ-SYS-004）。
- **完成判据（DoD）**：① check_rtl.py 通过、时序收敛；② 板级状态注入测试（静音/超时/错误三态）LED 与 UART 呈现一致（REQ-SYS-004 验收）；③ 长时间运行 UI 无类别/概率跳变毛刺（非新窗口时刻，REQ-INF-008）；④ 按键 10 次均正确复位重启（REQ-SYS-002）；⑤ 超时注入（调试降频）触发恢复、连续 60s 无挂死（REQ-REL-002）。
- **建议负责角色**：RTL

### T-M3-06 M3 端到端联调与演示脚本（REQ-VER-004）
- **前置依赖**：T-M3-03、T-M3-05、T-M2-08
- **涉及文件**：`docs/demo_script.md`、`reports/m3_e2e.md`、`docs/m3_photos/`
- **任务描述**：执行 design.md §9.3 M3 用例：T3.1 四要素 UI 同屏+截图；T3.2 高速摄像 UI 刷新 ≥10fps（逐帧计数波形相邻更新 ≤100ms，无 >200ms 静止）；T3.3 推理周期/端到端延迟对表测量（拍手沿 ×10：窗口最后采样→HDMI 显示 ≤3.5s；相邻推理启动 ∈[2.9,3.1]s）；T3.4 60s 连续运行日志+拔 SD 线 30s 静音恢复（1 窗口内恢复正常显示）；T3.5 超时注入恢复；编写演示操作手册（含权重 UART 加载 60s 一次性准备段说明，D-05）。演示路径：I2S 音频源发声 → HDMI 观看四要素。
- **完成判据（DoD）：REQ-VER-004 全项通过**：① 四要素齐备（截图归档）；② UI 刷新 ≥10fps（帧计数证据）；③ 推理周期 ≤3.0s（连续 60s UART 时间戳统计）+ 端到端 ≤3.5s（10 次对表测量 max）；④ 60s 稳定性日志归档 + 静音/超时恢复通过；⑤ 演示脚本（操作步骤+预期现象）归档。**里程碑 M3 达成**。
- **建议负责角色**：VER

---

## 六、VF：验证与收尾（4 个任务）

### T-VF-01 全量回归对拍与端到端一致率
- **前置依赖**：T-M3-06
- **涉及文件**：`scripts/run_regression.py`（汇总驱动）、`reports/regression_final.md`
- **任务描述**：汇总执行全量回归：Mel 三方对拍 ≥20 条（REQ-ACC-001 两指标 + 边界样本）；NPU 逐层对拍 ≥100 特征样本（REQ-ACC-002 ±1 LSB 100%）；logits/softmax/top-1 指标（REQ-ACC-003）；**板级端到端 vs inference_reference.py：≥20 条覆盖 8 类音频（每类 ≥2 条）top-1 一致率 ≥90%，差异样本逐条归因记录（REQ-ACC-005）**；确定性回放复验（REQ-ACC-004）。一键脚本化（pytest 入口）。
- **完成判据（DoD）**：① `pytest scripts/run_regression.py`（或等价入口）全绿：REQ-ACC-001~005 五项指标全部达标并写入 regression_final.md；② 差异样本归因表（若有 <90% 差异样本，逐条注明 Mel 边界/饱和/类别混淆原因）；③ 样本清单含每类 ≥2 条。
- **建议负责角色**：VER

### T-VF-02 代码审查与 lint 全量通过
- **前置依赖**：T-M3-06
- **涉及文件**：`scripts/check_rtl.py`（全量执行）、`reports/code_review.md`
- **任务描述**：全量静态检查（check_rtl.py 对 src/**/*.v 零违例，REQ-BLD-003）；关键代码人工审查：CDC 穷举表逐项核对（§1.4 表 7 条路径全部有同步器/FIFO 且 fdc async group 覆盖，R-09）；DDR3 契约 checklist（§5.3 四项：wready 写完成/dummy-write 前置/rvalid 逐周期收/长突发对齐，REQ-MEM-003 RTL 审查项）；复位树每域异步断言同步释放；亚稳态路径（SD/KEY 两级同步器，REQ-AUD-007 RTL 审查确认）；设计 vs 实现一致性核对（17 模块端口契约抽查）。
- **完成判据（DoD）**：① check_rtl.py 退出码 0（零违例报告归档）；② code_review.md 含 CDC/DDR3 契约/复位树三张 checklist 全部 ✓；③ 发现问题清单（若有）逐条修复或登记豁免理由。
- **建议负责角色**：VER（RTL 会审）

### T-VF-03 资源与时序报告归档
- **前置依赖**：T-M3-06
- **涉及文件**：`reports/pnr_final/`（Device Utilization + report_timing + sbit sha256）
- **任务描述**：最终全量构建报告归档与预算核对：LUT ≤53,000（预期 ~22.8k）、FF ≤66,600（~19.3k）、DRM ≤108（~107 贴边，R-11 核对削减项落实：波形单页/谱图单页/wbuf bank 复用）、APM ≤144（~20）、GPLL ≤4（DDR3 2+HDMI 1+I2S 1）、DDR3 空间 ≤32MB（§5.1 映射表，实际 <2MB）；All Constraints Met（setup/hold WNS/WHS ≥0，REQ-BLD-002）；构建日志归档 + sbit sha256 记录（REQ-BLD-001）；既有工程目录 git diff 零改动终核（REQ-BLD-004）。
- **完成判据（DoD）**：① 最终 pnr 报告五项资源指标全部 ≤ 预算（REQ-RSC-001~004/006 验收）；② `C: Bitstream-2001: SCBV` 之外无 Error、sbit 存在且 sha256 归档；③ 时序报告 All Constraints Met；④ DRM 逐模块分解表归档（核对 §10 修正项）。
- **建议负责角色**：BLD

### T-VF-04 板级验收总结与交付包
- **前置依赖**：T-VF-01、T-VF-02、T-VF-03
- **涉及文件**：`reports/acceptance_final.md`、`docs/`（演示脚本/操作手册/归档汇总）
- **任务描述**：按 REQ-VER-001~004 逐条核对 M0~M3 判据（每条引用对应测试证据文件）；69 条 EARS 需求验收状态总表（spec §10.1 分组）；交付包整理：位流+sha256、权重镜像+layer_contract、全部对拍报告、示波器/HDMI 照片、UART 日志、演示脚本；30min 稳定性抽测（REQ-SYS-001 长稳项）；未达标项（若有）跟进措施表。
- **完成判据（DoD）**：① acceptance_final.md 覆盖 REQ-VER-001~004 全部判据且每项有证据链接；② 69 条需求状态总表（达标/豁免+理由）无空白；③ 30min 连续运行无复位（REQ-SYS-001 抽测日志）；④ 交付包目录清单完整（评委可按演示脚本 10 分钟内复现全流程）。
- **建议负责角色**：VER（BLD 协助交付包）

---

## 七、CT：风险预案（3 个可选任务，触发条件驱动）

> 仅在对应风险触发时执行；不进入关键路径统计。触发与决策记录于 `reports/risk_decisions.md`。

### T-CT-01（可选）DRM 超限降级：行缓冲/FFT 级间迁 LUTRAM
- **触发条件**：T-M2-06/T-VF-03 中 PnR 报告 DRM >108 块或因 DRM 拥塞导致时序失败（R-11）
- **前置依赖**：T-M2-06（触发后插入）
- **涉及文件**：`src/npu/conv_engine.v`（行缓冲实现参数）、`src/mel/fft2048_sdf.v`（级间延迟线）、`reports/risk_decisions.md`
- **任务描述**：按 design.md §10/R-11 降级梯次执行：① conv2/conv3 行缓冲改 2 行+半行边带（−8 块）；② FFT 级间缓冲迁 CLMS 分布式 RAM（LUT 余量 57% 吸收）；③ 极端情况 conv 行缓冲 DDR3 化（带宽余量 0.3% 支撑）。每次降级后重跑对拍（±1 LSB 不变）+ 全量构建核对资源与时序。
- **完成判据（DoD）**：① 降级后 DRM ≤108 且 All Constraints Met；② 回归对拍指标不变（±1 LSB 100%）；③ 降级决策与资源前后对比归档 risk_decisions.md。
- **建议负责角色**：RTL

### T-CT-02（可选）FFT 精度升级路径：BFP 块浮点
- **触发条件**：T-M1-07 对拍中深衰减 bin（−70dB 以下）相对误差导致 REQ-ACC-001 max|Δ|>0.05 或 r<0.999（R-03 兜底）
- **前置依赖**：T-M1-07（触发后插入）
- **涉及文件**：`src/mel/fft2048_sdf.v`（BFP 改造）、`scripts/golden_pipeline.py`（同步 BFP 语义）、`tests/test_golden_mel.py`
- **任务描述**：按 design.md §3.2 备选方案实现 BFP：每级指数比较+前馈移位（较每级 ÷2 精度优 ~6dB）；golden_pipeline.py 同步改 BFP 语义保持 bit-accurate 对拍；重跑 REQ-ACC-001 全量 20 条对拍。
- **完成判据（DoD）**：① 升级后 REQ-ACC-001 两指标（max|Δ|≤0.05、r≥0.999）20/20 达标；② golden 与 RTL 仍逐级 bit 一致；③ PDS 时序收敛（BFP 增量逻辑不破坏 125MHz）；④ 升级决策归档。
- **建议负责角色**：RTL + MDL

### T-CT-03（可选）I2S 时钟实测校准：NCO 步进微调
- **触发条件**：T-M0-10/T0.1 示波器实测 60s 累计误差折算 >±500ppm（晶振本征偏差超预期或 GPLL 偏移，R-01 残余风险）
- **前置依赖**：T-M0-10（触发后插入）
- **涉及文件**：`src/audio/i2s_clk_gen.v`（STEP 参数）、`reports/risk_decisions.md`
- **任务描述**：依据示波器/频率计实测偏差方向与幅度，计算修正 STEP（28bit 累加器步进微调，保持有理数比率逼近）；重测 60s 累计误差；必要时提供运行时微调寄存器（UART 命令写 STEP）供现场校准。
- **完成判据（DoD）**：① 修正后 60s 累计误差折算 ≤±500ppm（实测记录归档）；② Mel 对拍复验（频率轴标定不受影响，REQ-ACC-001 抽测 3 条）；③ 校准值与决策归档。
- **建议负责角色**：RTL + VER

---

## 八、需求→任务追溯表（69 条 EARS 全定位）

| 需求组 | 需求 ID | 主任务（DoD 落点） | 辅助任务 |
| ---- | ---- | ---- | ---- |
| 性能 REQ-PRF（5） | REQ-PRF-001 | T-M0-06（win_tick 节拍） | T-M3-06（T3.3 实测 [2.9,3.1]s） |
| | REQ-PRF-002 | T-M3-06（拍手沿 ×10 ≤3.5s） | T-GP-04/05（延迟链核算） |
| | REQ-PRF-003 | T-M1-06（mel_cycles）/T-M2-06（npu_cycles）/T-M3-03（UI ≤100ms） | T-M3-06 |
| | REQ-PRF-004 | T-M3-03（60fps 波形） | T-M3-06（T3.2 ≥10fps） |
| | REQ-PRF-005 | T-M0-05（带宽核算+wait_cnt） | T-VF-04（等待计数板级验收） |
| 资源 REQ-RSC（6） | REQ-RSC-001~004 | T-VF-03（五项指标终核） | T-M0-09/T-M2-06（中期核对）、T-CT-01 |
| | REQ-RSC-005 | T-M2-02（16 通道组 ≤27.6KB 流式+读流量非零） | T-M2-01（DDR3 驻留+校验） |
| | REQ-RSC-006 | T-M0-05（地址映射） | T-M0-09（自检覆盖全区间）、T-VF-03 |
| 精度 REQ-ACC（5） | REQ-ACC-001 | T-GP-04（Python 闭环）/T-M1-07（板级 20 条两指标） | T-M1-01~05（逐级 ±1 LSB） |
| | REQ-ACC-002 | T-GP-05（Python 闭环）/T-M2-08（±1 LSB 100%，≥100 样本） | T-M2-03~05 |
| | REQ-ACC-003 | T-GP-05/T-M2-08（logits ≤0.25、Δp ≤0.02、top-1 ≥99%） | T-M3-04（softmax 板级） |
| | REQ-ACC-004 | T-M2-08（T2.4 十次回放位级一致） | — |
| | REQ-ACC-005 | T-VF-01（≥20 条每类 ≥2，板级 vs Python ≥90%+归因） | T-M2-08（T2.5 前置） |
| 构建 REQ-BLD（5） | REQ-BLD-001 | T-GP-01（六阶段脚本） | T-VF-03（日志+sha256 归档） |
| | REQ-BLD-002 | T-VF-03（All Constraints Met） | 各构建任务 DoD |
| | REQ-BLD-003 | T-GP-06（lint 清单） | T-VF-02（全量零违例） |
| | REQ-BLD-004 | T-GP-01（独立目录） | T-M0-04/07（复制+溯源）、T-VF-03（git 零改动终核） |
| | REQ-BLD-005 | T-M0-10（JTAG 三步流程×3） | T-VF-04（演示复现） |
| 可靠性 REQ-REL（3） | REQ-REL-001 | T-M3-05（自检链+SAFE_ERR） | T-M0-10（首错注入）、T-M2-01（WERR） |
| | REQ-REL-002 | T-M3-05（2× 看门狗重入） | T-M3-06（T3.5 注入恢复） |
| | REQ-REL-003 | T-M0-02（sd_idle）/T-M0-06（静音注入） | T-M3-03（UI 提示）、T-M3-06（T3.4 拔线 30s） |
| 可维护 REQ-MNT（3） | REQ-MNT-001 | T-M0-09（行式输出） | T-M2-07（STATS 帧+可解析） |
| | REQ-MNT-002 | T-M2-07（KEY1 导出协议） | T-M1-07（Mel 导出对拍） |
| | REQ-MNT-003 | T-M3-05（四态 LED） | T-M3-06（板级观察） |
| 音频 REQ-AUD（7） | REQ-AUD-001 | T-M0-01（主机模式三线） | T-M0-09（fdc 引脚+避让） |
| | REQ-AUD-002 | T-M0-01（NCO 频率合成） | T-M0-10（T0.1 示波器） |
| | REQ-AUD-003 | T-M0-01（±500ppm 设计） | T-M0-10（60s 实测）、T-CT-03 |
| | REQ-AUD-004 | T-M0-02（Philips 解码） | T-M0-10（逻辑分析仪） |
| | REQ-AUD-005 | T-M0-02（左右分离） | T-M0-06（右声道仅存档） |
| | REQ-AUD-006 | T-M0-09（i2s 约束齐全+选型依据） | — |
| | REQ-AUD-007 | T-M0-02（SD 双同步） | T-M3-05（KEY 同步消抖）、T-VF-02 |
| 存储 REQ-MEM（5） | REQ-MEM-001 | T-M0-04（IP 复用+实例名） | — |
| | REQ-MEM-002 | T-M0-06（环形缓冲+节拍） | T-M0-10（60s 无回卷） |
| | REQ-MEM-003 | T-M0-05（契约适配三规则） | T-VF-02（checklist） |
| | REQ-MEM-004 | T-M0-05（仲裁+wait_cnt） | T-VF-04（10 窗口统计） |
| | REQ-MEM-005 | T-M0-09（图案自检） | T-M0-10（T0.2 DDROK） |
| 特征 REQ-FTR（7） | REQ-FTR-001 | T-GP-02（参数固化+断言） | T-M1-* 全链 |
| | REQ-FTR-002 | T-M1-01（reflect 边界） | T-GP-04（首末帧对拍） |
| | REQ-FTR-003 | T-GP-02（系数表+sha256） | T-M1-03（COO 硬件） |
| | REQ-FTR-004 | T-M1-04（top_db 截断） | T-M1-07（深静音专测） |
| | REQ-FTR-005 | T-M1-05（μ/σ 两阶段） | T-M1-07（拼接音频专测） |
| | REQ-FTR-006 | T-M1-05（int8 量化输出+设计说明） | T-GP-04 |
| | REQ-FTR-007 | T-M1-06（mel_cycles） | T-M1-07（T1.2 ≤150ms） |
| 推理 REQ-INF（8） | REQ-INF-001 | T-M2-05（结构对照表+floor 池化） | T-M2-03（形状参数化） |
| | REQ-INF-002 | T-GP-03（镜像转换） | T-M2-04（requant 硬件语义） |
| | REQ-INF-003 | T-M2-01（加载+校验） | T-M2-02（推理期流式） |
| | REQ-INF-004 | T-M2-03（16 MAC/57.5ms） | T-M2-06（npu_cycles ≤200ms） |
| | REQ-INF-005 | T-M3-04（softmax+top-1+类别表） | T-M3-01（name_zh 字库） |
| | REQ-INF-006 | T-M2-07（逐层导出） | T-M2-08 |
| | REQ-INF-007 | T-M2-04（饱和策略） | T-GP-05（满幅专测） |
| | REQ-INF-008 | T-M3-05（双缓冲原子提交） | T-M3-06（无跳变观察） |
| UI REQ-UI（7） | REQ-UI-001 | T-M0-07（demo 复用+1080p） | T-M0-10 |
| | REQ-UI-002 | T-M3-03（四要素合成） | T-M3-06（T3.1 截图） |
| | REQ-UI-003 | T-M0-08（波形 ≥10fps） | T-M3-03 |
| | REQ-UI-004 | T-M3-02（谱图渲染） | T-M3-06（高/低音谱带移动） |
| | REQ-UI-005 | T-M3-01（name_zh 字库核对） | T-M3-03（显示核对） |
| | REQ-UI-006 | T-M3-03（置信度条） | T-M3-06（条长比例核对） |
| | REQ-UI-007 | T-M3-02（vsync 写闭锁） | T-M3-05（双缓冲）、T-M3-06 |
| 系统 REQ-SYS（4） | REQ-SYS-001 | T-M3-05（自动循环） | T-M3-06（60s）、T-VF-04（30min） |
| | REQ-SYS-002 | T-M3-05（KEY0 复位） | T-M3-05 DoD ④ |
| | REQ-SYS-003 | T-M3-05（KEY1 触发导出） | T-M2-07（协议） |
| | REQ-SYS-004 | T-M3-05（状态+LED/UART 一致） | T-M3-05 DoD ② |
| 验收 REQ-VER（4） | REQ-VER-001 | T-M0-10（M0 全项） | — |
| | REQ-VER-002 | T-M1-07（M1 全项） | — |
| | REQ-VER-003 | T-M2-08（M2 全项） | — |
| | REQ-VER-004 | T-M3-06（M3 全项） | T-VF-04（终验） |

**追溯完整性结论**：69 条 EARS 需求（PRF5+RSC6+ACC5+BLD5+REL3+MNT3+AUD7+MEM5+FTR7+INF8+UI7+SYS4+VER4）全部定位到至少 1 个主任务 DoD；设计文档 17 个模块全部出现在 ≥1 个任务（instrec_top→T-M0-09/T-M2-06/T-M3-05；i2s_clk_gen→T-M0-01；i2s_rx→T-M0-02；audio_cdc_fifo→T-M0-03；audio_sink→T-M0-06；ddr3_ctrl_axi+ddr3_arbiter→T-M0-05；ddr3_wrapper→T-M0-04；mel_engine 及 hann_rom/stft_framer/fft2048_sdf/mel_filter/log2_lut/db_norm/standardize→T-M1-01~06；npu_top 及 wdma/conv_engine/pool_engine/gap_fc→T-M2-02~06；softmax_top→T-M3-04；ui_renderer 及 waveform_disp/spectrum_disp/font_rom/bars_disp→T-M0-08/T-M3-01~03；hdmi_tx_if→T-M0-07；uart_debug→T-M0-09/T-M2-07；self_test→T-M0-09/T-M2-01；sys_ctrl→T-M0-09/T-M3-05；weight_loader→T-M2-01）。

---

## 九、关键路径与任务统计

### 9.1 关键路径（最长依赖链，14 节点）

> **T-GP-01 → T-M0-01 → T-M0-02 → T-M0-03 → T-M0-05 → T-M0-06 → T-M0-09 → T-M0-10 → T-M1-01 → …（M1 内部串行 6 任务）… → T-M1-07 → T-M2-01 → …（M2 内部串行）… → T-M2-08 → T-M3-06 → T-VF-01 → T-VF-04**

一句话概括：**「构建脚手架 → I2S/DDR3/HDMI 链路（M0 板级验收）→ Mel 逐级对拍（M1 板级验收）→ 权重加载与 NPU 逐层对拍（M2 板级验收）→ 四要素端到端（M3 验收）→ 全量回归与最终交付」**——即音频采集链 → 特征链 → 推理链 → 显示链的串行主干，总历时 ≈14 个关键任务节点（M1/M2 内部子模块链各自串行计入）。

### 9.2 任务总数统计

| 阶段 | 任务数 | 任务 ID 区间 |
| ---- | ---- | ---- |
| P0 工具链与 Python 金标准 | 6 | T-GP-01 ~ T-GP-06 |
| M0 链路贯通 | 10 | T-M0-01 ~ T-M0-10 |
| M1 Mel 特征引擎 | 7 | T-M1-01 ~ T-M1-07 |
| M2 INT8 CNN NPU | 8 | T-M2-01 ~ T-M2-08 |
| M3 UI 集成与端到端 | 6 | T-M3-01 ~ T-M3-06 |
| VF 验证与收尾 | 4 | T-VF-01 ~ T-VF-04 |
| **必做合计** | **41** | — |
| CT 风险预案（可选） | 3 | T-CT-01 ~ T-CT-03 |
| **总计（含可选）** | **44** | — |

### 9.3 角色工作量分布（必做 41 任务）

| 角色 | 任务数 | 主要阶段 |
| ---- | ---- | ---- |
| RTL 工程师 | 22 | M0/M1/M2 RTL 主体、M3 UI 与控制 |
| 模型工程师 | 6 | P0 金标准与转换工具全链 |
| 构建工程师 | 4 | P0 脚手架、M0 资产复制、VF 资源报告 |
| 验证工程师 | 9 | P0 lint、各里程碑板级验收、VF 收尾 |

（完）
- **建议负责角色**：VER