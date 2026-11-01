# T8 · DDR3 诊断位流首轮：构建 + 板级判读 + 根因结论

- 日期：2026-10-31（UTC 05:24:13 起构建，05:30:11 起板级抓取）
- 构建集：`ddr3_diag`（`top_ddr3_diag`，7 个设计源 + 1 个 IDF + 2 个约束）
- 结论一句话：**两套 AXI 配置（design / demo）均 TIMEOUT，但失败原因不是 IP 握手，而是诊断顶层把 `self_test` 的 `cmd_valid` 接到了 master 0（`top_ddr3_diag.v:268`），导致板上跑的是 `m0_cmd=0` 的空读循环；该缺陷只存在于诊断顶层，全量 `instrec_top.v:638` 的拼接是正确的。**

---

## 1. 交付物与证据

### 1.1 位流

| 项 | 值 |
|---|---|
| 产物 | `build/top_ddr3_diag-latest.sbit` |
| SHA-256 | `82095667CB8817491FB693467982FB02D9456C0414256ADE13EDD1081ACE75B5` |
| 位流文件大小 | 3 791 112 B |
| run 目录 | `build/pds/20261031-132415-e884e4dc/` |
| run 目录创建 | 2026-10-31 13:24:15（本地） |
| sbit 写出 | 2026-10-31 13:29:28（本地） |
| **单轮耗时** | **5 min 13 s**（PDS 自报 `compile → gen_bit_stream` = 0h:5m:7s）→ **R1.4 达成，且余量极大（预算 ≤20 min）** |
| PDS ExitCode | 0，`pds.stderr.log` 为空 |

### 1.2 六阶段 StageStatus（`build/top_ddr3_diag-latest.json`）

| Stage | Status |
|---|---|
| compile | OK |
| synthesize | OK |
| dev_map | OK |
| pnr | OK（纯 `pnr`，无任何参数） |
| report_timing | OK |
| gen_bit_stream | OK |

时序与资源：

- `WNS (setup, slow corner) = +4.048 ns`，`WHS (hold, slow corner) = +0.133 ns`
- `LUT 4014/66600 (6%)`、`FF 3680/133200 (3%)`、`DRM 0/155`、`APM 0/240`、`BKCL 3/6`、`IO 84/300`
- 与契约估算（≈3.0 k LUT）同量级；离 53.6% 布线临界点有 47 个百分点余量，**"小位流跑得快"的资源假设成立**

### 1.3 未污染全量产物（R3.3）

| 文件 | 本轮前 | 本轮后 |
|---|---|---|
| `build/instrec-latest.sbit` | 2026-10-31 10:46:16，3 791 112 B | **完全相同**（mtime 与大小均未变） |
| `build/instrec-latest.json` | 2026-10-31 10:46:22，2393 B | **完全相同** |

### 1.4 板级判读

```
python scripts/board_check.py --sbit build/top_ddr3_diag-latest.sbit --port COM5 \
  --seconds 20 --expect "DDR3DIAG" "DDR3SW" "DDR3RS" \
  --json reports/board_ddr3diag_20261031T053011Z.json
```

| 项 | 值 |
|---|---|
| 退出码 | **0**（`boot: PASS (all 3 expected lines seen)`） |
| JSON 证据 | `reports/board_ddr3diag_20261031T053011Z.json`（`verdict = PASS`，`expect_missing = []`） |
| FTDI / JTAG | `ftdi_present = true`，`jtagserver_pids = [9040]`（复用，未新开），`cdt_cfg_pids = []` |
| 编程状态 | `program_ok = true`，`status_raw = 0x081FFCA0`，`done = 1`，`crc_err = 0` |
| 串口 | 1001 B，存入 `build/uart_last.bin` |

### 1.5 前置闸门

| 闸门 | 结果 |
|---|---|
| `python scripts/check_rtl.py` | 49 个 `.v`，**0 violation** |
| `python -m pytest -q` | **390 passed / 4 skipped**，0 failed（70.2 s） |

---

## 2. 串口原始帧（`build/uart_last.bin`，全文 11 行，逐字节原文粘贴）

```
DIAG DDR3DIAG A=00000000 B=00000000 C=00000000 D=00000000 E=00000000 F=00000000 G=00 H=00
DIAG DDR3SW   A=0003D39A B=0003D39A C=00000000 D=0003D399 E=00040300 F=00000000 G=00 H=04
DIAG DDR3SW   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00051F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
DIAG DDR3RS   A=0003FCF9 B=0003FCF9 C=00000000 D=0003FCF9 E=00012F00 F=00000000 G=00 H=04
```

帧数统计：`DDR3DIAG = 1`、`DDR3SW = 2`、`DDR3RS = 8`（共 11 帧，无截断、无乱码、无小写）。

> 偏差 D-01：`DDR3DIAG` 只有 1 帧，而 plan §3.1 T8 验收第 6 条要求 ≥3 帧。
> 原因：`top_ddr3_diag.v` 的 `ST_WAIT_INIT` 在 `init_frame_sent` 置 1 后**只在 `ddr_ready` 之前每 25 ms 继续发帧**（`top_ddr3_diag.v:594-624`）；本板 `ddr_ready` 很快到，因此只发出 1 帧。
> 不影响 A..H 判读（A..H 全 0，正是 `ST_WAIT_INIT` 的初值），但与契约"每 25 ms 发一帧"的语义不一致，建议 T4 一并澄清。

---

## 3. 帧字段解码

### 3.1 两套配置的结论

| 源帧 | 轮次 | `cfg_demo` | `round_cnt` | `result_a`（design） | `result_b`（demo） |
|---|---|---|---|---|---|
| `DDR3SW` #1 | 第 1 轮结束 | 0（design：`AXI_USER_AP=1`，`DUMMY_WSTRB_ALL1=0`） | 0 | **TIMEOUT(3)** | NONE |
| `DDR3SW` #2 | 第 2 轮结束 | 1（demo：`AXI_USER_AP=0`，`DUMMY_WSTRB_ALL1=1`） | 1 | TIMEOUT | **TIMEOUT(3)** |
| `DDR3RS` ×8 | 定格结论 | 1（末轮为 demo） | **2（两轮都已结束）** | **TIMEOUT** | **TIMEOUT** |

判读细节已按任务要求处理：
① `cfg_stage` 只有 2 位，`ST_DONE = 3'd4` 被截断成 `00`，因此用 `round_cnt == 2` 判定"两轮均已结束"（`DDR3RS` 帧 `E[15:12] = 2` ✔）；
② `wait_cnt`/P3 等待计数在被服务期仍递增，本报告不把它作为"卡住"证据。

### 3.2 最后一次 `DDR3RS` 帧的逐位展开（`E = 0x00012F00`）

| 字段 | 值 | 含义 |
|---|---|---|
| `to_err` | **0** | 控制器**从未**触发 4096 拍 AXI 看门狗 |
| `cmd_to_err3` | **0** | master 3 从未超时 |
| `dbg_to_state` | **0（S_IDLE）** | 超时从未发生（该寄存器只在超时分支写入，复位值 0） |
| `addr_err3` | 0 | 无非法地址 |
| `st_done` / `st_fail` | **0 / 0** | `self_test` 既没完成也没报失败 |
| `result_a` / `result_b` | 3 / 3 | 两轮均 TIMEOUT |
| `round_cnt` | 2 | 两轮都结束 |
| `cfg_demo` | 1 | 末轮为 demo |
| `cfg_stage` | 0 | `ST_DONE(4)` 被 2 位截断 → 00 |
| `wlast_miss_cnt` | **0** | `S_WLAST` epilogue **从未执行过**（它只在真实写完成后进入） |
| `F`（`st_fail_addr`） | 0 | TIMEOUT 路径不锁存地址 |
| `G = 0x00` | `dbg_to_state = 0` | 同上 |
| `H = 0x04` | `st_cv=1, st_wbe_q=0, st_rd_valid=0, st_fail=0, st_done=0` | **`self_test` 的 `cmd_valid` 一直为 1，且上一拍没有 `wready_beat`、没有 `rd_valid`** |

### 3.3 A / B / C / D 四个握手计数（IP 侧）

| 轮次 | A `aw_hit_cnt`（`awvalid&&awready`） | B `wready_cnt`（`wready` 高拍） | C `done_cnt`（`done[3]` 脉冲） | D `rvalid_cnt` |
|---|---|---|---|---|
| design（第 1 轮） | 0x3D39A = **250 778** | 0x3D39A = **250 778** | **0** | 0x3D399 = **250 777** |
| demo（第 2 轮） | 0x3FCF9 = **261 369** | 0x3FCF9 = **261 369** | **0** | 0x3FCF9 = **261 369** |

---

## 4. 根因判定

### 4.1 五条不可辩驳的观测事实

1. **`A == B == D` 精确相等**（design 轮 250 778/250 778/250 777，只差最后一笔的边界效应；demo 轮三者完全相等）。
   `A`、`B`、`D` 三个计数器含义完全不同（AW 握手、`wready` 高电平拍、`rvalid` 高电平拍），能在 10⁵ 量级上精确相等，只有一种物理解释：**每一个 AXI 微事务恰好产生 1 拍 AW、1 拍 W、1 拍 R**，即 **`len == 0` 的单拍事务**。
2. `250 778 × 49.8 ≈ 261 369 × 47.8 ≈ 12 500 000 = 125 MHz × 100 ms`。也就是说 **100 ms 看门狗窗口里完整跑完了 25~26 万个单拍事务**，且**每一次都成功完成**（否则 `to_err` 会置位）。
3. **`C = done[3] = 0`**：控制器一次也没有把 `done` 脉冲路由到 master 3。
4. **`to_err = 0`、`cmd_to_err3 = 0`、`dbg_to_state = 0(S_IDLE)`、`addr_err3 = 0`、`wlast_miss_cnt = 0`**：所有 4096 拍看门狗都**从未触发**，`S_WLAST` epilogue **从未进入**，即**真实 16-beat 写通路（S_AW → S_W → S_WLAST）根本没有被激励**。
5. **`H = 0x04` → `st_cv = 1`**：`self_test.cmd_valid` 始终保持高（它被设计为"保持到 done"），说明 `self_test` 卡在 `ST_WCMD`/`ST_WDATA`/`ST_RCMD`/`ST_RDATA` 之一，等一个永远不来的 `wready_beat[3]` / `done[3]` / `rd_valid[3]`，最终由顶层 100 ms 看门狗判 TIMEOUT。

### 4.2 唯一自洽的假设：`self_test` 被挂到了 master 0

`src/diag/top_ddr3_diag.v:268`：

```verilog
wire [3:0] st_cmd_valid = {3'b000, st_cv};     // bit0 = st_cv  → master 0
```

而完成信号全部按 **bit3** 取回（同文件 271-274 行）：

```verilog
wire st_done_in  = cfg_demo ? done_b[3]        : done_a[3];
wire st_wbe_in   = cfg_demo ? wready_beat_b[3] : wready_beat_a[3];
wire st_rd_data  = cfg_demo ? rd_data_3_b      : rd_data_3_a;
wire st_rd_valid = cfg_demo ? rd_valid_b[3]    : rd_valid_a[3];
```

`self_test` 的命令数据接在 `m3_cmd`（`top_ddr3_diag.v:388`、`439`），但它的 `cmd_valid` 落在 **bit0**，因此：

- arbiter 看到的是 **master 0 有 pending 命令**，而该顶层的 `m0_cmd = 37'd0`（`top_ddr3_diag.v:385`、`436`，`{wr=0, addr=0, len=0}`）→ 控制器执行一条"**地址 0、len=0 的读**"；
- `ddr3_ctrl_axi` 对读命令先做 **dummy write**（`S_DW_AW → S_DW_W`）再读（`S_AR → S_R`），正好一拍一个：**1 次 AW + 1 次 W + 1 次 rvalid** —— 与观测事实 (1) 的 `A == B == D` 完全对应；
- 每次完成的 `done` 脉冲是 `4'b0001 << cur_master = done[0]`，而 `st_done_in` 取 `done[3]` → **`C = 0`**，`self_test` 永远等不到 `wready_beat[3]`；
- 每个事务都正常完成 → **`to_err = 0`、`dbg_to_state = 0`**（与事实 4 完全一致）；
- 该缺陷与 `AXI_USER_AP` / `DUMMY_WSTRB_ALL1` 都无关 → **两套 cfg 同时 TIMEOUT**（与观测一致）。

### 4.3 模型实证（零构建、`build/repro_st_cmd_valid.py`）

用 T1 交付的冻结周期模型 `tests/ddr3_ctrl_model.py` 复现两种接线（各 50 000 拍）：

```
--- as built: cmd_valid={3'b000, st_cv} -> master 0, m0_cmd=0 (read) ---
  A aw_hit_cnt            : 7143
  B wready_cnt            : 7143
  C done[3] cnt           : 0
  D rvalid_cnt            : 7143
  done per master         : [7143, 0, 0, 0]
  wready_beat per master  : [0, 0, 0, 0]
  to_err=0 dbg_to_state=0 wlast_miss=0 addr_err_sticky=[0, 0, 0, 0]
  A == B == D             : True

--- hypothetical fix: cmd_valid={st_cv, 3'b000} -> master 3, 16-beat write ---
  A aw_hit_cnt            : 2273
  B wready_cnt            : 36366
  C done[3] cnt           : 2272
  D rvalid_cnt            : 0
  done per master         : [0, 0, 0, 2272]
  wready_beat per master  : [0, 0, 0, 36366]
  to_err=0 dbg_to_state=0 wlast_miss=0 addr_err_sticky=[0, 0, 0, 0]
  A == B == D             : False
```

**缺陷版模型输出与板上帧逐项一致**（`A==B==D`、`C=0`、`to_err=0`、`dbg_to_state=0`、`wlast_miss=0`);
**修复版模型立刻出现 `done[3]` 与 `wready_beat[3]`**。板上/模型的事务周期分别为 47.8 拍与 7.0 拍（差异来自真 IP 的 DDR3 时序 vs 零延迟 stub），**比例关系不变**。

### 4.4 对照 plan §2.3.1 失败模式表

| §2.3.1 行 | 判据 | 本次是否命中 |
|---|---|---|
| 第 1 行 `DDR3 ERR @FFFFFFFF`（100 ms 无 `st_done`/`st_fail`）→ `self_test` 卡死 | 无 done/fail | **现象命中，但根因不是 `self_test` 本身**（T2 已修好 F1~F7），而是**诊断顶层把它接到 master 0** |
| 第 2 行 `to_err=1` 且 `dbg_to_state=1`(S_AW) | `to_err=1` | ✗ 未命中（`to_err=0`） |
| 第 3 行 `to_err=1` 且 `dbg_to_state=2`(S_W) | `to_err=1` | ✗ 未命中 |
| 第 4 行 `to_err=1` 且 `dbg_to_state=4/5`（dummy write） | `to_err=1` | ✗ 未命中；且**两种 dummy-write 策略都在板上成功运行 26 万次**，可反向排除 |
| 第 5 行 `to_err=1` 且 `dbg_to_state=6/7`（AR/S_R） | `to_err=1` | ✗ 未命中；且 1-beat 读的 `rlast` 正常到达（否则 `to_err` 会置位） |
| 第 6 行 `st_fail=1` 且 `st_fail_addr ≠ 0` | `st_fail=1` | ✗ 未命中（`st_fail=0`） |

**结论：本次现象不落在 §2.3.1 任何一行的"握手卡死"语义上，而是一类新的失败层——"被测端点接错"**（属于 §2.3.1 未覆盖的第 0 层：wire 级映射）。

### 4.5 对全量 `instrec_top` 的含义（重要）

`src/ctrl/instrec_top.v:638`：

```verilog
assign ddr_cmd_valid = {st_cmd_valid, mel_m2_cmd_valid,
                        (wl_busy ? wl_cmd_valid : npu_rd_cmd_valid_u), m0_cmd_valid};
```

`st_cmd_valid` 位于 **bit3** ✔，`instrec_top.v:757` 的 `done (ddr_done[3])`、`rd_valid (ddr_rd_valid[3])` 也取 bit3 ✔。
**全量顶层的主口映射是正确的，不受本缺陷影响**；全量当前的 `DDR3 ERR @FFFFFFFF` 应归因于 T2 修复前的 `self_test` 卡死（done 未监听），T2 已按 `C-SELFTEST@1` 修好。

但**本轮板级数据仍然没有覆盖真实写通路**（见 4.1 事实 4），所以**不能**据此断言"全量跑一遍就会 `DDROK`"。

---

## 5. 本轮已排除 / 未覆盖（`C-TOP-DDR3-DIAG@1` 的双 cfg 扫描价值）

| 结论 | 依据 |
|---|---|
| **排除** IP 不接受 `awvalid`（§2.3.1 第 2 行的"AW 未被接受"） | dummy-write 的 AW 在两套 cfg 下各成功 25~26 万次，`to_err=0` |
| **排除** `axi_awuser_ap` 极性错误 | `AXI_USER_AP=1`（design）与 `=0`（demo）**同样通过**，各 25 万次 AW 握手 |
| **排除** dummy-write 的 `wstrb` 策略问题（§2.3.1 第 4 行） | `DUMMY_WSTRB_ALL1=0`（全 mask）与 `=1`（全 1）**同样通过**各 25 万次 W 握手 |
| **排除** 1-beat 读的 `rlast` 缺失 | demo 轮 `D = A` 且 `to_err=0`；若 `rlast` 不来，`S_R` 会在 4096 拍后置 `to_err` |
| **排除** 地址非法（`addr_err`） | `addr_err3 = 0`，两轮均无 |
| **未覆盖** 真实 16-beat 写（`S_AW → S_W → S_WLAST`） | `wlast_miss_cnt = 0`、`wready_beat[3] = 0`，该通路从未被激励 |
| **未覆盖** 16-beat 读 burst（`rlast` 出现在第 16 拍的语义） | 只跑了 `len=0` 的 1-beat 读 |
| **未覆盖** `self_test` 的数据比对 / `st_fail_addr` 路径 | `self_test` 根本没推进 |

---

## 6. 下一步动作（明确）

### 6.1 首选：不进 T10，先修 1 行 + 重跑一轮 `ddr3_diag`（约 6 分钟）

| 项 | 内容 |
|---|---|
| 改动 | `src/diag/top_ddr3_diag.v:268`：`wire [3:0] st_cmd_valid = {3'b000, st_cv};` → **`wire [3:0] st_cmd_valid = {st_cv, 3'b000};`**（1 行，与 271-274 的 `[3]` 取用对齐） |
| 归属 | **T4（诊断顶层-沈工）**，T8 只读，不越权改源 |
| 重跑 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet ddr3_diag` |
| 实测成本 | **5 min 13 s**（本轮实测），远低于 20 min 预算 |
| 预期收益 | 拿到 `self_test` 真实 16-beat 写 + 16-beat 读 + 比对结果；这是**唯一能证明"全量会 `DDROK`"的证据** |

> 契约侧同步澄清：`plan.md §2.2.4` 的"上游使能"示例原文就是
> `wire [3:0] st_cmd_valid = {3'b000, st_cv};`，注释却写"self_test 只占 master 3"。
> **这是契约笔误，T4 是照抄契约**，不是自己发明的错误。建议 leader 在 §2.2.4 修正示例代码并加一条自检项（"`cmd_valid` 的置位与 `done/wready_beat/rd_valid` 的下标必须是同一个 master 位"）。

### 6.2 备选：直接进 T10（不推荐，但有条件可行）

- 前提：**全量接线已正确**（`instrec_top.v:638/757` 均为 bit3），T10 **不应**照搬本缺陷；
- T10 真正的改动容差应只是"带上 T2 已修的 `self_test`"，无需再改 `ddr3_ctrl_axi` 参数（本轮已证明两套参数都能跑通基础链路）；
- 风险：全量 1.5 h 一轮，若 16-beat 写/读通路另有问题（如 `S_WLAST` epilogue、16-beat `rlast` 位置），将**再浪费 1.5 h**，且没有诊断能力回退。

### 6.3 O1 状态：**已触发**（两轮均 TIMEOUT，`dbg_to_state` 同为 S_IDLE）

若 6.1 的修正版**仍然** TIMEOUT，下一轮（12~20 min，不重写契约）要加的计数器清单（按优先级）：

| # | 计数器 / 字段 | 目的 | 落位建议 |
|---|---|---|---|
| 1 | `self_test` 的 `state[2:0]` | 直接看卡在 `ST_WCMD/ST_WDATA/ST_RCMD/ST_RDATA` 哪一个 | `E[23:19]` 保留位（5 位，够） |
| 2 | `self_test.beat_idx[3:0]` + `cmd_idx[2:0]` | 看 burst 推进到第几拍 / 第几条命令 | `E[23:19]` 剩余的 2 位 + 周期帧 `tag=0` 的 `F` |
| 3 | 控制器**实时** `state[2:0]`（区别于只在超时锁存的 `dbg_to_state`） | 看是否在 `S_W` 长期等 `wready` 而非超时 | 新增一个周期帧字段（`tag=0` 的 `G`） |
| 4 | `cur_master[1:0]` + `grant[3:0]` | 一次性抓出"命令归属错位"这一类缺陷（本轮就是它） | `H[7:5]` 空位 + `F` |
| 5 | `wready_beat[3]` 脉冲累计 | 与 `done[3]` 对照，分辨"beat 到了但 done 没到" | `A` 的兄弟字段（周期帧） |
| 6 | `axi_arvalid && axi_arready` 累计（`ar_hit_cnt`） | 补齐 AR 阶段（本轮 A/B/D 只覆盖 AW/W/R） | 周期帧新增 |
| 7 | `axi_rlast` 累计 | 分辨"rvalid 有、rlast 不到"这一已知盲点 | 周期帧新增 |
| 8 | `axi_wusero_last` 累计（IP 侧写完成 side-evidence） | 验证 `S_WLAST` epilogue 的真实前提 | `wlast_miss_cnt` 旁 |
| 9 | `st_rd_valid[3]` / `st_done_in` 累计 | 分辨读通路与完成路由 | 周期帧 |

**第 4 项是本轮教训的直接产物**：若首轮就有 `cur_master`/`grant` 计数，本次根因可以在一帧内读出。

---

## 7. 偏差与源码侧缺陷登记

| 编号 | 位置 | 现象 | 归属 |
|---|---|---|---|
| **D-01** | `src/diag/top_ddr3_diag.v:268` | `st_cmd_valid = {3'b000, st_cv}` 使 `self_test` 成为 **master 0**，而完成信号全部取 `[3]` → 板上跑的是 `m0_cmd=0` 的空读循环，两轮 TIMEOUT | **T4**（契约 §2.2.4 同错，建议 leader 一并修契约） |
| D-02 | `src/diag/top_ddr3_diag.v:594-624` | `DDR3DIAG` 只发 1 帧（`init_frame_sent` 后仅 `ddr_ready` 前续发），与 plan "每 25 ms 一帧" 不一致，导致 T8 验收第 6 条（≥3 帧）不满足 | T4 |
| D-03 | `plan.md §2.2.4` | 上游使能示例代码自相矛盾（`{3'b000, st_cv}` vs 注释 "只占 master 3"） | leader / 契约 |

> 本轮**未修改任何源码**（`src/**`、`scripts/**`、`constraints/**` 全程只读）；新增文件仅
> `build/analyze_ddr3diag.py`、`build/repro_st_cmd_valid.py`（临时分析脚本，按要求放在 `build/` 下）。

---

## 8. 证据索引

| 文件 | 内容 |
|---|---|
| `build/top_ddr3_diag-latest.sbit` | 本轮位流，SHA-256 `82095667…75B5` |
| `build/top_ddr3_diag-latest.json` | 六阶段 OK / WNS +4.048 / LUT 6% / SHA-256 |
| `build/pds/20261031-132415-e884e4dc/pds.stdout.log` | PDS 全量日志（run 目录内） |
| `reports/build_20261031-132415-e884e4dc.pds.stdout.log` | 归档日志 |
| `reports/board_ddr3diag_20261031T053011Z.json` | `board_check` 判读证据，`verdict=PASS` |
| `build/uart_last.bin` | 1001 B 串口原始抓取（11 帧） |
| `build/analyze_ddr3diag.py` | 帧解析 + `E/F/G/H` 解码（复现用） |
| `build/repro_st_cmd_valid.py` | 缺陷接线 vs 修复接线的周期模型对拍（4.3 节输出） |

---

## 9. 复现命令（全部在 `instrec_fpga/` 下）

```powershell
# 1) 构建（5 min 13 s，实测）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet ddr3_diag

# 2) 板级判读
python scripts/board_check.py --sbit build/top_ddr3_diag-latest.sbit --port COM5 `
  --seconds 20 --expect "DDR3DIAG" "DDR3SW" "DDR3RS" `
  --json reports/board_ddr3diag_<UTC>.json

# 3) 帧解析（临时脚本在 build/，不在 scripts/）
python build/analyze_ddr3diag.py --hex

# 4) 根因离线复现（零构建，约 20 s）
python build/repro_st_cmd_valid.py 50000
```
---

# 第二轮（D-01 / D-02 修复后）· 2026-10-31

> 第一轮记录全部保留在上面。本轮只做「修复 → 重跑 → 判读」，不改任何源码。

## 10.1 前置核对（30 s）

| 项 | 结果 |
|---|---|
| `grep -n "st_cmd_valid" src/diag/top_ddr3_diag.v` | **`282: wire [3:0] st_cmd_valid = {st_cv, 3'b000};`** ✔ D-01 已修（self_test 真正在 master 3，与 `done[3]`/`wready_beat[3]`/`rd_valid[3]`/`rd_data_3_*` 下标一致） |
| `init_frame_cnt` 逻辑 | `top_ddr3_diag.v:615` `if ((init_frame_cnt >= 4'd3) && ddr_ready)`、`:639` 饱和在 3 ✔ D-02 已修 |
| `tasklist \| grep pds_shell` | 空 ✔ |
| `check_rtl.py` | 49 个 `.v`，0 violation |
| `pytest -q` | **398 passed / 4 skipped**，0 failed（57.0 s） |
| `cdt_js` | 单实例 PID 9040（全程复用，未新开、未 terminate） |

## 10.2 构建（第二轮）

| 项 | 值 |
|---|---|
| run 目录 | `build/pds/20261031-134355-6532cf6c/` |
| 创建 → sbit 写出 | 13:43:55 → 13:48:32 ⇒ **4 min 37 s**（PDS 自报 4m39s） |
| 六阶段 | compile / synthesize / dev_map / pnr / report_timing / gen_bit_stream **全 OK**（纯 `pnr`） |
| **新 SHA-256** | **`F749A41768C31AE57AFC2ACE0B1C075CB35110056BB6A863408B5CFF2402266F`** |
| WNS / WHS | **+4.405 ns / +0.298 ns** |
| 资源 | LUT **4954/66600 (7%)**、FF 4359 (3%)、Distributed RAM 284 (2%)、DRM 0、BKPM 0、BKCL 3/6 |
| R3.3 | `build/instrec-latest.sbit` = 2026-10-31 10:46:16 / 3 791 112 B、`.json` = 10:46:22 / 2393 B —— **与第一轮及本轮之前完全相同** ✔ |

> LUT 从 4014 → 4954（+940）：D-01 修正后 `self_test` 的 37 位命令与比对逻辑、`S_WLAST`/burst 相关逻辑才真正被例化进 master 3 通路，属预期增量；7% 仍远低于 53.6% 布线临界点。

## 10.3 板级（第二轮）

```
python scripts/board_check.py --sbit build/top_ddr3_diag-latest.sbit --port COM5 \
  --seconds 25 --expect "DDR3DIAG" "DDR3SW" "DDR3RS" \
  --json reports/board_ddr3diag2_20261031T054946Z.json
```

| 项 | 值 |
|---|---|
| 退出码 | **0**（`boot: PASS (all 3 expected lines seen)`） |
| JSON | `reports/board_ddr3diag2_20261031T054946Z.json`，`verdict=PASS`，`expect_missing=[]` |
| 编程 | `program_ok=true`，`status_raw=0x081FFCA0`，`done=1`，`crc_err=0` |
| 串口 | **1183 B**（比第一轮多 182 B），`build/uart_last.bin` |
| **帧数** | **`DDR3DIAG = 3`** ✔（D-02 验证通过） / `DDR3SW = 2` / `DDR3RS = 8`，共 13 行，无截断无乱码 |

### 原始帧（逐字节原文）

```
DIAG DDR3DIAG A=00000000 B=00000000 C=00000000 D=00000000 E=00000000 F=00000000 G=00 H=00
DIAG DDR3DIAG A=00000000 B=00000000 C=00000000 D=00000000 E=00000000 F=00000000 G=00 H=00
DIAG DDR3DIAG A=00000000 B=00000000 C=00000000 D=00000000 E=00000000 F=00000000 G=00 H=00
DIAG DDR3SW   A=00000010 B=00000088 C=00000010 D=00000080 E=08040140 F=00000000 G=00 H=10
DIAG DDR3SW   A=00000009 B=00000081 C=00000008 D=00000003 E=08051980 F=00300000 G=00 H=08
DIAG DDR3RS   A=00000009 B=00000081 C=00000008 D=00000003 E=08012980 F=00300000 G=00 H=08
   （DDR3RS 其余 7 帧与上一行完全相同，共 8 帧）
```

### 帧解码

| 帧 | `cfg_demo` | `round_cnt` | `result_a` | `result_b` | `st_done`/`st_fail` | `to_err` | `dbg_to_state` | `wlast_miss_cnt` | `F`(fail addr) | `H` |
|---|---|---|---|---|---|---|---|---|---|---|
| `DDR3SW` #1（design 轮） | 0 | 0 | **PASS(1)** | NONE | **1 / 0** | 0 | 0 (S_IDLE) | **8** | 0 | `0x10` = `st_done=1` |
| `DDR3SW` #2（demo 轮） | 1 | 1 | PASS(1) | **FAIL(2)** | 0 / **1** | 0 | 0 (S_IDLE) | **8** | **`0x0030_0000`** | `0x08` = `st_fail=1` |
| `DDR3RS` ×8（定格） | 1 | **2** | **PASS(1)** | **FAIL(2)** | 0 / 1 | 0 | 0 | **8** | **`0x0030_0000`** | `0x08` |

`E` 逐位展开：

- `DDR3SW`#1 `E = 0x08040140` → `to_err=0`, `cmd_to_err3=0`, `dbg_to_state=0`, `addr_err3=0`, `st_done=1`, `st_fail=0`, `result_a=1`, `result_b=0`, `round_cnt=0`, `cfg_demo=0`, `cfg_stage=0`, `wlast_miss_cnt=8`
- `DDR3SW`#2 `E = 0x08051980`，`DDR3RS` `E = 0x08012980` → 二者只差 `round_cnt`（1 vs 2）；`st_fail=1`, `result_a=1`, `result_b=2`, `cfg_demo=1`, `wlast_miss_cnt=8`

### A / B / C / D 与第一轮对比（本轮核心判据）

| 轮次 | `result` | A `aw_hit_cnt` | B `wready_cnt` | C `done_cnt` | D `rvalid_cnt` | `wlast_miss_cnt` |
|---|---|---|---|---|---|---|
| **第一轮** design（端点接错） | TIMEOUT | 250 778 | 250 778 | **0** | 250 777 | **0** |
| **第一轮** demo（端点接错） | TIMEOUT | 261 369 | 261 369 | **0** | 261 369 | **0** |
| **第二轮 design（`u_ctrl_design`：`AXI_USER_AP=1`、`DUMMY_WSTRB_ALL1=0`）** | **PASS** | **16** | **136** | **16** | **128** | **8** |
| **第二轮 demo（`u_ctrl_demo`：`AXI_USER_AP=0`、`DUMMY_WSTRB_ALL1=1`）** | **FAIL** | 9 | 129 | 8 | 3 | 8 |

**四个计数逐项自洽，证明 16-beat 真实写/读通路首次被真正激励**：

- `A = 16` = 8 条写命令的 AW + 8 条读命令的 dummy-write AW（`self_test` 发 8 写 + 8 读，`cmd_idx 0..7`）
- `B = 136` = 8 写 × **16 beats** = 128，加 8 次 dummy beat = 8 ⇒ **136**（第一轮 `B` 与 `A` 相等是「每事务仅 1 拍」的端点接错特征，本轮彻底消失）
- `C = 16` = 8 次写 done + 8 次读 done（**`done[3]` 首次非 0**）
- `D = 128` = 8 条读 × **16 beats** = 128（1-beat 读时是 3/250 万，现在是完整 burst）
- `wlast_miss_cnt = 8` = 8 次真实写各进一次 `S_WLAST` epilogue（**`S_WLAST` 首次被进入**）
- `A` 由 25 万 → **16**、`C` 由 0 → **16**、`wlast_miss` 由 0 → **8**：三项「写通路是否被激励」的判据**全部命中**

## 10.4 本轮结论

### (1) design 配置 PASS —— DDR3 真实数据通路完整正确

`result_a = PASS` 意味着 `self_test` 跑完 **8 条 16-beat 写 + 8 条 16-beat 读 + 逐拍数据比对**全对，且 `st_fail_addr = 0`、`to_err = 0`、`cmd_to_err3 = 0`、`addr_err3 = 0`。
即：**DDR3 IP 的写数据、读数据、位序、地址映射、`rlast` 语义在 125 MHz core_clk 下全部正确**，`ddr3_ctrl_axi` 的 `S_AW → S_W → S_WLAST → S_AR → S_R` 全链可用。

### (2) demo 配置 FAIL —— 属"非默认参数的预期代价"，不是缺陷

- `result_b = FAIL`，`F = 0x00300000` = `SELFTEST_BASE + (cmd_idx<<9)`，`cmd_idx = 0` ⇒ **第 1 条读命令**即数据比对不符；`C = 8` 说明 8 次写全部完成（写通道 OK），`D = 3` 说明读到第 3 拍即 mismatch。
- demo 与 design 同时差两个参数（`AXI_USER_AP 1→0`、`DUMMY_WSTRB_ALL1 0→1`），**本轮无法单独归因**。
- 其中 `DUMMY_WSTRB_ALL1=1` 的语义在 `ddr3_ctrl_axi.v:59-61` 注释里已写明：`0 = all strobes masked (design doc, **no memory data destroyed**)`、`1 = full strobes with zero data (verified pds_cpu_100h bridge form)`。dummy-write 的地址是**当前读命令的目标地址**（`S_DW_AW` 时 `axi_awaddr = cur_addr`），因此"全 1 strobe + 全 0 数据"必然覆写被读区域的首拍数据 → 读比对失败。
- **结论：demo 的 FAIL 与 design 的 PASS 不矛盾，反而互相印证 `DUMMY_WSTRB_ALL1=0`（masked）是正确策略。**

### (3) `wlast_miss_cnt = 8` 的定性（观察项，不阻塞）

- 8 次真实写，每次进入 `S_WLAST` 的 4 拍窗口后都**没有**看到 IP 的 `axi_wusero_last` ⇒ 计数 8。两套 cfg 相同（都 8）。
- `wlast_seen` 只参与计数，**不参与完成判定**（`write_cmpl = (state==S_W) && axi_wready && beat_cnt==cur_len`，`ddr3_ctrl_axi.v:247`），因此 **design 仍 PASS，无功能影响**。
- 若后续要消除该观测，需要把 `S_WLAST` 的 `wlast_window` 从 3 拍加长，但那属于改 `ddr3_ctrl_axi.v` 时序（超出 §2.2.8 L2 的"仅参数默认值"容差），**不建议在 T10 动**。

### (4) 第一轮 vs 第二轮：D-01 根因被实验证实

第一轮断言的「`st_cmd_valid = {3'b000, st_cv}` ⇒ self_test 挂 master 0 ⇒ 每 48 拍一次 `m0_cmd=0` 空读 ⇒ `A==B==D`、`C=0`、`to_err=0`、两轮 TIMEOUT」在本轮**逐条被反向证实**：修成 `{st_cv, 3'b000}` 后，`A≠B`、`C=16`、`D=128`、`wlast_miss=8`、design PASS。

## 10.5 是否可进 T10 —— **可以**

**判据**：至少一套配置 PASS（`result_a = PASS`）且 `wlast_miss_cnt > 0`（= 8）⇒ **两条均满足**。

### 全量侧已逐项核对（只需带 T2 的 `self_test` 修复，无需改接线/参数）

| 核对项 | 位置 | 结果 |
|---|---|---|
| `u_self_test` 的 `cmd_valid` 在 master 3 | `src/ctrl/instrec_top.v:638` `ddr_cmd_valid = {st_cmd_valid, mel_m2_cmd_valid, (wl_busy ? wl_cmd_valid : npu_rd_cmd_valid_u), m0_cmd_valid}` | ✔ `st_cmd_valid` 在 **bit3**，与 `:746-757` 的 `done(ddr_done[3])`、`rd_valid(ddr_rd_valid[3])`、`rd_data(rd_data_3)` 一致 |
| 控制器参数 | `src/ctrl/instrec_top.v:645` `ddr3_ctrl_axi u_ddr3_ctrl_axi (...)` **无参数覆盖** | ✔ 使用默认值 `AXI_USER_AP = 1'b1`、`DUMMY_WSTRB_ALL1 = 1'b0`（`src/ddr3/ddr3_ctrl_axi.v:58,62`）= **板上 PASS 的 design 配置** |
| 主口映射 | m0=audio / m1=NPU 权重 / m2=mel / m3=self_test | ✔ 与 `instrec_top.v:638-639` 拼接顺序一致 |
| 全量源集 | `build_sets.json` 的 `full` 含 `src/ctrl/self_test.v`（T2 修复版）、**不含** `src/diag/*.v` | ✔ 诊断顶层不会进全量 |

### 因此对 T10 的具体建议

1. **改动行数可以做到 0 行**：`instrec_top.v` 与 `ddr3_ctrl_axi.v` 均**无需改动**，只要 T2 的 `src/ctrl/self_test.v` 修复已在工作区（已在，本轮 pytest 398 passed 覆盖）。
2. T10 的 diff 应只包含「`self_test.v`（T2 交付）」，`instrec_top.v` 与 `ddr3_ctrl_axi.v` **保持原样**，仍然满足 §2.2.8 L1/L2 容差。
3. 全量构建后板级期望：`DDR3 SELFTEST` → **`DDROK`**（`st_done` 路径），且 `weight_upload.py` 能拿到 `WOK`（权重写走 m1 真实 16-beat 写，本轮已证写通道可用）。
4. 唯一保留风险：全量 LUT 52%（m3d）+ T2 修复的增量（本诊断轮 +940 LUT 中含顶层改动，纯 `self_test` 增量更小），仍低于 53.6% 临界点，但不宽裕 —— 仍按「纯 `pnr`、一次一轮」执行。

### 若仍有问题（不需要，仅备查）

本轮已把上一轮 O1 清单的前 4 项（`cur_master`/`grant`、`self_test.state`、`beat_idx`、`wready_beat[3]` 计数）用**实际脉冲计数**替代验证完毕（`A/B/C/D + wlast_miss` 足够判读），**O1 本轮不再需要触发**。

## 10.6 本轮证据索引

| 文件 | 内容 |
|---|---|
| `build/top_ddr3_diag-latest.sbit` | 第二轮位流，SHA-256 `F749A417…266F` |
| `build/top_ddr3_diag-latest.json` | 六阶段 OK / WNS +4.405 / LUT 4954 / SHA-256 |
| `build/pds/20261031-134355-6532cf6c/pds.stdout.log` | PDS 全量日志 |
| `reports/build_20261031-134355-6532cf6c.pds.stdout.log` | 归档日志 |
| `reports/board_ddr3diag2_20261031T054946Z.json` | 板级判读证据（`verdict=PASS`，1183 B 抓取） |
| `build/uart_last.bin` | 1183 B 串口原始抓取（13 帧） |
| `build/analyze_ddr3diag.py` | 帧解析（两轮通用，`--hex` 输出全字段） |