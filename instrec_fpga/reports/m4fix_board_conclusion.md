# m4fix 位流板级判定（T20，决定性实验）

**一句话结论：`DDROK` 没有出现，因此 `m0_done` **没有被 board-proven** 为 `@00300000` 的根因；但本轮串口现象相对 m4 发生了确定性变化（`DDR3 ERR @00300000` 那 19 字节整行消失、49 B → 30 B），说明该修复在板上确实生效。由于 `uart_debug` 在打印过程中会**静默丢弃**新的行请求，而 `sys_ctrl` 的 `DDROK`/`DDR3 ERR` 触发都不检查 `dbg_busy`，「自检通过但 `DDROK` 被丢」与「自检仍在 32.8 µs 处 abort、`DDR3 ERR` 被丢」两种解释产生**逐字节相同**的串口证据，本轮无法分开。**

- 位流：`build/instrec-latest.sbit`
  SHA-256 `B895FCACB9B037D421AE26885A7DBE2F04D5DEA1E5D3ECE385CC0B671707FBA2`（与 T19 manifest 一致，实测重算）
- `--expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"` 两次判读：**均 exit 5（FAIL）**
- 期望缺失项：`expect_missing = ["DDROK"]`
- 权重上传：`frame 0 (seq 0) not acknowledged`（与前几轮同）

---

## 1. 执行与证据

| # | 时间（UTC） | 命令 | exit | 串口字节 | 证据 |
|---|---|---|---|---|---|
| 1 | 10:31:49Z | `board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 25 --expect ... --json reports/board_m4fix_20261031T103149Z.json` | **5** | 30 B | `reports/board_m4fix_20261031T103149Z.json`、`reports/board_m4fix/run1_uart.bin` |
| 2 | 10:33:00Z | 同上（重烧）`--json reports/board_m4fix_20261031T1035Z.json` | **5** | 30 B | `reports/board_m4fix_20261031T1035Z.json`、`reports/board_m4fix/run2_uart.bin` |
| 3 | 10:37:13Z | 重烧（`--seconds 3`，仅为 RX 探针准备干净上电状态） | 4（`cdt_cfg` 未在超时内退出，按 R1 策略故意保留） | 30 B | `reports/board_m4fix_20261031T103713Z_probe_prep.json`、`reports/board_m4fix/run3_probe_prep_uart.bin` |

三次烧录的 JTAG 侧结果一致：`program: True`、`status: 0x081ffca0`、`done=1`、`crc_err=0`。
`cdt_js` 全程**复用 PID 9040**（脚本输出 `reusing the running jtagserver (PID 9040, not restarted)`，
`jtagserver instances stable at [9040]`），未新起第二个、未 terminate；未启动任何 `pds_shell`；
未改动 `src/**`、`scripts/**`、`constraints/**`。

### 串口原文（两次逐字节相同）

```text
INSTREC BOOT\n
DDR3 SELFTEST...\n
```

`python repr(build/uart_last.bin)` → `b'INSTREC BOOT\nDDR3 SELFTEST...\n'`（30 字节，无第 3 行）

## 2. 确定性

| 项 | run1 | run2 |
|---|---|---|
| 字节数 | 30 | 30 |
| SHA-256 | `CD65FF5C2F7BD5E71BC012BDC51D43B5DAB3A42750E255F3D635A717792FE11A` | **同一值** |
| 逐字节相同 | — | **是** |

（上一轮 m4 也是两次逐字节相同：`…@00300000` 的 49 字节。本轮同样是确定性现象，不是偶发。）

## 3. `DDROK` 判定

**`DDROK` 未出现**（`expect_missing=["DDROK"]`，`boot: FAIL (missing DDROK)`）。
按任务书判据，`DDROK` 是「`m0_done` 是否根因」的唯一 board-proven 判据 ⇒ **本轮拿不到该证明**。

## 4. 与上一轮（m4，`44E8F011…`）的差异

| 项 | m4（上一轮） | m4fix（本轮） |
|---|---|---|
| 串口长度 | 49 B | **30 B** |
| 关键行 | `INSTREC BOOT` / `DDR3 SELFTEST...` / **`DDR3 ERR @00300000`** | `INSTREC BOOT` / `DDR3 SELFTEST...`（**无 ERR 行**） |
| `@` 地址 | `@00300000`（首条命令 abort） | **不存在任何 `@` 地址**（既无 `@00300000`，也无 `@FFFFFFFF`） |

- **不是** `@FFFFFFFF`（watchdog 无结论）——本轮连 watchdog 超时行都没打出来。
- **也不是** `@00300000`——m4 的那一行整行消失。
- 因此「`@` 地址是否变化」这个问题在本轮**无法回答**：新一轮没有输出任何地址。可以确认的只是
  「m4 的确定性 abort 报告消失了」，这**不等于**「abort 消失了」。

旁证（构建侧，与 T19 结论一致、本轮独立复核）：
`build/pds/20261031-135808-f1cb68bd/compile/run.log` 有
`Verilog-2036 … Net m0_done connected to input port of module instance instrec_top.u_audio_sink has no driver, tie it to 0`（1 次）；
`build/pds/20261031-162107-81c5a894/compile/run.log` 中该告警 **0 次**。即 `m0_done` 已真正被驱动。

## 5. 时序对照（必须同时给出的部分）

| 域 | m4 | m4fix | 结论 |
|---|---|---|---|
| `ddrphy_sysclk` WNS（setup） | −1.740 ns | **−1.724 ns**（`report_timing/*.rtr:88`：`ddrphy_sysclk → ddrphy_sysclk −1.724 / TNS −337.801 / 1197 endpoints`） | 基本不变（改善 0.016 ns） |
| 是否仍为全局 WNS 决定域 | 是 | 是（`Design Summary : Some Constraints Violated`） | 未变化 |

（`ref_clk = 8.000 ns`，`ddrphy_sysclk` 由 PLL 倍频产生；−1.724 与上一轮 −1.740 同一量级，
即**时序状况没有实质变化**。）

**由此产生的不确定性（明确写出，不掩盖）：**

1. 本轮串口现象与上一轮**并非完全相同**（ERR 行消失了），所以严格意义上「时序」与「`m0_done`」
   本轮已被部分分开：**`m0_done` 确实改变了板上行为**（49 B→30 B），
   「`m0_done` 是无效修复 / 毫无作用」这一说法被否证。
2. 但「现象不同」只证明**触发时刻变了**，不证明**自检结果变了**。下方 §6 的打印竞态
   使得「通过」和「仍在 32.8 µs 失败」都能产生这 30 字节。
3. 因此**不得**把本轮失败归因于时序，也**不得**据此草率否定 `m0_done`。两个假设仍未分开。

## 6. 为什么 30 字节存在二义性（本轮新增的代码级证据）

`sys_ctrl` 在自检结束时**不检查**打印器忙闲就发打印请求（`src/ctrl/sys_ctrl.v`）：

```verilog
// ST_DDW
end else if (st_done) begin
    dbg_line_id <= 3'd3;  dbg_line_fire <= 1'b1;  state <= ST_RUN;     // DDROK
end else if (st_fail) begin
    dbg_line_id <= 3'd4;  dbg_line_arg <= {4'd0, st_fail_addr};
    dbg_line_fire <= 1'b1;  state <= ST_SAFEERR;                        // DDR3 ERR @addr
end
```

`uart_debug` 的 ROM 行锁存**只在不忙时接收**，忙时该请求被**静默丢弃且不重试**
（`src/ctrl/uart_debug.v:330-334`）：

```verilog
if (dbg_line_fire && !rom_pending && !ram_pending && (state == ST_IDLE)) begin
    rom_pending <= 1'b1; ...
end   // 否则 fire 直接丢失
```

而 `DDR3 SELFTEST...` 这一行本身要打印 17 个字符，每字符 ≈ 10 bit@115200（86.8 µs）
+ `TX_GAP = 12000` 拍@125 MHz（96 µs）≈ **3 ms 量级的忙窗口**，且它与 `st_start` **同拍**发出。
于是：

- 若自检**通过**：16 条 burst 在几十 µs 内结束 ⇒ `DDROK` 落在忙窗口内 ⇒ **被丢**，`state→ST_RUN`（静默）；
- 若自检**仍失败**：`self_test` 的 FSM 在 4096 拍（32.8 µs）abort 后给 `st_fail` ⇒ `DDR3 ERR` 同样落在忙窗口内 ⇒ **被丢**，`state→ST_SAFEERR`（静默）。

两者对 PC 侧的输出**逐字节相同**，这就是本轮 30 字节的体积上限。
m4 之所以能打出 `@00300000`，与「`m0_done` tie-0 使 m3 的 grant 被推迟到打印窗口之后」自洽
（m4 的自检结论来不及在窗口内产生，故没有被丢）——注意这只是与证据自洽的解释，
不是本轮可证实的结论。

## 7. 权重通路探针（本轮实测，结论受限）

DDROK 未出现，故按任务书 Step 3 的**触发条件不成立**；但为了给 §6 的二义性找判据，
额外做了两帧探针（一次性脚本 `build/rx_probe.py`，不在 `scripts/` 内）：

| 探针 | 帧 | 板端应有响应 | 实测 |
|---|---|---|---|
| NAK | CRC-16 故意取反的 256 B 帧（不碰 DDR3 路径） | `'N'` (0x4E) | **零字节** |
| ACK | 同内容、CRC 正确的帧（`'K'` 只在 m1 写 burst 完成后才发） | `'K'` (0x4B) | **零字节** |
| 完整上传 | `python scripts/weight_upload.py --port COM5` | `WOK <8hex>` | `RuntimeError: frame 0 (seq 0) not acknowledged`（exit 1） |

证据留档：`reports/board_m4fix/probe_result.txt`。

**所以说：`'K'` 缺失不能当作「DDR3 写通路坏」的证据**——连不依赖 DDR3 的 `'N'` 都没有回来，
说明**PC→FPGA 方向在本位流上从未被证明可用**（m4 轮次同样「无 `N`」，
见 `reports/e2e_conclusion.md` §3.3）。因此权重探针**无法区分「自检通过」与「自检失败」**，
也解释了历史上三次 `WOK` 失败为何都表现为「零回复」。

## 8. 结论：`m0_done` 是否是 `@00300000` 的根因？

- **board-proven：否**（判据 `DDROK` 未出现）。
- **部分证明：`m0_done` 的修复在板上生效**（`Verilog-2036` tie-0 告警消失；串口从 49 B 确定性变为 30 B 确定性）。
- **未被否证**：`m0_done` 仍然可以是 `@00300000` 的根因——「通过但 `DDROK` 被丢」与「仍失败但 `DDR3 ERR` 被丢」都不与任何实测证据矛盾。
- **时序假设本轮同样既未证实也未否证**：−1.724 与 −1.740 实质相同，若自检仍失败，失败时刻（32.8 µs）与 m4 同量级，两者仍未分开。

## 9. 下一步建议（一个信号即可一次分开这两者）

优先级从高到低，均为**一次构建即可判定**的最小改动（本轮按规定不动源码，交 leader 排任务）：

1. **让结果行不可丢（最小、最直接）**：`sys_ctrl` 的 `ST_DDW` 在 `st_done`/`st_fail` 时若 `dbg_busy`
   则不转移状态、保持结果（`result_pending` 锁存），待 `!dbg_busy` 再 `dbg_line_fire`。
   改动 <15 行、只在 `sys_ctrl.v`，下一次烧录即可直接读出 `DDROK` 或 `DDR3 ERR @<addr>`。
2. **导出 ctrl 现有诊断口**：`ddr3_ctrl_axi` 已经把 `to_err`、`cmd_to_err[3:0]`、`dbg_to_state[2:0]`
   输出到顶层（`src/ddr3/ddr3_ctrl_axi.v:94-96`），只需在 `instrec_top` 里把
   `cmd_to_err[3]`/`dbg_to_state` 接到新的行 id（如 id 5）并在 100 ms 超时后打印一次——
   可一次给出「m3 是否被 grant 过、卡在哪个 AXI 相位」。
3. **顺带修两处会持续误导运维的问题**：
   - `uart_debug` 的「忙则丢」应改为「忙则排队（深度 1）」或在 `dbg_busy` 上做反压；
   - `ddr3_arbiter` 的 starvation quota 只保护 P3（`P3_QUOTA_TIMEOUT=125000`），
     **P1（权重）没有配额**，m0 一旦连续请求，m1 可被无限饿死——这与「权重上传永远零回复」直接相关，
     建议给 P1 同样加配额。
4. **PC→FPGA 方向先做一次物理闭环证明**：把 `uart_rx`(B24) 与 `uart_tx`(C24) 短接做回环，或用
   现有 CPU 历史位流（ZBOOT 串口加载可证 RX）在同一块板、同一 COM5 上复测一次；否则任何 `WOK`
   类判据都不可信。

## 10. 偏差 / 风险

| 编号 | 内容 | 影响 |
|---|---|---|
| B-1 | 第 3 次烧录时 `cdt_cfg` 未在 300 s 内自行退出（PID 46156），按 R1 规则**故意保留未杀**；`cdt_js` 仍为单个 9040 | 若后续需要再烧录，需先确认 46156 是否已退出，否则第二个 `cdt_cfg` 会与它争 JTAG |
| B-2 | 探针脚本落在 `build/rx_probe.py`（gitignore 内），未进 `scripts/` | 不可复现于新克隆；如需长期使用应转正 |
| B-3 | 本轮 3 次判读的串口窗口 25 s ≫ 板端 100 ms 超时预算，故「迟到的行」不存在——沉默只能来自「已产生但被丢」或「从未产生」 | 见 §6 |

## 11. 证据清单

- `reports/board_m4fix_20261031T103149Z.json`、`reports/board_m4fix_20261031T1035Z.json`
- `reports/board_m4fix_20261031T103713Z_probe_prep.json`（探针前干净上电）
- `reports/board_m4fix/run1_uart.bin`、`run2_uart.bin`、`run3_probe_prep_uart.bin`（均 30 B，同 SHA-256）
- `reports/board_m4fix/probe_result.txt`（NAK/ACK 探针与完整上传记录）
- `build/uart_last.bin`（最后一次采集）
- 构建/时序旁证：`build/instrec-latest.json`、`reports/m4fix_conclusion.md`、
  `build/pds/20261031-{135808-f1cb68bd,162107-81c5a894}/compile/run.log`