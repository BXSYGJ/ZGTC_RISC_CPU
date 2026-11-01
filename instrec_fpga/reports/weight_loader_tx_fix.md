# T30 weight_loader 串口丢字符修复结论（S_TX / S_ACK / S_NAK）

> 日期：2026-11-01　分支：XSY　工程：`instrec_fpga/`
> 执行人：weightLOADER修复-施工（T30）
> 纪律：**只改** `src/ctrl/weight_loader.v`；未启动 PDS、未 `-DryRun`、未烧板、未碰 `cdt_js`、未 commit/push。
> 全量构建 `20261031-222313-0fde8a5a` 在跑期间完成，本地只做 Verilator 仿真 + pytest。

---

## 0. 结论（一句话）

**是。** 板级 `WOK` 三次零回复的**真因就是** `weight_loader.v` 的 `S_TX` / `S_ACK` / `S_NAK`
把 `uart_tx` 的**寄存型 `byte_wready`**（接受后多保持一拍高）当成"字节已发完"的判据，
导致**每隔一个字符丢一个**（`WOK 42851062\n` → `WK4816\n`），而 `scripts/weight_upload.py:162`
的判据是 `text.startswith('WOK')`，必然判失败。
三处改为「一次性 strobe + 等 ready 走完低-高周期」后，同一 TB 由 **8/10 FAIL → 10/10 PASS**，
串口文本为 **`KKKKWOK 42851062\n`**；并在**真实 `uart_tx.v` 实例**上复核
`started_frames=17 == accepted_bytes=17`（无丢、无重）。

---

## 1. 改动清单

### 1.1 文件与哈希

| 项 | 值 |
|---|---|
| 修改文件（唯一） | `instrec_fpga/src/ctrl/weight_loader.v` |
| SHA-256（改后） | `2252c6f7bb9b8ac35d1ddce1db018a93c71de27065b5fa9daa3dab870af0e035` |
| 对照：`src/ctrl/uart_tx.v`（**未改**） | `9ce20db2aa09f678ab0537ab97d131077400336a657c731860832350bf3cc762` |
| 对照：`src/ctrl/uart_debug.v`（**未改**） | `66e9892dd88e41fecdf0c5413378229b61b60851984b016d39d6380003667ec4` |
| 行数变化 | `git diff --numstat` = **+70 / −10**（净 +60，其中注释 30 行） |

### 1.2 四处改动（改后行号）

| 位置 | 行号 | 改法 |
|---|---|---|
| 新增触发器声明 | 100–105 | `reg tx_pend;`（strobe 已发、本帧未发完）、`reg tx_saw_low;`（已观察到 ready 变低） |
| 复位分支 | 161–163 | `tx_pend <= 1'b0; tx_saw_low <= 1'b0;` |
| `S_ACK`（'K'） | 303–321 | 电平保持 `tx_valid<=1` + `tx_valid&&tx_ready` 判完成 → **一次性 strobe + 低-高周期** |
| `S_NAK`（'N'） | 322–340 | 同上 |
| `S_END` | 393–397 | 进入 `S_TX` 前显式清 `tx_pend`/`tx_saw_low`，保证首字符不误判 |
| `S_TX`（13 字符 `WOK …\n`） | 399–434 | 同上，`tx_pos` 只在 ready 走完「低→高」后前进 |

### 1.3 核心改法（`S_TX`，其余两处同构）

```verilog
if (!tx_pend) begin
    if (tx_ready) begin                    // 对端空闲才发
        tx_data    <= tx_line[tx_pos];
        tx_valid   <= 1'b1;                // single-cycle strobe
        tx_pend    <= 1'b1;
        tx_saw_low <= 1'b0;
    end
end else if (!tx_ready) begin
    tx_saw_low <= 1'b1;                    // 帧正在移位：ready 掉低
end else if (tx_saw_low) begin             // ready 回到高 = 本帧真正结束
    tx_pend    <= 1'b0;
    tx_saw_low <= 1'b0;
    if (tx_pos == 4'd12) begin state <= S_FIN; weight_ok <= 1'b1; end
    else tx_pos <= tx_pos + 4'd1;
end
```

---

## 2. 机理与时序

### 2.1 `uart_tx` 的真实契约（`src/ctrl/uart_tx.v`）

```verilog
byte_wready <= ~busy;                       // 第 72 行：寄存型
if (!busy) if (byte_wvalid && byte_wready)  // 第 74–76 行：真实接受条件
```

因为 `byte_wready` 是**寄存**的 `~busy`，它在**接受之后的下一拍仍然读作 1**。
推论（在 1.2/2.2 中被用到）：**`tx_ready==1` 的那一拍，`uart_tx.busy` 一定为 0**，
即"看到 ready 高就发 strobe"必然被接受（`busy` 只会在这一拍才被置 1，下一拍才生效）。

### 2.2 旧代码为什么每两字符丢一个

| 拍 | `weight_loader` 旧行为 | `uart_tx` 真实行为 | 结果 |
|---|---|---|---|
| T | `tx_valid=1`、`tx_data=tx_line[0]`（'W'） | `!busy && wvalid && wready` → **接受 'W'**，`busy<=1` | 'W' 上线 |
| T+1 | `tx_valid&&tx_ready` 成立 → **`tx_pos` 前进到 1** | `busy=1`，虽然 `wready` 仍读 1，但**不接受** | 'W' 之外无字节被取，但 `tx_pos` 已跳过 'O' |
| T+2 | `tx_data=tx_line[1]`（'O'）→ 下一拍 strobe… | `wready=0` | 'O' **从未被采** |

实测（T29 已用行为模型 + 真实实例双重确认）：`WOK 42851062\n`（13 B）→ `WK4816\n`（7 B）。
丢的正好是 **偶数号字符** O、空格、2、5、0、2。

### 2.3 新代码的时序（`BAUD_DIV=4` 的探针口径，与真实 1085 同构）

| 拍 | `tx_pend` | `tx_saw_low` | `tx_ready` | 动作 | `uart_tx` |
|---|---|---|---|---|---|
| T | 0 | 0 | 1 | 发 strobe（`tx_valid` 于 T+1 有效） | 空闲 |
| T+1 | 1 | 0 | 1 | 什么都不做（等帧启动） | **接受**本字符，`busy<=1` |
| T+2 | 1 | 0 | 1（多保持的那一拍） | 什么都不做 —— **不再前进** | `busy=1`，不再接受 |
| T+3 | 1 | 0 | 0 | `tx_saw_low<=1` | 发送中 |
| … | 1 | 1 | 0 | 等 | 发送中 |
| T+F+1 | 1 | 1 | **1** | `tx_pend<=0, tx_saw_low<=0, tx_pos++` | 帧结束，回空闲 |
| T+F+2 | 0 | 0 | 1 | 发下一字符 | 空闲 |

**结构性性质**：`tx_pend` 从 strobe 发出一直保持到「ready 低过又回高」为止，因此
① 同一字符**不会发两次 strobe**（即使对端 ready 多保持一拍甚至恒高）；
② `tx_pos` 只在一个字符**完整上线后**才前进一次；
③ 进入 `S_TX` 时若对端正忙（ready=0），不会误跳过首字符（`S_END` 已清标志，且 `!tx_pend`
   分支要求 `tx_ready==1` 才发）。

---

## 3. 验证证据（三层，互相独立）

### 3.1 行为模型（交付用 TB）：**10/10 PASS**

```
python sim/run_sim.py weight_loader
[00:29:17] weight_loader  PASS  18.2s
OBS A: frame_cnt=4 weight_ok=1 weight_err=0 err_addr=00000000
OBS A: rtl_digest=42851062 tb_digest=42851062 wr_cmds=4 rd_cmds=4 wr_beats=32 rd_beats=32
UART_TEXT: KKKKWOK 42851062<0a>
CHECK PASS: A four chunks accepted (4 x 'K')
CHECK PASS: A terminal line starts with 'WOK'
CHECK PASS: A terminal line complete (13 = 'WOK ' + 8 hex + LF)
CHECK PASS: A weight_ok
CHECK PASS: A frame_cnt = 4
CHECK PASS: A write-then-read-back digest matches
CHECK PASS: A read-back covered all 4 chunks (rd_beats >= 32)
CHECK PASS: B corrupt CRC rejected (weight_err)
CHECK PASS: B NAK 'N' emitted
CHECK PASS: C good chunk accepted after reset
=== tb_weight_loader done: 10 checks, 0 errors ===
RESULT: PASS tb_weight_loader
```

- **10 项全 PASS**：原 8/10 → **10/10**，失败的两项（`starts with 'WOK'`、`complete 13 bytes`）均转 PASS。
- **串口文本 = `KKKKWOK 42851062\n`**：4 个 `K` + 13 字节 `WOK 42851062\n`，
  与期望**字节数一致（17）**，说明既**没有丢**也**没有重**（旧代码是 `KKKKWK4816\n` = 11）。
- `B` 段仍只发 1 个 `N`、`C` 段只发 1 个 `K` → `S_ACK/S_NAK` 改结构后**未引入重复发送**。

### 3.2 真实 `src/ctrl/uart_tx.v` 实例端到端（硬证据）

`build/sim/_probe/tb_wl_uart_src.sv` + `build/sim/_probe/run_probe.py`：
**直接例化 `src/ctrl/weight_loader.v` 与 `src/ctrl/uart_tx.v` 源文件**（`BAUD_DIV=4`，
帧长 40 拍，与 1085 同构），`tx_ready` 由真实 `uart_tx.byte_wready` 驱动：

```
OBS A: rtl_digest=42851062 tb_digest=42851062 wr_cmds=4 rd_cmds=4 wr_beats=32 rd_beats=32
UART_TEXT: KKKKWOK 42851062<0a>
OBS A: started_frames=17 accepted_bytes=17
CHECK PASS: A four chunks accepted (4 x 'K')
CHECK PASS: A UART digest line present
...
RESULT: PASS tb_weight_loader
```

- `accepted_bytes` 按 `tx_valid && tx_ready && !u_tx.busy` 统计（= `uart_tx.v:74-76` 真实条件）；
- `started_frames` 按 `uart_tx.busy` 上升沿统计（= 真实启动的帧数）；
- **17 == 17**，且 17 个字节逐一打印为 `K K K K W O K ␠ 4 2 8 5 1 0 6 2 \n`：
  **握手赢了的字节，一个不少地上了引脚**。旧代码同口径下为 11 字节（4 K + 7）。

### 3.3 闸门

| 闸门 | 结果 |
|---|---|
| `python scripts/check_rtl.py` | `checked 51 .v file(s) ... 0 violation(s) in 0 file(s)` ✅ |
| `python -m pytest -q` | **429 passed, 4 skipped**（97.4 s）✅ 与基线一致，无回退 |
| `python sim/run_sim.py self_test,ui_render,ddr3_subsys,ctrl_smoke,npu_chain --jobs 2` | **5 PASS / 0 FAIL**（59.0 s）✅ 无回退 |
| `python sim/run_sim.py weight_loader` | **PASS 10/10** ✅ |

`check_rtl.py` 的 51 个文件（含 `src/diag/**`、`src/ui/**`）全绿，说明新增两个触发器与
注释未触犯 SV-2005 子集约束。

---

## 4. `uart_debug.v` 是否有同型问题 —— **无**

### 4.1 结论：写法不同源，**结构上不可能**出现"每两字符丢一个"

`uart_debug.v` 驱动 `uart_tx` 的方式与旧 `weight_loader` 有一条**本质区别**：

| 维度 | 旧 `weight_loader`（缺陷） | `uart_debug`（安全） |
|---|---|---|
| `tx_byte_valid` 形态 | **电平保持**（每拍 `<=1`） | **单拍 strobe**（顶部默认 `tx_byte_valid <= 1'b0`，`:327`） |
| `ready` 的角色 | 被当成"**已完成**"判据 → 多保持一拍就多前进一格 | 只是"**允许发**"的门（gate），不是完成信号 |
| 字符之间的节拍 | 无间隔，靠 ready 相位 | 显式 `TX_GAP = 12000` 拍（`:302`），`> 一帧 10×1085 = 10850` 拍 |
| 双采风险 | 有（ready 多一拍即误判） | 无（`gap_cnt != 0` 挡住，`gap_cnt` 回 0 时 `uart_tx` 已空闲 ≥1150 拍） |
| 漏采风险 | 有（`tx_pos` 已前进） | 无（发 strobe 的拍 `ready==1` ⇒ `busy==0` ⇒ 必被接受；见 §2.1 推论） |

关键点：`uart_debug` 在发 strobe 的**同一拍**就把 `rom_idx/ram_rd_idx` 前进，并且立刻把
`gap_cnt <= TX_GAP`（`:380/:396/:422/:437`）。因为 `gap_cnt` 在随后的 12000 拍里非 0，
`uart_tx` 那一拍"多保持的 ready"**根本不会**被再判一次。因此 **既不会双采（同一字符发两次），
也不会漏采**。

### 4.2 实证：`ctrl_smoke` 48 字节全对

`ctrl_smoke` 的控制台输出（本次回归 PASS，与 T29 一致）：

```
CONSOLE_TEXT: INSTREC BOOT<0a>DDR3 SELFTEST...<0a>DDROK<0a>DDR3 STS 00<0a>
positions boot=0 selftest=13 ddrok=30 sts=36
```

13 + 17 + 6 + 12 = **48 字节，逐字节位置精确**（`selftest=13`、`ddrok=30`、`sts=36` 都落在
正确偏移上）。如果 `uart_debug` 有同型缺陷，这 48 字节里会丢掉一半，`positions` 不可能对得上。
这是"无同型问题"的直接反证。

### 4.3 一个**不属于本任务范围**的残余风险（R-1，未改代码）

`instrec_top.v:819-826` 的顶层仲裁存在 1 拍竞态：

```verilog
assign dbg_tx_ready  = tx_byte_ready & ~wl_tx_valid;   // 819-820
.byte_wdata (wl_tx_valid ? wl_tx_data : dbg_tx_data)   // 825
.byte_wvalid(wl_tx_valid | dbg_tx_valid)               // 826
```

`uart_debug` 在 T 拍看到 `dbg_tx_ready==1` 后，strobe 于 **T+1 拍**生效；若 T+1 拍
`wl_tx_valid` 恰变为 1，`uart_tx` 接受的是 **wl** 的字节，debug 字节被丢弃（debug 已启动 gap）。
触发需要 `wl` 的 `S_TX` 发 strobe 与 debug 的字符起点**同拍**，量级约 `1/10850`，且 wl 上传期间
debug 一般无 pending 行（`ST_IDLE` 不发 strobe）。**本任务纪律只允许改 `weight_loader.v`，故未修**；
建议后续把 debug 侧也改成 `tx_pend/tx_saw_low` 握手，或在 top 层用 wl 优先锁存器消除（记 R-1）。

---

## 5. 与 T29 报告 4.4 节参考实现的偏差

| 编号 | 偏差 | 理由 | 影响 |
|---|---|---|---|
| D-01 | 参考实现 `tx_pend` **只维持 1 拍**（发完即清），因此每个字符可能**多发一次 strobe**，靠 `uart_tx.busy` 丢弃来兜住 | 本实现让 `tx_pend` **维持到帧结束**，同一字符绝不发第二次，不依赖"多出来那拍一定 busy" | 更稳；对 `TX_FRAME` 极短（<2 拍）或恒 ready FIFO 的对端也不再重复发 |
| D-02 | 参考实现进入 `S_TX` 时若 `tx_ready==0`，会因 `if(!tx_ready) tx_saw_low<=1` 而**跳过首字符** | 本实现要求 `!tx_pend && tx_ready` 才发 strobe，进入时对端忙则等它空闲，不会跳字符；并在 `S_END` 显式清标志 | 消除一个只在"进入时 uart_tx 正忙"才暴露的丢字符隐患 |
| D-03 | 参考实现未在 `S_END` 清标志 | 本例在 `S_END` 清 `tx_pend/tx_saw_low`，保证 `S_ACK/S_NAK` 与 `S_TX` **共用**这两个寄存器时状态干净 | 无功能变化，仅防御 |

两处语义变化均**不改变** `WOK` 文本内容与 `weight_ok` 置位时机（都是在最后一个字符
`\n` **真正发完**后才置位，比旧代码更晚一点、也更正确），已由 §3.1/§3.2 验证。

---

## 6. 残余风险与未验证项

| 编号 | 项 | 说明 |
|---|---|---|
| R-1 | top 层 wl/debug 仲裁 1 拍竞态 | §4.3，本任务范围内未修（纪律：只改 weight_loader.v） |
| R-2 | 新写法依赖"帧期间 ready 必变低" | `uart_tx` 满足（一帧 10850 拍）。若将来换成恒 ready FIFO，需加超时兜底（参考实现同前提） |
| U-1 | **未构建 PDS** | 纪律要求不启动构建；新增 2 个触发器，预计对资源/时序无可测影响，但**未跑综合/时序** |
| U-2 | **未烧板** | 纪律要求不烧板；因此"板级 `WOK` 零回复已消除"目前是 **RTL 级证明（三层证据）**，不是 board-proven |
| U-3 | `S_ACK/S_NAK` 长时压力 | 仅验证了单字符 + 复位后恢复，未做多帧连续压力 |

**下一步（建议，不代替领导决策）**：下次全量位流构建后跑
`python scripts/board_check.py --sbit build/instrec-latest.sbit` 确认 BOOT/DDR3 行，
再跑 `python scripts/weight_upload.py` 看 `WOK`——若拿到 `WOK <8hex>`，U-2 即闭环。
建议顺手把 `weight_upload.py` 的 end-frame 分支把 `line` 原始字节 dump 出来（只读改动，
T29 §4.3 也已提出），这样板级"零回复"能留下原始字节证据。

---

## 7. 复现命令

```powershell
# 在 instrec_fpga/ 下
python sim/run_sim.py weight_loader                 # PASS 10/10，UART_TEXT: KKKKWOK 42851062
python build/sim/_probe/run_probe.py                # 真实 uart_tx 实例：17 accept == 17 frames
python scripts/check_rtl.py                         # 0 violation
python -m pytest -q                                 # 429 passed, 4 skipped
python sim/run_sim.py self_test,ui_render,ddr3_subsys,ctrl_smoke,npu_chain --jobs 2
```

探针与脚本（均在 `build/`，gitignored，不入库）：
`build/sim/_probe/tb_wl_uart_src.sv`（真实 `uart_tx` 端到端 + 帧计数）、
`build/sim/_probe/run_probe.py`（复用 `sim/run_sim.py` 的工具链与 runtime 缓存）。