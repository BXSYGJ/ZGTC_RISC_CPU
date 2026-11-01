# T31 结论报告：audio_sink 窗口阈值截断（已修，仿真 PASS）+ FFT bin 导出（部分修复，未达 bytes differ = 0）

- 任务：T31（团队任务 id=31）
- 文件边界：`src/audio/audio_sink.v`、`src/mel/fft2048_sdf.v`、本报告
- 状态：
  - **任务 A：完成，Verilator 仿真 `RESULT: PASS`**（窗口 132096 帧、8256 页、页地址 0..264160 全部逐项断言通过）。
  - **任务 B：部分完成（PARTIAL）**。定位并修复了 3 个独立缺陷（stage0 Q1.15 乘积、每级 n_cnt 相位、DRAIN 有效样本），
    Python 周期模型已做到 **1025/1025 逐值相等（re 与 im）**；但产品 RTL 的实测窗口仍差 11 拍，
    最后一步（窗口常量 2058 → 2069）**未能复跑验证**（本次会话后段 `bash` 工具被环境拒绝，
    见 §6）。**未达成 `feat bytes differ = 0`，也未能跑 `sim/run_sim.py mel,mel_credit` 闸门。**
- 未启动 PDS 构建、未烧板、未 push。

---

## 1. 任务 A：`audio_sink.v` 窗口阈值截断

### 1.1 缺陷

`localparam [16:0] WIN_FRAMES = 17'd132_096;` —— 132096 需要 18 位
（2^17 = 131072 < 132096），17 位声明把常量截断成 `132096 − 131072 = 1024`；
唯一使用点 `win_frame_cnt == WIN_FRAMES - 17'd1` 于是变成 `1023`。窗口从
**132095 帧（2.995 s @44.1 kHz）** 缩到 **1023 帧（23.2 ms）**。

### 1.2 改动（该文件内所有相关位宽一起改，避免留下 17 位假设）

| 行（现状） | 改动 |
|---|---|
| 214 | `localparam [17:0] WIN_FRAMES = 18'd132_096;`（原 `[16:0]` / `17'd`） |
| 215 | 新增 `localparam [13:0] PAGES_PER_WIN = 14'd8256;` |
| 337 | `reg [13:0] page_no;`（原 `[12:0]`；0..8255 需要 14 位，2^13 = 8192 < 8256） |
| 364 | `reg [13:0] page_no_wr;` 并同步改 `page_no_wr <= 14'd0` |
| 377 | `page_off = {page_no_wr[13:0], 5'b00000}`（原 `[12:0]`） |
| 383 | `reg [17:0] win_frame_cnt;`（原 `[16:0]`） |
| 387/394/395/400 | `18'd0` / `18'd1` 常量 |
| 394 | 比较 `win_frame_cnt == WIN_FRAMES - 18'd1` |
| 410-421 | 见 §1.3（页号锁存与递增时机） |
| 429-431 | `addr_left` 改用锁存的 `page_win_wr` |

### 1.3 顺带修掉的 3 个同链缺陷（同一 always 块，均为窗口契约的一部分）

1. **页号位宽截断**：`page_no` / `page_no_wr` 原为 13 位，最大 8255 需要 14 位，
   到第 8192 页就回绕、覆盖前 64 页（2048 B）。已改 14 位。
2. **页号递增节奏错误**：原代码在**每个 `frame_event`** 上 `page_no + 1`
   （注释写的是「132096 = 8256 × 16，页计数器锁步」，实现却是每帧 +1）。
   于是 `page_no_wr` 序列是 0,16,32,…，页步进变成 **512 B 而不是 32 B**，
   写指针在窗口内的步进放大了 16 倍。现改为**每个完成的 16 帧页（`page_full`）加 1**。
3. **页号/窗口号锁存晚一拍**：原 `page_no_wr` 在 `page_go` 拍锁存，而写 FSM 也在
   `page_go` 拍读 `addr_left`，于是每条写命令用的是**上一页**的偏移（实测第 2 条命令
   仍是 addr = 0）；最后一页还会因为 `win_id` 在同一拍 +1 而写到**下一个窗口**。
   现改为在 `page_full`（第 16 帧，早 `page_go` 一拍）同时锁存 `page_no_wr` 与
   `page_win_wr`，`addr_left` 用锁存的窗口选择。

### 1.4 验证证据（Verilator）

实验 TB 放在 `build/tb_exp/tb_audio_win.sv`（`build/` 是 gitignored 实验区，
未动 `sim/`）；运行入口 `build/run_sim_exp.py audio_win`
（复用 `sim/run_sim.py` 的工具链逻辑，只改工作目录与 case 列表）。

TB 全程**只通过端口**驱动（不靠层次探针，避免 Verilator 把观测信号优化掉）：
1 拍延迟的 CDC-FIFO 读模型 + 2 拍完成的 DDR3 写 done 响应器；用
`fifo_rd_valid` 重建 `frame_event`。

```
WIN_TICK n=1 cycle=165116 frames=132096 win_id=1 left_cmds=8255 last_addr=264128
WIN_SUMMARY frames=132096 ticks=1 frames_at_tick=132096 win_id_at_tick=1
PAGE_SUMMARY left_cmds_at_tick=8255 last_addr_at_tick=264128 left_cmds_final=8256 last_addr_final=264160 addr_errors=0 err_cnt=0
WINDOW_SECONDS window_frames=132096 at 44.1kHz = 2.9954 s
RESULT: PASS tb_audio_win
```

断言逐项：

| 断言 | 期望 | 实测 |
|---|---|---|
| `win_tick` 次数 | 1 | 1 |
| `win_tick` 出现在第几个被接受的帧 | 132096 | 132096 |
| `win_id` 在 tick 时 | 1 | 1 |
| tick 时刻已写左页数 | 8255 | 8255 |
| tick 时刻最后左页地址 | 8254×32 = 264128 | 264128 |
| 整窗左页命令数 | 8256 | 8256 |
| 最后左页地址 | 8255×32 = **264160** | 264160 |
| 页地址序列误差（必须严格 +32 递增） | 0 | 0 |
| `err_cnt`（写超时） | 0 | 0 |

对照：改前 17 位常量会让 tick 落在第 **1024** 帧（`1023 + 1`），这个 TB 的第一条
断言即失败。**这是 RTL 级证明，不是 board-proven**（未烧板）。

---

## 2. 任务 B：`fft2048_sdf.v` 的 bin 映射

### 2.1 先复核前一任务的定位链（有修正）

用现有 24,565 行 trace（`build/sim_mel/rtl_trace.txt`，`run_cnt state s_out_re[10]`）
与新的直驱 dump（`build/sim_mel/rtl_fft_beat.txt`,
`frame run_cnt ph2 state re im`，`build/tb_exp/tb_fft_bins.sv`）复核：

| 前一任务的结论 | 复核结果 |
|---|---|
| 同一 `run_cnt` 出 4 个 `last_vld` | **成立**（valid 寄存器只在 phase 3 更新，整 beat 4 拍都高）⇒ 必须按 `ph2 == 3` 每 beat 采一次 |
| 不能用 `drain_active` 做门控 | **成立**（ST_DRAIN 里 valid 只有 10~11 个，因为 valid 只在 `samp_vld` 为高时传播） |
| 真正有效输出在 `run_cnt = 1025..2047` | **不成立**。实测有效（valid）输出是 `run_cnt = 11..2057`，共 2047 个；`run_cnt = 1025` 只是**第一个非零值**的位置（前 1014 个输出是 delay line 空态）。 |
| F7 三处改动（`run_cnt==2047` 退出 / `out_cnt`、`bin_*` 加 `drain_active`） | **确认是错的**，已按下面的正确方案替换 |

### 2.2 三个真正的缺陷（按依赖顺序）

#### (B-1) stage 0 不是纯加减：漏掉了 Q1.15 乘积 `rhu(32767·d, 15)`

模块头写 "stage 0 is a pure add/subtract ... prod = rhu(32767*d, 15) == d exactly"。
该证明是**错的**：`rhu(32767·d, 15) = d` 只在 `|d| <= 16384` 成立，
`|d| > 16384` 时差 1 LSB（例：`d = 20629 → 20628`）。

逐级对拍（golden stage 1 的输出流 vs 模型 stage 0）：
修前 **1481/2047** 相等，修后 **2047/2047** 全等。

改法（无乘法器，纯移位/加法）：

```
32767·d + 16384 = 32768·d + (16384 − d)  ⇒  prod = d + ((16384 − d) >>> 15)
```

对应 RTL（`fft2048_sdf.v` 约 364-372 行）：

```verilog
wire signed [18:0] st0_rnd = 19'sd16384 - {{2{st0_d_r[16]}}, st0_d_r};
wire signed [16:0] st0_pr  = st0_d_r + {{13{st0_rnd[18]}}, st0_rnd[18:15]};
wire [17:0] st0_sum = {st0_dly[16], st0_dly} + {st0_pr[16], st0_pr};
wire [17:0] st0_dif = {st0_dly[16], st0_dly} - {st0_pr[16], st0_pr};
```

#### (B-2) 每级 `n_cnt` 缺少相位预置（整条 bin 流错误的真正原因）

每一级比上一级晚 1 拍（phase 0 捕获上一级 phase 3 的输出），但所有级的
`n_cnt` 都在 `clr_n` 时同时清 0。于是级 k 的 pass/butterfly 块边界相对它的
输入流错位 `off(k)`。用 Python 逐级求解得到唯一解：

```
off(k) = delay(k−1) + 1,   delay(0) = 1,   delay(k) = off(k) + 2^k
       ⇒  off(k) = 2^k + k − 1
       ⇒  delay(10) = 2^11 + 10 − 1 = 2057（= 2047 延迟线 + 10 个级间寄存器）
```

即 `n_cnt` 初值 = `(−off(k)) mod 2048`：

| 级 k | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| off(k) | 2 | 5 | 10 | 19 | 36 | 69 | 134 | 263 | 520 | 1033 |
| 预置初值 | 2046 | 2043 | 2038 | 2029 | 2012 | 1979 | 1914 | 1785 | 1528 | 1015 |

逐级验证（golden stage s = k+1 的输出流，含 re/im 两路）：

| 级 | 相位修前 | 相位修后 |
|---|---|---|
| 0 | 2047/2047（B-1 修后） | 2047/2047 |
| 1 | 0/2047 | 2044/2044（平移 4 拍后全等） |
| 2 | 1020/2039（只对一半，因为当时模型没算虚部） | 全等 |
| 10 | 垃圾 | 全等 |

整帧级：`y[2057+k] == golden[k]`，**re 1025/1025、im 1025/1025 逐值相等**
（输入 = 同一帧 windowed 重复两遍，模型 `build/` 内联脚本，复现命令见 §6）。

#### (B-3) ST_DRAIN 的样本被当成 dummy（`samp_vld = 0`）

`ST_DRAIN` 用 `bitrev(run_cnt[10:0])` 重新读 `in_buf`，`run_cnt` 的低 11 位回绕，
所以 DRAIN 的 2048 beat 就是**本帧数据的第二遍**。但原 `samp_vld =
run_active && run_cnt < 2048` 把它们标成无效 ⇒ valid 链在 DRAIN 里只有一个尾巴
（10~11 个），bin 永远出不来。现改为 `samp_vld = beat_active`。

另外 ST_RUN→ST_DRAIN 的切换时机也从「`run_cnt == 2047` 任意 phase」改为
「beat 2047 的 `ph2 == 3` 之后」—— 原写法会**每帧丢掉最后一个样本**，
使 11 级 delay line 每帧少喂 1 个样本。

### 2.3 bin 导出窗口的推导（任务要求说明区间理由）

```
组延迟 delay(10) = 2057          ⇒ 流输出 y[m] 携带 bin (m − 2057) mod 2048
y[m] 在样本 m 进入级联后 11 拍可见 ⇒ beat run_cnt = m + 11
phase-3 沿采到的是"上一拍"的寄存器值 ⇒ 真正承载 y[m] 的 beat = m + 12
⇒ bin k 的采样 beat：run_cnt = 2057 + 12 + k = 2069 + k
⇒ 1025 个 bin 的窗口：run_cnt ∈ [2069, 3093]（完全落在 ST_DRAIN 的 2048..4095 内）
```

`bin_idx = run_cnt − 2069`（`run_cnt` 直接派生，不经过 `out_cnt`），
`bin_beat = last_vld && ph2 == 2'd3 && 2069 <= run_cnt <= 3093`：
每帧**恰好 1025 个 `bin_valid`、1025 个唯一 `bin_idx`**，顺序与自然序一致。

> 为什么不是任务书里的 `1025..2047`：那个区间是"填充期 + 前 1014 个空输出"，
> 只有 `bin 0` 附近的少量值非零，且**不是**本帧的频谱。真正的 1025 个 bin 必须
> 等组延迟 2057 走完，只能在 DRAIN 出现(帧首 2048 beat 是填充/无效输出)。

### 2.4 当前实测状态（**未达成逐值相等**）

| 版本 | 窗口 | RTL dump vs golden（re 相等数） |
|---|---|---|
| 原始 F7（`out_cnt ≤ 1024` + drain 门控） | — | 0 / 1025（导出全 0） |
| 本任务：修 B-1/B-2/B-3 后，窗口取 **2058** | 2058..3082 | **12~21 / 1025**（≈随机水平） |
| 本任务：窗口改 **2069**（= 2058 + 11，按 §2.3 时序推导） | 2069..3093 | **未复跑**（见 §6） |

2058 → 2069 这 11 拍修正的依据是 §2.3 的"11 拍可见 + phase-3 采到上一拍"，
与模型口径严格对齐；但**没有仿真日志，不当作已验证**。

---

## 3. 闸门状态

| 闸门 | 结果 |
|---|---|
| `python scripts/check_rtl.py` | **未执行**（会话后段 `bash` 被环境拒绝，见 §6） |
| `python -m pytest -q` | **未执行**（同上） |
| `python sim/run_sim.py mel,mel_credit` | **未执行**（同上） |
| `python build/run_sim_exp.py audio_win` | **PASS**（14.6 s，§1.4） |
| `python build/run_sim_exp.py fft_bins` | 生成/dump 正常；数值未对齐（§2.4） |

### 3.1 PDS 综合风险（未编译验证，必须由下一次构建确认）

1. `localparam [10:0] CNT_INIT = 11'd0 - OFF_M[10:0];` —— 对 `localparam integer`
   做位选。项目里已有 `LO_MASK = ((9'd1 << ...) - ...)` 这种 generate 内 localparam
   表达式，但**没有**"位选 integer 参数"的先例，属 PDS parser 风险点。
   若 PDS 报错，安全改法：在 generate 里直接写
   `localparam [10:0] CNT_INIT = 11'd2048 - (11'd1 << k) - k[10:0] + 11'd1;`
   （把 `2^k + k − 1` 展开成只含移位与加法）。
2. `19'sd16384` / `{{13{...}}, st0_rnd[18:15]}` —— sized signed 字面量与部分选，
   SV-2005 合法，PDS 预计可接受。
3. 资源：stage0 只增加 19 位减法 + 4 位符号扩展，无乘法器；`n_cnt` 预置不增加逻辑。

---

## 4. 改动清单

| 文件 | 改动 |
|---|---|
| `src/audio/audio_sink.v` | `WIN_FRAMES` 18 位、`PAGES_PER_WIN`；`win_frame_cnt` 18 位；`page_no`/`page_no_wr` 14 位；页号在 `page_full` 上递增；`page_no_wr` 与 `page_win_wr` 在 `page_full` 锁存；`addr_left` 用 `page_win_wr` |
| `src/mel/fft2048_sdf.v` | (1) stage0 改为 `prod = d + ((16384 − d) >>> 15)`；(2) 每级 `n_cnt` 预置 `(−(2^k + k − 1)) mod 2048`；(3) `samp_vld = beat_active`；(4) ST_RUN→ST_DRAIN 改在 beat 2047 的 phase-3 之后；(5) 删除 `out_cnt`/`out_done`；(6) bin 导出窗口改为 `run_cnt ∈ [2069, 3093]`、`bin_idx = run_cnt − 2069`、按 `ph2 == 3` 采样 |
| `build/tb_exp/tb_audio_win.sv`、`build/tb_exp/tb_fft_bins.sv`、`build/run_sim_exp.py`、`build/gen_golden_fft_frames.py`、`build/analyze_fft_map.py` | 实验资产（`build/` 是 gitignored，不进主线） |
| `reports/mel_audio_fix_conclusion.md` | 本报告 |

---

## 5. 未达成项与后续最小动作（按优先级）

1. **跑 `python build/run_sim_exp.py fft_bins`（约 15 s）并检查**
   `build/sim_mel/rtl_fft_beat.txt` 在 `run_cnt ∈ [2069, 3093]` 上是否
   `re/im` 各 1025/1025 等于 `build/sim_mel/golden/fft_frames.npy[frame]`。
   - 若全等 → 直接进第 2 步。
   - 若不等 → 用 `build/analyze_fft_map.py`（全窗口搜索）求出实际偏移，
     一次性定出 `BIN_FIRST_RUN`，**不要再逐个 ±1 猜**。
2. **确认"每帧 1025 个 bin 都是本帧的谱"**（已有一半证据）。
   SDF 是连续流结构，输出 `y[m]` 对应输入窗口 `[m−2057, m]`。本设计让每帧的
   2048 个样本重复两遍（ST_RUN + ST_DRAIN），直觉上 `y[2057+k]` 的窗口是
   `x[k .. 2047+k]`，即 `x` 的循环移位 —— 但**块内 `bitrev` 排列 + `n_cnt`
   按块重置**使这一直觉不成立：
   `build/` 里的 Python 模型（同一 `bitrev` 块重复两遍 + 上表的 10 个相位）
   已经在 `y[2057..3081]` 上对 golden 得到 **re 1025/1025、im 1025/1025 全等**，
   即"重复输入 + 正确相位"确实给出同一帧的完整自然序谱。
   ⇒ 剩下的问题只是 RTL 与这个模型的**实现细节对齐**（窗口常量、phase-3
   采样口径），不是架构不可行。
   若第 1 步仍不等，**不要逐个 ±1 猜偏移**：用 `build/analyze_fft_map.py`
   在整段 4096 beat 上做全窗口逐值搜索（必要时按 `bitrev` 重排再搜），
   一次性定出 `BIN_FIRST_RUN`。
3. `python scripts/check_rtl.py` + `python -m pytest -q`（基线 429 passed / 4 skipped）。
4. `python sim/run_sim.py mel,mel_credit`（mel 复现死锁语料、mel_credit 必须
   `feat bytes differ = 0`）。
5. 全部通过后，才值得在 PDS 里验证 §3.1 的两个 parser 风险点。

---

## 6. 环境异常（必须记录）

本会话在任务 B 的最后一轮验证之后，`bash` 工具**全部被环境拒绝**
（`run_sim_exp.py`、`check_rtl.py`、以及任何 python/grep 命令都返回
"The user rejected permission to use this specific tool call"）。
因此：

- 任务 A 的 PASS 是**在拒绝发生之前**跑出来的（日志见 §1.4）；
- 任务 B 的窗口常量 2069 是在拒绝发生**之后**用编辑工具改的，**没有复跑**；
- 三个闸门（check_rtl / pytest / run_sim mel,mel_credit）**没有在本会话内执行**。

复现命令（环境恢复后按序执行）：

```powershell
cd instrec_fpga
python build/run_sim_exp.py audio_win     # 任务 A：应为 PASS
python build/run_sim_exp.py fft_bins      # 任务 B：dump -> build/sim_mel/rtl_fft_beat.txt
python build/gen_golden_fft_frames.py     # 需要时重生成 golden 前 6 帧
python build/analyze_fft_map.py           # 全窗口搜索实际偏移
python scripts/check_rtl.py
python -m pytest -q
python sim/run_sim.py mel,mel_credit
```