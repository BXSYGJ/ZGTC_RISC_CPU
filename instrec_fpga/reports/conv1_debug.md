# conv1 数值失配根因定位（T24）

> 定位对象：`build/top_npu_conv1_test-latest.sbit`（T22 conv1 单层 BRAM 验证位流）2026-10-31 板级抓取
> `build/uart_last.bin` → `reports/conv1_compare.json`
> 结论分级：**板上证据 / 静态证据 / 未证实** 三类，未证实的绝不写成结论。
> 本报告**未改动任何产品 RTL / 约束 / 构建脚本**，只产出诊断与修复方案。

---

## 0. 一句话结论

**错在「参数」——不是数据、不是权重、不是映射。**

`top_npu_conv1_test.v:230-231` 的 `ctr_base` 把 layer_contract 的**三段式布局**（48 bias / 48 M / 48 shift，每组各取连续 16 字）当成了**每组 48 字连续窗口**，于是每组送进 `conv_engine` 的 `(bias, M, shift)` 至少两项是错的；且 `ctr_base` 只有 **6 位**，`6'd96` 在 Verilog 里截断为 **32**，grp2 三段全部错位。板上的 `{0, 1, 2, 8, 255}` 值域、99.5% 落在 `{0,1,255}`、以及"每个通道在列方向完全恒定"这三件事，都是"`shift` 被送成一个随机 7 位值（1..125）"的直接后果。

另有两个**静态确定**、但与该 bug 叠加才会出现的缺陷（bank 覆盖、捕获读回错拍），以及**一个未闭合项**（第 5 节），下一轮 board 必须补测。

---

## 1. 板级证据基线

| 项 | 实测 | 判读 |
|---|---|---|
| `stream_samples` | **792,576** | = 64×3×258×16，egress 一拍不差，扫描/流水/done 全部正常 |
| `done_flag` / `sample_count` | 1 / **3072** | 状态帧与捕获口径自洽 |
| `missing_data_indices` | **[]** | 128 个数据帧齐全，串口无丢字节 |
| 6 窗口 mismatch | 389 / 503 / 332 / 473 / 390 / 384（各 512） | **全部窗口都错**，不是边界问题 |
| `expected_sum` / `observed_sum`（帧重组） | 26,685 / **184,223** | 观测均值 60 vs 期望 8.7 |
| RTL 自算 `sample_sum` | **184,269** | 与重组差 **46**（见假设 5） |
| 观测值集（全 3072） | `{0:1329, 1:902, 2:4, 8:94, 11:1, 33:30, 255:712}` | **99.5% 落在 `{0,1,255}`** |

### 1.1 两条"形态"证据（最强）

**(a) 观测值与「列」无关。** `win0 = row0/grp0/col0..31`、`win4 = row63/grp0/col0..31`，两者从 col 4 / col 2 起，**每个通道只有一个取值**（16/16 通道列不变）：

```
win0 col4..31 : [  0,  0,  0,  1,  0,  1,  0,  1,  0,  0,  0,  1,  0,  0,  1,  0]
win4 col2..31 : [  1,  0,  0,  0,255,  1,  0,  0,  0,  0,  0,  0,  0,  0,  1,  0]
golden col4..31: [  0,  0, 15,  0,  0, 25, 17,  0,  7,  0, 13, 14, 15, 13,  0,  2]
```

**(b) golden 也在同样位置列不变**（`conv1[ch,0,4:32].std()==0`，`conv1[ch,63,2:32].std()==0`）。
→ 所以「列不变」是**梅尔特征图在 padding 边界本来就平坦**这一数据属性，**不能**当成数据通路 bug 来解读。这条在本轮曾一度误导判断方向，特此写明，避免后人重复踩坑。

**(c) 行间不同。** 同一通道在 row0 与 row63 的稳定值不同（ch0: 0 vs 1；ch4: 0 vs **255**）。结合 (a)，说明 **acc 的均值随行变化，但列方向的变化被 requant 压平**——这正是"`shift` 过大 / 饱和"的特征。

---

## 2. 七个假设逐项

### 假设 1：权重分组错位（D-05 遗留）→ **排除**（但发现同源缺陷 P1）

**静态核对（`top_npu_conv1_test.v`）**
- `S_START`（L310-318）：`start0` 与 `job_grp<=0`、`gt_launch<=1` **同一拍**置位；
- job 引擎（L374-400）：`gt_step==GT_IDLE && gt_launch` 时**同一拍**消费 launch 并把 `c_step<=0`，所以 `ctr_addr` 第一次就用新 `job_grp` 的基址；T22 自述的"`job_grp` 比 `gt_step` 晚一拍"在源码里已经用"launch 与 job_grp 同拍更新"消除。
- boot 顺序（L320-335）：job0 → grp0 写入 **active**（`grp_arm==0`），job1 → grp1 写入 **shadow**（`grp_arm==1`，`conv_engine.v:761-779`）。`any_start` 清 `grp_arm` 发生在 `start0` 拍，早于第一次 `bias_valid`（L417-420 的组合 `grp_start` 只在 GT_CTR/c_step==0 那一拍为 1）。→ **第一组权重确实是 grp0，没有被跳过。**

**数值核对**：用 grp1 / grp2 的 27 个 tap 在 `row0/col0` 重算 acc，与 observed `[2,2,255,1,0,1,0,1,0,1,255,1,255,1,0,0]` 无一条吻合；且若权重整组错位，输出仍**随列变化**（tap 的 x 随列变），而板上列不变。→ 排除。

**但同一段代码有真缺陷（P1，静态确定）**：`tap_bank` 只有两个（L225-228），`use_grp[0]` 选 bank（L239-244），写入用 `job_grp[0]`（L406-408）。于是 **grp0 与 grp2 共用 `tap_bank0`**：grp2 扫描期间，为下一行 grp0 准备的 job 正在把 `tap_bank0[0..8]` 逐个覆盖（job 86 拍 vs grp2 单组扫描 4386 拍，覆盖发生在 grp2 的**前 ~5 个像素**内）。这会让每行 grp2 的前几个像素读到混合的 tap。**它与本次窗口 0/4（都是 grp0）无关，但必须一起修。**

### 假设 2：requant 参数（M/shift/zp_out）加载错位 → **支持：唯一根因（P0，静态 + 板上形态双重证据）**

**契约布局（`scripts/outputs/layer_contract.json` + `hex_conv1/conv1_ctr.hex`）**

```
ctr_rom[  0.. 47] = bias[0..47]      (int32, 例: -287, -257, -137, ...)
ctr_rom[ 48.. 95] = M[0..47]         (Q0.31, 例: 0x6910416E, 0x467C13C1, ...)
ctr_rom[ 96..143] = shift[0..47]     (uint8, conv1 实测 37..41)
```

`tests/test_conv1_debug_vectors.py::test_hex_contract_table_layout` 断言 hex 与契约**逐字相等**（bias/M/shift 三段全部通过，M ∈ [2^30,2^31)，shift ∈ [37,41]）。→ **hex 表本身正确，问题在 RTL 的读地址。**

**RTL 实际读到的（`top_npu_conv1_test.v:230-231` + L382）**

```verilog
wire [5:0] ctr_base = (job_grp == 2'd0) ? 6'd0 : (job_grp == 2'd1) ? 6'd48 : 6'd96;
...
if (c_step < 6'd48) ctr_addr <= {2'd0, ctr_base} + {2'd0, c_step};
```

`c_step` 0..48（L380-389），`c_bias` 1..16、`c_mult` 17..32、`c_shft` 33..48（L248-250），`cload_idx = cload_cnt[3:0]`（`conv_engine.v:741`）。按这个走法，每个 job 读的是 **`ctr_rom[ctr_base + 0 .. ctr_base + 47]` 一段连续 48 字**：

| 组 | `ctr_base` | 送进 `bias_act` | 送进 `m_act` | 送进 `shft_act` |
|---|---|---|---|---|
| grp0 | 0 | `bias[0..15]` ✅ | **`bias[16..31]`** ❌ | **`bias[32..47] & 0x7F`** ❌ |
| grp1 | 48 | **`M[0..15]`**（≈1.7e9）❌ | `M[16..31]` ✅ | **`M[32..47] & 0x7F`** ❌ |
| grp2 | **32**（`6'd96` 在 6 位内截断）| **`bias[32..47]`** ❌ | **`M[0..15]`** ❌ | **`M[16..31] & 0x7F`** ❌ |

断言（`test_rtl_group0_m_and_shift_come_from_the_bias_block`）：
`rtl[0].bias == contract[0].bias` 为真（**唯一碰巧对的一段**），
`rtl[0].m == ctr[16..31] == bias[16..31]` 为真，
`rtl[0].shift == [15,9,87,27,73,110,118,80,125,2,95,1,74,39,70,103]`，**最小 1、最大 125，完全落在契约 [39,41] 之外**。

**为什么这就解释了 board 的形态**

`requant_unit.v:135-159` 的 `shift_q` 是 7 位。`shift>=64` 时 64 位算术右移饱和为 0 / -1、`rem_mask` 变全 1、`half` 变 0，于是

```
prod > 0  -> y = 1        (恒定)
prod < 0  -> y = 0        (恒定)
prod == 0 -> y = 0
```

`shift` 在 1..38 时，`|acc*M|` 被压到 0 附近，同样塌成 0/1；只有 `shift` 很小且 `acc*M` 很大时才饱和到 **255**（`requant_unit.v:165-172`）。这与板上 `{0,1,2,8,255}`、99.5% 为 `{0,1,255}`、列方向恒定、行间偶发翻转**逐条吻合**。定量对照（模型，见 `build/conv1_trace.py`）：

| 模型 | 在 `win0+win4` 稳定段（928 样本）的 mismatch |
|---|---|
| golden（按契约正确参数） | **696** |
| contract 布局（同样正确） | 696 |
| **rtl（按上面错位表）** | **548** |

→ 换成 RTL 的错参数，匹配度**明显上升**（`test_rtl_parameter_mapping_beats_the_golden_but_does_not_close` 断言 `rtl_miss < golden_miss`）。方向上确认为"参数错"。

**zp_out**：`top_npu_conv1_test.v:281` 置 0，契约 `layers[0].zp_out = 0`，`cfg_valid` 在 `S_CFG` 单拍有效（L301-303），`conv_engine.v:481-489` 锁存 → **zp_out 正确，不是问题**。

**"rom_arg 24 位左移"**：本顶层**不存在**该逻辑（`ctr_dout` 直接进 `bias_s32/m_s32/shift_w`，L416-424），该描述属于 `wdma` 的权重/参数 DMA 路径，**与本 conv1 验证位流无关**，本轮不适用。

### 假设 3：16-lane TDM 的 lane → channel 映射 → **排除**

`permutation_match`：192 个捕获像素里，**0 个**像素的 16 个观测值是 golden 的置换（`test_observed_is_not_a_permutation_of_the_golden`）。
更强的证据：观测值域 `{0,1,2,8,11,33,255}` 与 golden 的典型值（如 ch14 的 **247**、ch7 的 **71**）**不相交**，任何置换都产生不出这些数。
静态上 `acc_snap[rhe_ch]` 与 `w_data_q2[8*g +: 8]` 的 lane 序号一一对应（`conv_engine.v:1080-1082`、`:922`），lane 顺序没有反接。

### 假设 4：ingress feat 顺序 / padding → **排除**

- `conv1_feat.hex` 与 `feat.npy` 展平**逐字节相等**（`test_feat_hex_is_the_golden_map`），即 ROM 的 `row*258+col` 排布正确；
- `conv_engine.v:642-661` 的读地址是 `cin_cnt*W + (out_col+dx-1)`，`g0_wr_addr = g0_ch*W + g0_col`（L505-516），写入与读出的行列语义一致；
- padding：RTL 在**读侧**把窗口外的 tap 强制 `x_eff = 0`（`conv_engine.v:911-912`），而 golden 的 `padded` 在 signed 域填 0（`golden_pipeline.py:753-754`，`x_u8 - zp_in`）。**两者等价**，不存在"用 49 直接进 int8 累加"的偏置。
- 反证：若 feat 顺序错，board 的输出必然**随列变化**（相邻列的 x 不同），但板上列恒定（且 golden 也恒定）——顺序错的假设无法解释这个形态。

### 假设 5：`sample_sum` 与重组差 46 → **支持：捕获读回错一拍（P2，静态确定）**

`top_npu_conv1_test.v:650-657`：

```verilog
if (ro_i < 5'd24) cap_rd_addr <= ro_base + {7'd0, ro_i};
if (ro_i != 5'd0) dsb[ro_i - 5'd1] <= cap_dout;      // cap_dout 是寄存器输出
...
cap_dout <= cap_ram[cap_rd_addr];                     // L586
```

`cap_rd_addr` 与 `cap_dout` **同一时钟沿更新**，所以 `dsb[0]` 在 `ro_i==1` 那一拍拿到的是**上一帧最后一个地址**的内容，而不是 `cap[ro_base+0]`。精确结论：

```
dsb[0]   = cap[base-1]        (首帧为 cap[0], 复位残留)
dsb[i]   = cap[base+i-1]  i=1..23     -> 每帧丢尾样本、重复前驱样本
```

于是 `observed_sum = cap_sum - cap[3071] + cap[0]`，与实测 `184269 - 184223 = 46` 自洽：
`cap[3071] = obs[1] + 46 = 2 + 46 = 48`，是一个合法的 u8 值（`test_readout_pipeline_drops_one_sample_per_frame`）。

**旁证**：`win0` 的 col4..31 完全恒定，所以这 1 个错拍读到的邻样本恰好同值，形态上看不出来——只有在 24 样本帧边界、且相邻值不同处才暴露为 sum 差。这也解释了为什么 `missing_data_indices == []` 却仍有 46 的口径差：**丢的不是串口字节，是帧内第 24 个样本**。

### 假设 6：捕获窗口相位（`y_valid` 与 `y_u8` 不同拍）→ **排除（写入侧）；读回侧见假设 5**

- `cap_wr = y_valid && in_window && cap_wp <= CAP_LAST`，`cap_sum += y_u8`，`cap_ram[cap_wp] <= y_u8` 全部在**同一拍同一表达式**（L561-587）——`y_valid` 与 `y_u8` 在 `conv_engine.v:1086-1087` 是**同源同拍**（都来自 `requant_unit` 的 `out_valid`/`y_u8`，`requant_unit.v:209-211` 同一 always 块），不存在相邻拍错配。
- `stream_samples == 792,576` 精确等于理论值 ⇒ `y_cnt` 与 `cap_wp` 的窗口比较、`in_window` 的 5 个 `WIN_BASE_*` 全部正确。
- 唯一缺陷在读回侧（假设 5）。

### 假设 7：round-half-even 与 clip → **排除（量级不符）**

`requant_unit.v:135-159` 的实现是标准 half-even（`rem>half | (rem==half & q0[0])`，符号对称）。
`test_round_half_even_vs_truncation_is_at_most_one_lsb` 断言：对 shift ∈ {1,7,12,41}，half-even 与截断的差 **≤ 1 LSB**。
而板上出现 `expected 4 -> observed 2`、`0 -> 255` 这种量级差异（还有 247 消失、33/8 冒出），**不是 1 LSB 能产生的**。→ 排除。

---

## 3. 唯一根因判断

| 排序 | 缺陷 | 证据强度 | 影响面 |
|---|---|---|---|
| **P0（根因）** | `ctr_base` 三段式布局错读 + `6'd96` 截断 | **静态确定 + 板上形态吻合 + 模型匹配度上升** | 全部 48 通道、全部 6 窗口 |
| P1 | `tap_bank0` 被 grp0/grp2 共用 | 静态确定 | 每行 grp2 前 ~5 像素（本次窗口未能覆盖） |
| P2 | egress 捕获读回错一拍 | 静态确定 + sum 差 46 数值自洽 | 每 24 样本丢 1 个（帧内） |
| P3 | （未证实）acc 与 Python 模型仍有偏差 | 穷举反证，见第 5 节 | 未知 |

**一句话答复**：conv1 数值错在 **参数**（requant 的 M/shift 加载错位），不是数据、不是权重、不是映射。

---

## 4. 最小修复方案（**不改产品 RTL，交团队另行派工**）

### P0 — `src/diag/top_npu_conv1_test.v`

**第 230-231 行**（删除 `ctr_base`，改为三段基址 + 分段索引；同时消除 6 位截断）：

```verilog
// group offset = job_grp * 16, kept at full 8-bit width (0/16/32)
wire [7:0] ctr_grp_off = {job_grp, 4'b0000};

// c_step 0 is the grp_start beat (no valid strobe); 1..16 bias, 17..32 M,
// 33..48 shift.  The three blocks are NOT adjacent in the contract.
wire [7:0] ctr_addr_n = (c_step == 6'd0)  ? (ctr_grp_off)
                      : (c_step <= 6'd16) ? (8'd0  + ctr_grp_off + (c_step - 8'd1))
                      : (c_step <= 6'd32) ? (8'd48 + ctr_grp_off + (c_step - 8'd17))
                                          : (8'd96 + ctr_grp_off + (c_step - 8'd33));
```

**第 382 行**：`ctr_addr <= {2'd0, ctr_base} + {2'd0, c_step};` → `ctr_addr <= ctr_addr_n;`
其余（`c_bias/c_mult/c_shft` 的区间、`cload_idx` 的 `cload_cnt[3:0]`）**均不变**，与 `conv_engine.v:741-793` 的 48 拍协议完全兼容。

> 校验：`ctr_addr_n` 对 grp0/1/2 分别覆盖 `0..15 / 48..63 / 96..111`（bias）、`48..63 / 64..79 / 112..127`（M）、`96..111 / 112..127 / 128..143`（shift），最大 143，不越界。

### P1 — `src/diag/top_npu_conv1_test.v`

**第 225-228 行**：`tap_bank0/1` → 三个 bank（`reg [127:0] tap_bank2 [0:8];`）。
**第 239-244 行**：`w_tap_word = tap_bank_sel[use_grp]`（`use_grp` 0/1/2 直接选）。
**第 406-408 行**：`tap_bank_sel[job_grp] <= acc_next`。
→ 每组独占一个 bank，预取不再覆盖正在扫描的组。

### P2 — `src/diag/top_npu_conv1_test.v`

**第 650-657 行**（`S_REPORT` 期间 `cap_wr` 已停，`cap_ram` 可安全组合读）：

```verilog
if (ro_i < 5'd25) begin
    if (ro_i < 5'd24)
        dsb[ro_i[4:0]] <= cap_ram[ro_base + ro_i];   // combinational read
    ro_i <= ro_i + 5'd1;
end
```

`cap_rd_addr` / `cap_dout` 两条路径在 report 之后可以删除或保留为空闲。

### 不变量（修完必须仍然成立）
- `bias_valid/mult_valid/shft_valid` 每拍**恰好一个**（`conv_engine.v:192-206` 的协议）；
- `grp_start` 独占 `c_step==0` 一拍（L417）；
- contract 装载仍在 `start0` 之后（L306-318 的注释约束）；
- `w_valid` 在 preload 窗口拉低（L429），否则 `tap_cnt` 会与 job 抢 bank。

---

## 5. 未闭合项（**未证实，禁止当结论用**）

我把 bias / M / shift 的"来源 16 字块"在 `ctr_rom` 的 9 个块上做了 **9³ = 729 组合穷举**（每通道同时约束 `win0` 的 28 个像素与 `win4` 的 30 个像素），目标 mismatch：

```
best 260 / 928  (bias_blk=0, M_blk∈{0,1,2,6,7}, shift_blk∈{6,7,8})
```

**没有任何一种"连续 16 字块"映射能把 board 解释到 0**，而契约布局（bias_blk=0, M_blk=3, shift_blk=6）本身给出 696/928。这说明：**除了 P0 之外，RTL 的 acc 与我 Python 模型算出的 acc 之间还有差异**（可能是 P1、也可能是 line-buffer/ingress 时序），但**目前没有板上证据能把它单独指认出来**。

→ 因此本条记为 **未证实**。下一轮必须按下面的最小验证动作取证，不能仅凭"改完 P0 就好了"就宣布收敛。

### 下一轮最小验证动作（按序，失败即停）
1. **只改 P0 与 P1**，重跑 `conv1_test` 构建（不碰 full / DDR3 集），板级抓 3072 样本；
2. 预期：`mismatch` 从 2471 显著下降；若降到 0 → P0+P1 即为完整根因；
3. 若仍非 0，在诊断顶层加**一个 16×32bit 的 acc 转储**（在 `out_row==0 && out_col==4 && grp_cnt==0` 的 `snapshot_go` 拍把 `acc_snap[0..15]` 打到 `cap_ram` 尾部），与 `build/conv1_trace.py --model contract --row 0 --col 4` 的 acc 对照——这是**唯一**能把"参数错"与"acc 错"分开的实验；
4. 再跑 P2 的 readout 修复，确认 `sample_sum == observed_sum`（不再差 46）。

---

## 6. 复现与文件

```powershell
# 离线 scoreboard（读 hex + golden + 归档观测）
python build/conv1_trace.py --check

# 逐点对照表
python build/conv1_trace.py --model rtl     --row 0 --col 4
python build/conv1_trace.py --model contract --row 0 --col 4

# 断言
python -m pytest tests/test_conv1_debug_vectors.py -q      # 17 passed
python -m pytest -q                                          # 429 passed, 4 skipped
```

| 文件 | SHA-256 |
|---|---|
| `build/conv1_trace.py` | `b30026f0281f2b94f6d36641a034d6322334e518689d9fdae2fb6412064b6fcf` |
| `tests/test_conv1_debug_vectors.py` | `db9ff9a58b5b7138323eb8410037ac77acd6d00b80f86b5ecebb630bc185087a` |

> `build/uart_last.bin` 在 2026-10-31 22:57 被另一个板级任务覆盖（现在只剩 2 个 DDR3DIAG 帧），所以 `win0/win4` 的 **32×16 观测矩阵已固化进测试与 trace 脚本**；`reports/conv1_compare.json`（22:43）仍完整，测试 `test_compare_json_is_consistent_with_the_archive` 会校验两者不漂移。

---

## 7. 风险与偏差

| 编号 | 描述 | 处置 |
|---|---|---|
| R-1 | 归档观测只含 grp0 的 win0/win4，P1（grp2 bank 覆盖）**本次板级未被覆盖** | P1 为纯静态结论，修完必须补测 grp2 窗口（win2/win5） |
| R-2 | `shift>=64` 的 Verilog 语义在 PDS 综合后的实际行为**未经板级验证**（我按 IEEE 1364"填符号位"建模） | 第 5 节步骤 3 的 acc 转储可同时证伪该假设 |
| D-1 | 729 组合穷举无法复现 board | 已显式标注**未证实**，不并入根因 |
| D-2 | `build/uart_last.bin` 被后续任务覆盖 | 观测固化进测试，并保留 `conv1_compare.json` 校验 |

**边界声明**：本报告未改动 `src/npu/*.v`、`src/diag/top_npu_conv1_test.v`、`scripts/compare_conv1.py`、`scripts/build_sets.json`、任何 `.fdc/.tcl/.ps1`；未烧板、未跑 PDS、未碰 `cdt_js`/`pds_shell`、未 commit/push。