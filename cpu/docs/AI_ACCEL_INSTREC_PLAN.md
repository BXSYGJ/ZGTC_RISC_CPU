# AI 加速架构规划 — InstrumentCNN（乐器组识别）在 RV32 SoC 上的部署

> 创建时间：2026-10-12，最后更新：2026-10-12（v2：改为**片内 BRAM 方案，暂不依赖 DDR3**）
> 上游目标：`D:\0000\111\001\Pango\InstRec`（乐器组活跃度识别，INT8 ≤0.8MB 部署约束）
> 本文档是 `HANDOFF_DDR3_AI_20260920.md` §6 的落地，把「部署小 YOLO」收窄为本项目实际模型 InstrumentCNN。

---

## 0. 决策摘要（v2 变更）

- **暂不使用 DDR3**（当前不可用），改为 **权重 + 激活全部放片内块 RAM（DRM）**。
- 依据：远程调试平台 PG2L200H 块 RAM = 415×36Kb ≈ **1.82MB**，权重 728KB + 激活峰值 ~200KB 完全放得下；且加速器因此**无需 DMA、无需改总线/仲裁器**，工程量大减。
- 注意：最终交付板 PG2L100H 块 RAM 仅 155×36Kb ≈ **697.5KB**，放不下 728KB 权重。这是**后续**要面对的问题（Flash 流式 / DDR3 / 压缩），**当前阶段不阻塞**（见 §12 风险 1）。

---

## 1. 结论先行

1. **不改指令集，不做 RVV / 自定义向量指令**——CNN 计算密集部分交给独立的 **int8 MAC 阵列 + 控制状态机**。
2. 加速器是**纯片内**单元：权重/激活常驻片内块 RAM，内部 FSM 直接读写，**不经过 DDR3 总线、不需要 DMA、不需要改仲裁器**。CPU 只做 **MMIO 配置 + 启动 + 轮询 done + 后处理（sigmoid/argmax）**。
3. 覆盖算子 = **Conv3x3(s1) + MaxPool2x2 + GAP + FC(GEMM) + int8→int8 反量化**，恰好覆盖 InstrumentCNN 全部 6 层，**无 YOLO 的 upsampling/concat/NMS**。
4. **实时性无压力**：单次推理 ≈58M MAC（1.5s 短窗口）；64 MAC/cycle @153MHz ≈ 9.8 GMAC/s → ≈6ms，窗口 1.5~3s，裕量 >200×。取 **64 MAC** 保守规模，优先正确性。

---

## 2. 器件资源（官方选型表，决定方案可行性的关键）

| 资源 | PG2L200H（远程调试） | PG2L100H（最终交付） |
|------|---------------------:|---------------------:|
| LUT6 | 159,800 | 66,600 |
| FF | 319,600 | 133,200 |
| 分布式 RAM | 2469 Kb | 1244 Kb |
| **块 RAM（DRM 36Kb/块）** | **415 → 14,940 Kb ≈ 1.82MB** | **155 → 5,580 Kb ≈ 697.5KB** |
| **APM（DSP 25×18）** | **740** | **240** |

模型 int8 权重 = **728.56 KB**。→ 200H 放得下（1.82MB），100H 放不下（697.5KB）。

---

## 3. 目标模型分析（InstrumentCNN）

### 3.1 层结构与形状

输入：mel 频谱 `(1, 64, N_FRAMES)` int8。N_FRAMES=130（1.5s 短窗口，5 组多标签主目标）或 258（2.97s，8 类）。以 130 帧为准。

| 层 | 算子 | 输出形状 | 权重形状(int8) | MAC 量(130帧) |
|----|------|---------|---------------|---------------:|
| 输入 | — | 1×64×130 | — | — |
| conv1 | Conv3x3+ReLU+Pool2 | 48×32×65 | 48×1×3×3=432 | 0.90M |
| conv2 | Conv3x3+ReLU+Pool2 | 96×16×32 | 96×48×3×3=41,472 | 21.2M |
| conv3 | Conv3x3+ReLU+Pool2 | 192×8×16 | 192×96×3×3=165,888 | 21.2M |
| conv4 | Conv3x3+ReLU+Pool2 | 256×4×8 | 256×192×3×3=442,368 | 14.2M |
| gap | AdaptiveAvgPool2d(1) | 256 | — | 0.03M |
| fc1 | Linear+ReLU | 128 | 128×256=32,768 | 0.03M |
| fc2 | Linear | 5（或 8） | 5×128=640 | ~0 |

合计 ≈684K 参数（int8 ≈0.71MB）；合计 MAC ≈**57.6M**（130帧）/ ≈115M（258帧）。

### 3.2 FPGA 友好特性

- **BN 已 fold 进 Conv 权重+bias**（`model_config.json` 的 `fuse_modules`），硬件无 BN。
- **量化**（`deploy/irmas/scale_params.json`）：权重 per-channel symmetric int8（zp=0），激活 per-tensor affine int8。conv1~fc1 输出 zp=0，仅 fc2 输出 zp=64。
- 无 skip / 无 depthwise / 无残差，纯顺序前向，逐层数据流最友好。
- **GAP 替代大 Flatten+FC**：conv4 输出仅 4×8=32 空间点，加速器内顺手完成。

### 3.3 激活内存足迹（int8）

| 张量 | 130 帧 | 258 帧 |
|------|-------:|-------:|
| 输入 mel | 8,320 | 16,512 |
| conv1 输出（**峰值**） | 99,840 | 198,144 |
| conv2 输出 | 49,152 | 98,304 |
| conv3 输出 | 24,576 | 49,152 |
| conv4 输出 | 8,192 | 16,384 |

---

## 4. 总体架构（片内 BRAM 方案）

```
RV32I核 → I/D-Cache → 总线(MEMORY_SYSTEM)        ← 与加速器无关，不动
   └── MMIO (0x10000600) ──► rv32_ai_accel（纯片内 NPU）
                               ├── 权重 BRAM  728KB（conv/fc int8 + bias + 反量化参数）
                               ├── 激活 BRAM  双缓冲 ~400KB（输入+各层中间）
                               ├── MAC 阵列  64 int8 MAC + 加法树（int32 累加）
                               ├── 反量化单元  multiplier+shift → int8（末层跳过出 int32）
                               └── 控制 FSM   逐层数据流编排 + MaxPool/GAP/FC
```

- **数据平面**：FSM 直接读权重 BRAM / 激活 BRAM，写回激活 BRAM，层间**片上直接传递**，零 CPU 参与。
- **控制平面**：MMIO 寄存器（并入 `rv32_peripherals`，新增 0x10000600 段）；done 走 `irq_external`。
- **CPU 职责**：写层参数 → start → 轮询 done → 读 logits → sigmoid/argmax → 输出。

### 4.1 为什么片内（而非 DDR3/DMA）

| 备选 | 结论 |
|------|------|
| DDR3 存权重 | 桥未上板验证 + 需改仲裁/DMA，当前不可用，弃 |
| Flash 流式加载 | 需要新写 QSPI DMA 读控制器 + 逐层调度，工程量更大 |
| **片内 BRAM** | 200H 有 1.82MB，够用；零总线改动，最快跑通 |

---

## 5. 计算数据流（逐层调度）

每层：FSM 从权重 BRAM 流式取权重、从激活 BRAM 取输入瓦片 → MAC 阵列累加 → 反量化 → 写激活 BRAM。

- **卷积层**：output-stationary；3×3/s1/p1 用 3 行输入行缓冲滑动；MaxPool2x2 在写出时寄存器比较完成。
- **GAP 层**：conv4 输出 256×4×8，每通道 32 点求和取均值，复用累加器。
- **FC 层**：复用 MAC 阵列做 GEMM（128×256、5×128）；fc2 出 int32 logits，跳过反量化。

---

## 6. 量化与反量化

对齐 FBGEMM 静态量化（`scale_params.json`）：

- 权重 int8 per-channel scale `s_w[oc]`（zp=0）；激活 per-tensor scale `s_a`。
- 累加 `acc_int32 = Σ w·a + bias_int32[oc]`（bias 为导出件 `*_bias_int32.npy`，已 fold BN）。

硬件反量化用 **TFLite fixed-point multiplier+shift**，离线导出随权重下发：

```
M[oc] = round( 2^S · s_w[oc] · s_a / s_out )   // int32，S 每层取 30~31
out_q = sat( (acc + bias) · M[oc] >> S ) + z_out   // z_out=0（conv1~fc1）
out_i8 = clamp(out_q, -128, 127)
```

- `M[oc]`、`S`、`z_out` 全部离线导出，硬件无浮点。
- 末层 fc2 跳过反量化，直接出 int32 logits。

---

## 7. 片内 BRAM 预算（200H）

| 用途 | 大小 |
|------|-----:|
| CPU boot ROM（现有）+ cache | ~65 KB |
| 权重 + bias + 反量化参数 | ~730 KB |
| 激活双缓冲（输入+各层中间） | ~400 KB |
| **合计** | **~1.2 MB < 1.82 MB** ✓ |

余量约 0.6MB，可容纳长窗口（258帧）或更大 MAC 阵列的中间缓冲。

---

## 8. 模块划分（RTL，SV-2005 规范）

| 文件 | 作用 |
|------|------|
| `cpu/rtl/rv32_ai_accel.sv` | NPU 顶层：控制 FSM + 数据流编排 + 反量化 |
| `cpu/rtl/rv32_ai_mac.sv` | int8 MAC 阵列（64 MAC，int32 累加）+ 加法树 |
| `cpu/rtl/rv32_ai_wram.sv` | 权重 BRAM（`syn_ramstyle="block_ram"`，初始化/加载接口）|
| `cpu/rtl/rv32_ai_aram.sv` | 激活 BRAM（输入+中间，双缓冲 ping-pong）|
| `cpu/rtl/rv32_ai_requant.sv` | 反量化（multiplier+shift+饱和，末层旁路）|
| `cpu/rtl/rv32_peripherals.sv` | **改造**：新增 0x10000600 AI 寄存器段 + done IRQ |
| `cpu/rtl/rv32_soc.sv` / `rv32_board_top.sv` | **改造**：例化加速器、接线（无总线改动）|

> 权重加载：调试阶段用 `$readmemh`/INIT 直接初始化权重 BRAM（bitstream 变大 ~1MB，可接受）；后续再改上电从 QSPI Flash 加载（§12 风险 2）。

---

## 9. MMIO 寄存器映射（0x10000600 段）

| 偏移 | 寄存器 | 读写 | 说明 |
|------|--------|------|------|
| 0x00 | AI_CTRL | W | bit0=start，bit3:1=层选择，bit4=末层出 int32 标志 |
| 0x04 | AI_STATUS | R | bit0=busy，bit1=done，bit2=error |
| 0x08 | AI_LAYER_CFG | RW | in_ch/out_ch/kernel/stride/pool/尺寸打包 |
| 0x0C | AI_REQ_BASE | RW | 反量化参数在权重 BRAM 内的偏移 |
| 0x10 | AI_OUT_PTR | RW | 结果/激活区指针（层间直接传则多为固定布局）|
| 0x14 | AI_IRQ | RW | 使能/清除，done 置位 |

软件驱动（C）：`ai_run_layer(cfg)`、`ai_infer(input,out)`；完成后读 logits → sigmoid/argmax。

---

## 10. 性能与资源估算

- **计算**：64 MAC @153MHz ≈ 9.8 GMAC/s；130帧 57.6M MAC ≈ 6ms；258帧 ≈ 12ms。
- **DSP**：64 int8 MAC ≈ 32 APM（200H 有 740，富余）；纯 LUT 也可实现（先跑通）。
- **BRAM**：见 §7，~1.2MB / 1.82MB。
- **LUT**：MAC 阵列 + FSM + 反量化，估计 <10K LUT，200H（159.8K）富余。

---

## 11. 验证方法学（对齐项目风格）

1. **黄金参考**：复用 `InstRec/deploy/irmas/weights/*.npy`，写 `ai_ref.py` 出逐层逐像素 int8 参考 + `M[oc]/S/z_out` 表 + BRAM 初始化 `.mem`。
2. **逐层对拍**：RTL 每层输出与 Python 参考 bit-exact 比对（需先落实 WSL/verilator 或走远程实验箱）。
3. **突变测试**：注入单点权重/激活/反量化错误，验证 checker 能抓。
4. **端到端**：真实音频 → CPU 抽 mel（或预留 mel 前端）→ 加速器 → 5 组 sigmoid，与 Python 整管线比对。

---

## 12. 分阶段路线图

| 阶段 | 内容 | 验收 |
|------|------|------|
| M0 | `ai_ref.py`（位级 int8 参考 + 反量化参数 + BRAM `.mem` 导出）| 与 `deploy/irmas` 一致 |
| M1 | 单层 Conv3x3 int8 引擎 RTL（权重/激活 BRAM + MAC + 反量化）| 单层 bit-exact |
| M2 | 完整 6 层流水（conv+pool+GAP+FC），层间激活片上直传 | 全模型 bit-exact |
| M3 | MMIO 寄存器 + CPU 驱动（bootloader 命令）+ 端到端 | 真实音频出组活跃度 |
| M4 | 远程实验箱（200H）上板调试 | 板上跑通 |
| M5（后续）| 100H 适配：权重放不下片内，需 Flash 流式 / DDR3 / 压缩 | 100H 交付 |

---

## 13. 风险与待定项

1. **100H 放不下权重（最大后续风险）**：697.5KB < 728KB。后续三选一：a) 模型压缩到 <600KB（剪枝/INT4/更小网络）；b) QSPI Flash 流式加载（需写 QSPI DMA 读控制器）；c) 接回 DDR3。**当前 200H 调试不受影响**。
2. **权重进 BRAM 的方式**：调试用 `$readmemh` 初始化（bitstream 变大）；最终形态是上电从 QSPI Flash 加载（现有 `rv32_spi_flash.sv` 1-bit 慢速，加载 728KB ≈0.9s，可接受，后续再优化 QSPI）。
3. **Mel 特征归属**：STFT(2048)+mel 滤波器在 RV32I 上很慢。先由 CPU 算（正确性优先），后续再议专用 FFT/mel 前端。
4. **目标模型**：5 组（130帧）为主，8 类（258帧）同构；`num_classes` 参数化，仅换 fc2 权重与 N_FRAMES。
5. **无本地仿真器**：需落实 WSL/verilator，或走远程实验箱（慢）。
6. **远程平台 DDR3 不可用**：本方案已规避；但 mel 前端若后续要大规模数据，仍需 DDR3。

---

## 14. 下一步动作（立即）

1. 写 `ai_ref.py`（位级 int8 参考 + 反量化参数 + BRAM `.mem` 导出），真值源 `InstRec/deploy/irmas/weights`。
2. 落实仿真环境（WSL verilator），或与用户确认走远程实验箱。
3. 起 `rv32_ai_mac.sv` + `rv32_ai_wram.sv` + `rv32_ai_aram.sv`，M1 单层对拍跑通。
