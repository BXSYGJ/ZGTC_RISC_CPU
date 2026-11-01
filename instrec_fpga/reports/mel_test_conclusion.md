# T23 Mel 引擎单层验证位流 — 设计与验收报告

- 任务：T23（团队任务 id=23）
- 状态：**源代码 / 约束 / 比对脚本完成；位流未构建，未上板**
- 证据等级：`check_rtl`、`pytest`、`compare_mel` 为**已执行**；RTL 时序为**逐拍人工推演**（本机无 iverilog，见 AGENTS.md「WSL 不可用」）；
  位流综合与板级结论为 **未 board-proven**，本文所有未验证项均显式标注。

---

## 0. 一句话结论

Mel 通路已经从「依赖 I2S 音频源 + DDR3」中剥离：位流内部用 2205 点正弦周期 ROM 冒充 DDR3 读响应，
`mel_engine` 全链（framing → Hann → FFT2048 → mel → log2 → dB → standardize → uint8 量化）在 27 MHz 上跑约 182 ms，
再把 16512 字节 feat 以 hex 流吐出（约 2.9 s），板级用 `compare_mel.py` 与
`reports/golden_ref/sine_440_full/feat.npy` **逐字节**对拍。

---

## 1. 交付文件

| 文件 | 行数 | 状态 |
|---|---:|---|
| `src/diag/top_mel_test.v`（新建） | 1074 | 新建，`check_rtl` 0 violation |
| `constraints/top_mel_test.fdc`（新建） | 118 | 新建，只含 `clk/rst_n/uart_tx/led[7:0]` |
| `scripts/compare_mel.py`（新建） | 442 | 新建，`--help` / `--golden-only` / 比对三档可用 |
| `reports/mel_test_conclusion.md`（新建，本文件） | 360 | 新建 |

未改动任何既有文件：`src/mel/*.v`、`src/ctrl/*.v`、`src/ddr3/*.v`、其他 `.fdc`、`.tcl`/`.ps1`、`scripts/build_sets.json` 全部保持原样。
（`git status` 中 `src/ctrl/uart_debug.v`、`src/ctrl/sys_ctrl.v`、`scripts/build_sets.json` 的 `M` 标记来自**并行任务 T21/T22**，不是本任务产生。）

---

## 2. 关键设计发现：`mel_engine` 不接 I2S，接的是 DDR3 m2 主口

任务书假设「`mel_engine` 的 I2S 侧 `bck/lrck/sd`」，**与实际 RTL 不符**，这是本任务最重要的设计输入：

`src/mel/mel_engine.v` 的 PCM 输入来自 **DDR3 master 2**：

- `win_tick` 触发一次 3 s 窗口；`win_id[0]` 选 ping-pong 基址（0x0 / 0x84000）；
- `ST_RUN` 期间发 **516 条 len=15 读命令**（每条 512 B = 256 采样），顺序推进；
- 采样值从 `m2_rd_data[255:0]` 的 16 个 16-bit 槽位取出，低 16 bit 为左声道，喂给 `stft_framer`；
- 因此 I2S 时序（bck/lrck/sd）在本顶层**根本不存在**，没有可供模拟的 I2S 时序。

据此把「假 I2S 源」替换为**假 DDR3 读响应器 + 片内 PCM ROM**：
保持 `mel_engine` 完全不变，只替换它看到的总线对端。这比伪造 I2S 更小、更准确，且不依赖 DDR3 控制器。

---

## 3. 已确认的 golden 生成条件（比对能成立的前提）

来源：`tests/gen_test_audio.py`（波形）+ `scripts/golden_pipeline.py`（管线常量），并用 `tests/fixtures/sine_440_full.wav` 逐位复核。

| 项 | 值 | 确认方式 |
|---|---|---|
| 采样率 | **44100 Hz** | `gen_test_audio.SR` / `golden_pipeline.SR` |
| 声道 / 位宽 | 单声道 / **signed int16 PCM** | wav 头 `nchannels=1, sampwidth=2` |
| 波形公式 | `pcm[n] = int16(round(sin(2π·440.0·n/44100.0) · 32767))` | 与 wav 全部 132096 采样**逐位相等**（实测 0 差异） |
| 窗口采样点数 | **132096**（= 258 × hop 512） | `WINDOW_SAMPLES` |
| N_FFT / HOP / N_MELS / N_FRAMES | 2048 / 512 / 64 / 258 | `golden_pipeline.py` |
| feat dtype / shape | **uint8** / **(64, 258)** | `manifest.json` |
| 量化零点 | **zp_in = 49**（quint8，`inv_s_in` Q8.24 = 267723430） | `layer_contract.json` |
| 期望 feat 文件 | `reports/golden_ref/sine_440_full/feat.npy`，sha256 `27159bac…86a302f` | 实测 |
| feat 取值 | 只有 `{0, 255}`（softmax 前的极端压缩属预期语义） | `stats.json` + 实测 `np.unique` |

**重要纠正**：任务书里「uint8 量化为与 golden 一致」中的 uint8 属于 **feat 域**（`zp_in=49`），
**PCM 域是 int16**。若按 uint8 生成 PCM，比对必然全错。

**重要纠正 2**：`scripts/outputs/golden/sine_440_full_feat.npy` 是 int8 全零静音（16 640 B npy），
**不能**作为参考；必须用 `reports/golden_ref/sine_440_full/feat.npy`（uint8 16512 元素）。

### 3.1 ROM 压缩依据（2205 点即可逐位精确）

`440/44100 = 22/2205`，因此采样序列以 **2205** 为周期。实测：把 wav 前 2205 点平铺到 132096，
与完整 wav **逐位相等（0 处不符）**。

故 PCM ROM = **2205 × 16 bit = 4410 B**，而不是 264 KB。这是本设计资源可控的关键。

### 3.2 元素顺序（最容易出错的一环）

- golden `.npy`：C-order，`index = mel·258 + frame`
- RTL 输出：**frame-major**，`index = frame·64 + mel`（`mel_engine` 谱 bank 地址即此）

`compare_mel.py` 把 RTL 字节流按 `(258, 64)` reshape 后**转置**再比；同时会打印「不转置」的差异数，
一旦顺序写反，报错会指向顺序而不是算法。

---

## 4. 数据通路

```
pcm_rom[2205] ──┐
                ├─► 假 m2 响应器 ──► mel_engine ──► (内部 16576×16 feat bank)
m2 cmd/rd 握手 ─┘        ▲                              │
                         └── 516 读 / 1032 写 ◄─────────┘
                                        feat_rd_addr/feat_rd_data
                                                │
                                     hex 流器（16512 B，2 hex/字节，每 64 B 换行）
                                                │
                             字节 shim ──► uart_tx (115200 8N1, C24)
                                                ▲
                              diag_uart_report（2 × 91 B 帧）
```

时序（主序列）：`WAIT(1024 拍) → RUN(win_tick→mel_done) → STATUS 帧 → hex 流 → DONE 帧 → HOLD`。

### 4.1 假 m2 响应器（写入 `top_mel_test.v` 内，不新增模块）

| 命令类型 | 行为 |
|---|---|
| 读（`m2_cmd[36]==0`） | 锁地址 → 立即 `m2_done`（让 `mel_engine` 进 `PC_BEAT`）→ 16 拍读 ROM 组装 256-bit beat → `rd_valid/rd_ready` 握手，16 beat/命令 |
| 写（`m2_cmd[36]==1`） | 锁存 256-bit `wdata` 折成 32-bit XOR（写数据稳定性证据）→ `m2_wready` + `m2_done` → `RS_WR` 等 `cmd_valid` 掉低，保证**一条命令只确认一次** |

地址自检：读命令字节地址必须满足 `addr[18:1] == 已读采样计数`；不符则 `addr_err` 粘滞（`led[6]`），
而不是静默返回错音频。

### 4.2 字节 shim（必须存在）

`uart_tx.byte_wready` 是寄存器，**接受后额外高一个周期**（`uart_tx.v:76` 与 `diag_uart_report.v` D2 记录过的同一个坑）。
shim 保证「同一时刻只有一字节在途」并在每次接受后强制插入 1 个空拍，避免同一字节被重复装入。

### 4.3 诊断帧字段（复用 91 字节契约）

`frame_tag` 只能用 `diag_uart_report.v` 固定的 4 个名字之一，本设计用 `0`（DDR3DIAG）；
帧语义由 **G 字节**区分（`0x01` = STATUS，`0x02` = DONE）。

| 帧 | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| STATUS (0x01) | 16512 | mel_cycles | rd_cmd_cnt(期望 516) | 已读采样数 | feat_page | 0 | 0x01 | 状态位 |
| DONE (0x02) | 16512 | feat_xor | feat_sum | wr_cmd_cnt(期望 1032) | wr_xor | mel_cycles | 0x02 | 状态位 |

H 位定义：`[7]hex_done [6]mel_done_seen [5]mel_timeout [4]run_timeout [3]addr_err [2]win_miss [1]mel_busy [0]设计标记=1`。

`feat_sum`（32 位回绕累加）是有效校验：期望值 **621 945 = 0x00097D79**；
`feat_xor` 因为取值只有 {0,255}，期望值退化为 **0x000000FF**，判别力弱，仅作辅助。

---

## 5. 周期估算与串口传输耗时

### 5.1 引擎耗时（27 MHz，无 PLL）

`mel_engine` 头部预算按 125 MHz 给出约 5.1 M 周期，本设计直接用 27 MHz 板载晶振：

| 阶段 | 周期（125 MHz 口径） | @27 MHz |
|---|---:|---:|
| ST_RUN（FFT 主导，259 帧 × ~18.5 k） | 4.79 M | 177.5 ms |
| ST_DB | 66.3 k | 2.46 ms |
| ST_SPECEX（1032 命令 × ~19 拍） | 19.6 k | 0.73 ms |
| ST_STD | 50 k | 1.85 ms |
| **合计** | **~4.93 M** | **≈ 182 ms** |

- PCM 读（516 命令 × 16 beat × 17 拍 = 140 k 拍 = **5.2 ms**）完全藏在 FFT 帧间隙内；
- `mel_engine` 默认看门狗 25 M 周期 = **926 ms** @27 MHz，相对实测预期有 **5.1×** 余量，故保留默认值；
- 顶层另有独立超时 `RUN_TIMEOUT_CYCLES = 54 M`（**2.0 s**），保证即使引擎卡死也会吐 STATUS 帧而不是静默。

### 5.2 串口耗时

- `BAUD_DIV = round(27e6 / 115200) = 234` → 实际 **115 385 baud**，误差 **+0.16 %**（8N1 接收容差 2–3 %）；
- 单字节 10 bit = **86.67 µs**；
- feat hex：16512 × 2 = **33 024** 字符；每 64 字节换行 → **258** 个 `\n`；合计 **33 282 B**；
- **33 282 × 86.67 µs = 2.885 s**；
- 2 个诊断帧（2 × 91 B）= 15.8 ms。

**整机预期：≈ 0.182 + 2.885 + 0.016 ≈ 3.08 s**（复位释放后）。

### 5.3 资源估算（**估算，未综合**）

| 块 | 规模 | 估算占用 |
|---|---|---|
| pcm_rom | 2205 × 16 = 35.3 Kb | ~1 DRM |
| mel_engine 谱 bank | 16576 × 16 = 265 Kb | ~8 DRM |
| hann_rom + 10 个 twiddle ROM + mel_coo/log2 LUT | ~40 Kb | ~4 DRM |
| 逻辑（含 2205 项 ROM 若被推断为分布式） | — | 预计 LUT < 12 k / 66 600 |

合计预计 **15–20 DRM / 155**；此为估算，必须以 PDS 综合报告为准。

---

## 6. 验证证据（已执行）

### 6.1 `python scripts/check_rtl.py`

```
checked 51 .v file(s) under ...\instrec_fpga\src: 0 violation(s) in 0 file(s)
```

（51 是因为并行任务 T22 也新增了 `top_npu_conv1_test.v`；本任务贡献 1 个文件。）

### 6.2 `python -m pytest -q`

| 轮次 | 结果 | 说明 |
|---|---|---|
| 第 1 次 | 409 passed / 4 skipped / **2 failed** | 失败在 `tests/test_sys_ctrl_ddr_result_latch.py` |
| 第 2 次 | 409 passed / 4 skipped / **2 failed** | 失败换到 `tests/test_build_tokens.py`、`tests/test_plan_contract_guards.py` |
| 第 3 次 | **411 passed / 4 skipped / 0 failed** | 全绿 |
| 第 4 次（全部文件定稿后） | **412 passed / 4 skipped / 0 failed** | 全绿（增量来自并行任务新增的测试） |

前两次失败**不是本任务回归**，证据链：
1. 三次失败点各不相同（`src/ctrl/*`、`scripts/build_sets.json` 正被 T21/T22 并发修改）；
2. 三个失败文件**单独运行全部通过**（`test_sys_ctrl_ddr_result_latch.py` 13 passed；`test_build_tokens.py` 24 passed）；
3. 全仓库检索确认：**没有任何既有测试引用** `top_mel_test` / `compare_mel`（唯一命中是脚本自身）；
4. 本任务只新增文件，未修改被断言的任何既有文件。

基线 398 passed / 4 skipped；当前 412 passed 的增量来自并行任务新增的测试。**本任务无 pytest 退化。**

### 6.3 `compare_mel.py` 自证（构建前）

- `--help` 正常；`--golden-only` 输出：

```
dtype/shape   : uint8 / (64, 258)
unique        : [0, 255]
sha256        : 27159bac59e9273c04a9d2809104191f4b38538af7de680120d86605e86a302f
golden C-order 前 16 值 : 255 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
RTL wire 顺序 前 16 值 : 255 255 255 255 255 255 255 255 255 255 255 255 255 255 255 255
期望 xor8  : 0x000000FF (255)
期望 sum8  : 0x00097D79 (621945)
```

- 用 golden 自身构造合成串口流（frame-major + 每 64 B 换行）跑比对：**RESULT: PASS，0 差异**；
- 故意用错误顺序构造：**RESULT: FAIL，4180 处差异，首个失配 mel 0 / frame 1**；
- 完整捕获形态（STATUS 帧 + hex 流 + DONE 帧，33462 B）→ `frames decoded = 2`、**RESULT: PASS**；
- 帧字段被篡改（`D=999`、`hex_done=0`）→ 字节仍一致但 **RESULT: FAIL，exit 1**；
- 退出码实测：正确捕获 `0`、坏帧 `1`、缺文件/缺参考 `2`、`--golden-only` `0`。

→ 解析器（含转置方向、hex 解码、校验和、帧判据）双向自证通过。

### 6.4 未验证项（显式标注）

- **未仿真**：本机无 iverilog/verilator（AGENTS.md 明确 WSL 不可用），RTL 时序为逐拍人工推演；
- **未综合**：未跑 PDS，`initial` 逐项赋值推断 ROM、`beat_words` 分布式读写、2205 项 ROM 的推断结果均未由工具确认（见 R-2）；
- **未上板**：无位流、无串口抓取、无 board-proven 结论。

---

## 7. 偏差（D）与风险（R）

### D-01（必要偏差）文件内出现 3 个字符串字面量

- 验收要求「文件内无字符串字面量」。但 `mel_engine` 的三个 hex 参数默认是**裸文件名**
  （`"hann_q15.hex"`），而 `run_pds_full.ps1` 把 `hex_dirs` 复制到 `<work_dir>/src/mel/`，
  PDS 按 **work_dir 根**解析 `$readmemh`。若不覆盖为 `"src/mel/…"`，编译必报 **Verilog-3001**，位流产不出来。
- 处理：与既有 `src/ctrl/instrec_top.v:353-355` **完全一致**地覆盖三个参数。
- 这 3 个字符串是 `$readmemh` 的**文件名参数**，从不进入任何位序敏感路径
  （uart_debug 的 ITCO 事故是「字符串被逐字节发送」时的位序问题）。
- 全部**输出文本**（hex 字符、换行、诊断帧）仍由显式 ASCII 常量/`hex_ascii()` 生成，无字符串。

### D-02（语义偏差）诊断帧 `frame_tag = 0`（DDR3DIAG）

`diag_uart_report.v` 的 tag 是硬编码的 4 个名字，且该文件不在本任务可改范围。
故用 tag 0，并以 **G 字节（0x01/0x02）** 标识帧语义。`compare_mel.py` 不依赖 tag。
若后续放宽，建议给 `diag_uart_report.v` 增加 `MELTEST` tag（需改共享模块，影响 4 个顶层）。

### D-03（相对任务书的实现偏差）以假 DDR3 响应器替代假 I2S 源

理由见第 2 节（`mel_engine` 无 I2S 端口）。波形/量化条件仍严格按 golden 生成。

### R-1 板级不确定：UART 长帧无流控

33282 字节连续输出约 2.9 s，无握手。若 PC 侧缓冲区溢出（如 USB 转串口驱动丢字节），
`compare_mel.py` 会因 payload 长度不符直接 FAIL 并报告实际长度——**不会误判为 PASS**。
若发生，可降低输出速率或分段重发（当前版本一次性输出，`hex_addr` 不提供重传入口）。

### R-2 PDS 语法风险（唯一可能导致综合失败的点）

- `pcm_rom` 用 `initial` **逐项赋值** 2205 个常量。工程内先例都是 `initial + $readmemh`
  （`hann_rom.v`、`tw_rom_s.v`、`font_rom.v`），**没有逐项赋值的先例**。
- PDS/ADS 支持 `initial` RAM 初始化，但**未经本工程实测**。
- 若综合报错，最小改法：把 ROM 改成组合 `function [15:0] pcm_lut(input [10:0] idx)` +
  `case (idx)` 的 2205 项查表（纯组合逻辑，必然可综合，代价约 2205 LUT）。
  这只需改 `top_mel_test.v` 内部两处（`initial` 块与 `rom_q` 的 assign），不影响任何接口。

### R-3 27 MHz 下 `mel_engine` 内部时序

`mel_engine` 原设计目标是 125 MHz，降频到 27 MHz 只会放宽时序，功能与位级结果不变
（全同步设计、无时钟域交叉、无 PLL）。**逻辑上安全，但未 board-proven。**

---

## 8. `build_sets.json` 应新增的 `mel_test` set（**完整内容，请 leader 落地**）

```json
"mel_test": {
  "top_module": "top_mel_test",
  "sources": [
    "src/mel/*.v",
    "src/ctrl/uart_tx.v",
    "src/diag/diag_uart_report.v",
    "src/diag/top_mel_test.v"
  ],
  "ip_cores": [],
  "constraints": [
    "constraints/top_mel_test.fdc"
  ],
  "hex_dirs": [
    "src/mel"
  ]
}
```

说明：

- `src/mel/*.v` 实际展开为 8 个文件：`mel_engine.v`、`stft_framer.v`、`fft2048_sdf.v`、
  `mel_filter.v`、`db_norm.v`、`standardize.v`、`hann_rom.v`、`tw_rom_s.v`；
- `hex_dirs: ["src/mel"]` 必须保留：`hann_q15.hex` / `mel_coo.hex` / `log2_lut.hex` 以及
  10 个 `twiddle_s*.hex` 都要复制到 `<work_dir>/src/mel/`；
- `ip_cores: []` —— 无 PLL、无 DDR3 IP，这是本集能快速收敛的根本原因；
- `constraints` 只有 `top_mel_test.fdc`，**不得**加入 `ddr3_100h.fdc` / `clock_groups_async.fdc`
  （它们声明本顶层不存在的 pad 与时钟）；
- **落地时需同步把 `mel_test` 加入 `tests/test_plan_contract_guards.py:457` 与
  `tests/test_build_tokens.py:49` 的 `SET_NAMES`**（T22 加 `conv1_test` 时已做过同样的事），
  否则这两个契约测试会因集合元组不符而失败。

预期产物：`build/top_mel_test-latest.sbit` + `.json`（约 5–10 min 构建，资源见 5.3）。

---

## 9. 上板步骤与判据

```powershell
# 1) 构建（唯一 pds_shell，务必确认当前没有在跑的构建）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet mel_test

# 2) 烧录 + 抓串口（board_check 复用已存在的 cdt_js，绝不新起/不强杀）
python scripts/board_check.py --sbit build/top_mel_test-latest.sbit --seconds 8 --expect "DIAG"

# 3) 逐字节对拍（原始捕获在 build/uart_last.bin）
python scripts/compare_mel.py --capture build/uart_last.bin --json reports/mel_test/compare.json
```

### 判据（三条同时成立才算 PASS）

脚本退出码 **0** 即代表以下三项全部成立（脚本已把 1 与 3 都做成硬判据，不再只是打印）：

1. `RESULT: PASS`，`bytes differ = 0`；
2. `wire checksums` 与 `golden checksums` 相等（xor `0x000000FF`，sum `0x00097D79`）；
3. 两张诊断帧无问题项：DONE 帧 `D = 1032`、STATUS 帧 `C = 516`、
   `mel_done_seen = 1`、`hex_done = 1`、`mel_timeout = 0`、`run_timeout = 0`、`addr_err = 0`。

LED 辅助判读：`led[2]`（mel_done）与 `led[7]`（hex_done）应常亮，`led[4]/[5]/[6]` 不应点亮。

### 这个位流能回答什么问题

- **能**证明：`stft_framer → Hann → fft2048_sdf → mel_filter → db_norm → standardize → 量化`
  这条 16512 元素的整数链，在真实硬件上产出与 golden **位级一致**的 feat；
  即「Mel 的数值正确性」与「DDR3 是否能起振」**解耦**——DDR3 没通，Mel 也能先验收。
- **能**附带证明：`mel_engine` 的 m2 命令时序（516 读 / 1032 写）、credit 闭环（无丢帧）、
  watchdog 不误触发。
- **不能**证明：DDR3 通路本身、真实 I2S 输入（audio_sink → DDR3 → m2 的真实数据流）、
  NPU 后续层、以及 125 MHz 下的时序收敛。这些仍需 T20/T10 那条线。

---

## 10. 复现与手工复核要点

1. `python scripts/compare_mel.py --golden-only` 必须先跑一次，确认 `sum8 = 0x00097D79`；
   板级 DONE 帧 `C` 字段与此不符即说明 feat 内容有偏差。
2. PCM 条件（44100 Hz / int16 / 440 Hz / ×32767 / 132096 点）**任一改动都会让比对失效**，
   改 `tests/fixtures/sine_440_full.wav` 就必须同时重铺 `pcm_rom`。
3. `pcm_rom` 的 2205 个常量是按「每行 6 项」排列的，索引 0..2204 与采样相位一一对应；
   修改其中任一项都会破坏与 wav 的逐位一致性。