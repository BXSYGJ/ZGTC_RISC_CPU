# InstRec-FPGA 交接快照 · 2026-11-01

> 上一份快照：`HANDOFF_SNAPSHOT_20261031.md`（其结论多数已被本轮推翻或细化）。
> **实时状态以 `docs/STATUS.md` 为准**，本文件提供资产清单、结论依据与踩坑记录。

---

## 一、一句话

**R1（DDR3 自检）已在板上证明（`DDROK`）；NPU 四层与 Mel 全链已在 RTL 级逐值验证通过；
剩余两个缺口是「多主口并发下的 IP 写通道污染」与「WOK 的 PC→FPGA 物理方向」。**

本轮最重要的认知转变：**此前所有板级失败结论都不可沿用**——修掉 9 个真 RTL 缺陷后，
DDR3、conv1~4、Mel、fc/softmax 的正确性才第一次被真正验证。

> **交接时的构建状态（必须如实告知接手人）**：`core_only` 第三次构建（含 `cmd_to_err[3:0]` 观测改进）
> **在布线中途中止，未收口、无新位流**（中止时未布 3270 个网络）。本次交接**不新增任何位流**，
> 可引用的位流全部是表 5.1 中已归档的那几份。日志留档
> `build/stall_evidence/flow_core_only_v3_interrupted_20261101.log`。
> 接手后若要继续，先从「六、未完成项」第 1 条开始，**不要试图续跑那个被中止的 run**（PDS 无增量布线）。

---

## 二、需求达成矩阵

| 需求 | 状态 | 证据（可复核） |
|---|---|---|
| **R1 DDR3 自检** | ✅ **board-proven** | 串口 `INSTREC BOOT` / `DDR3 SELFTEST...` / **`DDROK`** / `DDR3 STS 01`；`reports/board_core_only.json` `verdict=PASS`、`expect_missing=[]`、`status_raw=0x081ffca0`、`uart_bytes=48`；两次烧录逐字节一致 |
| **R2 权重上传 WOK** | ⚠️ 未达成，**归因已搬离 DDR3/RTL** | RTL 级：`sim/run_sim.py weight_loader` **10/10 PASS**，串口为完整 `WOK 42851062`；板上：FPGA→PC 通（`DDROK` 260 B 完整），**PC→FPGA 零字节**（连最简 `'N'` 都不回）⇒ 硬件侧 CP2102 TX→B24 或 UART 选择 |
| **R3 构建流水** | ✅ 达成 | 6 个构建集 `full`/`ddr3_diag`/`ui_demo`/`conv1_test`/`mel_test`/`core_only`；8 token；`-DryRun`；小位流 5~15 min vs 全量 2 h |
| **R4 UI 通路 M3** | ✅ **board-proven** | `top_ui_demo` 独立位流：四层各自出像素（`de_nonzero` 3.8e9、`spec` 131072/帧、`bars` 8000/帧、`text` 148/帧）、`vsync` 59.95 fps、`pix_clk +0.251`、`hdmi_init_fail` 全程 0 |
| **R5 板级判读脚本化** | ✅ 达成 | `board_check.py --expect` 退出码 5 + 12 键 JSON；22 项离线测试 |
| **R6 验证资产** | ✅ 达成 | **429 passed / 4 skipped**；`check_rtl.py` 52 个 `.v` **0 violation**；8 条跨契约护栏（含变异探测灵敏度验证） |
| 逐层对拍 | 部分解除 | conv1 单层**板上** `mismatch 0/3072`（`sum 26685`）；conv2~4 与 fc/softmax 为 RTL 级全对；**全链层间串联仍需 `layer_export`** |

---

## 三、本轮修掉的 RTL 缺陷（不修则旧板级结论全不可沿用）

### 3.1 阻塞级（决定 DDR3 能否通）

| # | 文件 | 缺陷 | 板级表现 |
|---|---|---|---|
| 1 | `src/ctrl/self_test.v` | `done` 端口**声明后从未使用** | AXI 超时 abort 后永久卡 `ST_WDATA` → `DDR3 ERR @FFFFFFFF` |
| 2 | `src/ctrl/instrec_top.v` | `st_wready_beat` 无驱动 | PDS 静默 `Verilog-2036` tie 0 → 首条写必 `@00300000` |
| 3 | `src/ctrl/instrec_top.v` | `m0_done` 无驱动 | `audio_sink` 电平保持式命令独占仲裁 → m3 被饿死 |
| 4 | `src/ctrl/sys_ctrl.v` | 三个结论行不查 `dbg_busy` | `DDROK`/`ERR` 被 3 ms 忙窗口静默丢弃（连续三轮只有 30 字节的成因） |
| 5 | `src/ctrl/weight_loader.v` | `S_TX` 与 `uart_tx.byte_wready` 相位不匹配 | **每隔一个字符丢一个**：`WOK 42851062` → `WK4816`（板级 WOK 零回复的真因，与 DDR3 无关） |

### 3.2 数值级（决定 NPU / Mel 是否算对）

| # | 文件 | 缺陷 | 失配量级 |
|---|---|---|---|
| 6 | `src/npu/requant_unit.v` | `shift_q`/`zp_q` 只锁存到 S1，S3 时已被下一拍覆盖 | lane k 用 lane k+1 的 shift |
| 7 | `src/npu/conv_engine.v` | `snapshot_go` 与 `advance_now` 同拍，16 拍 drain 跨 contract promote | 每组 `col257` 用下一组 M/shift（1300 个残差） |
| 8 | `src/audio/audio_sink.v` | `17'd132_096` 截断成 **1024**（需 18 位） | 窗口 2.995 s → **23.2 ms**（短 128 倍），破坏全链窗口语义 |
| 9 | `src/mel/db_norm.v` | `localparam signed [9:0] DB_NUM_S = 775` 超出 10 位有符号 | 775 被解成 **−249** → dB 全钳 0 → feat 全 `zp_in(49)`（16512/16512 失配） |
| 10 | `src/mel/mel_filter.v` | `sq_lo_sum` 19 位不足（lo² 对和上界 522242） | 溢出成负 → power 偏 2^19 或饱和 2^44−1 |
| 11 | `src/mel/mel_filter.v` | Stage B 4 级：`pwr_q` 在 F1 就锁存，而 power RAM 是同步读 | 每个 entry 乘的是**前一个 entry** 的功率（96.9% 可复现） |
| 12 | `src/mel/mel_filter.v` | COO offset 读地址 `ch + 6'd1` 6 位溢出（ch=63 时 →0） | ch63 每帧一个 MAC 都不发，acc=0 |
| 13 | `src/mel/fft2048_sdf.v` | stage0 用 `rhu(32767·d,15)` 近似 `d`，\|d\|>16384 差 1 LSB；每级 `n_cnt` 缺相位预置；`ST_DRAIN` 的实样本被当 dummy | 整条 bin 流错位 + 每帧只导出 1 个 bin |
| 14 | `src/mel/stft_framer.v` | `17'd132095` 截断成 1023（PH_STREAM 永不退出）；缺 `out_ready` 门控 | 流入帧数错、尾部 2 帧虚拟 push 抢跑 |
| 15 | `src/mel/mel_engine.v` | `FILL_CREDIT=1025` 配 `credit>=256` 门限 | 只发 4 命令 = 1024 样本 < PH_FILL 的 1025 → **永久死锁**（板上 `C=4/D=1024` 精确吻合），改 1280 后 516 条正常 |
| 16 | `src/mel/twiddle_s*.hex` | `export_twiddle_hex.py` 打包时 int16→uint32 符号扩展覆盖高 16 位 | **511/1024 个 twiddle 词损坏** |

### 3.3 观测与契约级

| # | 位置 | 改进 |
|---|---|---|
| 17 | `sys_ctrl.v` 的 `DDR3 STS` 字节 | 由 `{1'b0, cmd_to_err[3], to_err, dbg_to_state, st_fail, st_done}` 改为 `{cmd_to_err[3:0], to_err, dbg_to_state}`，**暴露每个 master 的超时位**（若早如此，本轮不会把 m0 的超时误判成 m3） |
| 18 | `self_test.v` | 删除端口已声明后又重复声明的 `wire [255:0] wdata`（PDS 静默容忍，Verilator 直接报错） |

---

## 四、验证矩阵（RTL 级 vs board-proven）

| 模块 | RTL 级（Verilator） | 板级 |
|---|---|---|
| conv1 | `mismatch 0 / 792,576` | **`mismatch 0 / 3072`**，`sum 26685 == 26685` |
| conv2 / conv3 / conv4 | 全 0 失配（合计 658,432 字节） | — |
| Mel 全链 | **`feat 16512 mismatch 0`**（`mel_credit` PASS，5.09 M cycles、259 帧） | — |
| gap→fc1→fc2→softmax | bit-exact（含 `FC2_ZP=56` 反向对照证明判据非空转） | — |
| `weight_loader` | `WOK 42851062` 13 字节完整、digest 三侧一致 | ⚠️ PC→FPGA 未通 |
| DDR3 控制器 | 15/15 场景 + 6/6 AW 场景 | **单 master `DDROK` ✅** |
| UI 四层 | 合成优先级逐像素 | **四层出像素 ✅** |
| `self_test` | 4 组 FSM 场景 PASS、`cmd_valid` 最短保持 21 拍 | 16 段写读全过（`STS 01`） |
| `sys_ctrl`+`uart_debug` | `DDROK` 在 204k 拍忙窗口内仍打印 | ✅ 同左 |

---

## 五、关键资产

### 5.1 位流

| 文件 | SHA-256 | 用途 |
|---|---|---|
| `releases/m5-ddrok-20261101/instrec_core_only_ddrok.sbit` | `d375a43dba3d5db68285cdba3c5158413379510ea53d29ea8baec17f4c4e18a8` | **R1 board-proven 证据**（单 master，APM 0） |
| `build/top_core_only-latest.sbit` | `67224B04D04DFC8468EEFD0B610C3653BDD692A9BA43B8F435DEF5FF8BE1E663` | NPU 接活版（APM 89），多 master 下 AW 失败 |
| `build/top_ui_demo-latest.sbit` | `D1EF2594F636EE6AA3140B151216B1390FEB84817301FF99627652C4CCE9B1A9` | UI 四层 board-proven |
| `build/top_npu_conv1_test-latest.sbit` | `5EEEC976F14288F66147EC9C6D2AAD6B568276E4F0EDA8F4368B9EF850FFA6FD` | conv1 板上 `mismatch 0` |
| `build/top_ddr3_diag-latest.sbit` | `F749A41768C31AE57AFC2ACE0B1C075CB35110056BB6A863408B5CFF2402266F` | DDR3 诊断（design 配置 PASS） |
| `build/instrec-latest.sbit` | `B895FCAC…`（m4fix） | 全量；**mel 通路带 `out_done` 粘滞缺陷，只能产 1 帧** |

> **注意**：`build/*-latest.sbit` 会被下一次同 set 构建覆盖。R1 证据已另存到 `releases/`，勿删。

### 5.2 报告（结论依据）

| 报告 | 内容 |
|---|---|
| `reports/multi_master_aw_timeout.md` | **多主口失败根因**：IP 写通道污染 + 6 场景仿真 + 4 个修复方案 |
| `reports/sim_ddr3_conclusion.md` | DDR3 控制器 15 场景（含 watchdog 五态、m0 抢占解除、blind spot） |
| `reports/conv1_fix_conclusion.md` | conv1 七项根因（P0a/P0b/P1a/P1b/P2/P3/P4/P5） |
| `reports/conv_multi_layer_conclusion.md` | conv2~4 全对（658,432 字节） |
| `reports/mel_final_closure.md` | Mel 逐级 mismatch 表与三处 `mel_filter` 缺陷 |
| `reports/mel_fft_final.md` | FFT bin 窗口 2058 的推导 + twiddle 打包缺陷 |
| `reports/weight_loader_tx_fix.md` | 串口隔字符丢失的三重证据 |
| `reports/ui_demo_conclusion.md` | UI 四层判据 |
| `reports/core_only_conclusion.md` | 精简顶层裁剪清单 |
| `reports/stall_evidence/` | 全量 LUT 34960 停滞的 6.7 小时日志 |

### 5.3 仿真基建（本轮新增，最重要）

```
sim/run_sim.py          统一入口：all --jobs 8 → 全套 44 秒
sim/tb_*.sv             11 个 TB：conv1 / mel / mel_credit / self_test / weight_loader /
                        ctrl_smoke / npu_chain / ui_render / ddr3_subsys / ddr3_aw_timeout / top_conv1
sim/ddr3_axi_model.sv   行为级 DDR3 IP 模型（可注入 awready 延迟 / 永不 ready / WSTRB_IGNORE）
```
Verilator 5.050 在 `H:\GG\bin\verilator.bat`（不在 PATH），g++ 16.2.0 就绪。

### 5.4 配套软件齐备度（PC 侧上位机 / 权重上传 / 判读脚本）

| 脚本 | 用途 | 状态 | 说明 |
|---|---|---|---|
| `scripts/board_check.py` | **烧录 + 串口判读一体化** | ✅ 可用 | `--sbit/--port/--seconds/--expect/--json`；退出码 0/2/3/4/**5**；自动复用已有 `cdt_js`；22 项离线测试 |
| `scripts/weight_upload.py` | 权重镜像上传（CRC-16/CCITT + 分块回执） | ⚠️ **脚本就绪、链路未通** | 脚本本身无缺陷（RTL 侧仿真 `WOK 42851062` 完整）；板上 **PC→FPGA 零字节**，属硬件通路问题，非软件问题 |
| `scripts/uart_capture.py` | 裸串口抓包 | ✅ 可用 | 配合 `build/uart_last.bin` |
| `scripts/compare_conv1.py` | conv1 逐字节对拍 | ✅ 可用 | 多模：`--golden-only/--self-check/--emit-hex/--uart-file/--json`；板上实测 `mismatch 0/3072` |
| `scripts/compare_mel.py` | Mel `feat` 逐字节对拍 | ✅ 可用（仿真侧已验） | 自带转置（golden 是 `mel*258+frame`）；板上未验 |
| `scripts/compare_layers.py` | 逐层对拍 | ⚠️ **缺 RTL 导出** | RTL 无逐层 UART 输出，恒返回 rc=1；需先做 `layer_export` |
| `scripts/diag_frames.py` | 91 字节诊断帧解析 | ✅ 可用 | `parse_frame/parse_all/DDR3_E_BITS` |
| `scripts/golden_pipeline.py` | **位级真值**（与浮点精确数学 0 LSB） | ✅ 权威 | 对拍只认它，不认 torch（torch 有 21~67 LSB tile 噪声） |
| `scripts/gen_weight_image.py` | 从 `layer_contract.json` 生成权重镜像 | ✅ 可用 | 691040 B，sha `19a74dbe…5d7a`，2700+1 帧 |
| `scripts/run_pds_full.ps1` + `build_full.tcl` + `build_sets.json` | 构建流水（6 个 set） | ✅ 可用 | 支持 `-BuildSet`/`-TopModule`/`-DryRun` |
| `sim/run_sim.py` + 11 个 TB | **Verilator 仿真基建** | ✅ 可用 | `all --jobs 8` 全套 **44 秒** |
| `scripts/check_rtl.py` | SV-2005 词法检查 | ✅ 必跑 | 52 个 `.v`，必须 0 violation |

**软件侧唯一真实缺口**：`layer_export`（逐层 UART 导出）尚未实现——这是「逐层对拍」的必要条件，与硬件无关。

**硬件侧依赖（脚本无法替代）**：
- 真实 I2S 音频输入（否则全链只能用 `conv1_test`/`mel_test` 的 golden 预置激励）
- CP2102 串口 TX→B24 通路（WOK 的 PC→FPGA 方向依赖它）
- FT2232H 下载器（`cdt_js` 单实例）

---

## 六、未完成项与下一步（按序）

### 6.1 多主口并发下的 DDR3 失败（**最高优先**）

**现象**：接通 audio/mel 的 core_only（APM 89、LUT 32615）板级 `DDROK` FAIL，`DDR3 STS 26`。

**判读（已修正）**：`STS 26` → `st_fail=1`、`dbg_to_state=001`(S_AW)、`to_err=1`、**`cmd_to_err[3]=0`**。
`cmd_to_err[3]=0` 与「m3 自己在 S_AW 超时」在 RTL 上互斥 ⇒ 超时者是 **m0**，m3 的 `st_fail` 是**数据失配**。

**根因**：**IP 侧写通道污染**——写数据阶段被中止后，未完成的写突发永不闭合，此后**所有 AW 永久被拒**
（仿真 A1 实测 13103 拍内 `awready` 一次都没出现）。仲裁已被证伪（m3 排队仅 5 拍、AW 等待 2 拍）。

**修复方案（按确定性排序，均在 `reports/multi_master_aw_timeout.md`）**：
1. ~~暴露 `cmd_to_err[3:0]`~~ **已实施**（`sys_ctrl.v`，1 行；测试同步 1 处；429 passed）
2. **`S_WDRAIN`**（根因，中等风险）：`ddr3_ctrl_axi.v` 的 `S_W`/`S_DW_W` 超时后不直接回 `S_IDLE`，
   而进入新增状态用 **`wstrb=0`**（**不能复用 `DUMMY_WSTRB_ALL1`**）补完剩余 beat 至 `cur_len`，
   清掉 IP 未完成突发。需 state 3→4 位 + dbg 3→4 位 + `sys_ctrl` 解码 + TB 断言同步。
3. **自检窗口 gate**（规避，5 行）：`instrec_top.v` 在 `st_start`..`st_done/st_fail` 窗口内屏蔽
   m0/m1/m2 的 `cmd_valid`。**注意**：`audio_sink` 是电平保持式，被 gate 会等不到 `done` → 需确认
   不会卡死到它自己的超时。
4. **`st_fail_addr` 细化到 beat 粒度**（可诊断性）：区分「首拍被 dummy write 破坏」与「中段错乱」。

**明确不推荐**：提高 `AXI_TO_LIMIT`（污染是永久的，只延长卡死）；给 m1/m2 加配额（仲裁不是瓶颈）；
改 audio 短突发（A4 已证伪）。

### 6.2 WOK（R2）

先分清两层，再谈修：
- 在 `core_only` 里加一个 `uart_rx` 活动计数器接 `led`，看 `weight_upload` 发包时 FPGA 侧**有无活动**；
- 有活动 → 协议/波特率/帧格式；无活动 → 硬件（CP2102 TX → B24 跳线 / UART 选择）。
**不要**再去动 `weight_loader`（`sim` 已证 `WOK 42851062` 完整）。

### 6.3 全链层间串联（逐层对拍的最后一块）

需新增 `src/diag/layer_export.v` + 串口三路仲裁，把各层输出按 `design.md` 9.2 导出。
预估：mel 33,024 B / conv1 792,576 / conv2 396,288 / conv3 196,608 / conv4 65,536 /
fc1 128 / fc2 32 / probs 8 ≈ **1.48 MB ≈ 5,801 帧**，115200 下约 **132 s**。
另需真实 I2S 音频输入（否则只能 DEFERRED）。

### 6.4 时序债

`ddrphy_sysclk −1.740 ns`（实际 102.67 MHz）未收敛。最差路径在
`u_weight_loader/beat_buf → m1_wdata`，**走线占 88.5%**（布局散布，非逻辑深度）。
注意：`instrec-latest.json` 的 `Wns` 只取 `Setup Summary` **第一行**（`clk_nco`），
**不是最差域**；`All Constraints Met` ≠ 收敛。

---

## 七、本轮新增踩坑记录（务必先读，能省数小时）

1. **LUT 敏感度极高**：34960（52.49%）**停滞 6.7 小时**（未布数 4400~4600 震荡）；
   裁 UI 后 32615（49.1%）**一次布通**。**差 1.9 个百分点即从永久停滞回到可行解** ⇒
   该器件是「余量为零」而非资源不足。任何新增 RTL 前先估 LUT。
2. **`iteration` 号不能当失败证据**：m4fix 布通于 iteration 1151；iter 500~950 长震荡仍属正常
   rip-up。**判据是未布数的固定间隔采样趋势**，不是 iteration 值。
3. **`DRM=0` 不等于 DDR3 PHY 缺失**：PHY 走专用硬核（`DDR_PHY 7/24`、`PPLL 2/6`、`TSERDES 14/48`）；
   `DRM` 是通用分布式 RAM。**`IO 85` 也不等于 pad 少了**（119 − vout28 − iic2 − i2s3 − key1_n1 = 85）。
4. **`APM=0` 才是真信号**：控制端 tie 常量会让整块 NPU 被常量传播删掉。**位流布通 ≠ 模块被例化**。
5. **PDS 只发 warning 静默 tie 0**：`Verilog-2036` 的「no driver」必须当真缺陷，不能当 waiver。
   同理 **`Verilog-4005` 保留字**（`tri`）、**重复声明**只有 Verilator 会报。
6. **多个独立 PDS run 可同时跑**（license 不冲突），但会把全量单轮拉长；小位流可与全量并行。
   **同顶层同改动的重复 run（子代理超时遗落）必须中止旧的**，否则抢 CPU。
7. **子代理有 120 分钟硬上限**：超时中止后**先核实 PDS 进程与产物**再决定是否重跑——
   产物可能已收口（2026-11-01 两次如此）。
8. **`mel_engine` 的 PCM 来自 DDR3 m2，不是 I2S**（无 I2S 端口，516 条 len=15 读命令）。
9. **TB 自身的门限坑**：`tb_mel_engine` 的 `WATCHDOG_LIMIT=2_000_000` 小于 4.77 M 帧预算，
   会把「正确但慢」误报成死锁；`drain_active` 门控拿不到 1025 个 bin（必须用 `run_cnt` 窗口）。
10. **dB 级 0 失配可能是假绿**：`top_db` 钳位会掩盖 log2 级缺陷，**第一判据必须用 mel/log2 级**。
11. **golden 索引方向**：`feat.npy` 是 `mel*258+frame`，RTL 是 `frame*64+mel`，须转置；
    TB 若用错方向会把失配放大约 17 倍。

---

## 八、命令速查（在 `instrec_fpga/` 下执行）

```powershell
# 静态与单测
python scripts/check_rtl.py                    # 必须 0 violation（52 个 .v）
python -m pytest -q                            # 429 passed / 4 skipped

# 仿真（首选，44 秒全套）
python sim/run_sim.py all --jobs 8
python sim/run_sim.py dd3_subsys               # 单 case：DDR3 控制器 15 场景
python sim/run_sim.py mel_credit               # 单 case：Mel 全链
python sim/run_sim.py weight_loader            # 单 case：WOK 主路径

# 构建（一次一个顶层；小位流 5~15 min，全量 1.5~2 h）
powershell -File scripts/run_pds_full.ps1 -BuildSet core_only
powershell -File scripts/run_pds_full.ps1 -BuildSet ui_demo
powershell -File scripts/run_pds_full.ps1 -BuildSet conv1_test
powershell -File scripts/run_pds_full.ps1 -BuildSet mel_test
powershell -File scripts/run_pds_full.ps1 -BuildSet ddr3_diag
powershell -File scripts/run_pds_full.ps1      # 全量 full（LUT ~34.9k 会停滞，慎用）
powershell -File scripts/run_pds_full.ps1 -BuildSet core_only -DryRun   # 只看文件展开

# 板级
python scripts/board_check.py --sbit build/top_core_only-latest.sbit --port COM5 --seconds 25 `
  --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK" --json reports/board_xxx.json
python scripts/compare_conv1.py --uart-file build/uart_last.bin
python scripts/compare_mel.py --capture build/uart_last.bin
```

**判据 token**：`INSTREC BOOT` / `DDR3 SELFTEST...` / `DDROK` / `DDR3 STS <2hex>`。
**不要用 `"RUN"`**：`sys_ctrl` 从不置 `dbg_line_id=5`，永不命中。

**`DDR3 STS` 位段（2026-11-01 新版）**：`{cmd_to_err[3:0], to_err, dbg_to_state[2:0]}`
- `bit7:4` 每 master 的超时位（m0/m1/m2/m3）
- `bit3` 任一 master 曾超时
- `bit2:0` 超时所在状态：1=S_AW 2=S_W 4=S_DW_AW 5=S_DW_W 6=S_AR 7=S_R

---

## 九、纪律提醒（不变）

- 同一时刻只能有**一个 PDS run** 在跑（本项目实测多 run 可行，但会互相拖慢；排期时按实际 ETA 报）。
- `cdt_js` 单实例（PID 9040），**只复用、绝不 terminate**；TCL 一律 `exit` 收尾。
- 改 RTL 前：`check_rtl` → `pytest` → 再构建。
- 分支 **XSY**，**不要自动 push**。
- 不提交 `build/`、`reports/*.log`、`__pycache__`。
- `instrec_fpga/` 之外零改动（`ai_pcb/`、`cpu/`、根目录散落文件都不要动）。
- `.codeartsdoer/` 被自身 `*` 规则忽略，重要资产不要只放那里。