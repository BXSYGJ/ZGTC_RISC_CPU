# T11 · 全量位流板级端到端（E2E）结论

> 执行人：板级E2E-施工（团队任务 id=11）　执行时间：2026-10-31 16:08–16:14（本地）
> 工程根：`instrec_fpga/`　　纪律：**未修改任何脚本 / RTL / 约束**，未 commit，未 push，未启动 `pds_shell`。
> 本报告只陈述**实测**与**可追溯的源码出处**；推断一律标注置信度，不与事实混写。

---

## 0. 结论摘要（一句话）

**DDR3 阻塞在全量位流上未解除。** `board_check --expect` 退出码 **5**，`DDROK` **未出现**；
串口得到 `INSTREC BOOT` / `DDR3 SELFTEST...` / **`DDR3 ERR @00300000`**（两轮重烧**逐字相同**），
`weight_upload` 三次（含一次 fresh 烧录后立即执行）均停在 **`frame 0 (seq 0) not acknowledged`**，未取得 `WOK`。
本轮两处 RTL 修复中，**修复①（`self_test` done 出口）已获得板上证明**；**修复②（`st_wready_beat` 接线）只证明"已接线"，板级效果未显现**。
阻碍点由代码级证据指向 **`ddrphy_sysclk` 域时序违约（WNS −1.740）**，其最差 6 条路径全部落在 `u_weight_loader` 的写数据通路，其中一条终点直达 DDR3 IP 的写数据寄存器。

---

## 1. 前提核对（P1–P4，全部满足）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| P1 | `Get-Process pds_shell` 为空 | 返回空 | ✅ 构建已收尾，无第二个 `pds_shell` |
| P2 | 位流新鲜 | `build/instrec-latest.sbit` 3,791,112 B，mtime **2026-10-31 16:00:55** | ✅ 晚于 T10 启动时刻 |
| P3 | 六阶段全 OK | `compile / synthesize / dev_map / pnr / report_timing / gen_bit_stream` = 六项 `OK` | ✅ |
| P4 | 位流 == manifest | `.sbit` sha256 = manifest `BitstreamSha256` = **`44E8F011D44E10254E33BCBE4622BEB3F53966894C00BD1962BE9420414D476C`** | ✅ 逐字符一致 |

- `BuildSet=full`、`TopModule=instrec_top`、`RunName=20261031-135808-f1cb68bd`、`Device=PG2L100H-6IFBG676`。
- 资源：LUT 34407/66600（52%）、FF 52193/133200（39%）、DRM 86/155（56%）、BKCL 6/6（100%）。
- **manifest 的 `Wns=0.523` 仅是 `clk_nco` 域**（`instrec_top.rtr:70,84`），**不是收敛证据**；最差域见 §6。

### JTAG / 下载器卫生（运行前后一致）

| 时点 | `cdt_js` | `cdt_cfg` | FTDI |
|---|---|---|---|
| 执行前 | `[9040]`（起于 2026-10-28 09:22） | 无 | present |
| 执行后 | `[9040]`（同一 PID，未重启、未 terminate） | 无（脚本故意不杀） | present，VID_0403 计数 = 5 |

`board_check.py` 走的是 `ensure_server()` 的 **reused** 分支（`scripts/board_check.py:178-199`），实测打印
`reusing the running jtagserver (PID 9040, not restarted)`；两次 JSON 的 `jtagserver_pids` 均为 `[9040]`。

---

## 2. Step 1 —— 烧录 + boot + DDR3 自检（核心判据）

### 2.1 命令（照 runbook §2 Step 1，`--json` 置于 `--expect` 之前）

```
python scripts/board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 25 \
  --json reports/board_e2e_20261031T080814Z.json \
  --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"
```

### 2.2 退出码与证据文件

| 项 | 值 |
|---|---|
| **退出码** | **5**（`EXIT_EXPECT_FAIL`，`board_check.py:71`） |
| 证据 JSON | `reports/board_e2e_20261031T080814Z.json`（12 键、无 BOM） |
| `verdict` | `FAIL` |
| `expect` / `expect_missing` | `["INSTREC BOOT","DDR3 SELFTEST","DDROK"]` / **`["DDROK"]`** |
| `program_ok` | `True` |
| `status_raw` | `0x081ffca0` → `done=1`、`crc_err=0` |
| `uart_bytes` | **49**（全长仅 49 B，无任何后续行） |

### 2.3 串口关键行原文（`build/uart_last.bin` 逐字节，od 复核）

```
INSTREC BOOT\n
DDR3 SELFTEST...\n
DDR3 ERR @00300000\n
```

- **`DDROK` 未出现** —— DDR3 自检未通过。
- 错误地址 **`@00300000` 不是 `@FFFFFFFF`**，两者语义完全不同：
  - `@FFFFFFFF` = `sys_ctrl` 的 100 ms 看门狗超时，`self_test` 未给结论（修复前的旧现象）；
  - `@00300000` = `st_fail_addr`，且**恰等于 `SELFTEST_BASE`**（`src/ctrl/self_test.v:72`：`28'h0030_0000`），
    即**第 0 条（cmd_idx=0）命令即失败**（`st_fail_addr <= cmd_addr`，`cmd_addr = SELFTEST_BASE + (cmd_idx<<9)`，`self_test.v:118`）。

### 2.4 可重复性（重要）

第二轮独立重烧（新 ts）：

```
python scripts/board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 20 \
  --json reports/board_e2e_20261031T081318Z_run2.json \
  --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"
```

结果与第一轮**逐字节一致**：退出码 5、`uart_bytes=49`、`status_raw=0x081ffca0`、串口三行完全相同、
`expect_missing=["DDROK"]`、`jtagserver_pids=[9040]`。

> 结论：`@00300000` **不是偶发**，是确定性行为。`done=1`、`crc_err=0` 说明**位流烧录本身成功**，
> 失败发生在烧录之后的 DDR3 自检阶段，与位流完整性无关。

---

## 3. Step 2 —— 权重上传（WOK 未取得）

### 3.1 离线预检（通过）

```
python scripts/weight_upload.py --image scripts/outputs/weights_image.bin --dry-run
→ image scripts/outputs/weights_image.bin: 691040 bytes,
  sha256 19a74dbec29d3a0f16ab06dc30f70312849977de0c6b345710b046b1908f5d7a
→ frames: 2701 (including end frame)
→ exit=0
```
镜像与 `layer_contract.json` 的 `image_total_bytes=691040` / `image_sha256` 一致（**未重新生成**）。

### 3.2 实测三次，全部 `frame 0` 即失败

| # | 时机 | 结果 | 退出码 |
|---|---|---|---|
| 1 | 第一轮烧录后（板子已输出 `DDR3 ERR`） | `RuntimeError: frame 0 (seq 0) not acknowledged` | 1 |
| 2 | 同一状态复测 | 同上（`frame 0`） | 1 |
| 3 | **第二轮 fresh 烧录后立即执行** | 同上（`frame 0`） | 1 |

- 没有任何 `WOK <8hex>`，也没有 `WERR <8hex>`；**板子对一个 262 B 帧在 4 × 0.5 s 内零字节回复**。
- 因失败发生在第 0 帧，`--retries 3`（`weight_upload.py:129`）已耗尽 → 无需担心长跑超时。

### 3.3 解读（状态机级论证）

`weight_loader` 的 `'K'`（0x4B）**不是收到帧即回**，而是**等 AXI 写完成**才回：

```
S_CHECK  → crc 通过 → cmd_valid<=1 → S_WRITE      (weight_loader.v:270-276)
S_WRITE  → if (done) → cmd_valid<=0, state<=S_ACK  (weight_loader.v:287-291)
S_ACK    → tx_data<=8'h4B ('K')                    (weight_loader.v:294-298)
```

因此「零字节回复」有且仅有三种可能：
1. `uart_rx` 侧根本没收到帧（FSM 停在 SOF 等待）；
2. 收到帧、卡在 `S_WRITE`，`done` 永不到达；
3. 收到帧但 CRC 失败会回 `'N'`（`weight_loader.v:300-303`）—— **实测无 `'N'`，故排除 CRC/帧格式错误**。

`done` 在 ctrl 中由 `write_cmpl || read_cmpl || to_abort` 产生（`ddr3_ctrl_axi.v:247-252`）。若 m1 命令被 grant 后
S_AW/S_W 走看门狗，`to_abort` **仍会发 `done`**（`ddr3_ctrl_axi.v:249-250`），weight_loader 就会回 `'K'`。
**实测连 `'K'` 都没有** ⇒ 排除「m1 被 grant 后超时」这一分支，剩下 (1) 未收帧 或 (2) m1 命令从未被 grant。

> 现有位流**没有** `weight_loader` FSM 状态或 arbiter `grant` 的 UART 导出，无法在板上区分 (1)/(2)。见 §8 D-8。

---

## 4. 两处 RTL 修复在板上的证明状态

| 修复 | 代码位置 | 板上证明 | 判定 |
|---|---|---|---|
| **① `self_test.v` 补 `done` 出口** | `self_test.v:226-235`（`ST_WDATA` 内 `else if (done)` → `st_fail` + `st_fail_addr<=cmd_addr` + `ST_END`） | 现象从 `@FFFFFFFF`（旧：stuck `ST_WDATA`，等 `sys_ctrl` 100 ms 看门狗）**变为 `@00300000`**；按 `AXI_TO_LIMIT=4096`（`ddr3_ctrl_axi.v:64`）@125 MHz ⇒ **32.8 µs** 内自行给出结论，远短于 100 ms | ✅ **板上证明生效** |
| **② `instrec_top.v` 补 `st_wready_beat` 驱动** | `instrec_top.v:750`：`assign st_wready_beat = ddr_wready_beat[3];`（`:746-749` 留有 Verilog-2036 tie-0 原注释） | 该 assign **源码在位**、`ddr_wready_beat[3]` 由 ctrl 输出（`ddr3_ctrl_axi.v:231`，`4'b0001 << cur_master`，`cur_master` 来自 grant 锁存 `:333-337`）；但板上仍报第 0 条命令失败，**看不到该修复带来的成功** | ⚠️ **只证明「已接线」，未证明「板级有效」** |

**修复②的旁证（跨位流对照）**：诊断顶层用的是等价接法
`st_wbe_in = cfg_demo ? wready_beat_b[3] : wready_beat_a[3]`（`src/diag/top_ddr3_diag.v:286`），
在 T8 第二轮的 `u_ctrl_design` 轮 **PASS**（`wlast_miss_cnt=8`、`done_cnt=16`、`wready_cnt=136`，
见 `reports/ddr3_diag_conclusion.md:412`）—— 说明**「`wready_beat[3]` 接到 `self_test`」这种接法本身是正确可用的**，
只要实现收敛。故修复②不是错误的改动，只是**在全量位流上被别的因素压住了**。

---

## 5. 决定性对照：同一 AXI 参数，diag PASS / 全量 FAIL

### 5.1 参数一致性核对（排除"参数选错"）

| 位置 | `AXI_USER_AP` | `DUMMY_WSTRB_ALL1` | 备注 |
|---|---|---|---|
| `ddr3_ctrl_axi.v:58` / `:62`（默认值） | `1'b1` | `1'b0` | = **design** 配置（PASS 的那套） |
| `top_ddr3_diag.v:392-395`（`u_ctrl_design`） | `1'b1` | `1'b0` | T8 第二轮 **PASS** |
| `top_ddr3_diag.v:443-446`（`u_ctrl_demo`） | `1'b0` | `1'b1` | T8 第二轮 **FAIL @0x00300000** |
| **`instrec_top.v:645`（全量例化）** | **未覆盖 → 取默认值 `1/b0`** | 同上 | = design 配置 |

⇒ **全量顶层用的是 T8 第二轮 PASS 的那套参数**，"参数选错"的解释被**排除**。

### 5.2 位流级对照

| 位流 | RunName | 顶层 | ctrl 配置 | 整设计 `Wns` | DDR3 自检（板级） |
|---|---|---|---|---|---|
| `build/top_ddr3_diag-latest.sbit`（13:48） | `20261031-134355-6532cf6c` | `top_ddr3_diag` | design | **+4.405** | **PASS**（`st_done=1`，16-beat 真实写完成） |
| `build/instrec-latest.sbit`（16:00） | `20261031-135808-f1cb68bd` | `instrec_top` | design（默认） | `clk_nco +0.523`；**`ddrphy_sysclk −1.740`** | **FAIL @0x00300000** |

⇒ 同一 RTL 子模块、同一 `self_test` 逻辑、同一 `0x300000` 地址、同一参数，
**唯一显著差异是时序收敛程度**。这使「时序违约」成为首要嫌疑，而不是自检逻辑或接线。

### 5.3 `ddrphy_sysclk` 域的违例路径（24 条最差路径全部端点）

从 `build/pds/20261031-135808-f1cb68bd/report_timing/instrec_top.rtr` 逐条配对 `Startpoint/Endpoint`：

| 条数 | Startpoint | Endpoint | 归属 |
|---|---|---|---|
| 2 | `u_weight_loader/beat_buf[7][212]` | `u_weight_loader/acc2[28]/CIN` | **权重 digest 累加** |
| 2 | `u_weight_loader/beat_buf[7][212]` | `u_weight_loader/acc2[24]/CIN` | **权重 digest 累加** |
| 2 | `u_weight_loader/beat_buf[7][212]` | **`ddr3_wrapper/.../mcdq_wdatapath/mcdq_wdp_align/r_data[212]`** | **DDR3 IP 写数据寄存器** |
| 2 | `u_npu/u_gap/lane_cnt[2]` | `u_npu/u_gap/acc_b_3_0/ram64x1d/WADDR[2]` | GAP 累加 RAM |
| 4 | DDR3 IP 内 `mcdq_dcp_buf` 分布式 FIFO `wptr[1]` | 同 FIFO `fifo_rdata_a[9]/[23]` WADDR | IP 内部 |
| 6 | `ddrphy_reset_ctrl/u_ddrphy_rstn_sync` | `ddrphy_wrlvl/*`、`ddrphy_rdcal/*` 复位端 | PHY 复位 |
| 6 | `u_ddrc_rstn_sync/sig_async_r1[0]` | `u_mel_engine/u_standardize/*/gopapm/RST_*` | mel 乘法器复位 |

**关键事实**：列出的 24 条最差路径中，**6 条（占比最高、且为全局 WNS 决定者）全部落在 `u_weight_loader` 的写数据通路**，
其中 2 条的终点是 **DDR3 IP 的写数据寄存器 `mcdq_wdp_align/r_data[212]`**。
⇒ 这不是"抽象的逻辑余量"，而是**权重写入 DDR3 的物理数据通路**在违例。

### 5.4 最差路径逐级溯源（`rtr:1943-1990`）

```
Startpoint : u_weight_loader/beat_buf[7][212]/opit_0/CLK
Endpoint   : u_weight_loader/acc2[28]/opit_0_inv_AQ_perm/CIN
Path Group : ddrphy_sysclk
...
core_clk  (USCM_215_576/CLKOUT → core_clk, fanout=6005)        5.550
u_weight_loader/beat_buf[7][212]/Q   tco 0.185 → 5.735
net (fanout=1)                       5.192 → 10.927   ← 单元内跨区走线
CLMS_327_1165/CR0                    0.410 → 11.337
net m1_wdata[212] (fanout=3)         2.999 → 14.336   ← 顶层长走线
CLMA_177_798/CR2 (CLKROUTE_612/CR)   0.222 → 14.558   ← 复用为"长线中继"
...
Data arrival time = 14.940     Logic 1.079 ns (11.491%)   Route 8.311 ns (88.509%)
```

- `core_clk` 由 `ddr3_wrapper/.../ddrphy_sysclk` 经 `USCM`/`HCKB` 缓冲输出、**fanout 6005**
  ⇒ **`ddrphy_sysclk` 域就是整个 core 逻辑域**，其 −1.740 直接作用于 `self_test`、`ddr3_ctrl_axi`、`weight_loader`、`mel_engine`。
- Route 占 **88.5%**，逻辑仅 1.079 ns ⇒ 属**布线拥塞 / 长线**，不是逻辑级数问题。

### 5.5 时序预算计算（说明"降频"不可行）

| 项 | 数值 |
|---|---|
| `ddrphy_sysclk` 目标周期 | 8.000 ns（125.000 MHz，`rtr:74`） |
| 实际数据到达（最差路径） | 9.740 ns 等效 |
| **WNS** | **−1.740 ns**（超目标 21.75%） |
| **TNS** | **−124.797 ns** |
| Failing endpoints | **482 / 140545** |
| 若降到 100 MHz（10 ns 周期） | WNS ≈ −1.740 + 2.000 = **+0.26 ns** 才勉强为正，几乎无余量 |
| DDR3 PHY 是否允许降频 | 否 —— `ddrphy_sysclk` 由 DDR3 PHY 的 GPLL 派生（`rtr:28`），与 PHY/校准时序绑定 |

⇒ **不能靠降频解**；必须降低这条 `m1_wdata[212]` 通路的走线延迟（寄存器打拍 / wdata 先寄存后 mux / 布局约束）。

### 5.6 组合 mux 使该违例路径成为"真路径"（原理性论证）

```
assign axi_wdata = (state == S_DW_W) ? 256'd0 :
                   (cur_master == 2'd0) ? m0_wdata :
                   (cur_master == 2'd1) ? m1_wdata :
                   (cur_master == 2'd2) ? m2_wdata : m3_wdata;   // ddr3_ctrl_axi.v:212-215
assign m1_wdata = wl_wdata;                                       // instrec_top.v:641
```

- 当 `cur_master == 3`（self_test）时，逻辑上输出只取 `m3_wdata`，`m1_wdata` 无关 ⇒ **对 self_test 是伪路径**；
- 当 `cur_master == 1`（weight_loader 写权重）时，`axi_wdata[212]` **就是** `m1_wdata[212]` ⇒ **对权重上传是真路径**。

**归纳结论**：
1. **`weight_upload` 的失败可直接归因于这条已量化违约的路径**（终点即 IP `r_data[212]`，且 digest 累加器 `acc2` 同一源头）。置信度：**高**。
2. **`self_test` 的 `@00300000` 不能归因于这 6 条已列路径**（它走 `m3_wdata`）。但 `ddrphy_sysclk` 域有 **482** 个 failing endpoints，
   报告只列最差 24 条，**未排除** `ddr3_ctrl_axi` 握手逻辑在剩余违例集合内。置信度：**中**，需 `dbg_to_state` 实证（§8）。

---

## 6. `@00300000` 的三种可能分支（当前无法唯一确定）

`self_test` 中**三条不同分支**都会在 `cmd_idx == 0` 时写入 `st_fail_addr <= cmd_addr`，而 `cmd_addr = SELFTEST_BASE + 0` ⇒ **都等于 `0x00300000`**：

| 分支 | 触发条件 | 代码 |
|---|---|---|
| A. 写阶段 watchdog abort | `ST_WDATA` 内 `!wready_beat && done` | `self_test.v:226-235` |
| B. 读数据首拍不匹配 | `ST_RDATA` 内 `rd_data != exp_beat` | `self_test.v:256-264` |
| C. 读阶段 abort | `ST_RDATA` 内 `!rd_valid && done_q` | `self_test.v:278-286` |

- A ⇒ 写握手从未成功（指向 `wready_beat` / `awready` / 仲裁）；
- B ⇒ **写是成功的**（16 拍都握手了），只是**写进 IP 的数据位 212 被违例路径污染**，读回不一致 —— 与 §5.3/§5.6 **完全自洽**；
- C ⇒ 读通道未回数据。

**区分手段被切断**：`ddr_dbg_to_state[2:0]`（记录超时发生在哪个 S_* 状态）在 `instrec_top.v:216` 声明、`:672` 连接到 ctrl 输出后
**没有任何消费者**（无 LED、无 UART、无寄存器导出）⇒ 全量位流在板上**无法读出**该字段。

> 因此本报告**不判定** A/B/C 中的哪一个；只给出「A 与 B 都能解释 `@00300000`」并在 §8 给出补齐手段。

---

## 7. Step 3 —— 逐层对拍：**DEFERRED（未执行，不计 PASS）**

### 7.1 判定

**逐层对拍 = DEFERRED。** 两个独立前置条件**同时**不满足：

| 前置 | 事实 | 出处 |
|---|---|---|
| ① RTL 有逐层 UART 导出 | **没有**。顶层 UART TX 只有两个源：`weight_loader`（`K`/`WOK`）与 `uart_debug`（6 条状态行），由 `wl_tx_valid` 优先、`dbg_tx_ready = tx_byte_ready & ~wl_tx_valid` 复用 | `instrec_top.v:806-816`；`uart_debug.v:86-91` |
| ② 有与 golden 同源的真实 I2S 输入 | **没有**。本次无音频源接入 | 现场无条件；`sine_440_full` wav 未播放 |
| ③（补充）即使有音频也无用 | 板子连 DDR3 自检都未过（`@00300000`），`sys_ctrl` 未进入运行态；`npu` 的 probs 只进 UI、不上 UART | `sys_ctrl.v:275-285` |

`compare_layers.py` 在任何情况下只能 `rc=1`（`compare_dir` 找不到 `layer_*.npy` → `FileNotFoundError` → `:455-457` 返回 1）。
**因此未运行该脚本，也不存在可写的"逐层结果表"** —— 把"没跑"写成"通过"是明确禁止的。

### 7.2 补齐清单（哪个模块、哪个量、每层多少字节）

需要在 `instrec_top` 中新增 **`src/diag/layer_export.v`**（帧协议按 `design.md 9.2`：`SOF=0xAA` + `layer_id` + `seq` + `len` + `payload` + `crc16`），
把下列 8 层 tap 接进去（tap 点已存在但当前被综合剪掉，见 `instrec_top.v:32,208`）：

| `layer_id` | 量 | 形状 | 线序 dtype | **字节数** | 256 B/帧的帧数 |
|---|---|---|---|---|---|
| `0x00` | MEL_Q8_8 | `(64, 258)` | int16 | **33,024** | 129 |
| `0x01` | CONV1 | `(48, 64, 258)` | uint8 | **792,576** | 3,096 |
| `0x02` | CONV2 | `(96, 32, 129)` | uint8 | **396,288** | 1,548 |
| `0x03` | CONV3 | `(192, 16, 64)` | uint8 | **196,608** | 768 |
| `0x04` | CONV4 | `(256, 8, 32)` | uint8 | **65,536** | 256 |
| `0x05` | FC1 | `(128,)` | uint8 | **128** | 1 |
| `0x06` | FC2_LOGITS | `(8,)` | int32（容器 = `out_u8 - zp_out`） | **32** | 1 |
| `0x07` | PROBS | `(8,)` | uint8（`--probs-encoding percent`） | **8** | 1 |
| `0x08` | STATS（无 golden 参考，`compare_layers.py:76-78` 记为 skipped） | `(8,)` | int32 | 32 | 1 |
| | **合计** | | | **1,484,232 B** | **≈5,801 帧** |

**传输预算**：每帧 262 B（256 payload + 6 头尾）× 5801 帧 = **1,519,862 B**；
@115200 8N1（10 bit/B）⇒ **≈ 131.9 s（2.2 min）**。必须用 `uart_capture.py --frames --out-dir` 抓取，且 TX 仲裁要给导出通道让路
（当前 `wl_tx_valid` 优先级高于 `dbg`，需在 `instrec_top.v:806-816` 增加第三路并明确优先级）。

**golden 侧**：必须显式 `--golden-feat reports/golden_ref/sine_440_full/feat.npy`（uint8，0..255）；
`scripts/outputs/golden/sine_440_full_feat.npy` 是 **int8 全零静音**，用默认路径得到的参考无意义（runbook K-3 / D-3 不变）。

**对拍工具本身已自检通过**（只证明工具、不证明板子）：
`python -m pytest tests/test_compare_layers_selfcheck.py -q` ⇒ **4 passed in 0.55s**。

### 7.3 其余 DEFERRED 项（沿 runbook §8，本次未变化）

| 编号 | 项 | 状态 |
|---|---|---|
| DEF-1 | conv1..probs 逐层数值一致 | **DEFERRED**（§7.1） |
| DEF-2 | 端到端识别结果（top1/置信度） | **DEFERRED**（依赖 DEF-1，且 probs 不上 UART） |
| DEF-3 | HDMI 画面/概率条/频谱 | 不在本任务范围（T9 `ui_demo`） |
| DEF-4 | 连续音频长跑稳定性 | **DEFERRED**（`overflow_warn` 只进 LED，`sys_ctrl.v:331-337`） |
| DEF-5 | 真实权重 → 真实音频识别准确率 | **DEFERRED** |

---

## 8. 偏差与缺陷指认（只指认，未修改任何文件）

| 编号 | 文件:行 | 现象 | 影响 |
|---|---|---|---|
| **D-8** | `src/ctrl/instrec_top.v:216`（声明）、`:672`（连接） | `ddr_dbg_to_state[2:0]` 无任何消费者；`ddr_to_err`(:214)、`ddr_cmd_to_err[3:0]`(:215)、`ddr_wlast_miss_cnt[7:0]`(:217) 同样悬空 | 板上无法区分 §6 的 A/B/C 三分支；也无法确认 `S_WLAST` 是否进入 |
| **D-9** | `src/ctrl/instrec_top.v:641` + `src/ddr3/ddr3_ctrl_axi.v:212-215` | `m1_wdata` 由 `wl_wdata` 直连进 256-bit 组合 mux，**中间无寄存器** | 直接产生 `m1_wdata[212]` 的 2.999 ns 顶层长线，是全局 WNS 决定者；`u_weight_loader/beat_buf[7]`→mux 跨区走线 5.192 ns |
| **D-10** | `src/ctrl/weight_loader.v:287-291` vs `:294-298` | `'K'` ack 依赖 AXI `done`；写通路不可用时上位机看到的是**零回复**，而非 `WERR` | 运维会误判为"串口/帧协议问题"；`weight_upload.py` 只能抛 `frame 0 not acknowledged`，无区分度 |
| **D-11** | `src/ddr3/ddr3_ctrl_axi.v:64`（`AXI_TO_LIMIT=4096`）vs `src/ddr3/ddr3_arbiter.v:91`（`P3_QUOTA_TIMEOUT=125000`） | self_test 的看门狗 32.8 µs，而 arbiter 的 P3 保底强授需要 ~1 ms —— **相差 30 倍** | 若其它 master 长期占用，m3 命令被 grant 后只剩 33 µs 完成 16-beat 读回，余量极小；属预算错配 |
| D-4（沿用） | `scripts/weight_upload.py:17` | docstring 称失败行为 `WERR @<hex> want <x> got <y>`，RTL 实际只打 `WERR <8hex>`（`weight_loader.v:338-340,354`） | 仅影响文案，不影响 `startswith('WOK')` 判定 |

> 纪律遵守说明：`scripts/**`、`src/**`、`constraints/**` **只读**，上述全部为**只指认未改动**。

---

## 9. 风险登记

| 编号 | 风险 | 量化依据 | 处置建议 |
|---|---|---|---|
| **R-1** | **不修 `ddrphy_sysclk` 时序 ⇒ 权重上传永不可能 `WOK`** | 最差 6 条违例路径全部在 `u_weight_loader` 写数据通路，其中 2 条终点为 IP `mcdq_wdp_align/r_data[212]`；`m1_wdata[212]` 净 delay 2.999 ns、Route 占比 88.5% | 在 `instrec_top.v:641` 与 ctrl mux（`ddr3_ctrl_axi.v:212-215`）之间给 `m1_wdata` 加一级寄存器，或在 ctrl 内先对 `m1..m3_wdata` 寄存后再 mux（可把 88.5% route 拆成两段）。**需 leader 决策，本轮不改** |
| **R-2** | **`@00300000` 的归因仍不唯一** | §6 三分支同址；D-8 无导出 | 下一轮诊断把 `dbg_to_state` / `to_err` / `wlast_miss_cnt` / `cmd_to_err[3]` 编入 `diag_uart_report` 帧（模块已存在，`src/diag/diag_uart_report.v`），用 `ddr3_diag` 小顶层（构建 12~20 min）一次定论 |
| **R-3** | `AXI_TO_LIMIT` 与 P3 quota 预算错配（D-11） | 32.8 µs vs 1 ms（30×） | 与 R-2 同轮评估；至少在 m3 保底强授后重置 `axi_to_cnt` |
| **R-4** | 三处悬空观测信号被 `pds_shell`/综合剪掉（D-8） | `:214-217` 全部无消费者 | 随 R-2 一并接线；否则每次板级失败都只能给"地址 = BASE"这一层信息 |

---

## 10. 证据清单

| 产物 | 路径 | 大小 | 说明 |
|---|---|---|---|
| 板级 12 键证据（第 1 轮） | `reports/board_e2e_20261031T080814Z.json` | 12 键 / `verdict=FAIL` | `--json`，UTF-8 无 BOM |
| 板级 12 键证据（第 2 轮重烧） | `reports/board_e2e_20261031T081318Z_run2.json` | 12 键 / `verdict=FAIL` | 与第 1 轮逐字段一致 |
| 串口原始字节（第 1 轮） | `reports/board_e2e/uart_run1_20261031T080814Z.bin` | **49 B** | od 复核三行 |
| 串口原始字节（第 2 轮） | `reports/board_e2e/uart_run2_20261031T081318Z.bin` | **49 B** | 与第 1 轮逐字节相同 |
| T8 串口（已保护，未被覆盖） | `reports/board_e2e/prior_uart_last_20261031T080814Z.bin` | 1,183 B | runbook Step 0.3 备份 |
| 当前 `build/uart_last.bin` | `build/uart_last.bin` | 49 B | = 第 2 轮内容 |
| 时序报告 | `build/pds/20261031-135808-f1cb68bd/report_timing/instrec_top.rtr` | — | §5.3/§5.4 出处 |
| 诊断位流对照 | `build/top_ddr3_diag-latest.json`（`Wns=4.405`）、`reports/ddr3_diag_conclusion.md:395-421` | — | §5.2 对照 |
| PDS 进程 | 无（`pds_shell` 全程未启动） | — | 纪律遵守 |
| JTAG | `cdt_js` = `[9040]`，前后不变 | — | 只复用、未 terminate |

---

## 11. 给 leader 的建议（按序）

1. **不要再用全量位流重试 `weight_upload`** —— 三次实测（含 fresh）全部 `frame 0` 无 ack，且根因路径已量化（R-1）。重试不产生新信息，只消耗下载器寿命。
2. **用 `ddr3_diag` 小顶层做一次「归因实验」**（12~20 min，不占全量槽位）：把 `dbg_to_state`/`to_err`/`wlast_miss_cnt`/`cmd_to_err[3]`
   编进 `diag_uart_report`，并且**在 diag 里复刻全量的多 master 负载**（当前 diag 只有 self_test 一个活跃 master，这正是它与全量最大的行为差异）。目标：唯一定论 §6 的 A/B/C。
3. **R-1 的 RTL 修复需要单独立项**（`m1_wdata` 打拍 / wdata 先寄存后 mux）。若不动 RTL，全量位流的 DDR3 写通路在 −1.740 下不具备可用性，
   T13 验收的「板级 e2e」只能判 **FAIL**，不能判 PASS 或 PARTIAL。
4. 逐层对拍（§7.2）是**独立增强任务**，不应混进本轮；其最小交付是 `layer_export.v` + TX 三路仲裁 + 2.2 min 抓取窗口。