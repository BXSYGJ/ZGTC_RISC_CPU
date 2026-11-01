# T29 三个仿真 TB 判据/驱动修复结论

> 日期：2026-11-01　分支：XSY　执行环境：Windows + Verilator 5.050（`H:\GG\bin\verilator.bat`）
> 约束遵守：只改 `sim/tb_ctrl_smoke.sv`、`sim/tb_npu_chain.sv`、`sim/tb_weight_loader.sv`；
> **未改任何 `src/**`**；未改 `sim/run_sim.py`；未改已 PASS 的 `self_test`/`ui_render`/`ddr3_subsys`。
> RTL 缺陷只在本报告中给出「文件+行号+机理+建议改法」，修复验证用的是 `build/` 下的临时副本。

## 0. 最终结果

| case | 修复前 | 修复后 | 判定 |
|---|---|---|---|
| `ctrl_smoke` | 0/6 PASS | **PASS 6/6** | 4 处均为 **TB 错**，RTL 正确 |
| `npu_chain` | watchdog（`gap_in=16384 gap_out=0`） | **PASS 4/4** | 1 处 **TB 错**，`gap_unit` 正确 |
| `weight_loader` | 6/12 PASS | **8/10 PASS（FAIL）** | 5 处 **TB 错已修**；剩余 2 项是 **RTL 缺陷**，TB 判据本身正确 |

全量回归（`python sim/run_sim.py all --jobs 2`，102.6 s）：**5 PASS / 4 FAIL**
（`self_test` / `ctrl_smoke` / `npu_chain` / `ui_render` / `ddr3_subsys` PASS；
`conv1` / `mel` / `mel_credit` / `weight_loader` FAIL）。三个原本 PASS 的 TB 未受影响。

### 最重要的两条结论

1. **T21 已获得 RTL 级证明**：`st_done` 在 `st_start` 后第 50 周期返回，远早于
   `DDR3 SELFTEST...` 行 17×12000 = 204k 周期的忙窗口结束，而 `DDROK` 仍然被打印，
   最终 `sys_run=1 / safe_err=0`。**「结论行不被 `dbg_busy` 丢弃」不再是模型推断，而是 RTL 实测。**
2. **`weight_loader` 的 `WOK` 主路径（写→读回→digest）已被仿真证明可用**，
   但 **`WOK <8hex>\n` 这条文本在 `uart_tx` 上每两个字符丢一个**，
   这正是板级「`WOK` 零回复」的机理（`weight_upload.py:162` 判据是 `text.startswith('WOK')`，
   实际收到 `WK4816\n` 于是判失败）。

---

## 1. `ctrl_smoke`：4 处 TB 错（RTL 正确）

### 1.1 修复后实测

```
OBS: sys_run=1 safe_err=0 stage_code=3 n_console=48 cycles=144010
CONSOLE_TEXT: INSTREC BOOT<0a>DDR3 SELFTEST...<0a>DDROK<0a>DDR3 STS 00<0a>
OBS: positions boot=0 selftest=13 ddrok=30 sts=36
CHECK PASS: BOOT line printed
CHECK PASS: DDR3 SELFTEST line printed
CHECK PASS: DDROK printed after SELFTEST (busy window survived)
CHECK PASS: DDR3 STS printed after DDROK
CHECK PASS: sys_ctrl reached RUN with pass
OBS: DDR3 STS code = 00 (to_err=0 cmd_to_err3=0 state=0 st_fail=0 st_done=0)
CHECK PASS: DDR3 STS reports no error bits (clean pass)
RESULT: PASS tb_ctrl_smoke
```

### 1.2 缺陷 A：字符串字面量对齐假设错误（`positions` 全 `-1` 的直接原因）——**TB 错**

`lit_char` / `lit_len` / `contains` 假设字符串字面量在宽向量里**左对齐**（首字符在 MSB）。
实测（探针 `build/sim/_probe/probe_str.sv`，Verilator 5.050）：

```
wide128: idx0=00 idx4=49 idx11=20 idx12=42 idx15=54
```

`"INSTREC BOOT"` 被**零扩展右对齐**到 bits[95:0]：`lit_char(...,0)` 读到 `0x00`，
`lit_char(...,4)` 才是 `'I'`。于是 `lit_len` 返回 16 而不是 12，`contains()` 恒返回 `-1`。
**控制台文本本身完全正确**（修复前日志里 `INSTREC BOOT\nDDR3 SELFTEST...\nDDRO` 就在）。

修法：token 改成显式 ASCII 字节拼接（首字符在 bits[127:120]，未用字节在低端补 0），
拼接的位序由标准定义，与字面量宽度扩展规则无关。

### 1.3 缺陷 B：等待窗口 400000 周期太短（`DDRO` 截断）——**TB 错**

`uart_debug` 每个字符后有内部 `TX_GAP = 16'd12000`（`src/ctrl/uart_debug.v:302`），
与 TB 那层 120 周期的 stub 无关。整链字节数 13+17+6+12 = **48**，即 48×12000 = **576,000** 周期。
TB 的 `i < 400000` 到 400,000 周期（= 34 字节，正好 13+17+4）就到期，控制台停在 `DDRO`。

修法：数据等待上限 400k→1.6M，新增 `!dbg_busy` drain（≤600k）后 `repeat(200)`；
watchdog 20 ms→40 ms。

### 1.4 缺陷 C：`DDR3 STS` 行按 8 位 hex 解析——**TB 错**

`uart_debug` 的 id 6 只发 **2** 个 hex 位 + `'\n'`
（`src/ctrl/uart_debug.v:401-405`：`hex_left <= 4'd2`），整行 9+2+1 = 12 字节；
TB 却从 `pos_sts+9` 连读 8 位并要求 `pos_sts+17 < n_console`。

修法：按 2 位 hex 解析（值域 0x00..0xFF）。

### 1.5 缺陷 D：把 `st_done` 当成 STS 的 PASS 标志——**TB 错（RTL 语义正确）**

STS 是**事后快照**：`sys_ctrl` 在发延迟行时组合读取 `ddr_sts_code`
（`src/ctrl/sys_ctrl.v:219-224`），此刻距 `self_test` 的单拍 `st_done` 已过去几十万周期，
bit0 必然为 0。PASS 的语义由 `DDROK` 承载（`sys_ctrl.v:369-371` 只在 `DDR_RES_PASS` 时发 id 3）。
所以干净通过时 STS = `0x00` **符合设计**。

修法：判据改为「**无错误位**」——bit6 `cmd_to_err[3]` / bit5 `to_err` /
bits[4:2] `dbg_to_state` / bit1 `st_fail` 全为 0。

---

## 2. `npu_chain`：1 处 TB 错（`gap_unit` 正确）

### 2.1 修复后实测

```
STAGE gap:  samples=256 mismatch=0 (expect 256)
STAGE fc1:  samples=128 mismatch=0 (expect 128)
STAGE fc2:  samples=16 mismatch=0 (expect 8)
STAGE prob: samples=8 mismatch=0 top1=0 (expect 8)
CHECK PASS: gap 256 channels bit-exact
CHECK PASS: fc1 128 outputs bit-exact
CHECK PASS: fc2 8 outputs bit-exact
CHECK PASS: softmax 8 probabilities bit-exact
RESULT: PASS tb_npu_chain
```

`fc2 samples=16` 是 16-lane 输出中 8 个真实通道 + 8 个 padding，比对只取前 8 个，符合设计。

### 2.2 机理：`layer_start` 比数据流晚 4 拍 —— **TB 错**

`gap_unit` 的 `last_beat` 条件（`src/npu/gap_unit.v:60-62`）要求四个位置计数器同时到顶；
而 `layer_start` 在 `S_ACC` 期间会清零这四个计数器（`gap_unit.v:149-154`）。
TB 的数据流从复位释放第一拍就开推（`tb_npu_chain.sv` 原 221-234 行），
sequencer 却 `repeat(4)` 之后才发 `gap_start`（原 363-374 行）。时间线：

```
posedge 9 : rst_n=1，TB 开始计 gap_in_cnt
posedge 10: DUT 收第 1 个 beat（按 row0/col0/lane0 起算）
posedge 14: DUT 收到 layer_start -> 计数器清零，但已吞掉 4 个 beat
posedge 15: DUT 把 TB 的第 5 个字节当作 row0/grp0/col0/lane0
```

数据流没有重放，计数器比数据流永久落后 4 拍 → `last_beat` 要到第 16388 个 beat 才成立，
而 TB 只送 16384 个 → **永远停在 `S_ACC`，`gap_we` 恒 0，`gap_out=0`**。
这与人给的判据一致（「看它停在哪个状态」= 从未进 `S_CONV`）。

修法：新增 `stream_en`，数据流在 `gap_start` 脉冲**被采样之后**才启动。

### 2.3 判据反向自校验（排除空转）

把 `FC2_ZP` 由 57 改成 56（`build/sim/_probe/tb_npu_neg.sv`）后重跑：

```
STAGE fc2:  samples=16 mismatch=5 (expect 8)
CHECK FAIL: fc2 8 outputs bit-exact
RESULT: FAIL tb_npu_chain (1 errors)
```

判据确实在检查数据通路。附带确认：`softmax` 在 logits 全体平移时不变（数学性质），
所以 neg-control 里 probs 仍 mismatch=0 是正确表现，不是判据失效。

---

## 3. `weight_loader`：5 处 TB 错已修 + 1 处 RTL 缺陷

### 3.1 修复后实测（8/10 PASS）

```
OBS A: frame_cnt=4 weight_ok=1 weight_err=0 err_addr=00000000
OBS A: rtl_digest=42851062 tb_digest=42851062 wr_cmds=4 rd_cmds=4 wr_beats=32 rd_beats=32
UART_TEXT: KKKKWK4816<0a>
CHECK PASS: A four chunks accepted (4 x 'K')
OBS A: terminal line bytes=7 (expect 13)
CHECK FAIL: A terminal line starts with 'WOK'
CHECK FAIL: A terminal line complete (13 = 'WOK ' + 8 hex + LF)
CHECK PASS: A weight_ok
CHECK PASS: A frame_cnt = 4
CHECK PASS: A write-then-read-back digest matches
CHECK PASS: A read-back covered all 4 chunks (rd_beats >= 32)
OBS B: weight_ok=0 weight_err=1 err_addr=00000000 uart_len=1
UART_TEXT: N
CHECK PASS: B corrupt CRC rejected (weight_err)
CHECK PASS: B NAK 'N' emitted
OBS C: weight_ok=0 weight_err=0 frame_cnt=1 uart_len=1
UART_TEXT: K
CHECK PASS: C good chunk accepted after reset
RESULT: FAIL tb_weight_loader (2 errors)
```

**`WOK` 主路径已通**：`wr_cmds=4 / rd_cmds=4 / wr_beats=32 / rd_beats=32`，
`rtl_digest == tb_digest == 42851062`。剩下的 2 项失败全部是**同一件事**：
`WOK <8hex>\n` 这 13 字节只送出 7 字节（`WK4816\n`）。

### 3.2 TB 错 ①：帧间零间隔，后 3 帧字节被写窗口吞掉 —— 已修

`send_byte` 每字节 2 周期（真 115200 ≈ 10868 周期/字节，快约 5400 倍）；
而 `weight_loader` 在 `S_WRITE`/`S_RD_*`/`S_ACK` 期间不采样 `rx_valid`
（`weight_loader.v:279-304`）。修复前证据：`wr_cmds=1`、`frame_cnt=1`、
`err_addr=00000200`（= BASE + seq 2×256，错位后的帧头被判 seq mismatch）。

**`frame_cnt` 语义核对**：RTL 在每个 chunk 的 `done` 上加一（`weight_loader.v:289`），
`frame_cnt` = **chunk 数**，4 帧 → 4 **是正确期望值**，TB 的判据没写错，是驱动节奏错。
修法：每帧后等 `busy` 落回 0（loader 回 `S_IDLE`）再发下一帧。

### 3.3 TB 错 ②：corrupt 帧注入方式错，CRC 被算成了合法值 —— 已修

原代码先翻转 `payload[37]` 再拿翻转后的字节推进 CRC（原 294-300 行），
于是数据与 CRC 自洽，RTL **正确接受**并回 `'K'`，`weight_err` 保持 0。
**不是 RTL 的 `weight_err` 没置位**：置位路径在 `weight_loader.v:252-256`，逻辑正确。
修法：CRC 用原始字节推进，线上发翻转后的字节。

### 3.4 TB 错 ③：`NN` 来自恒 ready sink 把同一字节收两次 —— 已修

修复前日志的 `KK` / `NN` 不是 RTL 发了两次：TB 的 sink 是 `reg tx_ready = 1'b1`（恒 ready），
而 `weight_loader` 在 `S_ACK`/`S_NAK` 里每拍都置 `tx_valid <= 1'b1`（`weight_loader.v:294-304`），
于是同一字节被捕获两次。
真实 `uart_tx` 的 `byte_wready` 是寄存的 `~busy`（`src/ctrl/uart_tx.v:72`），
且只在 `!busy` 时接受（`uart_tx.v:74-76`）→ 只接受一次。
修法：TB 内建 `uart_tx` 行为替身（`tx_ready` 寄存器 + `busy` + 帧时间），
捕获条件改为 `tx_valid && tx_ready && !tx_busy`。

### 3.5 TB 错 ④：复位后 C 段判据错 —— 已修

`weight_ok` 只在 end frame 走完 `S_RD_SET → S_RD_BEAT → S_RD_CHK → S_TX` 后才置位
（`weight_loader.v:344`）；C 段只发一个普通 chunk，没有 end frame，`weight_ok` 必然为 0。
修法：判据改为「收到 `'K'` 且 `frame_cnt==1` 且 `weight_err==0`」。

### 3.6 TB 错 ⑤：`rd_beats` 计数少 1 —— 已修

模型 `R_RB` 在 `beat == nbeats` 那拍直接 `done`、不再计数，但这一拍 DUT 仍在采样上一拍发出的
`rd_valid`（第 8 拍），所以旧代码报 7 而实际 8。
修法：改为独立 `always @(posedge clk) if (rd_valid) rd_beats <= rd_beats + 1;`，
与 DUT 采样点一致（现实测 32 = 4×8）。

---

## 4. RTL 缺陷：`weight_loader` 的 `S_TX` 与 `uart_tx` 握手契约不匹配

### 4.1 定位

| 项 | 内容 |
|---|---|
| 文件 | `instrec_fpga/src/ctrl/weight_loader.v` |
| 行号 | `S_TX` 分支 **363-374 行**（同类结构另有 `S_ACK` 294-298、`S_NAK` 300-304） |
| 对端 | `instrec_fpga/src/ctrl/uart_tx.v` **第 72 行** `byte_wready <= ~busy;`、**74-76 行** 接受条件 |

### 4.2 机理（逐步时序）

`uart_tx` 接受一个字节的真实条件是 `!busy && byte_wvalid && byte_wready`，
而 `byte_wready` 是**寄存**的 `~busy`——接受后的**下一拍它仍然为 1**（多保持一拍）。

`weight_loader` 的 `S_TX` 则每拍无条件 `tx_data <= tx_line[tx_pos]`、`tx_valid <= 1'b1`，
并用 `if (tx_valid && tx_ready)` 判定「这个字符发完了」→ `tx_pos` 前进。

```
拍 T   : loader 发 strobe；uart_tx !busy -> 接受第 1 个字符，busy<=1
拍 T+1 : ready 仍是 1（寄存多一拍）；uart_tx 因 busy 不接受任何字节
         loader 却把这拍当成"发完了"，tx_pos 前进一格 -> 该字符从未上线
拍 T+2 : ready 变 0，loader 不再前进，但 tx_data 已被覆盖成 tx_pos+1 的字符
```

结果是**每隔一个字符丢一个**。实测：

```
期望: W O K ' ' 4 2 8 5 1 0 6 2 \n   (13 字节)
实际: W K 4 8 1 6 \n                  (7 字节)  丢 O、空格、2、5、0、2
```

### 4.3 证据（三重，互相独立）

1. **行为模型**：TB 内按 `uart_tx.v:62-101` 逐行复刻的替身 → 收到 `KKKKWK4816\n`。
2. **真实 RTL 实例**：把 `src/ctrl/uart_tx.v` 原文件直接例化进探针
   （`build/sim/_probe/tb_wl_uart.sv`，`BAUD_DIV=4`）→ 逐字节记录
   `accept: K K K K W K 4 8 1 6 \n`，**与行为模型完全一致**。
3. **板级脚本判据**：`scripts/weight_upload.py:162` 是 `ok = text.startswith('WOK')`，
   收到 `WK...` 必然判失败——与 T11/T20 观测到的「`WOK` 零回复」一致。

> 说明：「板级零回复由本条缺陷造成」是**强支持但未 board-proven**：
> 板级没有抓到 end frame 之后的原始串口字节流。若要板上闭环，需要在
> `weight_upload.py` 的 end-frame 分支把 `line` 原始字节 dump 出来（只读改动）。

### 4.4 建议改法（已在 `build/` 副本验证 → TB 由 FAIL 变 PASS）

在 `S_TX` 中把「发字节」改成**一次性 strobe + 等对端 ready 走完一整个低-高周期**：

```verilog
    // 新增声明（与 tx_pos 同处）
    reg tx_pend;      // 一次性 strobe 已发出，等待 uart_tx 取走
    reg tx_saw_low;   // 已观察到 uart_tx 的 !ready（帧正在发送）

    S_TX: begin
        tx_valid <= 1'b0;                       // 只维持一拍
        if (!tx_ready) tx_saw_low <= 1'b1;      // 帧正在发送
        if (tx_pend) begin
            tx_pend <= 1'b0;                    // strobe 已被取走
        end else if (tx_saw_low) begin
            if (tx_ready) begin                 // 一帧发完，uart_tx 空闲
                tx_saw_low <= 1'b0;
                if (tx_pos == 4'd12) begin state <= S_FIN; weight_ok <= 1'b1; end
                else tx_pos <= tx_pos + 4'd1;
            end
        end else if (tx_ready) begin
            tx_data  <= tx_line[tx_pos];
            tx_valid <= 1'b1;
            tx_pend  <= 1'b1;
        end
    end
```

复位时补 `tx_pend <= 1'b0; tx_saw_low <= 1'b0;`。

验证结果（`build/sim/_probe/weight_loader_fix.v` + 同一 TB）：

```
UART_TEXT: KKKKWOK 42851062<0a>
CHECK PASS: A terminal line starts with 'WOK'
CHECK PASS: A terminal line complete (13 = 'WOK ' + 8 hex + LF)
...
RESULT: PASS tb_weight_loader
```

**注意两个前提**：
- 该方案依赖对端 ready 在一帧期间**变低**（`uart_tx` 满足）。若将来换成
  恒 ready 的 FIFO，需要加超时或改用「≥1100 拍字节间隔」方案（`uart_tx` 一帧 1085 拍）。
- `S_ACK`/`S_NAK`（294-304 行）目前只有单字符、实测只发一次，**当前无害**；
  建议一并改成同结构，避免以后每帧多字符时复发。
- 另一个与本次缺陷无关、但同源的健壮性隐患：`S_ACK/S_NAK/S_TX` 都依赖
  「对端 ready 在 valid 稳定期间保持为高」，换成零延迟 ready 的实现会重复发字节。
  固定为「一次性 strobe」后可一并消除。
- **未改** `src/**`，也未提交任何 RTL 改动。

---

## 5. 逐项判定汇总

| case | 断言/现象 | 判定 | 关键证据 |
|---|---|---|---|
| ctrl_smoke | `positions` 全 `-1` | TB 错 | 字面量右对齐探针：`idx0=00 idx4=49`；控制台文本本身正确 |
| ctrl_smoke | 文本截断在 `DDRO` | TB 错 | 400k 周期 = 34 字节；`uart_debug` `TX_GAP=12000` |
| ctrl_smoke | `DDR3 STS` 匹配失败 | TB 错 | id 6 只印 2 位 hex（`uart_debug.v:401-405`） |
| ctrl_smoke | `st_done=1` 断言失败 | TB 错 | STS 是事后快照，单拍 `st_done` 已回落；PASS 由 DDROK 承载 |
| npu_chain | `gap_in=16384 / gap_out=0` | TB 错 | `layer_start` 晚 4 拍 → 计数器永远差 4 → `last_beat` 不可达 |
| weight_loader | `frame_cnt=4` 失败（修复前 1） | TB 错 | 帧间零间隔 → `wr_cmds=1`；RTL 语义是 chunk 数，期望 4 正确 |
| weight_loader | `corrupt CRC rejected` 失败 | TB 错 | CRC 用翻转后字节计算，自洽合法 |
| weight_loader | `NAK 'N' emitted` 失败 | TB 错 | 恒 ready sink 重复捕获（`KK`/`NN`） |
| weight_loader | 复位后 C 段 | TB 错 | 单 chunk 不置 `weight_ok`（`weight_loader.v:344`） |
| weight_loader | `rd_beats` = 7 | TB 错 | 模型计数漏最后一拍 |
| weight_loader | `WOK` 行 7 字节 | **RTL 错** | `S_TX` 与 `uart_tx` 的寄存 ready 相位不匹配；真实 `uart_tx` 实例复核一致 |

## 6. 复现命令

```powershell
# 在 instrec_fpga/ 下
python sim/run_sim.py ctrl_smoke        # PASS 6/6
python sim/run_sim.py npu_chain         # PASS 4/4
python sim/run_sim.py weight_loader     # FAIL 8/10：2 项为 RTL 缺陷（WOK 行丢字符）
python sim/run_sim.py all --jobs 2      # 5 PASS / 4 FAIL
```

探针与证据文件（均在 `build/`，gitignored，不入库）：
`build/sim/_probe/probe_str.sv`（字面量对齐）、
`build/sim/_probe/tb_wl_uart.sv`（真实 `uart_tx` 实例复核）、
`build/sim/_probe/weight_loader_fix.v`（修复方案验证）、
`build/sim/_probe/tb_npu_neg.sv`（`FC2_ZP` 反向对照）。

## 7. 未证实项（显式声明）

- 「板级 `WOK` 零回复由 `S_TX` 丢字符造成」= **强支持，未 board-proven**（缺板级原始字节流）。
- 修复方案只在 `build/` 副本上跑过单一 TB，**未跑 PDS 综合/时序**（`S_TX` 新增 2 个触发器，
  预计对资源与时序无实质影响，但未验证）。
- `S_ACK`/`S_NAK` 在 `uart_tx` 上的单字符行为仅在本次仿真中验证为「只发一次」，
  未做长时/多帧压力。