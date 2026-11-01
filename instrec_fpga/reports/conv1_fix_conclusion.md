# T25 conv1 contract 映射修复 + 剩余失配排查（结论）

> 状态：**仿真归零 + 板级归零**（仿真 792576/792576；板级 3072/3072，`compare_conv1.py` exit 0）。
> 位流 SHA-256 `5EEEC976…`，run `20261031-235952-09aae62a`。
> 证据分级：`sim-proven` = Verilator 全流逐字节对拍；`board-proven` = 上板 UART 复核；
> `未证实` = 仅推理、未取证。本文所有根因均有 sim-proven 证据。

---

## 1. 结论摘要

| 项 | 修复前（板级） | 修复后（仿真，全流） |
|---|---|---|
| 全流 mismatch / 792576（仿真） | — | **0** |
| 采样窗口 mismatch / 3072（板级） | 2471（T22 首次）→ 1300（P4 后仍错位） | **0** |
| 首个失配 | `sample 0`（row0/grp0/col0/ch0，期望 4 得 2） | 无 |
| status 帧自算 sum（板级） | 184269（修复前） | **26685 == golden** |
| 串口重组 sum（板级） | 184223 | **26685 == golden** |
| `compare_conv1.py` 退出码 | 1 | **0** |
| `stream_samples` / `done_flag` | 792576 / 1 | 792576 / 1 |

失配数在逐项修复后的下降轨迹（Verilator，全 792576 样本）：

```
636264  修前（contract 映射错 + tap 相位错 + 2 bank 冲突 + requant shift 错位）
524703  + P0a/P0b(contract 映射与相位) + P4(cap 读回)
211388  + P1a(tap 子字相位)
  1300  + P1b(第三个 tap bank)
     0  + P2/P3(requant shift 相位、组边界 contract 快照)
```

1300 个残差**全部**落在 `col = 257`（每组最后一个像素）：`per_col_last = [0,0,0,0,0,0,0,1300]`。

---

## 2. 仿真方法（本轮的关键改变）

Verilator 5.050 + `sim/tb_top_conv1.sv` 直接仿真 `top_npu_conv1_test`（无 DDR3、无 IP，
只有 RTL + `hex_conv1/*.hex`）：

```
H:\GG\bin\verilator.bat --binary --timing -j 4 -Wno-fatal \
  --top-module tb_top_conv1 --public-flat-rw -Mdir build/sim_conv1_obj \
  src/diag/top_npu_conv1_test.v src/npu/conv_engine.v src/npu/requant_unit.v \
  src/ctrl/uart_tx.v src/diag/diag_uart_report.v sim/tb_top_conv1.sv
./build/sim_conv1_obj/Vtb_top_conv1.exe      # 1.5 s，产出 build/sim_conv1_y.bin
python build/compare_sim_conv1.py --json build/sim_conv1_cmp.json
```

- TB 抓全部 792576 个 `y_valid/y_u8`（不是 6 个 512 窗口），因此**边界、组边界、每一列
  都在观测范围内**——板级取样窗口恰好看不到 `col257` 的全貌。
- TB 在 `snapshot_go` 拍 dump `bias_act/M_act/shft_act/acc_snap[0..15]`，并逐拍 dump
  `c_step/ctr_addr/ctr_dout/cload_cnt` 与 `mac_cnt/x_eff/w_data_q2[7:0]`。
- 单轮迭代成本 1.5 s（编译 25 s），替代了 7 min 构建 + 烧板。

**诊断价值证明**：`row0/grp0/col0..2` 的 `acc_snap[0..15]` 与 T24 的 Python 模型
**逐值相同**（col0 = `4409 20494 -32693 -38427 31079 -34901 4755 10213 4491 -31666
-23631 -44053 1818 -33453 47671 17336`），说明 acc 通路本身没问题，残差全部来自参数/相位。

---

## 3. 根因清单（全部 sim-proven）

### P0a `src/diag/top_npu_conv1_test.v` — contract 地址映射
`conv1_ctr.hex` 是**块**布局：`0..47` 全部 48 个 bias、`48..95` 全部 M、`96..143` 全部
shift，块内同组 16 字连续。`conv_engine` 却按「本组 16 bias → 16 M → 16 shift」消费。
旧代码把「该组 48 字」当成一个连续窗口：

```verilog
wire [5:0] ctr_base = (job_grp==0) ? 6'd0 : (job_grp==1) ? 6'd48 : 6'd96;
ctr_addr <= {2'd0, ctr_base} + {2'd0, c_step};
```

两个错叠加：
1. 连续窗口 ≠ 三段（grp0 的 M 读成 `bias[16..31]`；grp1 的 bias 读成 `M[0..15]`）。
2. **`ctr_base` 只有 6 位，`6'd96` 截断成 32**（grp2 读到 `bias[32..47]` 当 bias）。

修复：按块基址 + `job_grp*16` + 块内 lane 取址（第 236–252 行）。

### P0b 同上 — contract ROM 地址相位晚 2 拍
仿真逐拍 trace（`build/sim_conv1_dbg.txt`）：

```
CTR c_step=1 ctr_addr=0 dout=-287  cnt=0   -> bias[0]
CTR c_step=2 ctr_addr=1 dout=-287  cnt=1   -> bias[0] 又写一次
...
CTR c_step=17 ctr_addr=49 dout=-5  mv=1 cnt=16 -> M[0] = bias[15]
```

`ctr_dout` 在地址寄存后再晚一拍，conv_engine 再晚一拍采样 → beat k 读到的是
「k−2 拍写下的地址」。修复：beat k 写逻辑字 `k+1`，并在 launch 沿预取 word0。

### P1a 同上 — tap 子字相位晚 2 拍
症状（第一次修完 contract 后仍 80% 失配）：`sim acc[lane k] == 模型 acc[lane k−4]`
（lane 4..15 拿到 lane 0..11 的权重，lane 0..3 是脏值），差值恰为
`bias[k] − bias[k−4]`。修复：`w_addr <= w_base + t_step + 1`（`t_step < 35`），
`c_step == 48` 沿预取 `w_base`。

### P1b 同上 — tap bank 数量不足
三个输出组连续轮转，却只有 `tap_bank0/1` 乒乓。grp2 用 bank0，而「grp1 结束时启动的
job（重新装载 grp0）」正好在 grp2 扫描期间改写 bank0 → **通道 32..47 整帧用的是 grp0
的权重**（`per_channel[32..47] ≈ 16300/16512` 错）。
修复：增加 `tap_bank2`，写入选 `job_grp`、读入选 `use_grp`。

### P2 `src/npu/requant_unit.v` — shift 流水相位错位（产品 RTL 缺陷）
`shift_q/zp_q` 只在 S1 锁存，而 S3 的桶形移位器要两拍后才用到它们，届时已被下一拍覆盖：

```
lane0: prod>>(shift=41) = 3.53 -> golden 4，仿真 7 = prod>>40 = lane1 的 shift
lane7: 仿真 18 == prod(lane7)>>40 == lane8 的 shift
lane15: 仿真 10 == prod(lane15)>>41 == 下一拍(回绕 shft_act[0])=41
```

修复：加 S2 级 `shift_q2/zp_q2`，S3/S4 使用对齐后的值（S4 再推一级 `zp_q3`）。
**这是 NPU 数值核心的通用缺陷，不止 conv1**（任何层只要相邻通道 shift 不同就会错）。

### P3 `src/npu/conv_engine.v` — 组边界像素用了下一组 contract
`snapshot_go` 与 `advance_now` 同拍：`acc_snap` 在快照沿变成当前组的正确值，但同沿
`act <= shd` 已把 contract 换成下一组，16 拍 drain 正好跨过 promote。
证据：col257 的 `acc` 与模型完全一致，但用 `M[16..31]/shift[16..31]`（下一组）重算时
**16/16 命中**（用本组 9/16）。
修复：drain 参数与 `acc_snap` 同沿快照到 `m_drn/shft_drn`。
（注：`boundary_ok` 只能让快照等 shadow 就绪，无法避免 promote 本身，**top 侧无法规避**。）

### P4 同上（top）— cap 读回差一拍
`cap_rd_addr` 与 `cap_dout` 同沿更新，而 `dsb[ro_i-1] <= cap_dout` 用的是上拍值：
每 24 样本帧整体错位一个样本（第一帧 `dsb[0]=cap_ram[0]` 重复）。
板上证据：`obs[0] == obs[1]`（都是 2）；status 帧自算 sum 184269 与重组 sum 184223 差 46。
修复：`cap_rd_addr(ro_i) = ro_base + ro_i + 1`，入帧沿预取 `ro_base`。

### P5 同上（top）— readout arm 与 frame fire 同沿，永久滞后一帧
P4 修好后，板级 `status` 帧自算 sum 已经等于 golden sum（26685），但重组的 3072 样本
仍 2470 个错——即 **cap 采集完全正确、只有 readout→UART 的重排错**。全 UART 链路仿真
（TB 直接抓 `tx_byte_valid/ready` 的字节流，交给 `compare_conv1.py`）复现出与板级
逐项相同的结果（2470 / 26998 / 26685），并给出帧级证据：

```
RO base=24 cyc=1719898      <- readout of block 1 finishes 24 beats AFTER
FR f=1     cyc=1719874      <- data frame 1 has already latched dsb
```

即 `F_WAIT` 的 else 分支在同一沿既 `report_fire` 又 `ro_base <= ro_base_next;
ro_i <= 0`，readout 要 25 拍而 fire 立刻锁存 dsb → 每个 data 帧携带 **上一块**，
最后一帧重复块 126。另外第 3 个 status 帧走的是 `sts_cnt != 0` 分支，**根本不 arm**，
所以第一块之后还会永久缺一次 arm。
修复：新增 `ro_arm` 标志，**fire 之后 1 拍**才 arm 下一块；并在最后一个 status 帧
（`sts_cnt == 1`）也 arm 首块。修复后全链路对拍：`mismatch=0`、`exit=0`。

---

## 4. shift 合法性核实（T25 第 2 步的要求）

`requant_unit` 对 64 位乘积做移位，`shift` 是 7 位（0..127），≥64 的语义在 PDS 下不可依赖。
对 `src/outputs/layer_contract.json` 的 conv1 段核实：

```
conv1 shift: min 37, max 41, 全部 1 <= shift <= 63  -> 合法
```

（契约整体 37..53，同样 ≤63。）修复后的地址映射保证 shift 只来自 `96+grp*16+lane`，
即真正的 shift 块，因此**不会再读到 M/bias 的低 7 位**。本轮仿真 792576 样本 0 失配，
也从行为上证明不存在越界移位。

---

## 5. 未修 / 未证实项

- 无「已知仍错但未修」项：全流仿真 0 失配。
- **未证实**：`conv_engine` / `requant_unit` 的修复对 conv2..conv4 的影响未做逐层仿真
  （本轮只证明 conv1 的 1 输入通道 / 3 组路径）。多层路径建议另开任务用同一 TB 框架验证。
- `tap_bank2` 增加 36 kbit DRAM（当前 conv1 位流 DRAM 占用 1%），资源影响可忽略但见第 7 节。

---

## 6. 构建与板级（已完成）

| 项 | 值 |
|---|---|
| BuildSet | `conv1_test` |
| Run | `20261031-235952-09aae62a` |
| Bitstream SHA-256 | `5EEEC976F14288F66147EC9C6D2AAD6B568276E4F0EDA8F4368B9EF850FFA6FD` |
| 阶段 | compile / synthesize / dev_map / pnr / report_timing / gen_bit_stream 全 OK |
| WNS / WHS | **28.726 ns** / 0.158 ns（27 MHz 时钟预算远宽于需求） |
| 资源 | LUT 3882/66600 (6%)、FF 5563/133200 (4%)、APM 20/240 (9%)、DRAM 48/19900 (1%) |
| 构建耗时 | compile→gen_bit_stream 6m29s（CPU）/ 约 10 min real |
| 板级 | `reports/board_conv1_fix.json` PASS（`DIAG` 命中）、`reports/conv1_compare_fix.json` **PASS** |

板级判读（`compare_conv1.py --uart-file build/uart_conv1_fix.bin`，逐字节）：

```
verdict      PASS          mismatch 0 / 3072
expected_sum 26685         observed_sum 26685
per_window   [0,0,0,0,0,0]
status       done=1  count=3072  sum=26685  stream=792576  windows=6  tail=0xA5
frames       parsed=132  status=1  data=128  missing=[]  ignored=0
exit code    0
```

中间位流（`20261031-233316-d4457ec7`，SHA `072856B7…`）的板级结果是
`sample_sum=26685`（引擎已对）但 `observed_sum=26998 / mismatch 2470`——正是 P5
（readout arm 滞后一帧）的指纹：前 24 个样本全对，从第 25 个（`col1/ch8`）开始错。
该中间证据归档在 `reports/conv1_compare_v2.json`（team-leader 采集）。

---

## 7. 交付物与复现命令

新增/修改文件：

| 文件 | 说明 |
|---|---|
| `src/diag/top_npu_conv1_test.v` | P0a/P0b/P1a/P1b/P4（T25 授权范围内） |
| `src/npu/requant_unit.v` | P2（+2 级寄存；`.orig` 备份在 `build/requant_unit.v.orig`） |
| `src/npu/conv_engine.v` | P3（drain 参数快照；`.orig` 在 `build/conv_engine.v.orig`） |
| `sim/tb_top_conv1.sv` | 全流 TB（792576 样本 + 内部探针） |
| `build/compare_sim_conv1.py` | 全流对拍 + 分通道/分组/分行/分列统计 |
| `build/conv1_fix_model.py`, `build/probe*.py` | 离线定位脚本（worktree 诊断，不入库） |

复现：

```
H:\GG\bin\verilator.bat --binary --timing -j 4 -Wno-fatal --top-module tb_top_conv1 \
  --public-flat-rw -Mdir build/sim_conv1_obj <5 个 RTL> sim/tb_top_conv1.sv
./build/sim_conv1_obj/Vtb_top_conv1.exe
python build/compare_sim_conv1.py --json build/sim_conv1_cmp.json      # 期望 exit 0
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet conv1_test
python scripts/board_check.py --sbit build/top_npu_conv1_test-latest.sbit \
  --port COM5 --seconds 10 --expect DIAG --json reports/board_conv1_fix.json
python scripts/compare_conv1.py --uart-file build/uart_last.bin --json reports/conv1_compare_fix.json
```

---

## 8. 偏差与风险

- **D-01（授权偏差）**：T25 原约束「只改 `src/diag/top_npu_conv1_test.v`」。仿真证明
  `requant_unit`(P2) 与 `conv_engine`(P3) 两处产品 RTL 缺陷不改则不可能归零，已改为最小
  侵入式修复并保留 `.orig`。需 team-leader 确认纳入主线（已另行汇报）。
- **D-02**：`build/uart_last.bin` 被其它 build set 覆盖，T22 原始 dump 已重采并存为
  `build/uart_conv1_oldrepro.bin`（mismatch 2471、sum 184223 与存档记录逐项一致，
  证明采集确定性）。
- **R-1**：`tap_bank2` 使 conv1 诊断位流的 DRAM 从 1% 略升，若 PnR 出现布线压力，
  可回退为「三组轮转 + 延迟加载」方案（但会牵动 job 时序，不推荐）。
- **R-2**：`requant_unit` 的相位修复会改变**所有**层的数值结果（朝 golden 方向）。
  这是修正，不是回归——但 fpga 全量位流的逐层对拍需重新跑一遍（见第 5 节未证实项）。