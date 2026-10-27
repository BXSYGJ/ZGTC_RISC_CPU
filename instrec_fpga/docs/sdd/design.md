# InstRec-FPGA 技术设计文档

| 项目 | 内容 |
| ---- | ---- |
| 文档标识 | design.md / instrec_fpga |
| 版本 | v1.0 |
| 日期 | 2026-10-26 |
| 作者 | 技术设计工程师（王工） |
| 上游输入 | `.codeartsdoer/specs/instrec_fpga/spec.md` v1.0（69 条 EARS 需求） |
| 目标器件 | 紫光同创 Logos2 `PG2L100H-6IFBG676`（-6 速级，FBG676 封装） |
| 目标板卡 | 盘古 100Pro+ 开发板 `MES2L676-100HP` |
| 工程落盘 | `D:\0000\111\001\Pango\ZGTC_RISC_CPU\instrec_fpga\` |
| RTL 规范 | SystemVerilog-2005 子集（`always @*`、无 SV-2012 语法）、标识符 snake_case、参数全大写、注释一律英文、顶层端口禁止 `.port()` 空连接（REQ-BLD-003） |

---

# 〇、设计输入核实结论（关键事实与决策依据）

设计前对本仓库及 InstRec 部署资产逐项核实，以下事实直接决定架构走向：

| # | 核实项 | 结论（证据） | 对设计的影响 |
| --- | --- | --- | --- |
| F-01 | 权重 scale 语义 | `InstRec/src/quantize.py` L564-581 证实 `deploy/weights/*_scale.npy` 保存的是 **q_weight.q_per_channel_scales()（权重 per-channel scale s_w，shape=(Cout,)）**，并非激活 scale。激活 per-tensor scale（s_in/s_out）与 zero_point **未落在 weights/ 目录**，必须由转换工具从 `deploy/quantized_model.pt`（TorchScript，fbgemm）的 activation_post_process 提取 | 部署镜像转换工具必须双源输入（npy + pt）；layer_contract.json 含 s_in/s_out/zp 逐层表（见 §6） |
| F-02 | 权重形状 | conv1(48,1,3,3)、conv2(96,48,3,3)、conv3(192,96,3,3)、conv4(256,192,3,3)、fc1(128,256)、fc2(8,128)，全部 int8 + int32 bias(对称 zp=0) | NPU 权重布局与分块方案输入（§4.1） |
| F-03 | 权重总量 | 685,864 参数 ≈ 0.67 MB（含 bias 724×4B） > 片上 DRM 总量 155×18Kb=2.79Mb | 权重 DDR3 驻留 + 16 输出通道分组流式（REQ-RSC-005，每组 ≤27.6KB ≤32KB/层） |
| F-04 | Mel 全局依赖 | `src/features.py` L103-121：`power_to_db(ref=np.max, top_db=80)` 与 per-sample 标准化 `(x-μ)/(σ+1e-6)` 均依赖整张 64×258 谱 | Mel 引擎采用「log2 域整谱缓冲（int16 Q8.8，15 DRM 块）+ 两遍处理」：第一遍 STFT→Mel→log2 存储，第二遍求 max/μ/σ→dB→标准化→int8 量化（§3） |
| F-05 | Mel 边界语义 | `features.py` L150-163：`center=True, pad_mode="reflect"`；帧数不足右侧补零、超出保留末端（L88-100） | STFT 帧供给器实现首帧前 1024 采样 reflect 翻转、窗口读越界补零（§2.2.6） |
| F-06 | 网络结构 | `src/model.py`：conv1(1→48,p1)+pool2 → conv2(48→96)+pool2 → conv3(96→192)+pool2 → conv4(192→256)+pool2 → GAP → fc1(256→128)+ReLU → fc2(128→8)；池化 floor 语义 258→129→64→32→16 / 64→32→16→8→4 | NPU 逐层形状表与 floor 池化实现（§4.4） |
| F-07 | DDR3 IP 契约 | `pds_cpu_100h/ipcore/ddr3_test/ddr3_test.v`：AXI 写通道无 `axi_wvalid` 输入（写完成以 `axi_wready` 判定）、读通道无 `axi_rready`（rvalid 期间须每周期收数）、无 axi_b 通道；数据宽度 256bit（8×32）；读前需 dummy-write | 仲裁器/控制器按此契约设计（§2.2.5、§5.3） |
| F-08 | DDR3 资产复用 | `pds_cpu_100h/constraints/ddr3_100h.fdc`（535 行：6 个 generated clock、每时钟独立 async group、multicycle 2、uncertainty 0.4、73 针 SSTL15）+ `scripts/gen_ddr3_fdc.py`；IP 实例名必须 `I_ips_ddr_top` | 约束以复制方式引入并重挂层级（§12） |
| F-09 | HDMI demo 通路 | demo 顶层 `ad_da_hdmi_top.v`：27MHz → pll（148.5MHz pix_clk + 10MHz cfg_clk）→ `ms72xx_ctl`（I2C K22/K23）→ `sync_vg` 1080p@60（H_TOTAL=2200/V_TOTAL=1125/H_ACT=1920/V_ACT=1080）；vout_data[23:0] 并行 RGB | UI 视频通路原样复用 demo 结构（REQ-UI-001，R-05 缓解） |
| F-10 | HDMI 引脚 | demo fdc 全 32+5 脚已核实（vout_data[23:0]、vout_clk T24、vout_de N19、vout_hs R20、vout_vs R21、iic K22/K23）；ADDA demo 占用的 FMC 脚（ad_data_in V16/V17/Y22/Y23/AB24/AC24/W25/Y26、ad_clk U20、da_clk T20 等）在本设计中**释放** | I2S 三线从释放的 FMC 脚中选（§8） |
| F-11 | GPLL 占用 | ddr3_100h.fdc 证实 DDR3 PHY 占 2 个 GPLL（rst_clk_gpll、ddrphy_gpll）+ 2 PPLL；HDMI demo pll 占 1 GPLL；核心域直接使用 DDR3 IP 输出的 `core_clk`（125MHz）不额外占 GPLL | I2S 时钟用最后 1 个用户 GPLL（216MHz=27×8），总 4 个 GPLL 满足 REQ-RSC-002 |
| F-12 | 资源基线 | pds_cpu_100h PnR 实测（20261025-112034）：全 SoC 8458 LUT / 4300 FF / 21 DRM / 4 APM / 1 GPLL（其中 DDR3 wrapper+PHY 为主要构成）；HDMI demo PnR 显示纯显示通路规模很小 | 本设计资源估算以实测数据为锚点（§10） |
| F-13 | 类别真源 | `deploy/class_names.json`：0=单簧管 … 7=小提琴（与 dataset.py 一致）；`irmas/model_config.json` classes 判过时禁用 | 字库字符集合与 UI 标签唯一真源 |
| F-14 | 构建流程 | `pds_shell.exe -file build_full.tcl`（六阶段）；模板 `pds_cpu_100h/scripts/build_full.tcl`；SCBV 警告豁免；无本地仿真 | 构建/验证方案（§9、§12） |
| F-15 | 板载引脚 | `.skills/pango-pg2l100h-dev/references/pin_constraints.md`：clk D18 / rst_n C22 / key C23 / led[7:0] / uart B24/C24，LVCMOS33 | 顶层引脚约束（§12） |

---

# 一、系统架构

## 1.1 顶层框图

```text
                        +---------------------------------------------------------------------+
   clk_27m (D18) -----> |  GPLL_D (audio_pll): 27MHz -> 216MHz (NCO 时基)                     |
                        +--------------------+------------------------------------------------+
                                             | clk_nco 216MHz
                                             v
                        +--------------------+----------------+
   i2s_sd   (V16) ----> |  i2s_clk_gen (NCO/DDS)             |----> i2s_bck  (U20, 1.4112MHz)
                        |  28bit 相位累加器 + tick 使能        |----> i2s_lrck (T20, 44.1kHz)
                        +--------------------+----------------+
                                             | pcm_tick / pcm_sample (s16, 虚拟 44.1kHz 节拍)
                                             v
                        +--------------------+----------------+
                        |  i2s_rx (Philips 格式, 左右声道分离)  |
                        +--------------------+----------------+
                                | ch_l s16 / ch_r s16 @44.1kHz 节拍
                                v
                        +--------------------+----------------+
                        |  audio_cdc_fifo (双时钟 DRM FIFO)    |  异步: 216M 域 -> 125M 核心域
                        +--------------------+----------------+
                                | pcm_l/s16, pcm_r/s16 @ core_clk
                                v
  +=======================================================================================================+
  |  核心域 core_clk 125MHz (DDR3 IP 输出)                                                                 |
  |                                                                                                       |
  |   +----------------+    写     +----------------------+    AXI 256bit   +-----------------------+      |
  |   | audio_sink     |---------->|                      |<---------------->| I_ips_ddr_top         |      |
  |   | (PCM 环形缓冲  |          |  ddr3_ctrl_axi       |  aw/w/ar/r       | (ddr3_test IP, 复制)  |      |
  |   |  写指针+节拍)   |<---------|  + 4 主仲裁器         |------------------>| 2 GPLL + 2 PPLL 内部  |      |
  |   +----------------+  窗口节拍  |  (固定优先级+配额)    |   rdata          +-----------+-----------+      |
  |                         |      +----------+-----------+                              |                  |
  |   窗口满触发            v                 ^ 读                                       | mem_dq/dqs/        |
  |   +----------------+    |      +----------+-----------+       PCM 读 / 权重读 / 谱读   | mem_a/ba/ctl 73 针 |
  |   | sys_ctrl       |    |      | mel_engine           |<------------------------------+      |
  |   | (自检链/超时/   |    +----->| stft_framer/hann/    |                                       |
  |   |  LED/静音检测)  |           | fft2048_sdf/mel_flt/ |---- log2 谱 (15 DRM)                   |
  |   +----------------+           | db_norm/standardize  |                                       |
  |         | 启动/状态            +----------+-----------+                                       |
  |         v                                 | feat int8 (64x258) 片上                                        |
  |   +----------------+                      v                                                       |
  |   | npu_top        |           +---------------------------+                                     |
  |   | wdma(权重流式) |<----------| 权重区 DDR3 (16 通道分组)  |                                     |
  |   | conv_engine x4 |           +---------------------------+                                     |
  |   | pool(GAP)/fc   |                                                                                    |
  |   +----------------+                                                                                    |
  |         | logits int32 x8 + probs                                                                      |
  |         v                                                                                               |
  |   +----------------+   结果双缓冲(vsync 对齐)  +-------------------+                                    |
  |   | softmax_top    |------------------------>| ui_renderer        |                                    |
  |   +----------------+                         | (波形/谱图/中文字   |                                    |
  |                                              |  库/置信度条合成)   |                                    |
  |                                              +---------+---------+                                    |
  |   +----------------+   KEY1 导出请求                   | rgb 24bit @ pix_clk                              |
  |   | uart_debug     |<-------------------------------- |   (经异步 FIFO 从 125M -> 148.5M)              |
  |   | (115200 8N1 +  |                                  v                                                  |
  |   |  逐层导出协议) |                     +-------------------+  27MHz -> GPLL_B (demo pll)             |
  |   +----------------+                     | hdmi_tx_if        |-> vout_data[23:0]/de/hs/vs/clk         |
  |                                          | + ms72xx_ctl(I2C) |-> iic_tx_scl K22 / iic_tx_sda K23       |
  |   +----------------+                     | + sync_vg 1080p60 |-> vout_clk T24 等                      |
  |   | self_test      |                     +-------------------+                                     |
  |   | (DDR3 图案/    |                                                                                |
  |   |  权重 sha256)  |                                                                                |
  |   +----------------+                                                                                |
  +=======================================================================================================+
                                    |
   led[7:0] <-----------------------+  (心跳/DDR OK/推理中/结果有效/错误码)
   uart_tx/rx (B24/C24) <----------- uart_debug
```

架构三原则（对应需求）：

1. **权重 DDR3 驻留、激活全片上行流水**（REQ-RSC-005 / R-04）：只有权重走 DDR3 分组流式；conv1→pool1→…→pool4→GAP 全程行条带流水，激活零 DDR3 回写。激活行缓冲峰值约 71KB（≈32 DRM 块）。
2. **Mel 两遍 + log2 域整谱缓冲**（REQ-FTR-004/005）：功率域 80dB 动态范围压缩为 log2 定点 int16 存储，规避 528Kb s32 整谱；两遍处理分别消解 ref=max 与 μ/σ 全局依赖。
3. **单核心域 + 双 IO 域**：NPU/Mel/仲裁/控制全部运行于 DDR3 IP 输出的 `core_clk`（125MHz），与 DDR3 AXI 同域零 CDC；仅音频（216MHz NCO 域）与像素（148.5MHz）两个外部域经异步 FIFO 隔离，CDC 面最小化（R-09 缓解）。

## 1.2 时钟树

| 时钟 | 频率 | 来源 | 用途 | GPLL 占用 |
| --- | --- | --- | --- | --- |
| `clk_27m` | 27 MHz | 板载晶振 D18 | 全部 GPLL 参考输入 | — |
| `core_clk` | 125 MHz | DDR3 IP 输出（PHY 内部 GPLL 分出） | 核心域：仲裁器/Mel/NPU/softmax/uart/sys_ctrl/自检 | （含在 DDR3 2 个 GPLL 内） |
| DDR3 PHY 内部 | — | rst_clk_gpll + ddrphy_gpll + 2×PPLL | DDR3 PHY（IP 内部，不可省） | 2 GPLL + 2 PPLL |
| `pix_clk` | 148.5 MHz | GPLL_B（复用 demo `pll` IP：27→148.5M + 10M） | 1080p@60 视频时序、UI 渲染、hdmi_tx_if | 1 |
| `cfg_clk` | 10 MHz | GPLL_B 第二输出 | ms72xx_ctl I2C 配置时钟（demo 原样） | （同上） |
| `clk_nco` | 216 MHz | GPLL_D（audio_pll：27×8 整数倍频） | I2S 时钟 NCO 时基 | 1 |
| `uart_clk` | — | 复用 `core_clk`（125MHz 分频得 115200 波特率，125e6/115200=1085.07，重采样 16× 过采样容差 ±0.04% 满足 8N1） | uart_debug | — |

**GPLL 合计 4 个 ≤ REQ-RSC-002 的 4 个上限**（DDR3 2 + HDMI 1 + I2S 1）。不为核心域新配 GPLL 是刻意决策：核心域与 DDR3 AXI 同时钟可彻底免除 AXI 通路 CDC，且省一个 GPLL 作为裕量。

### I2S 时钟方案选型（R-01 的正式决策）

**问题**：27MHz 与 44.1kHz 家族（BCK=1.4112MHz）无整数倍关系（27e6/44100 = 30000/49）。

**候选方案对比**：

| 方案 | 原理 | 误差 | 风险 | 结论 |
| --- | --- | --- | --- | --- |
| A. GPLL 分数分频直接合成 | 若 GPLL 支持小数模式 27MHz×49/117.6 | 理论 0 | Logos2 GPLL 小数模式在 PDS 2022.2-SP6.4 的稳定性未在本仓库验证过；demo 无先例 | 不采用（无板级先例） |
| B. **整数倍频 + NCO 相位累加器（DDS）** | GPLL 整数倍频 216MHz（27×8，无小数配置风险）+ 28bit 相位累加器产生 BCK 翻转 tick | 平均频率数学上精确（有理数比率 784/45000）；误差仅来自累加器舍入 ≈0.02ppm + 晶振本征 ~±50ppm | BCK 瞬时 jitter ±1 个 216M 周期（±4.63ns） | **采用** |
| C. 148.5MHz 或 125MHz 现有时钟分频 | 125e6/1.4112e6 = 88.57 非整数；148.5M 同理 | NCO 同 B 但时基更抖（且 125M 与 DDR3 争用） | 无独立音频时基 | 不采用 |

**方案 B 误差分析（REQ-AUD-003 验算）**：

- BCK 翻转频率目标 `F_bck_toggle = 2 × 1.4112MHz = 2.8224MHz`；NCO 步进 `STEP = round(2^28 × 2822400 / 216000000) = round(2^28 × 0.013072) = 3509057`（28bit 累加器，舍入残差 <1/2^28 → 频率误差 < 0.004ppm）。
- 216MHz 由 GPLL 整数倍频（M=8,D=1）产生，相对 27MHz 晶振理论零误差；实际总误差由板载晶振本征精度主导（典型 ±50ppm，远小于 ±500ppm）。
- 累加器溢出周期性：`216e6 / 2^28 × 3509057` 的相位循环周期为 45000 个 216M 周期（=784 个 BCK 翻转 = 392 个 BCK 周期 = 12.25 个 LRCK 半周期），长期平均频率精确锁死在 44.1kHz 家族比率上。
- BCK jitter：tick 时刻量化到 216M 周期（±4.63ns）。I2S 从机在 BCK 边沿采样 SD，建立/保持窗口通常 >50ns，4.63ns 抖动无影响；LRCK 相位切换同样由 tick 计数生成，与 BCK 严格同步（无差拍）。
- 28bit 累加器在 216MHz 的加法进位链（约 1.5ns）满足时序；若 PnR 紧张则拆 14+14 两级流水（不影响平均频率）。

**音频节拍语义**：`i2s_clk_gen` 输出 `bck_tick`（BCK 半周期使能脉冲）与 `bit_phase[4:0]`（BCK 域 16bit 移位相位）；i2s_rx 全部逻辑运行于 `clk_nco`，仅以 `bck_tick` 为使能推进，等价于在 44.1kHz 家族的虚拟时钟域工作，无亚稳态（tick 是同域使能信号）。

## 1.3 复位树

```text
rst_n (KEY0, C22, 异步低有效)
   |
   v
[core 域] rst_sync_core: 两级同步 + 10ms 释放延时计数器 (core_clk)
   |-> ddr3_ctrl_axi / mel_engine / npu_top / softmax / uart_debug / sys_ctrl / self_test
[音频域] rst_sync_nco:  两级同步 + GPLL_D lock 门控 (clk_nco)
   |-> i2s_clk_gen / i2s_rx
[像素域] rst_sync_pix:  两级同步 + GPLL_B lock 门控 + 1ms 计数 (pix_clk, 复刻 demo rstn_1ms 逻辑)
   |-> ui_renderer / hdmi_tx_if / ms72xx_ctl
[cfg 域] rst_sync_cfg:  同步释放 (cfg_clk 10MHz, demo 原样)
   |-> ms72xx_ctl
```

- 每个时钟域独立「异步断言、同步释放」复位（REQ-SYS-002；`.skills` 建议原样）。
- DDR3 IP 的 `resetn` 接核心域同步复位；IP 输出 `core_clk_rst_n` 用于复位 IP 侧 AXI 逻辑的补充复位。
- GPLL 未锁定（`pll_lock` 丢失）时对应域复位保持有效（REQ-REL-001 安全态链起点）。
- sys_ctrl 维护全局自检链状态机：`PLL_LOCK_WAIT → DDR3_INIT → DDR3_PATTERN → WEIGHT_LOAD_SHA → HDMI_I2C_CFG → RUN`，任一失败进入 `SAFE_ERR` 态（LED 错误码 + UART 报文 + 禁止 npu 结果提交 UI）。

## 1.4 CDC 策略

跨域路径穷举（R-09 全覆盖）：

| 源域 → 目的域 | 信号 | 隔离手段 | 说明 |
| --- | --- | --- | --- |
| 216M(nco) → 125M(core) | PCM 样本流（s16×2） | 双时钟 DRM FIFO `audio_cdc_fifo`（深 512×32bit，左右声道打包） | 音频速率 44.1kHz×2ch ≈ 88.2k 样本/s，FIFO 水位低，无溢出风险 |
| 125M(core) → 216M(nco) | 静音标志/使能（单 bit） | 两级同步器 | 控制类低速信号 |
| 125M(core) → 148.5M(pix) | UI 结果（类别/8 概率/谱图数据/波形列数据） | 结果寄存器组 + vsync 握手双缓冲；谱图/波形数据经双时钟 FIFO 成块搬运 | 更新只在垂直消隐期生效（REQ-UI-007 / UI 异常场景 2 防撕裂） |
| 148.5M(pix) → 125M(core) | vsync 脉冲（单 bit） | 两级同步 + 边沿检测 | 消隐期窗口指示 |
| 27M(异步) → 各域 | KEY1 按键 | 两级同步器 + 20ms 消抖（REQ-AUD-007） | |
| nco 域 SD 输入（异步） | i2s_sd 引脚 | 两级同步器（216M）后按 bck_tick 采样 | REQ-AUD-007 / 异常场景 2 |
| core → pix 波形列缓冲 | 1920×2×16bit 波形包络 | 双时钟 DRM FIFO（ping-pong 行组） | UI 每帧读取 |

所有跨域路径在 fdc 中以 `set_clock_groups -asynchronous` 覆盖（沿用官方 ddr3_100h.fdc 的每时钟独立 group 写法，新增 `pix_clk`、`clk_nco` 两个 group）。

---

# 二、模块划分与接口契约

## 2.1 模块清单与文件规划

| 模块 | 层级 | 文件（instrec_fpga/src/） | 职责 | 对应需求 |
| --- | --- | --- | --- | --- |
| `instrec_top` | 顶层 | `instrec_top.v` | 引脚汇聚、GPLL 例化、域复位、模块互联 | 全部 |
| `i2s_clk_gen` | 音频 | `i2s_clk_gen.v` | NCO 合成 BCK/LRCK、产生 bck_tick/bit_phase | REQ-AUD-002/003/004 |
| `i2s_rx` | 音频 | `i2s_rx.v` | Philips I2S 帧解码、左右声道分离、静音检测 | REQ-AUD-004/005、REQ-REL-003 |
| `audio_cdc_fifo` | 音频 | `audio_cdc_fifo.v` | 216M→125M 双时钟样本 FIFO | REQ-AUD-007 |
| `audio_sink` | 核心 | `audio_sink.v` | PCM 环形缓冲写指针（DDR3 窗口节拍生成）、静音注入 | REQ-MEM-002、REQ-PRF-001 |
| `ddr3_ctrl_axi` | 核心 | `ddr3_ctrl_axi.v` + `ddr3_arbiter.v` | 4 主仲裁 + AXI 契约适配（wready 写完成、读前 dummy-write、rvalid 逐周期收数）+ 突发组装 | REQ-MEM-003/004 |
| `ddr3_wrapper` | 核心 | `ddr3_wrapper.v` | IP 例化壳（实例名 I_ips_ddr_top 内层）、dbg 信号常量绑定 | REQ-MEM-001 |
| `mel_engine` | 核心 | `mel_engine.v` + `stft_framer.v` + `fft2048_sdf.v` + `mel_filter.v` + `db_norm.v` | 两遍 Mel 特征管线 | REQ-FTR-001~007 |
| `npu_top` | 核心 | `npu_top.v` + `wdma.v` + `conv_engine.v` + `pool_engine.v` + `gap_fc.v` | INT8 CNN 前向（权重流式、16 MAC 阵列、requant） | REQ-INF-001~008 |
| `softmax_top` | 核心 | `softmax_top.v` | 定点 softmax、top-1、概率×100 | REQ-INF-005 |
| `ui_renderer` | 像素 | `ui_renderer.v` + `waveform_disp.v` + `spectrum_disp.v` + `font_rom.v` + `bars_disp.v` | 四要素合成渲染 | REQ-UI-002~007 |
| `hdmi_tx_if` | 像素 | `hdmi_tx_if.v`（含 demo 复制的 `sync_vg/iic_dri/ms7200_ctl/ms7210_ctl/ms72xx_ctl`） | 1080p 时序 + I2C 配置 | REQ-UI-001 |
| `uart_debug` | 核心 | `uart_debug.v` + `uart_tx.v` + `uart_rx.v` | 状态/时间戳/逐层导出协议 | REQ-MNT-001/002、REQ-INF-006 |
| `self_test` | 核心 | `self_test.v` | DDR3 图案自检、权重回读校验（简化 sha256 之外的逐字比对 + 段校验和） | REQ-MEM-005、REQ-INF-003 |
| `sys_ctrl` | 核心 | `sys_ctrl.v` | 自检链状态机、超时看门狗（REQ-REL-002）、LED 编码、KEY1 消抖导出触发 | REQ-SYS-001~004、REQ-REL-001/002 |
| `weight_loader` | 核心 | `weight_loader.v` | UART 命令流 → DDR3 权重区写入 + 回读校验 | REQ-INF-003（§6） |

## 2.2 端口级契约表（关键模块）

以下契约表为 RTL 实现的强制接口（信号名 snake_case、位宽、方向、语义）。通用约定：所有 valid/ready 握手在 core_clk 域；多字节字段一律小端。

### 2.2.1 instrec_top（顶层引脚契约）

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `clk_27m` | 1 | in | 板载 27MHz（D18） |
| `rst_n` | 1 | in | KEY0 异步复位（C22，低有效） |
| `key1_n` | 1 | in | KEY1 导出触发（C23，低有效） |
| `led` | 8 | out | LED 状态（A20/C18/C19/E18/A17/A18/C17/B17） |
| `uart_rx` | 1 | in | CP2102（B24） |
| `uart_tx` | 1 | out | CP2102（C24） |
| `i2s_bck` | 1 | out | I2S 位时钟 1.4112MHz（U20） |
| `i2s_lrck` | 1 | out | I2S 帧时钟 44.1kHz（T20） |
| `i2s_sd` | 1 | in | I2S 串行数据（V16） |
| `iic_tx_scl` | 1 | out | HDMI 芯片 I2C 时钟（K22，demo 原样） |
| `iic_tx_sda` | 1 | inout | HDMI 芯片 I2C 数据（K23，demo 原样） |
| `vout_clk` | 1 | out | 像素时钟（T24） |
| `vout_de` | 1 | out | 数据使能（N19） |
| `vout_hs` | 1 | out | 行同步（R20） |
| `vout_vs` | 1 | out | 场同步（R21） |
| `vout_data` | 24 | out | 并行 RGB（demo fdc 32 脚原样） |
| `ref_clk_p/n` | 1+1 | in | 差分 125MHz DDR3 参考（N3/N2，SSTL15D_I） |
| `mem_*`（73 针） | — | inout/out | DDR3 引脚（ddr3_100h.fdc 原样） |

### 2.2.2 i2s_clk_gen

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `clk_nco` | 1 | in | 216MHz 时基 |
| `rst_n` | 1 | in | 同步释放复位 |
| `bck_phase` | 4 | out | BCK 半周期计数（0..31 构成 16bit×2 声道帧相位） |
| `bck_tick` | 1 | out | BCK 翻转使能（单周期脉冲，clk_nco 域） |
| `i2s_bck` | 1 | out | 输出引脚寄存器（bck_tick 时取反） |
| `i2s_lrck` | 1 | out | 帧时钟（bck_phase==31 边界翻转，低=左声道，Philips） |

### 2.2.3 i2s_rx

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `clk_nco` / `rst_n` | 1 | in | |
| `bck_tick` / `bck_phase` | 1/4 | in | 来自 i2s_clk_gen |
| `i2s_sd_sync` | 1 | in | 两级同步后的 SD 输入 |
| `pcm_valid` | 1 | out | 每完整 16bit 字有效（bck_phase 对应数据位中心） |
| `pcm_l` | 16 | out | 左声道样本（LRCK 低半帧，MSB 前、延迟 1 BCK 对齐） |
| `pcm_r` | 16 | out | 右声道样本 |
| `sd_idle` | 1 | out | SD 电平静止检测（>1 LRCK 周期无翻转 → 置位，恢复输入后 1 窗口内清除） |

### 2.2.4 audio_sink（PCM 环形缓冲写管理）

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `clk` (core_clk) / `rst_n` | 1 | in | |
| `pcm_valid` / `pcm_l` / `pcm_r` | 1/16/16 | in | CDC FIFO 出口 |
| `wr_req` | 1 | out | → ddr3_ctrl_axi 主口 0（音频写） |
| `wr_addr` | 28 | out | 字节地址（左声道区/右声道区交替打包 64bit=4 样本/拍以提升突发效率） |
| `wr_data` | 64 | out | 4×16bit 样本打包 |
| `wr_done` | 1 | in | 写完成（axi_wready 握手后） |
| `win_tick` | 1 | out | 窗口满节拍（每 132096 左声道样本一次，触发推理流水） |
| `win_id` | 16 | out | 窗口序号（UART 时间戳关联） |
| `mute_flag` | 1 | out | 静音标志（sd_idle 或全零样本持续 → 注入静音样本保持管线运转，REQ-REL-003） |

### 2.2.5 ddr3_ctrl_axi（仲裁器 + IP 契约适配）

对上层呈现 4 个统一的主设备请求口（REQ-MEM-004）：

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `m{i}_cmd_valid` | 1×4 | in | 主 i 请求（i=0 audio_sink 写、1 wdma 权重读、2 mel 读、3 ui 读） |
| `m{i}_cmd` | 38×4 | in | {wr(1), addr[27:0], len[7:0]}（len 为 256bit beat 数-1，最大 15=16 beat 突发 512B） |
| `m{i}_wdata` | 256×4 | in | 写数据（仅 i=0 有效） |
| `m{i}_rd_data` | 256×4 | out | 读返回数据（rvalid 期间逐周期有效，仲裁器内含 16 深弹性缓冲吸收 IP 无 rready 的推数据行为） |
| `m{i}_rd_valid` | 256×4 | out | 读数据有效 |
| `m{i}_done` | 1×4 | out | 命令完成（写：axi_wready 握手；读：rlast） |
| `m{i}_wait_cnt` | 32×4 | out | 仲裁等待周期计数器（REQ-MEM-004 板级观测导出） |

对 IP 侧（ddr3_wrapper）直接映射 ddr3_test.v 端口（aw/w/ar/r 通道、`axi_wdata[255:0]`、`axi_wstrb[31:0]` 全 1）；**IP 特例的硬性适配规则**（REQ-MEM-003）：

1. 写通道：`axi_awvalid` 拉高至 `axi_awready`；随后按 beat 摆 `axi_wdata`，**无 axi_wvalid 输入**——写完成判定 = 对应 `axi_wready` 采样到高且 beat 计数满；`axi_wusero_last` 作旁证。
2. 读通道：先发一次同地址 dummy-write（1 beat、数据任意、`axi_wstrb` 全 0 屏蔽无效写入），再发 `axi_arvalid`；`axi_rvalid` 一旦开始必须每周期接收 `axi_rdata`（仲裁器读缓冲深度 ≥ 突发长度 16，反压上游 `rd_valid`）。
3. `axi_awuser_ap=1`、`axi_awuser_id/aruser_id` 固定主设备编号（4'b0..3）。

仲裁策略：**固定优先级 + 带宽配额轮询**。优先级：音频写（P0）> NPU 权重读（P1）> Mel PCM 读（P2）> UI 读（P3）。P3 配保底配额（每 1ms 至少 1 次突发），防止 UI 饿死；各主等待计数器经 UART 可导出（验收 REQ-MEM-004）。

### 2.2.6 mel_engine

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `clk` / `rst_n` | 1 | in | core_clk 域 |
| `start` | 1 | in | 窗口节拍启动（sys_ctrl 触发） |
| `pcm_rd_req/addr/done` | — | — | → 仲裁器主口 2（读 132096+2048 样本，含 reflect 区） |
| `mel_done` | 1 | out | 特征就绪 |
| `mel_cycles` | 32 | out | 耗时计量（时间戳，REQ-PRF-003 验收） |
| `feat_q` | 8×(64×258) | out | int8 量化特征（片上双页缓冲，页 0/1 交替供 NPU 读） |
| `feat_page` | 1 | out | 当前完成页号 |
| `spec_rd_*` | — | — | log2 谱 UI 导出口（供 spectrum_disp 与 uart_debug 逐层导出复用，读第二遍的 dB 结果 int16 Q8.8） |

内部子模块（契约要点）：

- `stft_framer`：从 DDR3 PCM 流生成 258 帧 × 2048 点加窗输入。**边界语义硬件化**：帧 0 的样本 [0..1023] 来自 reflect 翻转的 y[1024..1]（y[-i]=y[i]）；帧 t 首样本地址 = 窗口基址 + 512×t - 1024；帧 257 尾部不足 2048 时右侧补零（读地址越界钳制到窗口末端后由零填充多路器接管，等价 reflect 语义中 librosa `center=True` 的末端填充——librosa 实际对末端也 reflect 填充，帧数 = 1 + 132096/512 = 258 帧内末端自然含 reflect 区，读指针越界到窗口末端之后的部分按 reflect 翻转索引，与 `_pad_or_truncate_frames` 语义一致）。
- `hann_rom`：2048×16bit Q1.15（periodic Hann，librosa `get_window("hann", 2048, fftbins=True)` 语义），2 DRM 块。
- `fft2048_sdf`：2048 点 SDF radix-2，11 级流水，每级 ÷2 缩放（§3.2）。
- `mel_filter`：COO 稀疏系数表流式乘加（§3.4）。
- `db_norm` + `standardize`：第二遍（log2 谱 → max → dB Q8.8 → top_db 截断 → μ/σ → int8 量化，§3.5/3.6）。

### 2.2.7 npu_top

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `clk` / `rst_n` | 1 | in | |
| `feat_page` | 1 | in | 消费 mel_engine 完成页 |
| `start` | 1 | in | sys_ctrl：特征就绪后启动前向 |
| `w_rd_req/addr/done/rd_data` | — | — | → 仲裁器主口 1（权重分组流式加载） |
| `logits` | 32×8 | out | int32 logits（dequant 前原值，UART 导出真源） |
| `layer_export_*` | — | — | 逐层中间结果导出口（conv1..4/fc1 输出经导出 FIFO 到 uart_debug，REQ-INF-006） |
| `busy` / `done` | 1 | out | 前向进行/完成 |
| `npu_cycles` | 32 | out | 耗时计量（含权重加载，REQ-PRF-003） |
| `timeout_flag` | 1 | out | 阶段超时（>2× 预算，REQ-REL-002 复位重入） |

### 2.2.8 ui_renderer / hdmi_tx_if

| 信号 | 位宽 | 方向 | 语义 |
| --- | --- | --- | --- |
| `pix_clk` / `rst_pix_n` | 1 | in | 148.5MHz 域 |
| `result_valid` | 1 | in | 125M→148.5M vsync 握手：新结果可用（消隐期锁存） |
| `top1_id` | 3 | in | top-1 类别 |
| `probs_q` | 8×8 | in | 8 类概率 ×100（0..100 定点 u8） |
| `wave_col_rd_*` | — | — | 波形列包络读（双时钟 FIFO，125M 写 148.5M 读） |
| `spec_pix_rd_*` | — | — | 谱图像素块读（64×258→显示区映射，双缓冲整页切换） |
| `mute_flag_sync` | 1 | in | 静音提示叠加 |
| `rgb` | 24 | out | 合成像素 → hdmi_tx_if |
| `hs/vs/de` | 1×3 | out | sync_vg 时序（demo 参数） |
| `cfg_clk`/`iic_*` | — | — | ms72xx_ctl（demo 原样） |
| `init_over` | 1 | in→out | I2C 配置完成（sys_ctrl 自检链消费） |

### 2.2.9 uart_debug / self_test / sys_ctrl（要点契约）

- `uart_debug`：115200 8N1（core_clk 分频）；行式 ASCII 状态输出（`BOOT/PLL/DDROK/WINF<n>/MEL<ms>/NPU<ms>/TOP<id,pct>/ERR<code>` 等，Python 可解析，REQ-MNT-001）；KEY1 触发进入二进制逐层导出协议（§9.2）。
- `self_test`：DDR3 图案自检（走 ddr3_ctrl_axi 主口 3 低优先级窗口，覆盖全部占用区间阶梯图案）+ 权重回读比对（§6.4）。
- `sys_ctrl`：自检链状态机、各阶段 2× 预算看门狗、LED 编码（`led[0]` 心跳 1Hz、`led[1]` DDR OK、`led[2]` 推理进行、`led[3]` 结果有效、`led[7:4]` 错误码）、KEY1 消抖触发、窗口节拍→流水线调度（mel→npu→softmax 串行链，UI 更新在结果提交后 ≤100ms 内由双缓冲自然达成）。
---

# 三、定点位宽决策表（Mel 通路位级语义）

## 3.1 全链路位宽总表

| 级 | 阶段 | 表示 | 位宽 | 动态范围/取值域 | 依据 |
| --- | --- | --- | --- | --- | --- |
| S0 | PCM 输入 | int16（s16） | 16 | [-32768, 32767] | I2S 16bit（REQ-AUD-002） |
| S1 | Hann 加窗 | s16 × Q1.15 → s32，>>15 舍入取 s17 | 17 | ≈±32768 | Q1.15 系数最大 32767/32768<1；round-half-up 与 golden 一致（§9.1） |
| S2 | FFT 2048 数据通路 | s18（符号扩展 1bit 防蝶形舍入偏置） | 18 | 每级 ÷2 后恒有界 | §3.2 溢出分析 |
| S3 | FFT twiddle | Q1.15（re/im 各 s16） | 16 | 单位圆 | 旋转精度 2^-15/级 |
| S4 | 功率谱 | re²+im²：s18→s36 乘积 s37 累加 | 37 | [0, 2^36] | 无舍入（精确整数乘加） |
| S5 | Mel 滤波累加 | Σ 功率×Q1.15：s37×s16→s53，累加器 s56 | 56 | 每通道 ≤ 2^38 量级（1025 bin 求和） | 32bin 三角权重和 ≈1，累加无溢出 |
| S6 | log2(Mel 功率) | int16 Q8.8 | 16 | [-33.0, +17.0]（覆盖功率 1e-10..2^36 的 log2 域） | §3.3 LUT 误差 0.0056（log2 域） |
| S7 | dB 域 | int16 Q8.8 | 16 | [-80.0, 0.0]（top_db 截断） | dB=3.0103×(log2−max_log2) |
| S8 | 统计量 μ/σ | s48 累加（ΣdB、ΣdB²）→ μ Q8.8、σ Q8.8 | 16 | μ∈[-80,0]、σ∈[0,80] | 16512 元素求和：80×256×16512<2^31，s32 够；用 s48 留裕量 |
| S9 | 标准化 z | (dB−μ)×inv_σ：Q8.8×Q8.8→Q8.16 截取 Q0.16？→ 输出 Q4.12 s16 | 16 | 典型 ±6σ → ±6 | §3.6 |
| S10 | CNN 输入量化 | z ×(1/s_in) round + zp → sat int8 | 8 | qint8 [-128,127] | fbgemm QuantStub 语义（§3.7） |

## 3.2 FFT 缩放策略选型与溢出分析

**选型：SDF radix-2 串行蝶形流水，11 级，每级数据右移 1bit（÷2，算术移位 + round-half-up 进位）**。

| 候选 | 溢出风险 | 精度 | 面积/复杂度 | 结论 |
| --- | --- | --- | --- | --- |
| 每级 ÷2（选定） | 零（蝶形增益 ≤2 被完全抵消，数学上恒有界） | 注入噪声 ~√11/2 LSB | 最简：无块指数通路 | ✅ |
| 块浮点（BFP） | 需指数比较/前馈 | 更优 ~6dB | 每级指数判断+移位器，PDS 综合风险↑ | 备选升级路径（对拍不达标时启用，R-03 兜底） |
| 每级 ÷4 | 零 | 差（有效位损失大） | 同上 | ✗ |

**溢出证明**：radix-2 蝶形 `X' = a + W·d`，`|W|=1` → `|X'| ≤ |a|+|d| ≤ 2·max(|a|,|d|)`。每级 ÷2 后 `|X'| ≤ max(|a|,|d|)`，归纳可得任意级数据幅值 ≤ 输入幅值上界（s17 满幅 2^17 → s18 容器绝对安全）。相干最坏增长（单频满幅 +2048 增益）被 2^-11 缩放精确抵消，Hann 相干增益 0.5 还留 6dB 裕量。

**量化噪声估算**（对 REQ-ACC-001 的链路预分配）：每级注入 ≤0.5 LSB（s18），11 级独立噪声累计 σ ≈ √11/2 ≈ 1.66 LSB。典型信号（RMS −12dBFS ≈ 8192）FFT 输出 RMS ≈ 8192×√(2048/2)×2^-11 ≈ 181，SNR ≈ 20log10(181/1.66) ≈ 40.7dB。dB 域误差 ≈ 10log10(1+10^-4) < 0.005dB；经 Mel 三角滤波 32bin 平均再稀释 √32。深衰减 bin（−70dB 以下）的相对误差增大，但其 Mel 功率贡献被邻近强 bin 稀释，且 top_db=80 截断吸收尾部误差——预留 BFP 升级路径作为兜底（§11 R-03）。

**吞吐**：SDF 每周期吞 1 复样本，2048 样本/帧 → 258 帧共 528k 周期 ≈ 4.2ms@125MHz ≪ 150ms 预算（含两遍与统计的完整预算核算见 §3.8）。

## 3.3 log2 转换（功率域 → log2 域）

实现：输入 Mel 功率 s56（规格化后取有效窗口）。步骤：

1. 规格化：前导 1 检测（优先编码器）得指数 `e`（整数部分 = e−56 偏置），尾数取规格化后高 8bit `m[7:0]`。
2. 查表：`log2(1.m)` 256 项 × 8bit（Q0.8），LUT 2Kb（1 DRM 块）。误差 ≤ 2^-8（log2 域斜率 ≤1/ln2 → 误差 ≤ 0.0056）。
3. 合成：`log2_q88 = ((e - 56) << 8) + lut_out`，int16 Q8.8。

dB 误差 = 3.0103×0.0056 ≈ 0.017dB ≪ 预算 1.25dB（0.05σ 归一化 ÷ σ≈25dB）。不启用线性插值（无必要，省 1 乘法器）。

## 3.4 Mel 滤波器系数存储

- 真源：离线脚本 `gen_mel_tables.py` 用 librosa `mel(sr=44100, n_fft=2048, n_mels=64, fmin=0, fmax=22050, htk=False, norm="slaney")` 生成 64×1025 稠密矩阵（与 `melspectrogram` 内部完全一致），抽稀疏 COO：非零系数约 4.0k 条（`weight > 1/8192`），每条 `{bin_idx s11, weight Q1.15 s16}`，表容量 4096×27bit ≈ 111Kb ≈ 7 DRM 块；表头含每通道起始偏移（64×13bit）。
- 运行时：帧内按 bin 升序流过功率谱，每 bin 查 COO 区间（平均 2.6 个 Mel 通道命中）做 `s37 × Q1.15 → 累加 s56`。总 MAC ≈ 258×1025×2.6 ≈ 68.8 万 @1 MAC/周期 = 5.5ms。
- 系数表 sha256 随 layer_contract.json 归档（REQ-FTR-003 验收）。

## 3.5 dB 转换与 top_db 截断（第二遍前半）

第二遍遍历 log2 谱（64×258×16bit 片上缓冲，15 DRM 块）：

1. 第一扫：求 `max_log2`（等价功率域 max，因 log2 单调）。
2. 第二扫：`dB_q88 = sat16((log2_q88 - max_log2) × 3.0103)`。定点实现：×3.0103 ≈ ×(775/256)（Q8.8 乘法，误差 0.003dB）；`< -20480`（−80dB×256）钳到 −20480（top_db 截断，REQ-FTR-004）；`> 0` 钳 0（含 ±1LSB 抖动防护）。
3. 同扫累加 `ΣdB`、`ΣdB²`（s48×2）。

## 3.6 per-sample 标准化（第二遍后半）

1. `μ_q88 = ΣdB / 16512`：时复用除法器（16 周期恢复除法，全设计共用 1 个 48/16 除法单元）。
2. `var_q16 = ΣdB²/16512 − μ²`（Q8.16 域）；`σ_q88 = sqrt(var)`：√ 用 16 次迭代 Newton-Raphson 或 8bit 平方根查表 + NR 一次精化（误差 < 2^-10）；`σ + 1e-6`（Q8.8 域 +1 LSB 下限，防除零，REQ-FTR-005/异常场景 1）。
3. `inv_σ`：NR 除法（时复用，2 次迭代精度 2^-16）。
4. `z_q412 = sat16(((dB_q88 − μ_q88) × inv_σ_q8) >> 8)`：Q8.8×Q8.8→Q8.16 截 12bit 小数（值域 ±8 覆盖 ±6σ）。

每窗口仅 3 次 16 周期除法/开方（3.0s 节拍），时复用成本可忽略。

## 3.7 CNN 输入量化（Mel→NPU 契约，REQ-FTR-006）

`x_q = sat_int8( round_even(z × inv_s_in) + zp_in )`：

- `s_in`/`zp_in` 从 quantized_model.pt 的 QuantStub activation_post_process 提取（离线，F-01）；定点化 `inv_s_in = round(2^16 / s_in)`（Q16.16 无符号，典型 s_in≈0.02~0.05 → inv≈20k~50k，16bit 容器溢出则升 Q8.24 s32——转换工具按实际值选 Q 格式并写入 layer_contract.json）。
- round 语义：PyTorch `quantize_per_tensor` 为 round-half-to-even；golden 模型与 RTL 一致实现（`round(x + 0.5) - (bit0(x+0.5) & sign)` 或等效位级操作，RTL 以加 0.5 截断 + 偶数对齐实现）。
- 特征双页缓冲：2×64×258×8bit = 264Kb = 15 DRM 块（与 log2 谱缓冲时分复用同一物理 DRM bank——第二遍读 log2 页写量化页，乒乓分页，总 Mel 引擎 DRM ≈ 15 块而非 30 块）。

## 3.8 Mel 引擎耗时预算（REQ-FTR-007 核算）

| 阶段 | 周期数 @125MHz | 时间 |
| --- | --- | --- |
| PCM 读 DDR3（132096+2048 样本，4 样本/拍突发） | ~34k + 仲裁等待 | 0.3ms |
| 第一遍：258 帧 ×（加窗+FFT 2048+功率+Mel 滤波） | 258×(2048+1025×2.6+开销) ≈ 780k | 6.3ms |
| log2 写谱 | 流水内含 | — |
| 第二遍扫描×2（max + dB/统计） | 2×16512×4 | 1.1ms |
| 标准化 + 量化输出 | 16512×2 + 常数计算 | 0.4ms |
| **合计** | **≈ 880k** | **≈ 7.0ms ≪ 150ms** ✅（余量 21×，吸收仲裁竞争与 RTL 低效） |

---

# 四、NPU 架构

## 4.1 数据流与权重流式加载

**逐层顺序执行 + 层内全行流水**（激活零 DDR3 回写）：

```text
feat_page(64x258 int8, 片上) ──┐
                               v
 conv1(3x3,pad1) 行流水 ─> requant ─> pool1(2x2 floor) ─> conv2 ─> requant ─> pool2 ─>
 conv3 ─> requant ─> pool3 ─> conv4 ─> requant ─> pool4 ─> GAP ─> fc1+ReLU(requant) ─> fc2 ─> logits
   ^每层: wdma 按 16 输出通道组从 DDR3 预取权重 -> wbuf(≤27.6KB) -> MAC 阵列消费
```

**权重分块（16 输出通道/组，满足 REQ-RSC-005 的 ≤32KB/层）**：

| 层 | 权重形状 | 总字节 | 16 通道组数 | 单组字节（峰值缓冲） |
| --- | --- | --- | --- | --- |
| conv1 | 48×1×3×3 | 432 B | 3 | 144 B |
| conv2 | 96×48×3×3 | 41,472 B | 6 | 6,912 B |
| conv3 | 192×96×3×3 | 165,888 B | 12 | 13,824 B |
| conv4 | 256×192×3×3 | 442,368 B | 16 | 27,648 B |
| fc1 | 128×256 | 32,768 B | 8（16 行/组） | 4,096 B |
| fc2 | 8×128 | 1,024 B | 1 | 1,024 B |

权重缓冲实现为单缓冲流式（组计算完成→下一组加载），无需乒乓：组间加载间隙 ≈ 27.6KB/512B 突发 = 54 突发 ≈ 数千周期，与组计算时间（conv4 组：16×192×9×32w? 见下）相比可忽略；若时序紧张可升级乒乓（DRM +13 块，仍在预算内，作为保留手段）。

**激活行缓冲（3×3 滑窗，逐层流水共存）**：

| 级 | 行缓冲内容 | 容量 |
| --- | --- | --- |
| conv1 输出（喂 pool1+conv2） | 3 行 × 48ch × 131 宽 × int8 | 18.9 KB |
| conv2 输出 | 3 行 × 96ch × 66 宽 | 19.0 KB |
| conv3 输出 | 3 行 × 192ch × 34 宽 | 19.6 KB |
| conv4 输出（pool4 只需 2 行） | 2 行 × 256ch × 18 宽 | 9.2 KB |
| **合计** | | **≈ 66.7 KB ≈ 30 DRM 块** |

边界填充（pad=1）：行缓冲以零行预填、列相位 0/末尾插零（行缓冲写侧零注入，无需额外存储）。

## 4.2 MAC 阵列规模选型

核算基准：总 MAC 114.6M，预算 ≤200ms（含权重加载），@125MHz。

| 方案 | MAC/周期 | 前向计算时间 | APM 占用（9×9 拆分） | LUT 估算 | 结论 |
| --- | --- | --- | --- | --- | --- |
| 8 MAC | 8 | 114.6M/8/125M = 114.6ms | 4 | ~4k | 贴 200ms 预算，权重加载叠加上溢风险 ✗ |
| **16 MAC（选定）** | **16** | **57.3ms** | **8** | ~6k | 3.5× 预算余量，面积适中 ✅ |
| 32 MAC | 32 | 28.7ms | 16 | ~10k | LUT/布线代价翻倍，无必要 ✗ |

16 MAC 阵列与 16 通道权重组天然对齐：每周期完成一个输出像素位置上**同一输入分块的 16 个输出通道**的部分积累加（`pe[c] += x[cin][dy][dx] × w[c][cin][dy][dx]`，c=0..15 并行，cin/dy/dx 串行扫描 9×Cin 拍）。int8×int8 用 APM 18×18 拆 9×9（每 APM 出 2 路 int8 乘法）；累加器 16×s32。

**APM 分配总账**：MAC 阵列 8 + requant 32×24 乘法 4（时复用，见 §4.3）+ FFT 复数蝶形 4 + Mel 滤波 s37×s16 用 2 + softmax/杂项 2 ≈ **20 APM ≪ 144**（REQ-RSC-004）。

## 4.3 requant 通路（REQ-INF-002/007 的硬件语义）

fbgemm 融合算子等效实现（权重对称 per-channel，zp_w=0）：

```text
acc_s32[c] = Σ_(cin,dy,dx) x_s8 × w_s8[c][cin][dy][dx] + bias_s32[c]
y_s8[c]    = sat_int8( (acc_s32[c] × M[c]) >>> shift + zp_out )
其中离线: M[c], shift = fixed_point( s_w[c] × s_in / s_out )
```

- `M[c]` 为 per-channel 定点乘子（Q 格式统一 Q0.31，`M = round(s_w[c]×s_in/s_out × 2^shift)`，shift 使 M∈[2^30, 2^31) 即 [0.5,1) 归一），与 `zp_out`、`zp_in`（fc1 输入 zp 通道）一并写入 layer_contract.json → DDR3 权重区头部 → wdma 逐组装载（每组 16×(32bit M + 5bit shift) + 层级 zp 常量）。
- 硬件通路：`acc_s32 × M_s32` → s64 乘积（APM 32×24 拼位：实际取 M 高 24bit Q0.23，误差 < 2^-23，64bit 容器）→ `>>> shift`（barrel shifter）→ `+ zp_out` → 饱和 [-128,127]。
- **时复用**：16 通道 requant 在 16 周期内逐通道处理（1 个 32×24 乘法/周期）；MAC 阵列每 9×Cin ≥ 432 周期才产出 16 个结果，requant 16 周期完全隐藏。
- 饱和策略与 PyTorch `clamp` 语义逐位一致（先 requant 饱和再入行缓冲）。
- conv1~4 的 `zp_out` 通常为 0（ReLU 融合后激活非负、fbgemm qint8 对称域），但硬件按任意 zp 实现（fc1 输入通道 zp 可能非 0），不做假设。

## 4.4 GAP / FC / pool floor 语义

- **GAP**：256 通道 × 4×16 输入，每通道 64 值求和 → `gap_s32[c] = Σ s8`（requant 前 int8 直加，之后按 fc1 输入量化 requant：`fc_in_s8 = sat((gap_s32 × M_gap) >>> shift + zp_gap)`，M_gap 离线 = s_conv4_out/s_fc1_in）。256 个 s32 累加器。
- **fc1**：256×128 MAC：向量机模式（x 端 s8 广播、w 端流式），16 MAC 并行 16 输出神经元 → 128×256/16 = 2048 周期。ReLU 融合：requant 后 clamp min 0（qp 对齐）。
- **fc2**：128×8 → 64 周期。输出 logits **int32 原值保留**（dequant 不在片上做：UART 导出 int32，softmax 用定点，UI 百分比用定点，见 §4.5）。
- **pool floor（R-10）**：2×2 stride2 硬件实现 `out_w = W[10:1]`（floor(W/2)），滑窗起点 `x∈{0,2,...,2(out_w−1)}`；W 为奇数（258/129）时**最后一列/行不消费直接丢弃**。逐层形状硬件对照表（REQ-INF-001 验收）：

| 层 | 输入 (C,H,W) | 输出 (C,H,W) |
| --- | --- | --- |
| conv1+pool1 | (1,64,258) | conv:(48,64,258) → pool:(48,32,129) |
| conv2+pool2 | (48,32,129) | conv:(96,32,129) → pool:(96,16,64) |
| conv3+pool3 | (96,16,64) | conv:(192,16,64) → pool:(192,8,32) |
| conv4+pool4 | (192,8,32) | conv:(256,8,32) → pool:(256,4,16) |
| GAP | (256,4,16) | (256,) |
| fc1+ReLU | (256,) | (128,) |
| fc2 | (128,) | (8,) |

## 4.5 softmax（定点）

`p_i = exp(l_i − l_max) / Σ exp(l_j)`：8 路 int32 logits → 减 max → 差值 Q6.9 缩放（logits 差动态 ±2^20 → 截取高 15bit Q6.9）→ exp 查表 512 项 × Q0.16 → 8 值求和（s48）→ 时复用除法得 p_i（Q0.16）→ ×100 取整 → u8 百分比。误差分析：Q6.9 输入量化 0.002 → exp 相对误差 0.2%；REQ-ACC-003 容差 max|Δp|≤0.02（绝对概率），0.2% 相对误差在 p<1 域 ≤0.002 ✅。top-1 一致性由 logits ±0.25 容差保障。

## 4.6 NPU 耗时核算（REQ-INF-004）

| 层 | MAC 数 | 16 MAC@125MHz | 权重加载（DDR3 突发） |
| --- | --- | --- | --- |
| conv1 | 1.78M | 8.9ms? → 1.78M/16/125M = 0.89ms | 0.4KB 忽略 |
| conv2 | 42.5M | 21.2ms | 41KB = 82 突发 ≈ 0.1ms |
| conv3 | 42.5M | 21.2ms | 166KB ≈ 0.4ms |
| conv4 | 28.3M | 14.2ms | 442KB ≈ 1.0ms |
| fc1+fc2 | 0.034M | 0.02ms | 34KB ≈ 0.1ms |
| **合计** | **114.6M** | **≈57.5ms ≪ 200ms** ✅（REQ-INF-004 的 ≥8 MAC/周期等效性：16 MAC/周期 = 2× 下限） | ≈1.6ms（与计算部分重叠后净增 <1ms） |

---

# 五、DDR3 地址布局与带宽预算

## 5.1 地址映射（字节地址，256bit=32B 对齐）

| 区域 | 基址 | 大小 | 内容 |
| --- | --- | --- | --- |
| PCM 左声道环形缓冲 | `0x0000_0000` | 2 窗口 × 264KB = 528KB | 132096 样本/窗 × s16；写指针模 264KB（REQ-MEM-002 深度 2 窗口） |
| PCM 右声道备用区 | `0x0008_4000` | 264KB | 右声道仅存档不进特征（REQ-AUD-005） |
| 权重镜像区 | `0x0010_0000` | 736KB（对齐 0x0010_0000..0x001B_8000） | 逐层分块布局（§5.2）+ 层契约表头 |
| Mel log2 谱导出区 | `0x0020_0000` | 64KB | 板级导出与 UI 频谱备份（片上 15 DRM 为运行真源，此区仅 KEY1 导出快照） |
| 自检图案区 | `0x0030_0000` | 64KB | DDR3 写读自检覆盖代表窗口（REQ-MEM-005；地址区间覆盖性由扫描全区的读校验保证） |
| 保留 | — | ~31MB 余量 | ≤32MB 上限（REQ-RSC-006）✅ 总占用 < 2MB |

## 5.2 权重镜像区逐层布局（layer_contract.json 生成的固化表）

| 偏移（自 0x0010_0000） | 内容 | 字节 |
| --- | --- | --- |
| +0x0000 | 镜像头：magic `IRW1`、层数 6、sha256 截断 128bit、总长 | 32 |
| +0x0020 | 层契约表：6 层 × 64B（M[16]×s32 组块化、shift、zp_in/zp_out、组数、组大小、地址偏移） | 384 |
| +0x0200 | conv1 权重（48×9 + bias 48×4 + M 48×4） | 912 |
| +0x0600 | conv2（41472 + 384 + 384） | 42,240 |
| +0xA800 | conv3（165888 + 768 + 768） | 167,424 |
| +0x33800 | conv4（442368 + 1024 + 1024） | 444,416 |
| +0x9F800 | fc1（32768 + 512 + 512） | 33,792 |
| +0xA7C00 | fc2（1024 + 32 + 32） | 1,088 |
| **合计** | | **≈ 690KB** |

## 5.3 与 ddr3_ctrl 的适配要点（REQ-MEM-003 checklist）

1. 写：`aw` 握手 → 逐 beat 摆 `wdata`（无 wvalid）→ `wready&&beat_cnt==len` 判完成（`wusero_last` 旁证）。
2. 读：同地址 dummy-write（wstrb 全 0，1 beat）→ `ar` 握手 → `rvalid` 期间逐周期收 `rdata`（读弹性缓冲 16 深，反压只存在于仲裁器内部）。
3. 全部长突发（len=15，512B/命令）+ 地址 32B 对齐；权重区按组预读。
4. 板级自检显式包含「读前 dummy-write」路径验证项（验收 checklist 归档）。

## 5.4 带宽预算表（REQ-PRF-005）

各主设备峰值/平均速率（AXI 256bit @125MHz = 4GB/s 理论；按 50% 突发效率保守取 2GB/s 可用）：

| 主设备 | 模式 | 峰值速率 | 平均速率（3s 窗口） | 等待预算 |
| --- | --- | --- | --- | --- |
| P0 音频写 | 连续小批量（4 样本/拍聚合 64bit，8 拍=256B 突发/2ms） | 0.18MB/s | 0.176MB/s | ≤ 节拍 10%：FIFO 深度吸收（512 样本 ≈ 11.6ms 缓冲 > 最坏仲裁延迟） |
| P1 权重读 | 前向期间集中突发（57.5ms 内 690KB） | 12MB/s（57.5ms 内摊） | 0.23MB/s | 计入 200ms 预算余量 3.5× |
| P2 Mel PCM 读 | 窗口触发后 7ms 内读 268KB | 38MB/s（瞬时） | 0.09MB/s | Mel 预算 150ms，实际 7ms，等待容忍 >140ms |
| P3 UI 读 | 每帧 1 次波形列突发（1920×4B=7.7KB/16.7ms） | 0.46MB/s | 0.46MB/s | 保底配额每 1ms 1 突发 |
| **合计** | | | **≈0.96MB/s ≪ 285MB/s** ✅ | 任何引擎饿死风险 ≈ 0（设计核算表即 REQ-PRF-005 交付物） |

结论：本设计带宽占用极低（历史实测 4.6MB/s 是 CPU 随机单拍场景；本设计全 512B 长突发，效率高一个数量级），DDR3 压力来自**延迟与仲裁公平**而非带宽；等待计数器导出为板级验收手段。

---

# 六、权重加载方案

## 6.1 离线转换工具（scripts/gen_weight_image.py）

输入（双源，F-01）：
1. `InstRec/deploy/weights/*.npy`（24 个量化文件：weight_int8 / bias_int32 / scale(weight per-channel) / zero_point）；
2. `InstRec/deploy/quantized_model.pt`：TorchScript 遍历量化模块提取 `activation_post_process` 的 `scale()`/`zero_point()`/`dtype`（s_in、s_out、zp_in、zp_out 逐层），并加载 `deploy/class_names.json` 校验 8 类顺序（R-06 复核点：与 INSTRUMENT_NAMES 比对断言）。

输出：
- `weights_image.bin`：按 §5.2 布局的 DDR3 镜像（小端、逐组重排为硬件消费序：16 通道交错）；
- `layer_contract.json`：逐层 {s_in, s_out, zp_in, zp_out, M[16] 十六进制组块, shift, 组数, 地址偏移, 形状表}（人可读 + sha256）；
- `mel_tables.coe` + `mel_tables.json`：Hann 2048×Q1.15、Mel COO 4096×27bit、log2 LUT 256×8、exp LUT（sha256 归档，REQ-FTR-003）。

可重复性：脚本纯确定性（无随机源），重复执行逐位一致（REQ 数据约束 §6.3.4）。

## 6.2 上电进 DDR3 的方案决策

| 方案 | 可行性 | 结论 |
| --- | --- | --- |
| a) JTAG 烧 BRAM ROM 再搬 DDR3 | 0.69MB 超片上 DRM 总量 2.79Mb，物理不可行 | ✗ |
| b) ddr3_test IP 初始化文件（.mi） | ddr3_test 为 PHY/控制器 IP（非 BRAM IP），idf 无初始内容加载路径；且 JTAG 位流仅配置 FPGA，不初始化 DDR3 颗粒 | ✗（已核实 IP 生成物无 mi 机制） |
| c) **UART 上位机加载（选定）** | 0.69MB@115200bps ≈ 60s（hex 帧 69% 效率）一次性成本；M2 阶段每次上电流一次；权重 DDR3 驻留后每 3s 推理复用零重载 | ✅ |
| d) HDMI demo 的 I2C EEPROM | 24xx02 容量 2Kbit ≪ 5.5Mb，物理不足 | ✗ |

**执行流程**：上位机 `weight_upload.py`（PC 端）经 UART 发分块帧（256B 数据 + CRC16 + 序号，板级 weight_loader 回读校验 + 段累加校验和 + 终局全镜像比对（读回与发端 sha256 对比报文），失败块自动重传）。加载完成 → self_test 置 `WEIGHT_OK` → sys_ctrl 放行推理循环（REQ-REL-001 自检链第 4 环）。

**板级时间预算**：60s 加载发生在「下载位流 → 上位机加载权重 → 运行」的演示准备段，不在 3s 推理周期内；演示操作员手册注明该一次性步骤（REQ-BLD-005 三步流程外附加说明，非偏差）。

## 6.3 推理期权重流（REQ-INF-003）

前向启动时 wdma 按层按组预取（§4.1）；层间顺序执行天然顺序预取；每窗口重读 690KB（DDR3 驻留复用指无需重新加载 UART，DDR3 读流每窗必须，已计入 §5.4 预算 P1）。
## 6.4 权重回读校验（REQ-INF-003 验收）

weight_loader 加载完成后：self_test 读回全权重区 → 板级维护 128bit 分段累加校验（等效弱 sha256，避免片上实现完整 SHA 的 LUT 成本）→ 与镜像头比对 → 通过置 `WEIGHT_OK` 并 UART 打印 `WOK <校验和hex>`；失败打印首错地址 `WERR @<addr> want <x> got <y>`（REQ-REL-001 错误链）。上位机侧同时独立计算 bin 文件 sha256 归档（验收证据双保险）。

---

# 七、HDMI UI 设计

## 7.1 视频通路复用（REQ-UI-001）

- `hdmi_tx_if` 原样复用 demo 结构：GPLL_B（27MHz→pix_clk 148.5MHz + cfg_clk 10MHz）+ `ms72xx_ctl`（I2C 序列驱动 HDMI 发送芯片，iic_tx_scl K22 / iic_tx_sda K23）+ `sync_vg`（1080p@60：H_TOTAL=2200/V_TOTAL=1125/H_SYNC=44/H_BP=148/H_ACT=1920/V_SYNC=5/V_BP=36/V_ACT=1080）。
- 复用方式为**整文件复制**（sync_vg.v / iic_dri.v / ms7200_ctl.v / ms7210_ctl.v / ms72xx_ctl.v → instrec_fpga/src/hdmi/，保留原模块名与端口，仅删除 demo 顶层 ad_da_hdmi_top.v / pattern_vg.v / grid_display.v / wav_display.v 的顶层接线，功能由 ui_renderer 等价接管）。
- R-05 缓解策略落地：M0 里程碑第一步先以「原样 demo + 新顶层」出板验证显示，再叠加数据通路。

## 7.2 UI 布局分区（1920×1080）

```text
+------------------------------------------------------------------------+
| ① 波形区  y ∈ [0, 300)     背景深蓝 + 网格线（复刻 grid_display 视觉）      |
|    绿色波形（min/max 包络竖线对），1920 列 ← 132096 样本抽点               |
+------------------------------------------------------------------------+
| ② Mel 频谱区 y ∈ [320, 760)  440 行 × 1920 列                           |
|    64×258 谱图 → (x=frame*1920/258, y=mel*440/64) 最近邻映射             |
|    dB 值 [-80,0] → 伪彩（蓝→青→绿→黄→红 5 段线性插值）                    |
+------------------------------------------------------------------------+
| ③ 类别文本区 y ∈ [780, 930)                                            |
|    "识别结果：小提琴  96%" 16x16 字库 3 倍放大（48x48 有效字高）          |
+------------------------------------------------------------------------+
| ④ 置信度条区 y ∈ [950, 1080)  8 行 × 16 行高                            |
|    每行：中文名标签(16x16) + 水平条（长度 = probs×1400px 满量程）+ 百分比  |
+------------------------------------------------------------------------+
   静音时：③ 区叠加「静音/无输入」提示（REQ-REL-003）
```

## 7.3 中文字库 ROM

- 字符集合（去重）：`单簧管失真电吉他女声长笛钢琴次中音萨克斯小号小琴别结识别静音无输入` + ASCII `0-9%: ` ≈ 30 汉字 + 14 ASCII。
- 点阵 16×16bit/字 → ROM 总量 30×256 + 14×128 ≈ 9.5Kb ≈ **1 DRM 块**（font_rom.v，$readmemh 加载 `font_16x16.hex`，由 gen_font.py 从点阵字库生成并 sha256 归档）。
- 大字渲染：像素 3×3 复制放大（无插值逻辑成本）。
- 中文用字与 class_names.json 的 name_zh 逐字核对（REQ-UI-005 验收，R-06 二次防线）。

## 7.4 波形渲染（REQ-UI-003，≥10fps）

- 数据通路：audio_sink 维护「UI 波形列包络」专用降采样器：132096 样本/3s 窗口 → 1920 列，每列 68.8 样本求 min/max → 2×s16/列。**降采样在核心域按列滚动计算**（每样本 O(1) 更新所属列的 min/max，窗口翻转时列缓冲整体切换）。
- 列缓冲：1920×2×16bit×2 页（ping-pong）= 122Kb ≈ 7 DRM 块（125M 写 / 148.5M 读双时钟）。
- 刷新节拍：每帧（16.7ms）ui_renderer 读取当前页 → 波形更新率 60fps ≫ 10fps（REQ-PRF-004）✅；列数据滚动感通过「每帧读不同相位页」实现（页切换在 vsync 消隐）。

## 7.5 Mel 频谱图渲染（REQ-UI-004）

- 像素源：mel_engine 第二遍的 dB 谱（Q8.8 int16）。显示侧映射前先做 8bit 灰度压缩：`g = (dB + 80)×255/80`（0.3dB/级，视觉足够）。
- 谱图页缓冲：64×258×8bit = 132Kb ≈ 8 DRM 块（双页乒乓，推理完成时刻 vsync 切换 —— REQ-UI-007 保持最近结果语义天然满足）。
- 伪彩映射：组合逻辑（5 段线性插值常数乘法），无存储。
- 显示区缩放：最近邻（`frame×1920/258` 定点乘常数 `1920/258≈7.44`，`mel×440/64≈6.875`）。

## 7.6 置信度条（REQ-UI-006）

- 8 条水平条，条长 = `probs_q(u8, 0..100) × 1400 / 100`（整数乘 14 → 0.7px 精度 ≪ 验收的 1px 容差）。
- top-1 行高亮描边；条形填充色按类别固定 8 色（常数表）。

## 7.7 像素流水与行缓冲

ui_renderer 输入 sync_vg 的 `x_act/y_act/de/hs/vs`，输出 24bit RGB：纯组合查表 + 1 级寄存器流水（148.5MHz 时序宽裕：font ROM 1 拍、谱图/波形/条形均为 1 拡查表 + 1 拍选择器 = 3 级流水，对 de/hs/vs 补偿 3 拍延迟）。无整帧行缓冲需求（各要素数据源均为片上双页缓冲，随机访问 DRM 读端口按 (x,y) 计算地址）。

---

# 八、I2S 引脚选型

## 8.1 避让分析

已占用引脚集合（零冲突校验对象）：
- HDMI demo：vout_data[23:0] + vout_clk/de/hs/vs（32 脚）+ iic K22/K23；
- DDR3：73 针（SSTL15 bank，物理上与 LVCMOS33 FMC bank 不同，无冲突）；
- 板载：clk D18、rst_n C22、key1 C23、led×8、uart B24/C24。

## 8.2 选型结论（REQ-AUD-001/006）

| 信号 | 引脚 | Bank | 原 demo 占用 | 选型依据 |
| --- | --- | --- | --- | --- |
| `i2s_bck`（out） | **U20** | BANKL6（3.3V） | ad_clk（ADDA demo，本设计释放） | demo 中即为输出脚（IO 驱动能力已验证），FMC 子卡连接器走线最短组 |
| `i2s_lrck`（out） | **T20** | BANKL6 | da_clk（释放） | 同上，与 U20 相邻（同 bank 同走线束，BCK/LRCK skew 最小） |
| `i2s_sd`（in） | **V16** | BANKL6 | ad_data_in[7]（释放） | demo 中即为输入脚（输入时序路径已验证），与 U20/T20 同 bank |

三脚均 LVCMOS33 / VCCIO 3.3（BANKL6 统一电平，REQ-AUD-001 的 FMC 通用 IO 要求满足）。约束写入 `constraints/i2s_audio.fdc`（LOC/VCCIO/STANDARD/DIRECTION + 输出 DRIVE 8 / SLEW SLOW——BCK 1.4MHz 慢沿利于信号完整性）。

## 8.3 与外部 I2S 源的接线约定

本系统为唯一主机（spec §5.1.3 场景 3 约定）：BCK/LRCK 由 FPGA 驱动，SD 由源驱动；源须配置为从机模式（外部自理，spec §1.4/§3.2 边界）。FMC 连接器对应管脚映射关系记录于设计文档附录（由 3_Hardware 原理图核对的对应关系在 M0 板级首次接线下以万用表/示波器复验，作为 REQ-AUD-006 选型依据归档）。

---

# 九、验证方案

## 9.1 Python bit-accurate 金标准（golden_pipeline.py）

- 位置：`instrec_fpga/scripts/golden_pipeline.py`（+ `check_rtl.py` 对拍驱动）。
- 建模范围与 RTL **同位宽、同舍入、同查表**：Hann Q1.15 乘后 >>15 round；FFT 11 级每级 ÷2（round-half-up 进位）；功率 s37 精确；Mel COO 表（同一 mel_tables.coe）；log2 256 LUT；dB ×775/256；requant M/shift（同一 layer_contract.json）；softmax Q6.9 + 512 exp LUT。定点操作全部用 NumPy int64/int32 显式实现（禁 float捷径）。
- 层级对拍模式：`--stage pcm|log2spec|dbspec|feat|conv1..4|fc1|fc2|logits|probs` 逐级输出 .npy。
- 上游参考对拍：同一脚本 `--ref librosa` 模式输出浮点参考（调用 InstRec `extract_mel_waveform` + `inference_reference.py`），用于 REQ-ACC-001 的 max|Δ|≤0.05 / r≥0.999 与 REQ-ACC-002/003 指标统计。

## 9.2 UART 逐层导出协议（REQ-MNT-002 / REQ-INF-006）

KEY1 触发（或 UART 命令 `X`）后按以下帧序列导出最近一次推理（hex 帧，帧头 0xAA）：

```text
AA <layer_id:1> <seq:2> <len:2> <payload:len> <crc16:2>
layer_id: 0=MEL_Q8.8(64x258 s16, 33KB) 1=CONV1 2=CONV2 3=CONV3 4=CONV4
          5=FC1 6=FC2_LOGITS(8x s32) 7=PROBS(8x u8) 8=STATS(时间戳/等待计数)
大数据层支持抽样模式（layer_id|0x80 → 每 16 元素取 1，~25KB/层，全量模式 ~400KB@115200≈60s，抽样 ~8s）
```

PC 端 `uart_capture.py` 收帧重组 .npy → 与 golden_pipeline 对应 stage 输出比对 → 报告（±1 LSB 命中率、max|Δ|、r）。

## 9.3 板级测试用例清单（M0~M3，对应 REQ-VER）

| 里程碑 | 用例 | 判据 |
| --- | --- | --- |
| M0 | T0.1 示波器测 BCK/LRCK 频率与占空比 | 1.4112MHz/44.1kHz ±500ppm（REQ-AUD-002/003，REQ-VER-001） |
| M0 | T0.2 UART 观测 DDROK + 自检首错注入 | REQ-MEM-005 |
| M0 | T0.3 HDMI 网格+实时波形（已知正弦源） | 波形随输入变化（REQ-VER-001） |
| M1 | T1.1 KEY1 导出 Mel 谱 ↔ golden ↔ librosa 三方对拍（≥20 条音频） | REQ-ACC-001 两指标 |
| M1 | T1.2 Mel 耗时 UART 时间戳 ≤150ms | REQ-FTR-007 |
| M1 | T1.3 全静音窗口对拍（amin/eps 路径） | REQ-FTR-004/005 异常场景 1 |
| M1 | T1.4 两段不同响度拼接音频跨窗统计 | REQ-FTR-005 验收 |
| M2 | T2.1 权重 UART 加载 + WOK 校验 | REQ-INF-003 |
| M2 | T2.2 逐层导出对拍 ±1LSB 100%（≥100 特征样本） | REQ-ACC-002 |
| M2 | T2.3 logits/softmax/top-1 指标 | REQ-ACC-003 |
| M2 | T2.4 同音频回放 10 次 logits 位级一致 | REQ-ACC-004 |
| M2 | T2.5 已知类别 ≥10 条板级 top-1 ≥80%、与 Python 一致 ≥90% | REQ-VER-003 |
| M3 | T3.1 四要素 UI 同屏 + 截图 | REQ-UI-002 |
| M3 | T3.2 高速摄像 UI 刷新 ≥10fps | REQ-PRF-004 |
| M3 | T3.3 推理周期/端到端延迟对表测量（拍手沿 ×10） | REQ-PRF-001/002 |
| M3 | T3.4 60s 连续运行日志 + 拔 SD 线 30s 静音恢复 | REQ-SYS-001、REQ-REL-003 |
| M3 | T3.5 超时注入（调试降频）恢复 | REQ-REL-002 |
| M3 | T3.6 PnR 资源/时序归档 | REQ-RSC-001~004、REQ-BLD-002 |

---

# 十、资源估算表（REQ-RSC 验收预核）

以 pds_cpu_100h 实测（8458 LUT / 4300 FF / 21 DRM / 4 APM 全 SoC，其中 DDR3 wrapper 部分约 2.5k LUT / 21 DRM 为锚点）+ HDMI demo（纯显示通路，规模小）外推：

| 模块 | LUT | FF | DRM | APM | 依据 |
| --- | --- | --- | --- | --- | --- |
| ddr3_wrapper + ddr3_ctrl_axi + 仲裁器 | 3,500 | 2,500 | 21 | 0 | pds_cpu_100h 实测锚点 + 4 主仲裁/弹性缓冲增量 |
| audio_pll(GPLL) + i2s_clk_gen(NCO) + i2s_rx + CDC FIFO | 800 | 600 | 1 | 0 | NCO 28bit 累加 + 帧解码 + 512×32 FIFO |
| audio_sink（环形指针+波形降采样） | 600 | 500 | 7 | 0 | 波形列双页缓冲 122Kb |
| mel_engine：FFT SDF | 2,500 | 3,500 | 5 | 4 | 11 级流水 + 级间 2047×36bit |
| mel_engine：帧器/功率/Mel 滤波/log2/dB/标准化 | 2,200 | 1,800 | 23 | 2 | COO 7 + log2 谱/特征复用 15 + LUT 1 |
| npu_top：wdma + conv_engine(16 MAC) + pool + GAP/FC | 6,500 | 5,500 | 30 | 12 | 行缓冲 30 + 权重组缓冲 14（与 wbuf 合并计数于 30 内：行缓冲 30 单列，wbuf 14 → 修正下行） |
| npu_top：wbuf 权重分组缓冲 | (含上) | (含上) | 14 | (含上) | 27.6KB 峰值组缓冲 |
| softmax_top | 400 | 300 | 1 | 2 | exp LUT 512×16 |
| ui_renderer（波形/谱/字库/条/流水） | 3,500 | 2,500 | 16 | 0 | 谱图双页 8 + 字库 1 + 显示杂项 |
| hdmi_tx_if（demo 复制） | 800 | 600 | 0 | 0 | demo 规模 |
| uart_debug + weight_loader + self_test + sys_ctrl | 2,500 | 2,000 | 2 | 0 | UART 收发 + 加载状态机 + 看门狗 |
| **合计** | **≈22,800** | **≈19,300** | **≈120 → 修正 105** | **≈20** | 见下方 DRM 修正说明 |

**DRM 细算修正**（避免双计）：21(IP) + 1(音频FIFO) + 7(波形列) + 5(FFT) + 23(Mel含COO/LUT/log2谱/特征) + 30(激活行缓冲) + 14(wbuf) + 1(softmax) + 16(UI) + 2(杂) = **120 块 > 108 预算！** 必须削减——决策：

1. **log2 谱与特征缓冲复用已计入**（15 块两用）✓；
2. **wbuf 与 conv 行缓冲 bank 复用**：权重组缓冲仅在层启动时使用，与「上一级行缓冲」时分重叠度低但物理可分 bank 共享 → wbuf 由 14 块降为与 conv4 行缓冲错峰复用 8 块（保守保留 6 块净增）→ **−6 块**；
3. **波形列缓冲单页化**：UI 波形刷新容忍列级撕裂（滚动波形无静态语义）→ 单页 3.5 块 → **−3.5 块**；
4. **谱图页单页 + vsync 写闭锁**：谱图更新率 0.33Hz（3s 周期），写入在 7ms Mel 完成后立刻搬（消隐期原子切换整页太保守）→ 单页 4 块 → **−4 块**；
5. **FFT 级间缓冲用分布式 RAM 兜底选项**（CLMS LUTRAM）——保留为 PnR 超限时的降级手段，不预先启用。

修正后合计：21+1+3.5+5+23+30+8+1+12+2 ≈ **106.5 块 ≤ 108** ✅（余量 1.5 块紧张，**风险表 R-11 挂牌跟踪**；进一步释放手段：行缓冲 conv2/conv3 级改 2 行+半行边带（−8 块）或 LUTRAM 迁移）。

| 指标 | 估算 | 预算（REQ-RSC） | 器件容量 | 结论 |
| --- | --- | --- | --- | --- |
| LUT | ≈22,800 | ≤53,000 | 66,600 | ✅ 余量 57% |
| FF | ≈19,300 | ≤66,600 | 133,200 | ✅ 余量 71% |
| DRM | ≈107 | ≤108 | 155 | ⚠️ 贴边通过（缓解见 R-11） |
| APM | ≈20 | ≤144 | 240 | ✅ 余量 86% |
| GPLL | 4 | ≤4 | 6 | ✅ 恰好满足 |

---

# 十一、风险表（≥8 条，含缓解措施）

| 编号 | 风险 | 影响 | 等级 | 缓解措施（本设计落地项） |
| --- | --- | --- | --- | --- |
| R-01 | I2S 时钟精度（27MHz 与 44.1k 家族无整数比） | 采样率偏差影响 Mel 频率轴 | 高 | §1.2 方案 B：216MHz 整数倍频 + 28bit NCO，误差 <0.01ppm（合成部分）+ 晶振 ±50ppm ≪ ±500ppm；M0 用例 T0.1 示波器实测闭环 |
| R-02 | DDR3 带宽/仲裁争用 | 引擎超时丢帧 | 高 | §5.4 带宽核算（0.96MB/s ≪ 285MB/s）+ 固定优先级+配额 + 等待计数器导出（REQ-MEM-004 验收） |
| R-03 | FFT/Mel 定点精度对拍不达标 | REQ-ACC-001 失败 | 高 | §3 逐级误差预算（dB 域 0.02dB ≪ 1.25dB）；golden_pipeline 先行锁位宽；BFP 升级路径保留（§3.2） |
| R-04 | 权重/激活超片上 BRAM | 布局失败或降并行 | 高 | 权重 16 通道组流式（≤27.6KB/组）；激活全行流水零 DDR3 回写；DRM 贴边削减方案 §10 |
| R-05 | HDMI demo 跨工程复制后黑屏 | M0 失败 | 中 | 整文件复制保留层级语义；M0 第一步原样 demo 出板；I2C/PLL 引脚与约束零改动（§7.1） |
| R-06 | 类别映射元数据冲突 | UI 类别全错 | 中 | 唯一真源 class_names.json；转换工具内置断言（§6.1）；字库生成脚本二次核对（§7.3） |
| R-07 | 无本地仿真兜底 | 调试周期长 | 中 | golden 位级对拍 + KEY1 逐层导出协议（§9.1/9.2）；状态机语义 1:1 建模 |
| R-08 | PDS 综合器 SV-2005 边界 | 构建失败 | 中 | 沿用已验证风格（always @*、显式 wire/reg、无空端口连接）；大型生成代码降级展开；沿用六阶段 tcl |
| R-09 | CDC（4 时钟域） | 间歇数据损坏 | 中 | CDC 路径穷举表（§1.4）；全部 FIFO/双同步器；fdc 每时钟独立 async group；时序全绿硬门槛 |
| R-10 | 奇数池化截断 floor | 形状漂移对拍挂 | 低 | §4.4 形状对照表 + 硬件 `W[10:1]` 实现 + 对拍 checklist 首项核对 conv1 输出 48×32×129 |
| R-11 | **（新增）DRM 预算贴边（107/108）** | PnR 拥塞/时序失败 | 高 | §10 削减方案（波形单页、谱图单页、wbank 复用）；备用降级：FFT 级间/行缓冲迁移 CLMS 分布式 RAM（LUT 余量 57%）；极端情况 conv 行缓冲 DDR3 化（带宽余量巨大） |
| R-12 | **（新增）激活 scale 提取依赖 quantized_model.pt 内部结构** | 转换工具产出错误契约 | 中 | F-01 已核实导出脚本语义；转换工具对 6 层逐一断言 scale/zp 合理性（s∈(1e-4,1)、zp∈[-128,127]）；golden 端到端对拍（REQ-ACC-003）为最终防线 |
| R-13 | **（新增）UART 权重加载耗时/失败** | M2 上电流程长 | 低 | 60s 一次性成本（演示准备段）；分块 CRC 自动重传；加载进度 UART 百分比回显 |
---

# 十二、构建集成

## 12.1 目录结构（REQ-BLD-004：独立落盘、复制资产、零改动既有工程）

```text
instrec_fpga/
├── src/                      # 全部 RTL（.v，SV-2005）
│   ├── instrec_top.v
│   ├── audio/                # i2s_clk_gen.v / i2s_rx.v / audio_cdc_fifo.v / audio_sink.v
│   ├── ddr3/                 # ddr3_wrapper.v / ddr3_ctrl_axi.v / ddr3_arbiter.v
│   ├── mel/                  # mel_engine.v / stft_framer.v / fft2048_sdf.v / mel_filter.v / db_norm.v
│   ├── npu/                  # npu_top.v / wdma.v / conv_engine.v / pool_engine.v / gap_fc.v
│   ├── ui/                   # ui_renderer.v / waveform_disp.v / spectrum_disp.v / font_rom.v / bars_disp.v
│   ├── hdmi/                 # hdmi_tx_if.v + demo 复制(sync_vg.v / iic_dri.v / ms7200_ctl.v / ms7210_ctl.v / ms72xx_ctl.v)
│   ├── ctrl/                 # sys_ctrl.v / self_test.v / weight_loader.v / uart_debug.v / uart_tx.v / uart_rx.v / softmax_top.v
│   └── ip/                   # audio_pll(例化壳)/hdmi_pll(例化壳) 由 ipcore 生成物引用
├── ipcore/
│   └── ddr3_test/            # 从 pds_cpu_100h/ipcore/ddr3_test 整目录复制（REQ-BLD-004 溯源清单登记）
├── constraints/
│   ├── instrec_top.fdc       # 板载(clk/rst/key/led/uart) + I2S 三脚(U20/T20/V16) + HDMI 37 脚(demo fdc 复制)
│   ├── ddr3_100h.fdc         # 从 pds_cpu_100h 复制，层级前缀改为 ddr3_wrapper.I_ips_ddr_top（保持 IP 实例名）
│   └── gen_ddr3_fdc.py       # 复制（生成/校验 73 针表）
├── scripts/
│   ├── build_full.tcl        # 六阶段批处理（模板见下）
│   ├── run_pds_full.ps1      # 令牌展开 + pds_shell 调用 + sha256 校验（参考 pds_cpu_100h 同名脚本）
│   ├── gen_weight_image.py   # §6.1 权重镜像/层契约转换
│   ├── gen_mel_tables.py     # Hann/Mel COO/log2/exp LUT 生成（coe/hex + sha256）
│   ├── gen_font.py           # 字库 hex 生成
│   ├── golden_pipeline.py    # §9.1 位级金标准
│   ├── check_rtl.py          # SV-2005 lint 清单（REQ-BLD-003：snake_case/always@*/无空连接/英文注释抽查）
│   ├── weight_upload.py      # §6.2 UART 上位机加载
│   └── uart_capture.py       # §9.2 导出采集对拍
├── build/                    # 时间戳构建输出（git 忽略）
└── docs/                     # 对拍报告/验收记录归档
```

## 12.2 build_full.tcl 模板（结构沿用 pds_cpu_100h 六阶段）

```tcl
# PDS batch flow for InstRec-FPGA (instrec_top).
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src audio *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src ddr3 *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src mel *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src npu *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src ui *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src hdmi *.v]]] { add_design $design }
foreach design [lsort [glob [file join "__PROJECT_ROOT__" src ctrl *.v]]] { add_design $design }
add_design "__PROJECT_ROOT__/ipcore/ddr3_test/ddr3_test.idf"
add_constraint "__PROJECT_ROOT__/constraints/instrec_top.fdc"
add_constraint "__PROJECT_ROOT__/constraints/ddr3_100h.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -system_verilog -top_module instrec_top
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
```

## 12.3 约束文件组织

- `instrec_top.fdc`：`create_clock clk_27m 37.037`；新增 `pix_clk`、`clk_nco` 时钟声明（GPLL 输出，create_generated_clock 或由 IP 传播）；`set_clock_groups -asynchronous` 覆盖 {clk_27m / pix_clk / clk_nco / ref_clk 系 DDR3 家族}（沿用官方每时钟独立 group 写法）；板载 + I2S + HDMI 引脚（HDMI 37 脚自 demo fdc 逐针复制，仅顶层名对齐 `vout_*`/`iic_*`）。
- `ddr3_100h.fdc`：整文件复制，唯一改动为时钟/引脚路径前缀从 `ddr3_wrapper.I_ips_ddr_top` 保持不变（顶层直接例化 ddr3_wrapper 于 instrec_top 下，层级前缀与原工程对齐——通过在 instrec_top 中将 wrapper 实例命名为 `ddr3_wrapper` 精确复刻，实现零语义改动复制）；`gen_ddr3_fdc.py` 校验 73 针表一致性。
- DDR3 IP 实例名硬性保持 `I_ips_ddr_top`（REQ-MEM-001 / REQ-BLD-004）。

## 12.4 run_pds_full.ps1

沿用 pds_cpu_100h/scripts/run_pds_full.ps1 模式：展开 `__PROJECT_ROOT__`/`__BUILD_ROOT__` 令牌 → 调 `pds_shell.exe -file build_full.tcl -work_dir <build> -project_name instrec_fpga` → 扫描日志 Error（`C: Bitstream-2001: SCBV` 按已知豁免）→ 校验 `build/.../generate_bitstream/instrec_top.sbit` 存在并记录 sha256（REQ-BLD-001）。

---

# 十三、需求→设计章节追溯表

| 需求 | 设计覆盖章节 | 关键设计决策 |
| --- | --- | --- |
| REQ-PRF-001（3.0s 节拍） | §2.2.4、§5.1 | 环形缓冲写指针每 132096 样本产 win_tick |
| REQ-PRF-002（端到端 ≤3.5s） | §3.8、§4.6、§7.4 | Mel 7ms + NPU 57.5ms + UI 双缓冲 ≤1 帧延迟 → 总 ≈3.02s |
| REQ-PRF-003（分阶段预算） | §3.8、§4.6、§7.7 | 各级 cycles 计数器经 UART 导出 |
| REQ-PRF-004（UI ≥10fps） | §7.4 | 波形 60fps 帧率刷新 |
| REQ-PRF-005（带宽 ≤285MB/s） | §5.4 | 带宽核算表交付 + 等待计数器 |
| REQ-RSC-001~004 | §10 | LUT 22.8k/FF 19.3k/DRM 107/APM 20/GPLL 4 全部达标（DRM 贴边挂牌） |
| REQ-RSC-005（权重 DDR3） | §4.1、§6 | 16 通道组 ≤27.6KB 片上缓冲 |
| REQ-RSC-006（DDR3 ≤32MB） | §5.1 | 总占用 <2MB |
| REQ-ACC-001~005 | §3、§9.1/9.2 | 位级误差预算链 + golden 对拍 + 导出协议 |
| REQ-BLD-001~005 | §12 | 六阶段 tcl + lint 清单 + 独立目录 + JTAG sbit |
| REQ-REL-001（自检链安全态） | §1.3、§6.4 | sys_ctrl 状态机 + 错误码 |
| REQ-REL-002（超时重入） | §2.2.7、§2.2.9 | 2× 预算看门狗 + 阶段复位重入 |
| REQ-REL-003（静音鲁棒） | §2.2.3/2.2.4、§7.2 | 静音注入 + UI 提示 |
| REQ-MNT-001~003 | §2.2.9、§9.2 | 行式状态输出 + KEY1 导出 + LED 编码 |
| REQ-AUD-001~007 | §1.2、§2.2.2/2.2.3、§8 | NCO 时钟 + Philips 解码 + 引脚选型 + 双同步器 |
| REQ-MEM-001~005 | §2.2.5、§5、§6.4 | IP 复制/契约适配/仲裁/图案自检 |
| REQ-FTR-001~007 | §3 全章 | 参数固化 + 两遍语义 + 位宽表 + 耗时核算 |
| REQ-INF-001~008 | §4 全章 | 结构对照表 + requant + 导出 + 双缓冲提交 |
| REQ-UI-001~007 | §7 全章 | demo 复用 + 布局 + 字库 + 渲染 |
| REQ-SYS-001~004 | §1.3、§2.2.9 | 自检链 + KEY 复位/触发 + LED/UART 一致 |
| REQ-VER-001~004 | §9.3 | M0~M3 用例清单 |

---

# 十四、与 spec 的偏差与发现记录（显式声明，无静默偏离）

| # | 事项 | 性质 | 说明与理由 |
| --- | --- | --- | --- |
| D-01 | `*_scale.npy` 语义精确化 | 事实澄清（非偏离） | 用户/需求背景称「conv1_scale.npy 等为激活量化 scale」；实测 `src/quantize.py` L564 证实其为**权重 per-channel scale**。激活 scale/zp 必须从 quantized_model.pt 提取（§6.1 转换工具双源输入）。设计按实测事实执行，语义结果不变（fbgemm requant 公式两者都需要），但转换工具实现与 spec §6.3 的「24 个核心文件」表述存在补充依赖（pt 文件），已在 F-01/R-12 登记 |
| D-02 | pds_cpu_100h 资源参考值更新 | 事实澄清 | 背景材料称 7653 LUT；最新 PnR 实测 8458 LUT（§10 锚点取实测值，对预算结论无影响） |
| D-03 | HDMI demo 实际路径 | 事实澄清 | demo 位于 `D:\0000\111\001\Pango\docs\...`（Pango 根 docs，非 ZGTC_RISC_CPU/docs）；REQ-BLD-004 复制资产路径以此为准 |
| D-04 | DRM 预算贴边 | 设计内解决 | 估算 107/108 块，通过波形单页化/谱图单页化/wbuf bank 复用达成；R-11 挂牌 + 分布式 RAM/DDR3 化降级路径预留 |
| D-05 | REQ-BLD-005 三步流程的附加说明 | 流程补充（非偏离） | 权重 UART 加载（60s）为演示准备段一次性步骤，不违背「下载位流→复位→运行」的运行态流程语义；操作手册注明 |
| D-06 | spec §9 R-01 候选「分数 PLL」未采用 | 决策落实 | 无板级先例（§1.2 方案对比），采用整数倍频 + NCO，精度更优且风险可控 |

---

# 十五、结语

本设计以「权重 DDR3 流式 + 激活片上行流水 + log2 域两遍 Mel + 单核心域」四决策消解全部硬约束：114.6M MAC @16 并行 57.5ms（预算 3.5×）、Mel 7ms（21×）、带宽 0.96MB/s（285MB/s 预算的 0.3%）、DRM 107 块（贴边通过挂牌跟踪）、GPLL 4/4。所有 69 条 EARS 需求在 §13 追溯表有唯一设计落点；三个事实级发现（F-01/D-01 权重 scale 语义、D-03 demo 路径、D-02 资源锚点）已显式登记。下一步进入 spec-task-agent 的任务分解（本设计文档为唯一上游）。

（完）