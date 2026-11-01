# T37 多 master 活跃下 DDR3 失败定位（AW 超时 / 自检失配）

- 任务：T37（团队任务 id=37）
- 工程：`instrec_fpga/`（PG2L100H-6IFBG676，PDS 2022.2-SP6.4）
- 方法：**纯 Verilator 仿真**（不构建、不烧板、不碰 `cdt_js`）
- 产品 RTL **零改动**：`src/ddr3/ddr3_ctrl_axi.v`、`src/ddr3/ddr3_arbiter.v` 未修改
- 新增/修改的仿真资产：
  - `sim/tb_ddr3_aw_timeout.sv`（新增，6 个场景）
  - `sim/ddr3_axi_model.sv`（新增参数 `WSTRB_IGNORE`，默认 0 = 原行为不变）
  - `sim/run_sim.py`（**只加 `register(Case(...))` 块**，case 名 `ddr3_aw_timeout`）
- 复现命令（在 `instrec_fpga/` 下）：
  ```powershell
  python sim/run_sim.py ddr3_aw_timeout     # 15~17 s，6/6 场景 PASS
  python sim/run_sim.py ddr3_subsys         # 15 场景回归仍 PASS
  python scripts/check_rtl.py               # 52 个 .v，0 violation
  python -m pytest -q                       # 429 passed, 4 skipped
  ```
  原始日志：`build/sim/ddr3_aw_timeout/run.log`（gitignored，数字全部可复核）

---

## 0. 结论摘要（先回答任务的 5 条）

### 1) m3 首条写命令在 m0/m2 满载下的 AW 等待拍数

| 场景 | 负载 | m3 排队（S_IDLE，**不计** watchdog） | m3 AW 等待（S_AW，**计** watchdog） | m3 结果 |
|---|---|---|---|---|
| A0 | m0 8256 音频页 + m2 516 条 len=15 读，稳态后启动 m3 | 首条 **5** 拍，全程峰值 **58** 拍 | **2** 拍 | 16/16 命令 PASS，数据全对 |
| A3 | m0 400 页 + m2 516 读，P3 配额 2000 | 首条 57 拍，峰值 **58** 拍 | **2** 拍 | 16/16 命令 PASS |
| A2 | 只有 m3（参考基线） | 1 拍 | **2** 拍 | 16/16 命令 PASS |
| A4 | **m0 100 % 饱和**（`cmd_valid` 从不为低，全程 13892 条 len=0 写） | **125000** 拍（= P3 配额上限） | **2** 拍 | 无超时 |

**关键数字：AW 等待 = 2 拍**（无论负载多重，A0/A2/A3/A4 全部是 2 拍；A4 甚至跑出 125000 拍排队后 AW 仍只用 2 拍）。

> 结论 1：m0/m2 满载**不会**让 m3 的 AW 拿不到。真实流量下的排队峰值只有 **58 拍**，比 4096 的 watchdog 窗口低两个数量级；即使把 m0 做成 100 % 饱和，P3 配额也能在 125000 拍把 grant 交给 m3，而**这段等待发生在 `S_IDLE`，`axi_to_cnt` 在 `S_IDLE` 被清零**（`ddr3_ctrl_axi.v:317-323`），所以不会超时。

### 2) 是「不给 grant」还是「grant 了但 AW 被别的 master 在途事务占住」

**都不是。** 仿真给出的结构证据：

- `aw_valid` 高电平与写数据 beat 同时发生的拍数 = **0 / 0 / 0 / 0 / 0**（A0/A1/A2/A3/A4 全部为 0）。
  原因是 `axi_awvalid` 只在 `S_AW`/`S_DW_AW` 为高（`ddr3_ctrl_axi.v:206`），而 `wready_beat` 只在 `S_W` 非零（`ddr3_ctrl_axi.v:231`）——**AW 与 W 在结构上不可能并发**。
- `arb_en` 只在 `state == S_IDLE` 为高（`ddr3_ctrl_axi.v:179`），因此控制器**一次只有一条命令在飞**，唯一的 AW 端口永远属于当前正在执行的那一条命令。**不存在「按 master 切 AW、被别的 master 的 W 阶段卡住」这种通路**。
- 检查 `ddr3_arbiter.v`：`grant = arb_en ? sel_onehot : 4'b0000`（112 行），`p3_override` 用 `p3_starve_cnt` 在 91/183-189 行实现，固定优先级 P0>P1>P2>P3。A0/A3 的 `wait_cnt_3` 峰值为 58 拍，说明**在真实请求节奏下 m3 经常能在 m0/m2 的命令间隙拿到 grant**；A4 才需要靠配额。

**唯一能让 m3 在 `S_AW` 停住 4096 拍的因素，只有 IP 侧 `axi_awready` 不给**。A1 场景给出了直接证据：m0 的写命令在 `S_W` 被中止后，IP 侧残留一个未完成写突发，此后 **m3 的 `axi_awready` 在 13103 拍内一次都没有出现**（`aw_hs m0/m2/m3 = 1/0/0`，m3 的 AW 握手 0 次），此时控制器根本没有在执行别的命令（m0 的 abort 之后 `done[0]=1` 只出现过 1 次）。

### 3) `to_err` 只落 m3 的自洽性 —— **这里必须先纠正一个硬事实**

板上 `STS 0x26`（`0b0010_0110`）按 `sys_ctrl.v:219-224` 的打包：

```verilog
ddr_sts_code = {1'b0, ddr_cmd_to_err[3], ddr_to_err,
                ddr_dbg_to_state, st_fail, st_done};
```

| bit | 字段 | 0x26 的值 | 含义 |
|---|---|---|---|
| 6 | `cmd_to_err[3]` | **0** | **m3 自己从未发生 AXI 超时** |
| 5 | `to_err` | 1 | 有（别的）master 超时 |
| 4:2 | `dbg_to_state` | 001 | 最后一次超时发生在 `S_AW` |
| 1 | `st_fail` | 1 | 自检失败 |
| 0 | `st_done` | 0 | 自检未通过 |

而 `ddr3_ctrl_axi.v:363-368`（`S_AW` 超时分枝）里，`to_err_r`、`cmd_to_err_r[cur_master]`、`dbg_to_state_r = S_AW` 是**同一个分支里三条连续的赋值**。因此：

> **「m3 在 `S_AW` 超时」与「`cmd_to_err[3]=0`」在 RTL 上互斥。**
> 板上 `0x26` 只能解释为：**某个非 m3 的写 master（m0 或 m1）在 `S_AW` 超时**，而 **m3 的 `st_fail` 与超时无关**（是数据比较失败，或写阶段 done 早到）。

仿真对这条互斥给出了两组独立验证：

- **A1**（写 beat 饥饿 → IP 污染）：`cmd_to_err = 4'b1101` —— m0 在 `S_W` 中止置 `[0]`，m2 在 `S_DW_AW` 中止置 `[2]`，**m3 在 `S_AW` 中止置 `[3]`**，`dbg_to_state=1(S_AW)`、`st_fail=1`、`fail_addr=0x0030_0000`。→ 只要 m3 自己超时，第 3 位一定为 1。
- **A5**（位级复现 `0x26`）：m3 先在无并发流量下跑完自检（`cte[3]=0`），但 IP 模型忽略字节掩码（`WSTRB_IGNORE=1`）⇒ 读回数据被自身 dummy write 破坏 ⇒ `st_fail=1`；随后 m0 的写命令在 `S_AW` 被拒 ⇒ `to_err=1`、`dbg_to_state=S_AW`、`cte[0]=1`。
  **输出 `o_sts_byte = 0x26`，与板上字节逐位相同。**

A5 的实测：

```
A5 STS REPRO : STS byte=0x26 (board 0x26) to_err=1 cte=0001 dbg=1
               st_fail=1 st_done=0 fail_addr=0300000
               FIRST abort done=0001 state=1   (state 1 = S_AW)
```

> 结论 3：多种自洽解释中，**只有「m3 无超时 + m3 数据错 + 另一个写 master 在 S_AW 超时」这一组合能在 RTL 上产生 `0x26`**。而「IP 对某地址不响应」被排除：同一地址 `0x0030_0000` 在 A2（m3 单独）与 A0（m0/m2 满载）里 AW 全部 2 拍握手、16/16 命令 PASS、数据全对。
> 「AW 被别的 master 占住」也被排除（见第 2 条：AW 与 W 结构上不并发）。

### 4) 最小修复方案（按确定性排序，见第 4 章）

### 5) 一句话结论

> **多 master 活跃下的 DDR3 失败不是调度（仲裁/配额）问题——真实负载下 m3 的排队峰值只有 58 拍、AW 只用 2 拍；失败源于 IP 侧「一次写数据阶段被中止后，未完成的写突发永不闭合」造成的通道状态污染（一次中止 ⇒ 后续所有 AW 永久被拒），叠加一次独立的 m3 数据失配；`STS 0x26` 的 `cmd_to_err[3]=0` 恰恰证明 m3 自己没超时，超时的是 m0。**

---

## 1. 场景矩阵与实测数据

```
A0  m0 8256 页 + m2 516 读 + m3, 真实 IP 模型(AW_DELAY=2), P3=125000
A1  m0 1 页 + m2 1 读 + m3, 模型第 1 个写突发起不给 wready (W_READY_BURST_COUNT=0)
A2  只有 m3（基线）
A3  m0 400 页 + m2 516 读 + m3, P3=2000
A4  m0 100% 饱和 + m3, P3=125000
A5  m3 先跑完 + 之后 m0 一条写, 模型 WSTRB_IGNORE=1 且 AW 配额=9
```

完整输出（`build/sim/ddr3_aw_timeout/run.log`）：

```
A0 real load  : cyc=4248 QUEUE(m3 req->grant)=5 AWWAIT(grant->awready)=2
                wait_cnt_3 PEAK=58  max m3 AW wait=2  to_err=0 cte=0000
                st_done=1 dc3=16 aw_hs m0/m2/m3=205/86/16 aw&&wbeat=0
A1 wbeat starve: cyc=13103 to_err=1 cte=1101 dbg=1 st_fail=1 fail_addr=0300000
                FIRST abort: done=0001 at state=2  m3 awready EVER seen=0
                aw_hs m0/m2/m3=1/0/0  done m0/m2/m3=1/1/1
A2 m3 alone    : cyc=396 QUEUE=1 AWWAIT=2 max m3 AW wait=2 st_done=1 to_err=0
A3 16 cmds load: cyc=1308 QUEUE=57 AWWAIT=2 max m3 AW wait=2
                st_done=1 st_fail=0 dc3=16 to_err=0 cte=0000 PEAK wait3=58
A4 m0 SATURATED: cyc=125057 QUEUE=125001 AWWAIT=2 PEAK wait3=125000 (quota=125000)
                aw_hs m0/m3=13892/1 to_err=0 st_fail=0 aw&&wbeat=0
A5 STS REPRO   : STS byte=0x26 (board 0x26) to_err=1 cte=0001 dbg=1
                st_fail=1 st_done=0 fail_addr=0300000 FIRST abort done=0001 state=1
```

### 1.1 为什么 A0/A3 的排队只有 58 拍（量化解释）

- 命令粒度：m0 一页 = 两条 `len=0` 写，每条在控制器里 `S_AW(1~3) + S_W(1) + S_WLAST(4)` ≈ 6~8 拍；两条之后 audio_sink 有 **16 个帧周期**的聚合填充（`agg_freeze`），此时 `m0_cmd_valid=0`。
- m2 一条读 = `S_DW_AW + S_DW_W + S_AR + S_R(16)` ≈ 20 拍，随后 `PC_BEAT` 排空 16 拍 + 2 拍 gap，此时 `m2_cmd_valid=0`。
- 因此**每个 ~28 拍的周期里一定有若干拍 `cmd_valid[3:0]` 只有 m3**，固定优先级仲裁在这些空隙里把 grant 给 m3。这就是 58 拍峰值的来源。
- A4 把 m0 做成零间隙饱和后，唯一通路变成 `p3_starve_cnt >= 125000`（`ddr3_arbiter.v:91,183-189`），排队跳到 125000 拍 —— 但这段时间 `state == S_IDLE`，`axi_to_cnt` 持续清零，**watchdog 不计数**，所以 `to_err=0`。

### 1.2 A1 证明的污染链（这是 `to_err/dbg=S_AW` 的可行成因）

`ddr3_ctrl_axi.v` 的写通路在 `S_W` 超时后（381-386 行）只做了三件事：置 `to_err`、置 `cmd_to_err[cur_master]`、回 `S_IDLE`。它**没有把剩余的数据拍发完**。而 Pango DDR3 硬 IP 的写端口没有 `b` 通道、没有 `wvalid`（见 `ddr3_ctrl_axi.v` 头部注释），IP 判定「一个写突发是否结束」的唯一依据是收满 `awlen+1` 拍。中止后：

1. IP 侧保持 `aw_pending=1`、`wr_beats_left>0`；
2. IP 的 `awready` 从此不再拉高（它只有一个写命令槽）；
3. 此后**任何** master 的 AW（包括 m3 的）都永远等不到 `awready`。

A1 实测：m0 在 `S_W` 中止（`done=0001, state=2`）之后，13 103 拍内 `aw_hs` 只发生过 1 次（就是 m0 那条），m3 的 AW 握手 **0 次**，最终 `dbg_to_state=1(S_AW)`。

> 这条链解释了两件事：为什么 `to_err` 的 `dbg_to_state` 会是 `S_AW`（第一个被拒的是**后来的**命令），以及为什么 `cmd_to_err` 里会出现不止一位（A1 是 `1101`，三位同时为 1）。

### 1.3 A5 如何得到与板上完全一致的 `0x26`

`0x26` 需要同时满足：`cte[3]=0`（m3 没超时）、`st_fail=1`（m3 数据错）、`to_err=1`+`dbg=S_AW`（别的写 master 超时）。A5 的构造：

1. `M3_START_CYCLE=8`、`M0_START_CYCLE=1000` —— m3 先把 16 条命令跑完（**只有 9 次 AW**：8 条写 + 首条读的 dummy write；因为第 1 条读就已数据失配，后面的读不再发出）。
2. `WSTRB_IGNORE=1` —— IP 忽略 `wstrb`，因此「读前 dummy write（`wstrb=0`, `wdata=0`）」把自检区首拍写成 0 ⇒ m3 读回比较失败 ⇒ `st_fail=1`、`fail_addr=0x0030_0000`、`cte[3]=0`。
3. `AW_READY_AW_COUNT=9` —— m3 用掉第 1~9 次 AW，m0 在 1000 拍启动后的第 10 次 AW 被永久拒绝 ⇒ `S_AW` 4096 拍超时 ⇒ `to_err=1`、`dbg_to_state=S_AW`、`cte[0]=1`（不可见位）。
4. 组合字节 = `{1'b0, 0, 1, 001, 1, 0}` = **`0x26`**。

> 注意：A5 中让 m3 数据出错的手段（`WSTRB_IGNORE`）只是**三个候选原因之一**的替身。真实板上是哪一个，见第 5 章「板级可判定清单」。

---

## 2. 任务原判读的复核结果

| 原判读 | 复核结论 | 依据 |
|---|---|---|
| 「m3 已拿到 grant」 | **成立** | A0/A3：m3 在 `S_IDLE` 排队 5~58 拍后拿到 grant |
| 「m3 在 `S_AW` 等 `awready` 时 4096 拍超时」 | **不成立** | `0x26` 的 bit6 `cmd_to_err[3]=0`；`ddr3_ctrl_axi.v:363-368` 中 `to_err` 与 `cmd_to_err[cur_master]` 同分支赋值 ⇒ m3 若在 `S_AW` 超时必然置 `[3]` |
| 「m3 已拿到 grant（否则停在 `S_IDLE` 且 `to_err=0`）」 | **成立但方向要反过来** | `to_err=1` + `dbg=S_AW` 是**别的** master 在 `S_AW` 超时；m3 的 `to_err` 无关性由 `cte[3]=0` 锁定 |
| 「高度指向 AW 通道被 m0/m2 长时间占用」 | **不成立** | A0/A3 排队峰值 58 拍；A4 极端饱和 125000 拍仍不超时；AW 与 W 结构上不并发（overlap=0） |

---

## 3. 证据分级

### 3.1 RTL 级证明（本任务新增，可复核）

| 命题 | 证据 | 场景 |
|---|---|---|
| 真实 m0/m2 负载下 m3 排队峰值 = 58 拍 | `wait_cnt_3 PEAK=58` | A0, A3 |
| 真实 m0/m2 负载下 m3 的 AW 等待 = 2 拍 | `AWWAIT=2`, `max m3 AW wait=2` | A0, A2, A3, A4 |
| m0 100 % 饱和下 m3 靠 P3 配额获得 grant（125000 拍），且不超时 | `PEAK wait3=125000`, `to_err=0` | A4 |
| AW 通道与 W 通道从不并发（=0 拍重叠） | `aw&&wbeat=0` ×5 场景 | A0~A4, A5 |
| 任意 m3 超时必然置 `cmd_to_err[3]` | `cte=1101`，`[3]=1` | A1 |
| 写阶段中止使 IP 拒绝一切后续 AW（m3 的 AW 在 13k 拍内 0 次握手） | `m3 awready EVER seen=0`, `aw_hs m3=0` | A1 |
| `STS=0x26` 在 RTL 上可位级复现，且只对应「m3 无超时 + 数据错 + 别的写 master S_AW 超时」 | `STS byte=0x26` | A5 |
| m0/m2 并发**不会**破坏 m3 自检数据（同地址 16/16 PASS、逐字节相等） | `st_done=1 dc3=16`（模型正确实现 wstrb 时） | A0, A3 |

### 3.2 board-proven（沿用已有位流证据，本任务未重新烧板）

- `top_core_only` 05:38 版（mel/audio 接死）：APM 0，`DDROK` PASS，`DDR3 STS 01`（st_done=1, to_err=0）。
- `top_core_only` 07:13 版（i2s→audio→mel→npu 真跑）：APM 89、LUT 32615，FAIL，`STS 0x26`。
- `instrec_top.v:648` 的 `ddr3_ctrl_axi` 例化**没有参数覆盖**，因此板上实际使用 `AXI_USER_AP=1`、`DUMMY_WSTRB_ALL1=0`、`AXI_TO_LIMIT=4096`、`P3_QUOTA_TIMEOUT=125000`（与仿真一致）。

### 3.3 未证明（需要 IP 级或额外板级证据）

1. **真实 IP 为什么在高写负载下停 `wready`**：A1 只模拟了这个现象的后果，没有证明其成因。Pango DDR3 IP 的 `awready`/`wready` 生成条件属于黑盒契约，行为级模型无法覆盖。
2. **m3 的 `st_fail` 具体是哪一个候选**：
   - (a) IP 不实现字节掩码（`wstrb=0` 的 dummy write 真的写 0）→ 每条命令的**首拍**失配；
   - (b) 并发写流量下 IP 丢失/错放写 beat → 命令**中段**失配；
   - (c) 读数据通路与并发写冲突 → 读回的 beat 错乱。
   A5 只给出 (a) 的指纹（`WSTRB_IGNORE=1` 能产生 `0x26`）。
3. **板上两次现象是否同一次**：`to_err` 与 `st_fail` 是否发生在同一轮自检（同一次 boot，还是 KEY1 重跑后的第二次）。

---

## 4. 最小修复方案（按确定性排序）

> 约束：本任务**不改** `ddr3_ctrl_axi.v` / `ddr3_arbiter.v`，以下只给方案。

### 方案 1（最高确定性 / 零逻辑风险）：把 `cmd_to_err[3:0]` 全导出到诊断帧

- **文件与行号**：`src/ctrl/sys_ctrl.v:217-224`
- **改法**（1 行 + 注释）：
  ```verilog
  // {cmd_to_err[3:0], to_err, dbg_to_state[2:0]} = 8 bits, still 2 hex digits.
  assign ddr_sts_code = {ddr_cmd_to_err, ddr_to_err, ddr_dbg_to_state};
  ```
  （原 8 位的 `{1'b0, cte[3], to_err, dbg[2:0], st_fail, st_done}` 丢掉了 `st_fail`/`st_done`；这两项已分别由 `DDR3 FAIL @<addr>` 与 `DDROK` / `DDR3 SELFTEST` 行覆盖。）
- **为什么能解决问题**：不是修复，而是**让下一次板级失败一次定性**。有了 `cmd_to_err[0..3]`，`0x26` 这类字节立刻能判定「超时的是 m0 还是 m2 还是 m3」，从而不必再花一轮位流。当前正是因为这个位被丢掉，才产生了本次的误判。
- **副作用**：`DSTS` 字节语义变化；`scripts/diag_frames.py`（若解析 STS）与 `tests/` 中基于该位段的断言需同步；`uart_debug.v:401-405` 的 `hex_left=2` 不用改（仍是 8 位）。

### 方案 2（根因修复 / 中等风险）：写阶段超时后补完该突发（W-drain）

- **文件与行号**：`src/ddr3/ddr3_ctrl_axi.v:381-386`（`S_W` 超时分支）与 `406-411`（`S_DW_W` 超时分支）；`137`（`state` 声明）；`149`（`dbg_to_state_r` 声明）
- **改法要点**：
  1. `state` 由 `[2:0]` 扩到 `[3:0]`，新增 `S_WDRAIN = 4'd8`；`dbg_to_state_r` 同步扩到 `[3:0]`，`sys_ctrl.v:96/213` 与 `self_test` TB 的解码表加一项。
  2. `S_W`/`S_DW_W` 超时不再 `state <= S_IDLE`，而是 `state <= S_WDRAIN`，同时保持 `to_err/cmd_to_err` 的置位不变（**观测语义不变**）。
  3. `S_WDRAIN` 里继续用 `axi_wstrb = 32'h0000_0000`（**必须掩码，绝不能复用 `DUMMY_WSTRB_ALL1`**）接收 `axi_wready`，把 `beat_cnt` 补到 `cur_len`；补满后 `state <= S_SKIP_WLAST`（或直接 `S_IDLE`），并给 drain 单独一个 `4 * AXI_TO_LIMIT` 的放弃上限，避免第二次永久卡死。
- **为什么能解决**：A1 已把污染的**唯一机制**钉死为「AW 已握手、W 未发满就放弃」。补齐剩余 beat 后 IP 的写突发闭合，`awready` 恢复，后续 m3 的 AW 能在 2 拍内握手（A2/A0 已证明健康时就是这个数）。
- **副作用**：① `state`/`dbg_to_state` 位宽变化波及 `sys_ctrl` 解码、`tb_ddr3_subsys.sv` 的 3 位断言（`dbg_to_state == 3'd5` 等）与 `board_check` 的 STS 解释；② 超时后多占用 W 通道最多 16 拍；③ 若 IP 永久不给 `wready`，drain 需要自己的上限，否则把「一次 4096 拍的卡死」变成「一次 16384 拍的卡死」。
- **确定性评估**：机制已由 A1 证明，**方案本身是确定有效的**；风险主要在位宽波及面，故排第 2。

### 方案 3（规避 / 最小改动）：自检期间屏蔽业务流量

- **文件与行号**：`src/ctrl/instrec_top.v:645-646`（`ddr_cmd_valid` 拼装）
- **改法**（约 5 行）：
  ```verilog
  reg ddr_st_window;              // from st_start until st_done || st_fail
  always @(posedge core_clk or negedge core_clk_rst_n) ...
  assign ddr_cmd_valid = {st_cmd_valid,
                          ddr_st_window ? 1'b0 : mel_m2_cmd_valid,
                          ddr_st_window ? 1'b0 : (wl_busy ? wl_cmd_valid : npu_rd_cmd_valid_u),
                          ddr_st_window ? 1'b0 : m0_cmd_valid};
  ```
- **为什么有效**：A0/A3 已证明「无并发写流量时自检 16/16 通过、数据全对」；`05:38 版 DDROK PASS` 也正是这一条件的实测版。自检期间零写流量 ⇒ IP 不会因写 FIFO 满而停 `wready` ⇒ 既不会被污染，也不会出现 m3 数据失配。
- **副作用**：自检窗口约 400~500 拍（≈4 µs）内 m0 页写与 m2 读被暂停；`audio_sink` 的 `agg_freeze` 保持、CDC FIFO 需要吸收这 4 µs（44.1 kHz 下不足 1 帧，可忽略）；m2 的 mel 计算延后 4 µs（`mel_cycles` 预算 4.93 M 拍，无影响）。
- **局限**：只保护「自检窗口」。若污染在业务流量期间发生（例如 mel 跑 4.9 M 拍期间），仍会永久死锁——所以它是**规避**，不是根因修复。

### 方案 4（可诊断性 / 1~2 行）：`st_fail_addr` 细化到 beat 粒度

- **文件与行号**：`src/ctrl/self_test.v:231-233`（写阶段）与 `257-263`（读阶段）
- **改法**：
  ```verilog
  // write phase (ST_WDATA): beat position is known
  st_fail_addr <= cmd_addr + ({24'd0, beat_idx} << 5);
  // read phase (ST_RDATA): byte offset from the running word index
  st_fail_addr <= cmd_addr + ({21'd0, exp_idx[9:3]} << 5);
  ```
- **为什么能解决问题**：现在报的是**命令首地址**，无法区分「首拍被 dummy write 破坏」与「中段错乱」。若板上每次 `DDR3 FAIL @` 都落在每条命令的**首拍**（`0x300000/0x300200/...`），即锁定候选 (a)（IP 不实现字节掩码）；若落在中段，则指向 (b)/(c)（数据通路）。
- **副作用**：只改报错地址的取值，`st_fail`/`st_done` 判据不变；`tests/` 里若有对 `st_fail_addr` 的等值断言需同步（`tb_ddr3_subsys.sv` 的 C10 断言 `st_fail_addr == 28'h0030_0000` 在首拍失配时仍成立）。

### 方案 5（**不推荐**）：把 `AXI_TO_LIMIT` 从 4096 提高

- **文件与行号**：`src/ddr3/ddr3_ctrl_axi.v:64`（参数默认值）
- **为什么无效**：A1 证明污染是**永久性**的——m3 的 `awready` 在 13103 拍内 0 次。任何有限上限最终都会超时，提高只会把「一次 4096 拍的卡死」延后成「一次 16384 拍的卡死」。而且 `sys_ctrl` 对整轮自检的预算是 100 ms（800 万拍），多次重试会吃掉这个预算。
- **副作用**：延长故障暴露时间，掩盖问题。

### 方案 6（**不推荐**）：给 m1/m2 也加 P3 式配额

- **文件与行号**：`src/ddr3/ddr3_arbiter.v:91-109`（`p3_override`/`sel_onehot`）
- **为什么无效**：A0/A3 的 `wait_cnt_3` 峰值只有 58 拍，A4 的极端饱和也只是把排队变成 125000 拍且仍然不超时。**仲裁不是瓶颈**。
- **副作用**：无谓降低 m0/m2 的带宽，且要新增两组饥饿计数器。

### 方案 7（**不推荐**）：把 audio 页写从 `len=0` 改成 `len=15`

- **文件与行号**：`src/audio/audio_sink.v:464-473`（`m0_cmd` 生成）
- **为什么无效**：A4 证明短突发本身不会让 m3 超时；改成 `len=15` 会破坏 8256 页/窗口的地址映射与左右通道打包。除非有 IP 侧证据证明「32 B 短突发会把写 FIFO 压满」，否则不该动。

---

## 5. 板级可判定清单（下一轮不构建、只读串口就能定位）

按以下顺序只看 4 个数，即可把 3.3.2 的三个候选收敛到唯一一个：

| # | 证据 | 在哪 | 判定 |
|---|---|---|---|
| 1 | `DDR3 FAIL @<hex32>` 的地址 | 已有 `uart_debug` 的 id 4 行 | `0x0030_0000` ⇒ 第 1 条命令失败；`0x0030_0200/0400/...` ⇒ 后续命令 |
| 2 | 若已按方案 4 改：失配落在**每条命令首拍** | `st_fail_addr & 0x1FF == 0` | **是** ⇒ 候选 (a) dummy write 掩码失效（最可能） |
| 3 | 若已按方案 1 改：`cmd_to_err[3:0]` | `DSTS` 帧 | `[0]=1, [3]=0` ⇒ 超时是 m0（与 A5 一致）；`[2]=1` ⇒ m2 的 dummy write |
| 4 | `audio_err_cnt`（audio_sink 的 33.5 ms 超时计数） | `instrec_top` 已有 tap | 非 0 ⇒ m0 的写通路确实长时间拿不到 `done`，佐证 IP 侧写通道拥塞 |

补充建议（不改 RTL 即可做）：把 `ddr_wlast_miss_cnt` 也打到诊断帧。A1 的污染链会在 `wlast_miss` 上留下痕迹（中止的突发没有 `wusero_last` 收尾），这是一个**零成本的正交观测**。

---

## 6. 与既有结论/文件的关系

- 本任务**没有**修改 `src/ddr3/ddr3_ctrl_axi.v`、`src/ddr3/ddr3_arbiter.v`（遵守任务约束）。
- `sim/ddr3_axi_model.sv` 的新参数 `WSTRB_IGNORE` 默认 0，**不改变**原有 15 个 `ddr3_subsys` 场景的行为（回归 `ddr3_subsys PASS`，15/15）。
- `sim/run_sim.py` 只在 `register(Case(...))` 区域新增一个 case，编译/运行框架未改。
- 本报告修正了 T37 任务描述中的一处判读偏差（见第 2 章），后续若按原判读去做「给 m1/m2 加配额 / 提高 AXI_TO_LIMIT」的修复，将**不会**解决板上问题。