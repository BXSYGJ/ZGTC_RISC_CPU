# Mel 引擎系统性收口报告（T35）

日期：2026-11-01　工程：`instrec_fpga/`　目标：`sim/run_sim.py mel_credit` 的 `feat` 16512 字节逐字节与 golden 相等

## 1. 结论摘要

- **`mismatch = 0`，`RESULT: PASS`**（`FEAT_SAMPLES 16512 mismatch 0`、`FIRST_MISMATCH none`）。
- 采用「golden 逐级对拍先定第一处分叉」的方法，共定位并修复 **3 个真实 RTL 缺陷** + **1 个 TB 统计口径缺陷**；
  其中两处缺陷（power 容器宽度、MAC 值对齐）都在 **mel_filter.v 内部**，第三处在同一模块的 COO offset 读地址上。
- T34 的两处改动经决定性实验判定：**power 求和扩宽是等价改写（已回退）**；**TB 的 DDR3 读应答器握手是必需修复（保留）**。
- 历史数字 16512 → 7472 → 10924 的「倒退」并非全部由 RTL 造成：`sim/tb_mel_engine.sv` 的 golden 表索引一直是
  mel-major，而 `sim/run_sim.py` 的 `prepare_mel()` 写出的表是 frame-major（`feat.T.reshape(-1)`），统计口径被放大到真实值的 ~17 倍
  （同一份 RTL：错误索引 4369 vs 正确索引 261）。

## 2. 逐级 mismatch 表（每级独立探针）

探针：`build/tb_exp/tb_mel_probe.sv`（在 `src/mel/mel_filter.v`、`stft_framer`、`fft2048_sdf`、`db_norm`、
`standardize` 的各级端口/内部节点上 dump），对拍器：`build/probe_mel_stages.py`，真值：`scripts/golden_pipeline.py`
（2026-11-01 复核：该脚本的 `feat` 与 `reports/golden_ref/sine_440_full/feat.npy` 0/16512 差异，真值同源）。

| 级 | 比对口径 | 样本数 | 修复前（起点） | 修 `sq_lo_sum` 宽度 | 修 MAC 值对齐 | 修 ch63 offset |
|---|---|---|---|---|---|---|
| feed | `pcm_feed_valid && pcm_feed_ready` 样本 vs golden `pcm[]` | 132096 | **0** | 0 | 0 | 0 |
| win | fft 实际消费的 `in_ready && in_valid` vs golden `windowed` | 24576（12 帧） | **0** | 0 | 0 | 0 |
| fft | `bin_valid` 的 `bin_idx/re/im` vs golden `fft` | 12300（12×1025） | **0** | 0 | 0 | 0 |
| power | `mel_filter.p_s48`（ph3 写 RAM 拍） vs golden `power` | 12288（12×1024） | **3219** | **0** | 0 | 0 |
| mel | `mel_filter.acc`（`l2_start` 拍） vs golden `mel_filter_coo` | 16576（259×64） | **16249** | 16249 | **259** | **0** |
| log2 | `mel_q88` vs golden `log2_fixed` | 16576 | **16083** | 16083 | 259 | **0** |
| db | `db_norm` B 口写值 vs golden `dbspec` | 16512 | **14582** | 3345 | 0※ | **0** |
| feat | `standardize` feat 写口 vs golden `feat` | 16512 | **13242** | 261 | 0 | **0** |

※ db 在「修 MAC / 未修 ch63」阶段为 0 是**假绿**：ch=63 的 log2 错成 −14336 与 golden 一起被 `top_db` 下限
`-20480` 钳位，dB 级看不见，说明 dB clamp 会掩盖上游缺陷（见 §6-R3）。

**第一处分叉的判定过程**：`feed/win/fft` 全等 ⇒ 起点不在 framer/FFT；`power` 3219/12288 错 ⇒ 第一处分叉在
`mel_filter` Stage A。修掉后 `mel` 仍 16249 错 ⇒ 第二处在 Stage B。修掉后仅剩 ch=63 ⇒ 第三处在 Stage B 的
offset 读地址。逐级数字单调下降，无任何一次修改让 mismatch 变大。

## 3. 本次修复的三个 RTL 缺陷（均在 `src/mel/mel_filter.v`）

### D-35-1　`sq_lo_sum` 的 19 位**有符号**容器溢出（Stage A / power）

```verilog
wire signed [18:0] sq_lo_sum = sq_lo_re_r + sq_lo_im_r;   // 旧
wire signed [19:0] sq_lo_sum = sq_lo_re_r + sq_lo_im_r;   // 新
```

`lo^2` 对和上界 = `2*(2^9-1)^2 = 522242`，需要 20 位**无符号**；19 位有符号只到 `2^18-1 = 262143`。
溢出为负后：`pwr_rnd < 0` ⇒ `pwr_rnd[53:10]` 全 1 ⇒ `p = 2^44-1`。

golden 证据（修复前 power 级 12288 个受检 bin 的 diff 只有三种取值）：

| diff（golden − RTL） | 个数 | 物理含义 |
|---|---|---|
| 0 | 9069 | `lo^2` 和未溢出 |
| 512 | 730 | 溢出量 = `2^19`，在 `>>10` 域正好差 512 |
| −2^44 | 2489 | `pwr_sum_s < -512`，44 位窗口被全 1 饱和（典型点：golden p = 511，RTL = 2^44−1） |

修复后该级 `12288/12288` 全等。

### D-35-2　MAC 的 power 读数比 COO 权重重一拍（Stage B / mel）

power RAM 是**同步读**（`pwr_q <= pwr_ram[ram_ra]`），而流水在 F1 拍就把 `pwr_q` 锁进 `q_p`：F1 拍 RAM 的
读数据要到 F2 拍才到，于是每个 entry 的权重乘的是**前一个 entry 的 bin 功率**。修复为 6 级流水
（F1 锁 `q_w` → F2 的 `pwr_q` 合法后锁 `q_p/q_w_d` → F3 APM+CLB → F4 combine → F5 accumulate），
`ST_FLUSH` 的 5 拍窗口与 `flush_clear` 落点保持不变（最后一个 entry 的 F2..F5 落在 fl_cnt 0..3，
fl_cnt==4 是 clear 拍，无 `f5_v` 冲突）。

golden 证据（修复前，用 golden power + COO 表反推 RTL 的累加模型）：

```
model[i] = power[bin(i-1)] * w(i)   (i 越段时取上一通道最后 entry 的 bin)
16561/16576 与 RTL 的 acc 逐值相等（残差 515，来自段首/冷启动项）
正确模型 power[bin(i)] * w(i) 仅 327/16576 命中
```

即 RTL 的累加值 96.9% 可以用「bin 索引 −1」精确复现，因此错位方向确定不是猜测。修复后该级
（其余缺陷已修的前提下）只剩 ch=63 的 259 个失配。

### D-35-3　COO offset 读地址 `ch + 6'd1` 的 6 位溢出（Stage B / ch63）

```verilog
{5'b0, roff_ph == 2'd0 ? ch : ch + 6'd1}   // 旧：ch=63 时 63+1 截断成 0
wire [6:0] rom_ch = {1'b0, ch} + ((roff_ph == 2'd0) ? 7'd0 : 7'd1);  // 新
```

`ch=63` 时第二个 offset 读成 `offsets[0] = 0`，于是 `e_idx(=offsets[63]=1841) >= off_hi(=0)`，该通道
**一个 MAC 项都不发**，`acc = 0`，`log2(0) = -14336`，每帧 1 个通道（×259 帧 = 259 个失配）。

golden 证据：`mac` 级全 259 个失配都在 `ch == 63`，RTL acc = 0 而 golden = 1587683（frame 0）；
`mel_coo.hex` 的 `offsets[63..64] = 1841, 1960`，语义上不可能为空段。

## 4. T34 两处改动的去留判定

### 4.1 `mel_filter.v` 的 power 三项「先符号扩展到 54 位再移位」→ **回退**

决定性实验：保持 `sq_lo_sum` 宽度修复与全部其他修复不变，只把求和改回

```verilog
wire signed [53:0] pwr_sum_s = (sq_hi_sum <<< 18) + (cross_sum <<< 10) + sq_lo_sum;
```

结果 **power 12288/12288 全等、mel/log2/db/feat 全 0**，与「先扩展到 s54」版本**逐位相同**。

原理：Verilog 的移位表达式在加法（上下文决定宽度）中，左操作数先被扩展到**赋值上下文宽度**（这里是
54 位和容器），并非取操作数自身宽度。所以 T34 注释里的「self-determined width 截断高位」论断不成立，
该改动是 no-op。按「无 golden 证据支持即回退」的纪律已回退，并删除三个 `*_ext` wire。

### 4.2 `sim/tb_mel_engine.sv` 的 DDR3 读应答器握手 → **保留**

golden 证据：在 `pcm_feed_valid && pcm_feed_ready` 上逐样本抓取喂入 `stft_framer` 的序列，
**132096/132096 与 golden `pcm[0..132095]` 逐值相等**（`feed` 级 0 bad）；同时
`rd_cmds = 516 = 132096/256`、`rd_beats = 8256 = 516×16`、`addr_err = 0`。

即「每命令 16 beat、beat 保持到 `m2_rd_ready`」的握手是**正确的**，旧版每命令只取 1 beat 会把 PCM 打乱。
另外 `win` 级（framer → fft 的 2048 样本）也全等，说明 T34 的握手改动没有引入帧级偏移。

## 5. 已有多轮修复的有效性复核（本次未改，仅验证）

| 既有修复 | 本次证据 |
|---|---|
| `FILL_CREDIT 1025 → 1280` | `mel_credit`：`cmds=2580`、`rd_cmds=516`、`accepted=132096`、`frames=259`、`timeout=0`，无死锁 |
| `stft_framer` 的 18 位 `132095` 与 `out_ready` 门控 | `win` 级 24576 值全等（含首/末帧反射），fft 每帧 1025 bin 连续 0..1024 |
| `fft2048_sdf` 的 stage0 / `n_cnt` 相位 / `BIN_FIRST_RUN` | `fft` 级 12 帧 × 1025 bin 的 re/im 逐值全等 |
| `db_norm` 的 `DB_NUM_S [10:0]` | `db` 级 16512 值全等（含 `-20480` 下限路径） |
| `audio_sink` 的 18 位 `WIN_FRAMES` | 本 TB 直驱 mel_engine，未覆盖该模块（T31 证据仍有效，本次不复测） |

## 6. 已知偏差与未修项（按纪律只报告）

- **R1（偏差）** `mel_filter` 每帧只计算 1024 个 bin 的功率，**bin 0 丢失**：`ST_IDLE` 拍 `bin_valid`
  只用来跳 `ST_PWR`，而功率流水启动条件是 `pwr_active && bin_valid`，第一拍 `pwr_active=0`。
  实测 `pwr` dump 每帧 1024 个、bin 序列 1..1024。COO 表只引用 bin 1..1022，**当前无语义影响**；
  若将来表引用 bin 0 需修（建议 `ST_IDLE` 分支同时激活功率流水）。
- **R2（观察）** `stft_framer` 的 `win_valid` 在帧间悬空：`out_run=0` 时该寄存器不再重载，
  因而帧间一直为高（dump 可见同帧号重复数十万拍）。`fft2048_sdf` 只在 `ST_LOAD` 采样
  `in_ready && in_valid`，实测 `win` 级全等，**功能无影响**，属时序卫生问题。
- **R3（风险）** dB 的 `top_db` 下限会掩盖 log2 缺陷：ch=63 的 `-14336` 与 golden 一起被钳到 `-20480`，
  使 `db`/`feat` 在 ch63 仍为 0 失配。今后回归请以 `mel`/`log2` 级而非 `feat` 为第一判据。
- **R4（口径）** 历史 mismatch 数字（16512 / 7472 / 10924）都来自错误的 golden 表索引，
  **不可与新数字直接比较**；已修 TB（`gold_feat[idx]`，与 `prepare_mel()` 的 `feat.T.reshape(-1)` 一致）。
- **R5（未做）** 未烧板、未跑 PDS 构建（按 T35 纪律），本结论仅为 **RTL 级证明**，不是 board-proven。
- **R6（TB 观察）** 应答器对 `m2_cmd_valid` 电平重复应答写命令：`wr_cmds = 2064 = 2 × 1032`
  （`m2_done` 撤下之前该 valid 仍为高，R_IDLE 会再收一次同一命令）。读命令不受影响
  （`rd_cmds = 516` 精确）；`mel_engine` 只在 `EX_CMD` 响应 `m2_done`，重复脉冲落在 `EX_READ`
  被忽略，故 `feat` 0 失配。真实 DDR3 控制器不会有此行为，属 TB 侧卫生问题。

## 7. 复现命令

```powershell
# 主判据（约 25~32 s）
python sim/run_sim.py mel_credit --verbose

# 逐级对拍（约 25 s + 30 s）
python build/run_sim_exp.py mel_probe --verbose
python build/probe_mel_stages.py

# 词法 / 回归
python scripts/check_rtl.py          # 51 files, 0 violation
python -m pytest -q                  # 429 passed, 4 skipped
```

关键日志：

```
MEL_CREDIT cmds=2580 accepted=132096 frames=259 wr_cmds=2064 timeout=0 done=1 cycles=5094395
MEL_DONE mel_cycles=5094387 feat_page=1
FEAT_SAMPLES 16512 mismatch 0
FIRST_MISMATCH none
RESULT: PASS tb_mel_engine
```

逐级终态：`feed/win/fft/power/mel/log2/db/feat` 均为 **0 bad**。

## 8. 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `src/mel/mel_filter.v` | 产品 RTL | D-35-1（`sq_lo_sum` s19→s20）、D-35-2（Stage B 6 级流水）、D-35-3（offset 地址 7 位）；回退 T34 的等价扩宽 |
| `sim/tb_mel_engine.sv` | 仿真 TB | 修正 golden 表索引（mel-major → frame-major） |
| `reports/mel_final_closure.md` | 文档 | 本报告 |
| `build/tb_exp/tb_mel_probe.sv`、`build/probe_mel_stages.py`、`build/run_sim_exp.py` | 实验资产（`build/` 已 gitignore） | 逐级探针与对拍器 |

未改：`src/mel/standardize.v`（排查后确认无缺陷）、`stft_framer.v`、`fft2048_sdf.v`、`db_norm.v`、`mel_engine.v`
（按纪律只报告不改；`mel_engine.v` 现有的 `FILL_CREDIT=1280` 正确）。