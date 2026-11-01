# conv2 / conv3 / conv4 多层仿真验证（结论）

> 证据分级：`sim-proven` = Verilator 全流逐字节对拍；`numpy-proven` = 用生成的同一份表
> 在 Python 里复算 golden；`未证实` = 未取证。本轮**全部是 sim-proven**。
> 方法：纯 Verilator，单 case、`--jobs 2`，未启动任何 PDS 构建、未烧板。

---

## 1. 结论

| 层 | 几何 (CIN→COUT, H×W) | 组数 | tap/像素/组 | 样本数 | mismatch | expected_sum | observed_sum | 判定 |
|---|---|---|---|---|---|---|---|---|
| conv2 | 48→96, 32×129 | 6 | 432 | 396,288 | **0** | 5,452,780 | 5,452,780 | **PASS** |
| conv3 | 96→192, 16×64 | 12 | 864 | 196,608 | **0** | 2,590,535 | 2,590,535 | **PASS** |
| conv4 | 192→256, 8×32 | 16 | 1,728 | 65,536 | **0** | 1,505,962 | 1,505,962 | **PASS** |

合计 **658,432 个输出字节，逐字节 0 失配**，且三层 `per_group` 全为 0。

**这证明**：`requant_unit.v`（P2：`shift_q`/`zp_q` 少一级寄存）与 `conv_engine.v`
（P3：drain 跨 contract promote）两处产品 RTL 修复，在 conv2/3/4 的
**不同 `shift` 值域（39..43）、不同组数（6/12/16）、不同 `CIN`（48/96/192）、
不同 tap 数（432/864/1728）** 下同样收敛，不存在参数化边界问题。

---

## 2. 方法

### 2.1 表生成 + numpy 自证（先于仿真，避免"布局理解错"被误判成 RTL bug）

`build/gen_layer_hex.py --layer <1..3>` 从 `scripts/outputs/weights_image.bin` + 层契约
导出与 conv1 同形的三张表：

```
build/ml_conv/L<n>/tap.hex   每组 4*TAPS 个 32 位字（组 major），
                            一个 128 位 tap 字 = 16 个输出 lane（lane0 在 bits[7:0]）
build/ml_conv/L<n>/ctr.hex   bias(COUT) + M(COUT) + shift(COUT)，块内 16 字/组连续
build/ml_conv/L<n>/x.hex     输入图，按 conv_engine 的入流顺序 (row, col, ch)
```

`--self-check` 用**这三张表本身**在 numpy 里重算整层并与 golden 比：

| 层 | max_abs_diff | mismatch | total |
|---|---|---|---|
| conv2 | 0 | 0 | 396,288 |
| conv3 | 0 | 0 | 196,608 |
| conv4 | 0 | 0 | 65,536 |

说明权重反交织（group-major `(k, 16)` 布局）、`(cin, dy, dx)` tap 顺序、
`(row, col, ch)` 输入顺序三项理解都对——仿真里若再出错，只可能是 RTL 或 TB 的调度。

### 2.2 通用层 TB（`sim/tb_conv_layer.sv`）

`conv_engine` 的 4 层形状是**编译期参数**且四层共享一个物理核，所以 TB 不需要改
参数，只需 `conv_sel=LAYER` + 对应 `startN/doneN/advN` + 对应 `xN` 端口。loader 复刻
conv1 已验证的相位纪律：

- contract：49 拍/组（beat 0 = `grp_start`），beat k 写逻辑字 `k+1`，launch 沿预取 word 0；
  **块由 beat 计数 16/32 选择，块基址是 `0 / COUT / 2*COUT`**；
- tap：`4*TAPS+1` 拍，`w_addr = base + t_step + 1`，进入 TAP 时预取 word 0，
  **每组一个 tap bank**（2 个 bank 无法支撑 ≥3 组）；
- 组轮转：boot 装 grp0(ACT)+grp1(SHADOW)，运行时 `job_grp = (use_grp+2) % GROUPS`。

### 2.3 全流对拍

`build/compare_sim_layer.py --layer <1..3>` 把 `build/sim_L<n>_y.bin`（**全部**
`GROUPS*H*W*16` 个样本，不是抽样窗口）与 `golden_ref/conv<n>.npy` 按
`(row, group, col, lane)` 重排后逐字节比，并输出 per-group / per-channel /
per-row / 首末列分布。

---

## 3. 过程中发现的两个 **TB 侧**缺陷（不是 RTL）

1. **激励送错端口**：conv2/3/4 的 ingress 端口是 `x1/x2/x3`（由 `sel` 选择），
   一开始全接在 `x0_*` → conv_engine 永远等不到行数据（挂死，`ing_row=2, n=0`）。
   修：按 `LAYER` 选择端口。
2. **contract 块阈值写错**：把「块选择」写成 `>= COUT / >= 2*COUT`，而正确阈值是
   **每组固定 16 字**（`>=16` bias→M，`>=32` M→shift），块基址才是 `COUT/2*COUT`。
   症状：conv2 首像素 `expected 70 observed 0`、per-channel 呈"部分通道全对/部分全错"。
   修前 conv2 mismatch 195,372；修后 0。
   注：conv1 的 `top_npu_conv1_test.v` 用的是 `>=16/>=32`，本来就是对的——这个错误
   只存在于新写的通用 TB 里，**不影响已交付的 conv1 位流（SHA 5EEEC976…）**。

**acc 级交叉验证**：修好后 conv2 首个像素的 `acc_snap[0..15]`
（`87480 -80447 -190165 -261689 -112270 -8310 -190060 -124436 77164 -48290 -1170
-54453 -86464 -178659 42376 -194306`）与 numpy 模型**逐值相同**，说明 conv2 的
ingress/pad/tap/contract 通路全部正确，残差只可能来自 requant（已由 0 失配排除）。

---

## 4. 复现命令（单 case，`--jobs 2`）

```
# 生成表 + numpy 自证
python build/gen_layer_hex.py --layer 1 --self-check     # conv2
python build/gen_layer_hex.py --layer 2 --self-check     # conv3
python build/gen_layer_hex.py --layer 3 --self-check     # conv4

# 逐层仿真（示例：conv2）
H:\GG\bin\verilator.bat --binary --timing -j 2 -Wno-fatal --top-module tb_conv_layer \
  -GLAYER=1 -GCIN=48 -GCOUT=96 -GH=32 -GW=129 -Mdir build/sim_L1_obj --build-jobs 2 \
  src/npu/conv_engine.v src/npu/requant_unit.v sim/tb_conv_layer.sv
./build/sim_L1_obj/Vtb_conv_layer.exe
python build/compare_sim_layer.py --layer 1 --json build/sim_L1_cmp.json

# conv3: -GLAYER=2 -GCIN=96 -GCOUT=192 -GH=16 -GW=64   -> build/sim_L2_obj
# conv4: -GLAYER=3 -GCIN=192 -GCOUT=256 -GH=8 -GW=32   -> build/sim_L3_obj
```

单轮成本：编译 25–40 s（`--jobs 2`）+ 仿真 5–7 s；三层合计 < 3 分钟。

---

## 5. 未证实 / 边界

- **未证实**：`pool_engine` / `gap_unit` / `fc_engine` / `softmax_top` 的板级或 RTL 级
  逐值验证（本轮只覆盖 4 个 conv 层；这些模块仍只有编译级 + Python golden 证据）。
- **未证实**：conv2..conv4 的**多层串联**（conv1→pool1→conv2→…）未在 RTL 里跑通；
  本轮每层独立喂 golden 上一层输出，验证的是「层内数值通路」，不是「层间数据流」。
- `tap_bank` 在 TB 里是 `GROUPS × TAPS × 128 bit` 的行为模型，不代表可综合资源；
  conv1 位流里实际只有 3 个 bank（`tap_bank0/1/2`，DRAM 48/19900 = 1%）。
- 本报告未改动任何已 PASS 的模块（`self_test` / `ui_renderer` / `ddr3_subsys`），
  未启动 PDS 构建，未烧板。