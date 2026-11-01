# T28 DDR3 子系统仿真结论（`sim/tb_ddr3_subsys.sv`）

> **状态**：仿真已完成，15 个场景 **全部 PASS**（`scenarios failed: 0 / 15`）。
> **证据**：`reports/sim_ddr3_run.log`（本次运行的完整 stdout）、本文件、下方哈希。
> 本文所有数字均来自仿真输出，不引用未跑过的推断；**模型假设与未证实项见 §10**。

---

## 1. 一句话结论

**控制器 + 仲裁器 + 自检这一层在 DDR3 IP 遵守已知契约时是完全正确的（16 条命令 364 拍完成、`st_done=1`）；
但这套仿真不能替代烧板来证明「真实 DDR3 通不通」——它证明的是「若 awready 不来，控制器必然在 4096 拍（32.8 µs）
于 `S_AW` abort，并记录 `cmd_to_err[3]=1 / dbg_to_state=S_AW`」，这正是板级 `DDR3 STS` 行需要比对的那组编码。**

换句话说：仿真把「DDR3 状态」压缩成一个可判读的三元组
`(to_err, cmd_to_err[3], dbg_to_state)`，并把每一类握手失败对应的取值固定下来；
真实 DDR3 的 PHY/DLL 行为仍然只能由板级 `DDR3 STS`（T21 新增）给出。

---

## 2. 交付物与哈希

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `sim/tb_ddr3_subsys.sv` | 74324 B | `CA93 8592 0279 6414 8A20 A84B 69D8 F493 5BBD E397 74A6 59B3 5323 D817 0A1B 6BAE` |
| `sim/ddr3_axi_model.sv` | 15087 B | `D5BF 32E5 2996 E241 D289 4255 66A5 239E D095 E39E E230 D4D8 0EFC 53A7 BEB2 E08B` |
| `sim/prep_rtl_sim.py` | 2444 B | `26A1 9435 523A 244E D421 D218 2893 2EBE D572 009B 2C41 FF66 23F3 16D1 54B9 16C8` |
| `sim/run_sim.py`（改 1 个 register 块；T27 并发维护，哈希为 23:53 快照） | 31679 B | `51E4 4AA9 D97C 7C5E 4DE9 6FA7 263D CBF1 B9CC 5142 BE75 8CC2 D521 10CF 623A 67F1` |
| `reports/sim_ddr3_run.log` | 3336 B | `B26A 2390 4225 94D1 3184 92F5 D05A E67A 4B69 BDA1 A846 6AB7 F0C3 EEA1 C7AB DAA0` |

未改动 `src/**`、`constraints/**`，未跑 PDS、未烧板、未触碰 `cdt_js`；未 commit / 未 push。

---

## 3. 运行方式与耗时

```powershell
cd instrec_fpga
python sim/run_sim.py ddr3_subsys      # 本次实测 33.6 s（含 Verilator 生成 + g++ 编译）
```

| 阶段 | 实测 |
|---|---|
| Verilator `--cc` 生成 + g++ 链接（每次） | 17.6 ~ 40.0 s（视 obj 缓存命中） |
| **纯仿真运行**（12 310 拍 @10 ns ≈ 123 µs 模拟时间） | **0.030 s** |
| 单次 `run_sim.py ddr3_subsys` 总墙钟 | **17.6 ~ 40.0 s（均 < 2 min 上限）** |

> 独立命令行（不经 `run_sim.py`）写在 `tb_ddr3_subsys.sv` 头注释 §17-37 行，含 `python sim/prep_rtl_sim.py` 一步。

---

## 4. 仿真架构

```
tb_ddr3_subsys.sv (tb + 15 个 ddr3_subsys_case 实例，并行)
  └─ ddr3_subsys_case (每场景一份)
       ├─ ddr3_ctrl_axi  (src/ddr3/ddr3_ctrl_axi.v, 含内部 ddr3_arbiter 例化)
       ├─ self_test      (src/ctrl/self_test.v, 挂 master 3)
       ├─ ddr3_axi_model (sim/ddr3_axi_model.sv, 行为级 IP)
       └─ 场景驱动 (m0/m1/m2 激励 + 判据 FSM)
```

**行为模型固化的是项目的硬契约（不是标准 AXI）：**

| 契约 | 模型实现 |
|---|---|
| 无 `axi_rready` | 读 burst 启动后每拍推一个 beat，不做任何反压握手 |
| 无 `axi_wvalid` | `wready` 高即认为该拍被 IP 接收（与控制器 `wready_beat` 判据同拍） |
| 无 `b` 通道 | 写 burst 以 `awlen+1` 拍收完为完成 |
| `axi_wusero_last` | 最后一拍被接收后的**下一拍起保持 4 拍**，覆盖控制器 4 拍 epilogue 窗口 |
| 字节 strobe | 按 `wstrb` 逐字节写（`wstrb=0` 不破坏原数据）——这是 §7.6 机理的基础 |

**故障注入参数**：`AW_READY_AW_COUNT`（前 N 个 AW 才 ready）、`W_READY_BURST_COUNT`、`AR_NEVER`、
`R_MODE`（0 正常 / 1 `rvalid` 恒 1 且 `rlast` 永不到 / 2 `rvalid` 恒 0）、`AW_DELAY`/`AR_DELAY`/`W_DELAY`。
另外可观测 `obs_len0_wr` / `obs_len0_wstrb0` / `obs_len0_wstrb1`（单拍写的 strobe 形态）。

---

## 5. 场景矩阵与逐项结果

| # | 场景 | 判据 | 结果 |
|---|---|---|---|
| C00 | 健康模型 + self_test 16 条命令 | `st_done=1, st_fail=0, done[3]=16, to_err=0, wlast_miss=0` | **PASS** |
| C01 | `m0_done` **接通**（audio 语义），m0 + m3 并发，配额 125 000 | self_test 完成且不依赖配额 | **PASS** |
| C02 | `m0_done` **断开**（m4 失效态），配额 500 | self_test 仍能完成（靠配额兜底） | **PASS** |
| C03 | 读命令**电平保持**，fifo 未排空时 | 排空后仍被 grant，`done[2]=2` | **PASS** |
| C04 | 读命令**单拍脉冲**，fifo 未排空时 | 命令丢失（4 000 拍无 done，`to_err=0`） | **PASS** |
| C05 | `awready` 永不来（self_test） | `to_err=1, cmd_to_err[3]=1, dbg=S_AW, done[3]=1, st_fail=1` | **PASS** |
| C06 | `wready` 永不来（self_test） | 同上，`dbg=S_W` | **PASS** |
| C07 | `arready` 永不来（self_test，8 写成功后） | `dbg=S_AR, done[3]=9, st_fail=1` | **PASS** |
| C08 | `awready` 永不来（简单读 → 卡 dummy 写地址） | `dbg=S_DW_AW` | **PASS** |
| C09 | `wready` 永不来（简单读 → 卡 dummy 写数据） | `dbg=S_DW_W` | **PASS** |
| C10 | `DUMMY_WSTRB_ALL1=1` + self_test | `st_fail=1, fail_addr=0x0030_0000` | **PASS** |
| C11 | 四主口同时请求，配额实际关闭 | 完成顺序 `m0→m1→m2→m3`（`seq=0b00011011`） | **PASS** |
| C12 | 看门狗盲点（`rvalid` 恒 1 / `rlast` 永不到） | 12 288 拍后 `to_err=0, done[2]=0`，仍在 S_R | **PASS** |
| C13 | P3 配额（200 拍），m0/m1/m2 持续重发 | m3 拿到 1 条；m1/m2 被饿死 0 条 | **PASS** |
| C14 | 写数据阶段 abort 后的恢复 | 第 1 条卡 `S_DW_W`，第 2 条卡 `S_DW_AW` | **PASS** |

**逐项清单（TB 自打印，节选 `reports/sim_ddr3_run.log`）：**

```
1.  self_test 16 cmds all complete        : PASS
2.  m0_done fix keeps m3 served           : PASS
2b. m0_done open still bounded by quota   : PASS
3a. level-held read cmd is safe           : PASS
3b. single-cycle read cmd is lost         : PASS
4.  watchdog fires in S_AW                : PASS
4b. watchdog fires in S_W                 : PASS
4c. watchdog fires in S_AR                : PASS
4d. watchdog fires in S_DW_AW             : PASS
4e. watchdog fires in S_DW_W              : PASS
5.  watchdog blind spot reproduced        : PASS
6a. dummy strobe all-zero is safe         : PASS
6b. dummy strobe all-one corrupts read    : PASS
7a. fixed priority m0>m1>m2>m3            : PASS
7b. P3 quota override works               : PASS
x.  abort recovery (IP state polluted)    : PASS
scenarios failed         : 0 / 15
```

---

## 6. `DDR3 SUBSYS VERDICT`（仿真原样输出）

```
DDR3 SUBSYS VERDICT
  self_test 16 cmds        : PASS
  st_done / st_fail        : 1 / 0
  to_err / cmd_to_err[3]   : 0 / 0
  dbg_to_state (timeout at) : S_AW
  m0 starvation resolved   : YES (m3 done cyc C01=376 wired vs C02=8412 quota-only)
  watchdog blind spot      : CONFIRMED
```

> `dbg_to_state` 行取 C05（`awready` 永不来）的编码。按任务要求填单值，其余阶段的编码见 §5 与 §8。

---

## 7. 七项要求逐条结论

### 7.1 基本读写（16 条命令）
C00：**PASS**。`st_done=1 / st_fail=0`，`done[3]=16`（8 写 + 8 读），`to_err=0`，`wlast_miss=0`，
`addr_err=0`，全程 **364 拍（2.9 µs @125 MHz）**。
→ 控制器状态机、读 fifo 弹性、`wusero_last` 侧证据在契约成立时**没有缺陷**。

### 7.2 `m0_done` 修复有效性
| 配置 | m3 完成时刻 | 是否依赖 P3 配额 | m0 完成数 |
|---|---:|---|---:|
| C01 `m0_done` 接通 | **376 拍** | 否（配额 125 000 远未触发） | 2 |
| C02 `m0_done` 断开（m4 态） | **8 412 拍** | 是（配额 500，每条 ≈525 拍） | 128 |

→ **starvation 已解除**：接通后 m3 在 m0 的页间空隙内完成，快了 **22.4 倍**；
断开时不会永久卡死（配额兜底），但吞吐退化为「每 1 ms 一条」，与 m4fix 想修的行为一致。

### 7.3 单拍 vs hold `cmd_valid`
- C03（hold）：第二个读在 fifo 排空后正常拿到 grant 并完成（`done[2]=2`）——**hold 是安全解**。
- C04（单拍）：在 fifo 非空（`arb_en=0`，读命令需 `fifo_empty`）的窗口内发出的单拍请求**被完全丢弃**
  （4 000 拍无 done，且 `to_err=0`，因为命令根本没进入控制器、连看门狗都看不到它）。
→ 与 T1 模型结论一致：**`cmd_valid` 必须是电平保持到 `done`**。

### 7.4 看门狗触发
`awready` 永不来（C05）：4096 拍后 `to_err=1`、`cmd_to_err[3]=1`、`dbg_to_state=1(S_AW)`、
`done[3]` 单拍脉冲、FSM 回 `S_IDLE`，`self_test` 转 `st_fail`（不再永久卡死）。
其余阶段同样命中：`S_W`(C06)、`S_AR`(C07)、`S_DW_AW`(C08)、`S_DW_W`(C09)。
→ 六个阻塞态都有看门狗路径并实测命中；`S_R` 的守卫存在盲点（见 7.5），`S_WLAST` 不含看门狗（4 拍 epilogue，无风险）。
实测周期：C05 `cyc=4111`、C06 `4112`、C07 `4290`（8 写 ≈180 拍 + 4096 + 15）、C08 `4111`、C09 `4112`。

### 7.5 看门狗盲点
C12（`rvalid` 恒 1 / `rlast` 永不到）：跑 **12 288 拍 = 3 × AXI_TO_LIMIT** 后
`to_err=0`、`done[2]=0`、`rd_valid[2]` 持续为 1、FSM **永久停在 `S_R`**。
→ 根因在 `src/ddr3/ddr3_ctrl_axi.v:317-323`：累加条件包含 `(state == S_R) && !axi_rvalid`，
只要 `rvalid` 一直为 1 就永远清零计时；`S_R` 退出只认 `rlast`（426-439 行）。
**若真实 IP 出现「rvalid 恒 1 但 rlast 不来」，控制器没有任何第二道守卫**（无 beat 计数上限、
无 fifo 满告警），会永久挂死并让 `self_test` 永远等不到 `done`。这是**已知且已复现的风险**。

### 7.6 dummy-write 策略
- C00（`DUMMY_WSTRB_ALL1=0`）：8 次读 → **8 次单拍写、8 次 `wstrb` 全 0**，数据完好，自检 PASS。
- C10（`DUMMY_WSTRB_ALL1=1`）：第 1 次读的 dummy 写 **`wstrb=全 1`、`wdata=0`**，
  把读区首拍 32 B 覆写成 0 → 首个读命令的首 beat 立即失配，`st_fail=1`、`st_fail_addr=0x0030_0000`。
→ **这就是 T8 中 demo 配置（ALL1）FAIL 的完整机理**：dummy 写只对「先读后写」的区域安全，
对「读了马上要比对」的自检路径是破坏性的。`DUMMY_WSTRB_ALL1` 必须保持 0。

### 7.7 四主口仲裁
- C11（配额关闭）：并发请求的完成序列严格为 **m0 → m1 → m2 → m3**，固定优先级正确。
- C13（配额 200 拍，m0/m1/m2 持续重发）：m3 在被饿死的情况下仍拿到 **1** 条（配额生效）；
  但 **m1（NPU 权重）/ m2（mel）完成 0 条**——见 §9 的 R-2。

---

## 8. 关键定量推论：为什么 m4fix 板上只能看到 30 字节

仿真给出三条硬时间：

| 情形 | 从 `st_start` 到结论的时间 | 换算 |
|---|---:|---:|
| DDR3 正常（C00） | 364 拍 | **2.9 µs** |
| `awready` 不来 → abort（C05，`AXI_TO_LIMIT=4096`，实测 `cyc=4111`） | 4096 拍 | **32.8 µs** |
| m0_done 断开 + 配额 500（最坏慢速通过） | 8412 拍 | **67.3 µs** |

而 `DDR3 SELFTEST...` 这一行在 `uart_debug` 里产生的忙窗口是 **~3 ms** 量级（T20 报告）；
`uart_debug` 在忙时**静默丢弃** `dbg_line_fire`（`src/ctrl/uart_debug.v:330-334`）。

→ **无论 DDR3 通还是不通，结论行都在 `st_start` 后 3 µs ~ 67 µs 内产生，全部落在 3 ms 忙窗口内**：

- DDR3 通 ⇒ `DDROK` 被丢 → 30 字节；
- DDR3 不通 ⇒ `DDR3 ERR @...` 被丢 → 同样 30 字节；
- 即使 `m0_done` 断开让自检慢 22 倍（67 µs），**仍然**远小于 3 ms ⇒ 仍被丢。

**所以 m4fix 的 30 字节在时间上只能得出这两种解释，与 T20 的二义性分析完全一致，
并且给出了可复算的定量边界（结论窗口 3 µs…67 µs ≪ 3 ms 忙窗口）。**

> 本仿真**没有**把 `sys_ctrl` / `uart_debug` 放进环内，因此不是「逐字节复现 30 字节」，
> 而是「证明 30 字节是唯一可能输出」的时间关系。串口侧的修复属 T21（结论锁存 + `!dbg_busy` + `DDR3 STS`）。

---

## 9. 发现的缺陷与设计缺口（只报告，未改 RTL）

| ID | 位置 | 机理 | 影响 |
|---|---|---|---|
| **R-1（仿真期间已修复）** | 原 `src/ctrl/self_test.v:136` | 端口已声明 `output wire [255:0] wdata`，模块体内又写了一次 `wire [255:0] wdata;`，**重复声明**；PDS 容忍，Verilator 5.050 直接 `%Error: Duplicate declaration of signal: 'wdata'`。**在本仿真交付前，上游已删除该行**（`sim/prep_rtl_sim.py` 现报 `patched=False`） | 修复前必须派生副本（`sim/run_sim.py` 的 `overrides` 自动完成）；修复后 `_apply_overrides` 走 `count==0` 分支直接用源文件。**修复前后本 TB 均为 `RESULT: PASS`** |
| **R-2** | `src/ddr3/ddr3_arbiter.v:91-112` | 只有 **P3** 有 starvation 配额（`p3_override`）；P1/P2 没有 | C13 实测：m0 持续满载时 **m1/m2 完成 0 条**（永久饿死），m3 靠配额得 1 条。当前音频是稀疏的（每页 ≈363 µs 一条 len=0），因此板上未暴露；若音频注入模式（FIFO 空时 2 834 拍节拍）叠加 `m0_done` 失效，NPU 权重/mel 会被无限期推迟 |
| **R-3** | `src/ddr3/ddr3_ctrl_axi.v:317-323, 426-439` | 看门狗只在 `S_R && !rvalid` 时累加；`S_R` 只认 `rlast` 退出 | `rvalid` 恒 1 而 `rlast` 不到 ⇒ **永不超时**（C12 复现）。建议加「单 burst beat 计数 > `cur_len`」或「持续 N 拍无 `rlast`」的第二道守卫 |
| **R-4** | `src/ddr3/ddr3_ctrl_axi.v:359-440`（abort 路径） | abort 只把控制器 FSM 拉回 `S_IDLE`，**不通知 IP 放弃未完成的 burst** | C14 复现：一旦写数据阶段超时，模型仍持有未完成写 burst ⇒ 后续每条命令都卡在 `S_DW_AW` 4096 拍，**无法自愈**。见 §10 的模型假设标注 |

---

## 10. 模型假设与**未证实项**（显式标注）

1. **`awready` 语义**：模型假设「一个未完成的写 burst 会让后续 AW 不 ready」（R-4/C14 的基础）。
   真实 IP 是否允许多 outstanding AW **未 board-proven**。因此 R-4 是「模型下的必然、真实器件下的待证」。
2. **`wusero_last` 时序**：模型在最后一拍**之后**拉高并保持 4 拍。真实 IP 的具体相位未测；
   若真实器件不给 `wusero_last`，控制器只会累计 `wlast_miss_cnt`（不阻塞），因此**不影响通过/失败判定**。
3. **DDR3 电气/PHY/DLL**：模型是零延迟、永远正确存取的理想器件。**本仿真对真实 DDR3 是否「通」零信息**。
4. **未在环**：`sys_ctrl`、`uart_debug`、`ddr3_wrapper`、DDR3 PHY。所以串口字节序列不在本仿真结论内。
5. `AXI_TO_LIMIT` 用默认 4096、`P3_QUOTA_TIMEOUT` 在 C01 用 125 000（默认值）、C02/C13 缩小以便仿真；
   缩小配额只改变「多久拿到 grant」，不改变仲裁语义（C11 已用大配额验证固定优先级）。

---

## 11. 偏差与风险

| 类型 | 内容 |
|---|---|
| 偏差 D-1 | 交付物增加 `sim/prep_rtl_sim.py`（R-1 的独立绕过路径）与 `reports/sim_ddr3_run.log`（证据），任务只列了 3 个文件 |
| 偏差 D-2 | 修改了 `sim/run_sim.py` 的 `register(Case(name="ddr3_subsys"...))` 块：加 `overrides`（R-1）、`extra_flags=["-y","sim"]`（模型文件解析）、去掉 `optional=True`。**只改这一个块**，未动其它 case 与构建逻辑 |
| 偏差 D-3 | 任务要求「复现 30 字节静默」——本仿真只能定量复现产生该现象的时间关系（§8），未逐字节复现（无串口模块） |
| 偏差 D-4 | 仿真期间上游修改了 `src/ctrl/self_test.v`（删除重复声明）与并发维护了 `sim/run_sim.py`。本报告结论在**修复前（74315 B 版 TB/旧 RTL）与修复后（74324 B 版 TB/新 RTL）两次运行中一致**，均为 15/15 PASS |
| 风险 R-A | C02/C13 用缩小配额，不能据此推断真实 1 ms 配额的时序 |
| 风险 R-B | 行为模型是 2 态（Verilator 2-state），X 传播类隐患不在覆盖范围内 |
| 风险 R-C | 模型内存为 256-bit × 65 536 beat 的扁平数组（低 2 MB），0x00/0x10/0x20/0x30 四个 64 KB 段互不别名，但**不是通用 DDR3 地址译码模型** |

---

## 12. 能否替代「烧板读 30 字节」来判断 DDR3 真实状态？

**不能完全替代，但能把判断空间压缩到可枚举。**
仿真能证明的是：控制器/自检/仲裁在三类场景下（健康、各阶段握手卡死、看门狗盲点）行为与设计一致，
并且**每一类失败都有唯一的 `(to_err, cmd_to_err[3], dbg_to_state)` 编码**；
它不能证明真实 IP 的 ready/rlast 行为，也不能替代串口判读。

**可操作的结论**：板级只需拿到 T21 的 `DDR3 STS` 一行，按下表与仿真的期望编码对号入座即可定论：

| 板级 `DDR3 STS` | 含义 | 对应仿真场景 |
|---|---|---|
| `to_err=0, cte3=0, dbg=0` 且已有 `DDROK` | DDR3 通 | C00 |
| `to_err=1, cte3=1, dbg=1 (S_AW)` | PHY/DLL 未就绪，`awready` 不来 —— 最可能的真实故障 | C05（32.8 µs abort） |
| `dbg=2 (S_W)` | 写数据通路卡死 | C06 |
| `dbg=4/5 (S_DW_*)` | 读前 dummy 写阶段卡死 | C08 / C09 |
| `dbg=6 (S_AR)` | 读地址通道卡死 | C07 |
| `to_err=1, dbg=7` | 读数据永不到（`rvalid` 恒 0） | `R_MODE=2`（模型支持，未单列场景） |
| `to_err=0` 但无 `DDROK` 且长期无进展 | **看门狗盲点**（`rvalid` 恒 1 / `rlast` 不到） | C12（已复现） |

一句话：**仿真把「DDR3 卡在哪」变成了一张 6 行查表；真实那一格仍然必须由板级 `DDR3 STS` 填。**