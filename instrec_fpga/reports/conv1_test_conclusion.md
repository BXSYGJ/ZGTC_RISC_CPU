# T22 conv1 单层 BRAM 验证位流 —— 构建与板级结论

- 任务：T22（团队任务 id=22）
- 工程：`instrec_fpga/`，分支 `XSY`
- 日期：2026-10-31
- 状态：**位流前全部就绪（静态验证完成）；真实构建与上板判读未执行**（由 team leader 另行排构建槽）
- 结论口径：本文件只写有证据的部分。凡未在本机实际跑过的（PDS 真实综合/布局布线、板上串口实测）都显式标注为 **未构建 / 未 board-proven**。

---

## 1. 一句话结论

**这份位流上板后能回答「conv1 计算是否正确」。**
判据是三个同时成立的条件：

1. 串口收到至少 131 帧 91 字节 C-DIAG-UART@1 帧，其中 `frame_tag=2` 且 `A=434F4E31`（"CON1"）的状态帧可解；
2. 状态帧 `E = 0x0C1800`（= 792576，完整 egress 流计数）且 `C = 0x00000C00`（= 3072，采样窗口数）；
3. 128 个 `frame_tag=3` 数据帧按 `G|H<<8` 重组出的 3072 个 u8 值，与
   `reports/golden_ref/sine_440_full/conv1.npy` 的同一采样集合**逐字节 0 失配**。

三者任一不满足 → 判为「未证实」，并按 `per_window` / `first_mismatch` 的
`(row, group, col, channel)` 反解定位。

说明：本条只回答 conv1 单层的计算通路（MAC + requant + 扫描 + 行缓冲 + 权重/contract 装载）。
不覆盖 pool/gap/fc/softmax，不覆盖 wdma 与 DDR3 权重搬运，不覆盖多层流水重叠。

---

## 2. 交付文件

| 文件 | 行数 | 字节 | SHA-256 (前 16) |
|---|---|---|---|
| `src/diag/top_npu_conv1_test.v` | 758 | 32677 | `4a2e1a21c688bab3` |
| `constraints/top_npu_conv1_test.fdc` | 116 | 5500 | `c613e0e8972a57f2` |
| `scripts/compare_conv1.py` | 502 | 20742 | `af532fd0ddca0715` |
| `scripts/build_sets.json` | 87 | 2046 | `edaaafa712dc62e3` |
| `hex_conv1/conv1_w32.hex` | 108 | 972 | `6a0b1ef2e282c9e2` |
| `hex_conv1/conv1_ctr.hex` | 144 | 1296 | `ad87639ca587a487` |
| `hex_conv1/conv1_feat.hex` | 16512 | 49536 | `cc8308817a789991` |
| `reports/conv1_test_conclusion.md` | 本文件 | — | — |

### 2.1 `scripts/build_sets.json` 新增 set（原文）

```json
"conv1_test": {
  "top_module": "top_npu_conv1_test",
  "sources": [
    "src/npu/conv_engine.v",
    "src/npu/requant_unit.v",
    "src/ctrl/uart_tx.v",
    "src/diag/diag_uart_report.v",
    "src/diag/top_npu_conv1_test.v"
  ],
  "ip_cores": [],
  "constraints": [
    "constraints/top_npu_conv1_test.fdc"
  ],
  "hex_dirs": [
    "hex_conv1"
  ]
}
```

`full` / `ddr3_diag` / `ui_demo` 三套内容一字未动（`git diff scripts/build_sets.json` 只有新增块）。
`conv1_test` 故意不装 DDR3 IP、不装任何 PLL：

- 无 `ddr3_test.idf` → 无 `ddr3_wrapper` / `mem_*` / `ref_clk_p/n`
- 无 `pll.idf` → 单一 27 MHz 时钟域，无生成时钟、无 CDC
- 约束只装 `top_npu_conv1_test.fdc`（**不装** `ddr3_100h.fdc`；装它会引用未定义的 `ref_clk_p`/`mem_*` 与 `ddr3_wrapper` 层级）

---

## 3. 设计说明

### 3.1 时钟与周期预算

- 时钟：**27 MHz 板载时钟（D18）直连全设计**，不使用 PLL。
  核算：conv1 全尺寸（1×64×258 → 48×64×258）总 MAC = 48·64·258·9 = **7,133,184**；
  16 lane 并行 → 理论下限 445,824 MAC 拍；实测节拍 49,536 像素 × 3 group × **16 拍/像素/组**
  = 792,576 扫描拍。合计约 **825,772 拍 @ 27 MHz ≈ 30.6 ms**，远小于 1 s，
  因此 27 MHz 足够，引入 PLL 只会多一个时钟域。

| 项 | 拍数 | @27 MHz |
|---|---|---|
| conv1 扫描（16 拍/像素/组 主导） | 49,536 × 3 × 16 = 792,576 | 29.4 ms |
| ingress 回放（与扫描串行，按行节流） | 64 × 258 = 16,512 | 0.6 ms |
| group 边界预装（192 次 × 86 拍） | 16,512 | 0.6 ms |
| boot（2 job × 86 拍） | 172 | 6.4 µs |
| **计算合计** | **825,772** | **≈ 30.6 ms** |
| UART（131 帧 × 91 B × 10 bit × BAUD_DIV 234） | 27,895,140 | **1.033 s** |
| **整轮合计** | — | **≈ 1.07 s** |

BAUD_DIV = round(27e6 / 115200) = **234**（实际 115384.6 baud，误差 +0.16%，在 8N1 容限内）。
16 拍/像素/组的来源：requant 需 16 拍 TDM drain，而 9-tap 扫描只用 12 拍，drain 主导
（与 `conv_engine.v` 头部的 conv1 行 `max(12,16)=16` 一致）。

### 3.2 权重/偏置/输入存储（624 B + 16.5 KB，全在片内）

由 `python scripts/compare_conv1.py --emit-hex` 从**唯一真源**生成，不手抄：

| 表 | 来源 | 内容 | 行数 |
|---|---|---|---|
| `conv1_w32.hex` | `weights_image.bin` offset **512**，前 432 B | 27 个 tap 字（每个 16 lane s8），每 tap 拆 4 个 32 位小端字 | 108 |
| `conv1_ctr.hex` | 同段，`bias_off=432` / `m_off=624` / `shift_off=816` | 48 bias + 48 M + 48 shift（shift 存低 7 位） | 144 |
| `conv1_feat.hex` | `reports/golden_ref/sine_440_full/feat.npy`（uint8, zp_in=49） | 64×258 = 16512 字节 | 16512 |

生成时做了三重自校验（`emit_hex` 中 `raise SystemExit`）：image 大小 == `image_total_bytes`；
bias/M/shift 各段逐元素 == `layer_contract.json` 的 `bias_int32` / `M` / `shift`。
已实测通过（`bias match True` / `M match True` / `shift match True`）；
首轮曾因负 bias 用 `02X` 格式化输出成 `-11F`，已改为按表宽两补码输出（D-04）。

### 3.3 顶层状态机

```
S_CFG   ── cfg_valid 1 拍（zp_in=49, zp_out=0, conv_sel=0）
S_START ── start0 1 拍          ← 必须在首轮 contract 之前（见 3.5）
S_BOOT  ── job0: contract g0 (49 拍) + tap g0 (37 拍) → ACTIVE bank / tap bank0
           job1: contract g1 (49 拍) + tap g1 (37 拍) → SHADOW bank / tap bank1
S_RUN   ── 并行四条：
            (a) tap 流：w_valid=1，w_data = tap_bank[use_grp&1][tap_idx]，tap_idx 环 0..8
            (b) ingress：按行节流回放 feat ROM（3 级流水）
            (c) 采集：y_cnt 命中 6 个窗口 → cap_ram[3072]
            (d) 边界：adv0 → use_grp 切到下一组、启动下一组预装 job（86 拍，期间 w_valid=0）
S_STOP  ── done0 锁存后静置 256 拍（让最后一个像素的 16 拍 drain 落地）
S_REPORT── 3 帧状态帧 + 128 帧数据帧，每帧等 UART busy 上升沿再下降沿
```

job 内部三段：`GT_IDLE → GT_CTR（c_step 0=grp_start，1..48=48 个 contract beat）→ GT_TAP（t_step 0=预取地址，1..36=装 9 个 128 位 tap）→ GT_IDLE`。
`gt_launch` 与 `job_grp` 同一拍建立，从而保证 CTR 第一拍读到的就是新组的 ROM 基址
（早期版本 naive 实现在这里差 1 拍，会发出错组权重，已修正，见 D-05）。

### 3.4 conv1 语义对齐（位级）

| 契约点 | golden (`golden_pipeline.conv2d_int8`) | 本设计 |
|---|---|---|
| 输入域 | `x_u8 - zp_in`（int64），pad 填 0（signed 域） | `conv_engine` 存 u8 容器、MAC 拍实时减 `zp_in`；pad 由 read-side guard 返回 0 |
| bias | `acc + bias_int32[c]` | `load_go` 时 `acc ← bias_act[c]` |
| requant | `round_half_even(acc*M >> shift) + zp_out`，`clip 0..255` | `requant_unit` 同式（tie-to-even 进位 + 饱和） |
| conv1 参数 | `zp_in=49, zp_out=0, shift∈[37,41], M∈[1.09e9,2.09e9]` | 与 `conv1_ctr.hex` 一致（逐元素校验） |

`contract` 里的 `zp_in_correction.wsum` 在 golden 里**未被使用**（padding 用 `padding_value == zp_in` 填，signed 域即 0，无需修正项）。这一点已由 `--self-check` 用 golden 重算验证：**792,576 个值，max_abs_diff = 0**，说明 `conv1.npy` 就是位级真值，板上对上它就是对上 golden。

### 3.5 两个容易踩错的 conv_engine 隐含契约（本设计的实现依据）

1. **`grp_start` 必须独占一拍、不与任何 valid 同拍。**
   `conv_engine` 的 contract loader 是
   `if (grp_start) cload_cnt<=0; else if (valid...) cload_cnt<=cload_cnt+1`。
   若 `grp_start` 与第一个 bias beat 同拍，`cload_idx` 会连续两拍为 0，`bias[1]` 覆盖 `bias[0]`，整组 contract 错位。
   本设计给 `grp_start` 一个**无 valid 的独立 beat**（`c_step=0`），该拍顺便预取 ROM word 0。
2. **首轮 contract 必须在 `start0` 之后装载。**
   `conv_engine` 在 `any_start` 时清 `grp_arm`，而 `load_go` 要求 `grp_arm`。
   先装 contract 再 `start0` 会把 active bank 丢掉 → `load_go` 永不发生 → 永久卡死。
   本设计把 `S_START` 排在 `S_BOOT` 之前。（这对 `wdma` 的原始实现对错未知，不影响本位流。）

### 3.6 ingress 行节流（3-bank 行缓冲的安全约束）

`conv_engine` 的 3 个 bank 按 `row % 3` 映射，写 `row k` 会覆盖 `row k-3`，
而 `row k-3` 在扫描 `row k-2` 时仍是窗口行（dy=0）。因此本设计写 `row k` 的条件是
`k <= row_done_cnt + 1`（`row_done_cnt` = 已扫完行数，由 `adv0` 每 3 次计 1）。
代价是 ingress 与扫描串行，约 +2% 时长（258 拍/行 vs 13,158 拍/行扫描）。

### 3.7 输出抽样口径

conv1 全流 792,576 个 u8，115200 下要 69 s，因此只取 **6 个互不重叠的 512 样本窗口 = 3072 个值**（131 帧 ≈ 1.03 s）。
窗口按流序号 `k = ((row*3+grp)*258+col)*16+lane` 定义，RTL 与本脚本硬编码一致：

| 窗口起点 k | 覆盖 | 目的 |
|---|---|---|
| 0 .. 511 | row0 grp0 col0..31（ch0..15） | 上边界 + 左边界（pad） |
| 4128 .. 4639 | row0 grp1 col0..31（ch16..31） | group 1 的 contract 切换 |
| 8256 .. 8767 | row0 grp2 col0..31（ch32..47） | group 2 的 contract 切换 |
| 402464 .. 402975 | row32 grp1 col128..159 | 常规内部块 |
| 780192 .. 780703 | row63 grp0 col0..31 | 下边界 + 左边界 |
| 792064 .. 792575 | row63 grp2 col226..257 | 右边界（col 257 + pad 列） |

覆盖 48 个输出通道全部、上下左右四边 padding、以及 3 个 group 的 contract 轮转。
`y_cnt`（完整流计数）随状态帧回传，用于证明「没丢拍」而不只是「采样对」。

---

## 4. 验证证据（本机实测）

### 4.1 `python scripts/check_rtl.py` → 0 violation

```
checked 51 .v file(s) under ...\instrec_fpga\src: 0 violation(s) in 0 file(s)
exit=0
```

### 4.2 `-BuildSet conv1_test -DryRun` 展开

```
DRYRUN top=top_npu_conv1_test set=conv1_test design=5 ip=0 constraint=1 hex=3
DRYRUN project_name: top_npu_conv1_test_pds
```

生成的 `build.tcl` 实读：

```
add_design ".../src/npu/conv_engine.v"
add_design ".../src/npu/requant_unit.v"
add_design ".../src/ctrl/uart_tx.v"
add_design ".../src/diag/diag_uart_report.v"
add_design ".../src/diag/top_npu_conv1_test.v"
add_constraint ".../constraints/top_npu_conv1_test.fdc"      (唯一一条约束)
file copy -force ".../hex_conv1/conv1_ctr.hex"  "…/<run>/hex_conv1"
file copy -force ".../hex_conv1/conv1_feat.hex" "…/<run>/hex_conv1"
file copy -force ".../hex_conv1/conv1_w32.hex"  "…/<run>/hex_conv1"
```

5 个设计文件 + 0 IP + 1 约束 + 3 个 hex，与要求完全一致；无 `mem_*` / `ref_clk`。

### 4.3 `python -m pytest -q` → 412 passed / 4 skipped

任务给出的基线是 398 passed / 4 skipped；当前工作区（含其它未提交任务）实测
**412 passed, 4 skipped, 2 warnings in 187 s**，无 failure、无 error，未出现退化。
（数量差来自工作区里其它任务已并入的测试，不是本任务新增。）

### 4.4 `python scripts/compare_conv1.py --help` / `--golden-only` / `--self-check`

- `--help`：可用（argparse 全文打印）。
- `--golden-only`：打印 6 个窗口的 `(row, group, col, channel)` 区间、前 N 个期望值、
  期望样本和 `26685`。
- `--self-check`：用 golden 管线从 `feat.npy` 重算 conv1 并与 `conv1.npy` 比对
  → `{"max_abs_diff": 0, "mismatch_count": 0, "total": 792576}`（**位级 0 差异**）。

### 4.5 帧通路回环自测（离线，无硬件）

用**期望值**合成 131 帧真实格式的 91 字节帧（3 状态 + 128 数据），再喂给
`compare_conv1.py --uart-file`：

- 正常 dump → `verdict=PASS`，3072/3072，`expected_sum == observed_sum == 26685`，
  `frames.parsed=131 / data=128 / missing=[]`，6 个窗口 mismatch 全 0；
- 人为翻转某一数据帧单个字节 → `verdict=FAIL`，`mismatch_count=1`，并精确反解出
  `sample=1019, row=0, group=0, col=63, channel=11`。

即：解析 → 反解 → 比对 → 定位 这条链路本身已被证明可用（不是纸面设计）。

### 4.6 保留字检查

对 `top_npu_conv1_test.v` 剥注释/字符串后提取 234 个标识符，与 IEEE 1364-2001 保留字表取交集：
**没有任何保留字被用作信号名**（`tri` / `reg` / `wire` / `always` / `task` / `time` / `event` / `edge` 等均未出现为标识符）。
出现的关键字全部是合法语法用法（`module` / `always` / `posedge` / `case` / `assign` / `signed` / `integer` / `or` 等）。

---

## 5. 授权外的必要改动（偏差）

任务给的「只允许写这些文件」清单里没有下面 3 个文件，其中 `run_pds_full.ps1` 还在「禁止改」列表里。
但不改它们，验收 2 与验收 3 **必然失败**，因此按最小必要改动处理，并在此逐条留痕（可单独回退）。

| 编号 | 文件 | 改动 | 为什么必须 |
|---|---|---|---|
| D-01 | `scripts/run_pds_full.ps1` | `[ValidateSet('full','ddr3_diag','ui_demo')]` → 加 `'conv1_test'`（1 行） | 该白名单在参数绑定阶段就拒绝 `conv1_test`，`-DryRun` 直接报 `ParameterArgumentValidationError`。不加则验收 2 无法达成。只加一个字符串，无行为变更。 |
| D-02 | `tests/test_build_tokens.py` | `SET_NAMES` 加 `'conv1_test'`、`TOP_MODULES` 加一项；一条断言文案 `three` → `listed` | 文件里有硬断言 `tuple(sets) == SET_NAMES`，新增 set 必然让它 red。 |
| D-03 | `tests/test_plan_contract_guards.py` | `SET_NAMES` 加 `'conv1_test'`（1 行） | 同上（Guard 5 的同型断言）。 |

D-02/D-03 只把新 set 加入「期望集合」，**既有隔离检查全部保留**：
`ddr3_diag` 仍禁 `src/npu/`、`ui_demo` 仍禁 DDR3 IP 与 `ddr3_100h.fdc`、`full` 的约束加载顺序断言原样未动。

| 编号 | 说明 |
|---|---|
| D-04 | hex 生成器的第一次输出把负 bias 格式化成 `-11F`（按数值大小而非表宽选字段宽度）。已改为按表宽两补码输出并重生成，校验 bias/M/shift 逐元素相等。 |
| D-05 | 顶层 job 引擎第一版存在 1 拍相位错位（`job_grp` 比 `gt_step` 晚一拍生效），会发出**上一组**的权重。已重构为 `GT_IDLE/GT_CTR/GT_TAP` + 独立 `gt_launch`，使 `job_grp` 与 CTR 首拍同拍生效。 |
| D-06 | 顶层第一版把首轮 contract 排在 `start0` 之前，会被 `conv_engine` 的 `any_start` 清掉 `grp_arm` 而永久卡死。已把 `S_START` 前置到 `S_BOOT` 之前。 |

---

## 6. 风险与未证明项

| 编号 | 风险 | 证据等级 | 处置 |
|---|---|---|---|
| R-1 | `conv_engine` 自身从未板上/仿真验证。它「16 拍/像素/组」的节拍由代码静态推导（drain gate `rhe_busy_cnt==0`），**未仿真**（本机无 iverilog/verilator，WSL 不可用）。若实际不是 16 拍，只影响耗时（估算偏大或偏小），不影响逐字节判据。 | 静态推导 | 上板后看状态帧 `E` 是否恰为 `0x0C1800`，可反证流完整性 |
| R-2 | 32 位宽 `$readmemh`（108/144 行表）在 PDS 下的解析未在本机验证；工具链只到 `-DryRun`。若报 Verilog-3001/宽度错误，退路是把 32 位表改 8 位字节表 + 组合拼装（`conv1_feat.hex` 已是 8 位，同类写法可用）。 | 未构建 | 真实构建时首看 compile 阶段日志 |
| R-3 | ingress 行节流约束 `ing_row <= row_done_cnt + 1` 由 3-bank 地址映射与窗口依赖推出，**未经仿真**。若推导有误，症状是**大范围**失配（很多 channel/多行同时错），而不是零星几个点。时序余量核算：conv 扫 row r+1 的 dy=2 tap 在行边界后约第 11 拍读 row r+2 的 col 0..1，而 ingress 在边界后约第 3–4 拍已写入（1 字节/拍，比 16 拍/像素的扫描快 16 倍），余量约 7–8 拍；这是静态推算，未含布线延迟与时钟树 skew。 | 静态推导 + 拍级推算 | 用 `per_window` 失配分布判别：6 个窗口全错 → 行数据污染；仅个别点错 → 数值路径问题；仅 row≥2 的窗口错 → 行节流余量不足 |
| R-4 | 板级串口链路（FTDI/CP2102）丢字节时，症状是 `missing_data_indices` 非空 / 帧数不足，**不应**判为计算错误。状态帧连发 3 次即为抗单帧丢失。 | 设计 | 脚本把「帧不全」与「值不等」分开报告 |
| R-5 | 本设计不验证 `wdma` 的权重搬运顺序。它只复用 conv_engine 的 tap/contract **端口契约**（每拍一个 128 位 tap 字、48 beat contract）。若 wdma 在契约上与 conv_engine 不一致，本任务不能替它证明。 | 范围外 | 单独立项 |

---

## 7. 上板判读步骤（构建槽到位后）

```powershell
# 1) 构建（唯一一次 pds_shell，勿并发）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet conv1_test
#    产物：build/top_npu_conv1_test-latest.sbit（+ .json 里的 StageStatus / WNS / SHA-256）

# 2) 烧录 + 抓串口（复用既有 board_check，勿新起 cdt_js）
python scripts/board_check.py --sbit build/top_npu_conv1_test-latest.sbit --json reports/board_conv1.json

# 3) 判读
python scripts/compare_conv1.py --uart-file build/uart_last.bin --json reports/conv1_compare.json
#    exit 0 = PASS；exit 1 = FAIL/证据不足（看 per_window 与 first_mismatch）
```

预期串口形态：约 1.03 s 内吐出 131 行 91 字节帧，LED `[1]`（done）与 `[2]`（frames sent）常亮，
`[3]`（capture full）常亮，`[0]` 心跳约 3 Hz。

预期状态帧字段：
`A=434F4E31 B=00000001 C=00000C00 D=0000683D E=000C1800 F=00000000 G=06 H=A5`
（`D=0x683D=26685` 是 3072 个期望样本的 u8 之和；它把「采样错位」和「数值错」区分开）

---

## 8. 待补项（无假结论）

1. **真实 PDS 构建未执行**：无 `.sbit`、无 WNS、无资源占用实测。`-DryRun` 只证明文件列表与
   token 替换正确，不证明可综合。
2. **未上板**：状态帧/数据帧的板级形态、`E=0x0C1800`、`D=0x683D` 均尚未实测。
3. `conv_engine` 的 16 拍/像素/组节拍只是静态推导，未经仿真。
4. 本文档所有「正确性」结论都是**位流前**的：hex 逐元素校验、golden `self-check` 0 LSB、
   帧通路回环 PASS/FAIL、lint 0 violation。这些成立不等于板上成立。

因此当前状态是：**static-verified, not board-proven**。