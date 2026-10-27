# AI 加速架构方案 — PCB 缺陷检测（YOLOv8n）移植 PG2L100H（DDR3 + 自研 NPU 路线）

> 创建日期：2026-10-26
> 状态：**v1.1 决策已拍板（2026-10-26 用户确认：路线 A + 128 MAC 起步 + 1024 输入 + M0 立即启动；InstRec 搁置，聚焦 PCB 视觉；100Pro 板卡在线随时可用）**
> 上游依据：DYH 分支提交 1a2aa4e（pcb-aoi，YOLOv8n 七类 PCB 缺陷检测器）+ 陈工/林工两路调研
> 定位：本文档是 `AI_ACCEL_INSTREC_PLAN.md`（InstRec 片内方案）面对 YOLOv8n 量级模型（int8 权重 ≈3MB）的架构演进——加速器从「纯片内、零总线改动」转向「DDR3 权重/激活存放 + AXI DMA + 第三总线主控」，CPU 退居控制面与后处理。

---

## 0. 待决事项（置顶）

四个关键决策点，**已全部于 2026-10-26 由用户拍板**，本文其余章节按拍板结果执行：

| # | 决策点 | 选项 | 状态 |
|---|--------|------|------|
| ① | **技术路线** | 路线 A：DDR3 NPU 原样移植 YOLOv8n；路线 B：重训 <600KB 小检测器 + 片内 NPU（对比详见 §2） | **✅ 已拍板：路线 A** |
| ② | **MAC 起步规模** | 128 MAC（参数化 `MAC_UNITS` 可扩 256）；直接上 256 | **✅ 已拍板：128 起步** |
| ③ | **输入分辨率** | 1024×1024；640×640（M0 顺带测出的备选，见 §2 减压阀） | **✅ 已拍板：先保 1024（M0 同时测 640 备选）** |
| ④ | **M0 是否立即启动** | M0 = 纯 PC 侧量化验证（~1 周，硬件零投入，见 §9） | **✅ 已拍板：立即启动（M0 量化部署 + M1-A RTL 已并行开工）** |

---

## 1. 三个改变决策的事实

| # | 事实 | 出处 |
|---|------|------|
| 1 | **DYH 模型 = YOLOv8n**（width 0.25 / depth 0.33），**7 类缺陷**：dry_solder_joint / improper_installation / pcb_damage / short_circuit / insufficient_solder / reverse_component / excess_solder。输入 **1024×1024**；**3.01M 参数** → int8 权重 **≈3.0MB**；计算量 **≈11.1 GMAC/帧**；峰值激活 **4.2MB**（P1 层 512×512×16）。FP32 ONNX 未量化（opset 12，Ultralytics 8.4.87）；ONNX 算子统计：Conv 64 / Sigmoid 57 / Mul 59 / Concat 17 / MaxPool 3 / Resize 2 / Softmax 1。 | DYH 提交 1a2aa4e 的 `pcb-aoi/README.md` 与 `recovered/model-inspection.json` |
| 2 | **100H 片内 BRAM 仅 697.5KB**——3MB 权重放不进（200H 的 1.82MB 也放不下）→ InstRec「全片内」方案对 YOLO **数学上不可行**，**DDR3 路线是硬约束**。 | `AI_ACCEL_INSTREC_PLAN.md` §2 + 林工调研 |
| 3 | **DDR3 底座良好**：AXI 256bit@125MHz 理论 **4GB/s**；实测合并吞吐 4.6MB/s 纯属「单 beat（awlen=0）+ 半宽（读 32B 用 16B）+ 串行 CDC 电平握手 + write-allocate 放大 + 27MHz CPU 域」**协议开销**（实测反推 ≈91 CPU 拍/事务）；**0x10000600 MMIO 段完全空闲**（RTL case default rsp_error，全仓库 grep 零命中）；120MHz CoreMark 位流（BRAM-only 顶层）与 DDR3 位流（27MHz 直连）**从未同一位流**。 | 陈工调研（`rv32_burst_ddr3.sv` / `ddr3_test.v` / `rv32_peripherals.sv` 分析） |

> **一句话结论：CPU 与 DDR3 底座是好的，瓶颈全在接入方式；必须做「带 AXI DMA 的第三总线主控 NPU」，CPU 退居控制面与后处理。**

---

## 2. 两条路线对比

| 维度 | 路线 A：DDR3 NPU 原样移植 | 路线 B：重训小模型 + 片内 NPU |
|------|--------------------------|------------------------------|
| 模型 | DYH `best.pt` 原样，量化后 mAP@0.5 损失 **<3pt** | 蒸馏自训小 CNN；7 类仅 **1230 张**训练图，精度不可控，可能掉 **10pt+** |
| 权重存放 | DDR3，3MB | 片内，<600KB |
| 总线改动 | 新增 AXI 仲裁器 | 零改动 |
| NPU 工程 | DMA + 多算子引擎 | 复用 InstRec 6 算子 |
| 工程量 | 6-10 周 | 4-5 周（含训练） |
| 性能 | 128 MAC@125MHz → **0.7s/帧**；256 MAC → 0.35s | 64 MAC → 数十 ms |
| 时序风险 | 120MHz+DDR3+NPU 同位流需收敛；100H 芯片慢 17%，有 100MHz 退路 | 纯 BRAM，风险低 |
| 竞赛故事 | **完整**：自研 RV32 核 + 自研 NPU + DDR3 大模型部署 + 全链量化 | 弱化 |
| 主要风险 | 工程周期 / 仲裁饿死 / 量化精度 | 精度不可达标，需返工路线 A |

**推荐路线 A**，理由：

1. 用户目标就是移植 DYH 模型，B 实质是换模型；
2. 赛题高阶任务③的故事完整性；
3. B 最大坑是精度不可控，返工代价等于两条路线都做。

- **风险控制**：靠 **M0 前置闸门**（见 §9）——量化精度问题在硬件投入之前暴露。
- **减压阀**：1024→640 输入（计算量降为 **4.35 GMAC**、激活峰值 **1.6MB**、权重不变），M0 顺带测精度，**不改变架构**。

---

## 3. 总体架构（路线 A）

三层视图：CPU 面不动，控制面与数据面为新增。

```
        ┌────────────────────────── CPU 面（不动） ──────────────────────────┐
        │   RV32IM 核 ──i/d_req──► I$/D$ ──► burst 仲裁 ──► BRAM（<64KB）   │
        └──────────────┬────────────────────────────────────┬───────────────┘
                       │ MMIO 0x10000600（控制面，新增）      │ burst ≥ 0x0001_0000
                       ▼                                    │
        ┌──────────────────────────────┐        ┌───────────▼───────────────┐
        │      rv32_ai_accel（NPU）     │        │  rv32_burst_ddr3          │
        │  ┌────────────────────────┐  │        │  （AXI master #1，现有）  │
        │  │ NPU 寄存器组            │  │        └───────────┬───────────────┘
        │  │  · 2FF + 电平握手 CDC   │  │                    │
        │  │   （复用 rv32_burst_    │  │        ┌───────────▼───────────────┐
        │  │    ddr3 成熟模式）       │  │        │ 数据面（新增）：           │
        │  └────────────────────────┘  │───────►│ rv32_axi_arbiter（新增）   │
        │  desc_engine + 算子引擎      │  AXI   │  master #1：rv32_burst_ddr3│
        │  + wbuf/abuf tile 缓冲      │ master │  master #2：NPU DMA        │
        │                              │  #2    │  （256bit，16-beat 突发）  │
        │  NPU done ──► irq_external   │        └───────────┬───────────────┘
        │  （rv32_peripherals 加 case，│                    ▼
        │   约 20 行）                 │        ┌───────────────────────────┐
        └──────────────────────────────┘        │ ddr3_test IP（AXI slave， │
                                                │  256bit @ 125MHz）        │
                                                └───────────┬───────────────┘
                                                            ▼
                                                    DDR3（4GB 窗口低 16MB）
```

三个设计决策及其依据：

| # | 决策 | 依据 |
|---|------|------|
| 1 | **NPU 挂 AXI 层而非 CPU burst 总线层** | CPU 侧 32bit/16B 粒度太细、共享 I$/D$ 仲裁、要过 CPU 域 CDC；AXI 层 256bit 现成、NPU 与 DDR 控制器同 core_clk 125MHz 域省一次 CDC，`rv32_memory_system.sv` **一行不动** |
| 2 | **MMIO 控制面 + DMA 数据面分离** | 呼应 `HANDOFF_DDR3_AI_20260920.md` §6.2 |
| 3 | **CPU 不改指令集不做 RVV** | HANDOFF §6.1 已论证 |

---

## 4. AI 加速单元（NPU）内部设计

`rv32_ai_accel`（SV-2005，放 `cpu/rtl/`）模块清单：

| 模块 | 职责 |
|------|------|
| `desc_engine` | 层描述符链表 FSM（整网自动逐层执行） |
| `axi_dma` | 双通道 DMA；16-beat/512B 突发；outstanding 2~4 |
| `wbuf` | 权重 tile 缓冲，~64KB |
| `abuf` | 激活 ping-pong 缓冲，~128KB |
| `pe_array` | **128×int8 MAC**（参数化 `MAC_UNITS`，可扩 256）+ int32 累加树 |
| `requant` | M/S 定点反量化 + clamp |
| `silu_lut` | sigmoid LUT + int8 乘 |
| `maxpool` | 2×2 s2 与 5×5 s1 两模式 |
| `misc_engine` | MEMCPY（= Concat 通道偏移搬运）/ UPSAMPLE（= nearest×2 行重复） |
| `detect_prefilter` | sigmoid + 阈值 0.25 预过滤，输出稀疏 `anchor_id,cls,conf,box` |

算子覆盖表（对照 §1 事实 1 的 ONNX 算子统计）：

| ONNX 算子（数量） | 硬件实现 |
|------------------|----------|
| Conv 3×3 s1/s2、1×1（64 个） | PE 阵列 output-stationary |
| Sigmoid+Mul（SiLU） | requant 后 LUT，[0,1] 无符号量化域 |
| BN | 离线 fold |
| Concat（17） | MEMCPY 描述符 |
| Resize nearest×2（2） | UPSAMPLE 描述符 |
| MaxPool 5×5 s1（3，SPPF） | maxpool 引擎（等效 9/5/1 级联） |
| Softmax(DFL)+解码+Transpose | CPU 软件（M4 可选硬化） |
| NMS | CPU 软件（conf≥0.25 过滤后通常 <100 框） |

**Detect 头预过滤是点睛之笔**：21504×71≈**1.5MB** 原始输出若直接给 CPU（按 4.6MB/s 要 **0.33s**），NPU 写出前预过滤稀疏化后缩到**几十 KB**，CPU 读回 + NMS **<100ms**。

**MAC 规模建议 128 起步**：≈64 APM（100H 有 240，CPU muldiv 已占部分）；128 MAC@125MHz = **16 GMAC/s** → 0.7s/帧，静态 AOI 足够。

---

## 5. 数据通路设计

### 5.1 CPU 面（不动）

现有 CPU 侧总线、I$/D$、burst 仲裁、BRAM 后端零改动（见 §3 框图上层）。

### 5.2 控制面（新增）：MMIO 寄存器组草案（0x10000600 段）

| 偏移 | 名称 | 说明 |
|------|------|------|
| 0x00 | CTRL | bit0=start，bit1=soft_reset |
| 0x04 | STATUS | busy / done / error / desc_idx |
| 0x08 | DESC_HEAD | 描述符链表头地址（DDR3） |
| 0x0C | DESC_COUNT | 描述符数量 |
| 0x10 | OUT_HEAD | 输出区头地址（DDR3） |
| 0x14 | OUT_COUNT | 输出条目数（NPU 写回） |
| 0x18 | IRQ | 使能 / 清除 |
| 0x1C.. | PERF | 周期计数 |

### 5.3 数据面（新增）：AXI 仲裁

- `rv32_axi_arbiter`：事务级 round-robin + **CPU 保底配额**——防 NPU 长突发饿死 CPU 取指（旧桥 4096 拍超时会造成 cache fill 错误）。
- **透传 IP 非标准行为警示**：无 `axi_rready`（IP 推数据须每拍就绪）；写完成看 `wready`。

### 5.4 DDR3 内存布局（4GB 窗口低 16MB）

| 地址 | 区域 | 大小 | 内容 |
|------|------|------|------|
| 0x0001_0000 | 权重区 | 3.2MB | int8 权重 + int32 bias + M/S 表 |
| 0x0004_4000 | 输入帧 | 3MB | 1024×1024×3 int8（letterbox 后） |
| 0x0007_8000 | 激活交换区 | ~8MB | tile ping-pong |
| 0x000F_8000 | 输出区 | 64KB | 稀疏检测结果 |
| 0x0010_0000 | 自由区 | — | 摄像头帧缓冲预留 |

### 5.5 描述符机制

CPU 一次配置整网（导出器直接生成描述符 bin 灌 DDR3），NPU 自动逐层执行，**全网红零 CPU 介入、完成才中断**——推理期间 CPU 并行做上一帧 NMS / UART 输出，**帧间流水**。

---

## 6. RISC-V 核职责

| 阶段 | CPU 职责 |
|------|----------|
| 初始化 | 灌权重 → 写 DESC_HEAD / OUT_HEAD → start（**ms 级**） |
| 推理中 | 空闲，或处理上一帧 NMS（帧间流水） |
| 推理后 | 读稀疏结果 → DFL 解码（可选）→ NMS → UART 报告（**<100ms @27MHz**） |
| 预处理 | M1-M3 由 host PC 预做；M4 可选 NPU resize 引擎或 CPU |

**CPU 核零改动**：无新指令、无 RVV、无新异常；`irq_external` 合并线加一位 NPU done。

---

## 7. 量化部署流水线（PC 侧全部新增 Python）

```
best.onnx
  │ ① onnxruntime.quantization 静态 QDQ（校准 1230 张图分层采样 ~400 张，
  │    沿用 InstRec seed=42 方法）
  ▼ 量化 ONNX
  │ ② mAP 验收（vs FP32 损失 <3pt；超标调 per-channel / 校准集）
  ▼ 【go/no-go 闸门】
  │ ③ export_yolo_deploy.py（对齐 InstRec npy 命名：
  │    {layer}_weight_int8 / _scale / _zero_point.npy；
  │    bias_int32 = round(bias_fp32 / (s_w[oc]·s_a_in))；
  │    全量化点 scale 表含 QuantStub 输入与 Concat 汇聚点；
  │    NPU 层描述符链表 .bin）
  ▼
  │ ④ ai_ref.py 位级 int8 逐层参考（含 SiLU / Concat / Upsample / SPPF 语义）
  ▼
  │ ⑤ RTL 对拍：单层 bit-exact → 全网 bit-exact（WSL verilator）
```

> **★重大警示（林工调研数值验证确认）**：InstRec 导出件 `*_bias_int32.npy` **实为 fp32 bias 直接取整**（`match round(fp32)==True` 已验证，数值仅 [-3,3]，而 TFLite 惯例应为数百量级）——硬件按 `acc + M>>S` 公式直接使用**必对拍失败**。YOLO 导出器必须从第一行起按正确语义写，**禁从 InstRec 复制该段代码**。

---

## 8. 性能预算（1024 输入）

| 项目 | 128 MAC@125MHz | 256 MAC@125MHz |
|------|---------------:|---------------:|
| MAC 计算 11.1 GMAC | 0.70s | 0.35s |
| DDR3 激活流量（~40MB/帧，双缓冲后残余） | +0.10~0.15s | +0.10~0.15s |
| Detect 预过滤 | ~20ms | ~20ms |
| CPU NMS + 输出 | ~100ms | ~100ms |
| **端到端** | **≈0.85~1.0s/帧** | **≈0.5~0.6s/帧** |

**DDR3 侧只需 ~50MB/s 有效带宽**（距离理论 4GB/s 有 **80 倍裕量**，仲裁效率打三折也无压力）。

---

## 9. 分阶段路线图

| 阶段 | 周期 | 内容 | 验收 | 退路 |
|------|------|------|------|------|
| **M0** | ~1 周（纯 PC） | 量化 + 导出器 + ai_ref + 描述符 bin + mAP 验收 | mAP@0.5 损失 <3pt；640 输入精度一并测 | 调校准 / QAT，不动硬件 |
| **M1** | ~1.5 周 | AXI 仲裁器 + DMA + 单层 conv 引擎；27MHz DDR 位流 | 单层 bit-exact 上板 | 仿真环境先行（WSL verilator） |
| **M2** | ~1.5 周 | 全算子 + 描述符链 + 预过滤，全网跑通 | 全网 bit-exact + 真图检出正确 | 慢层回退 CPU 计算 |
| **M3** | ~1 周 | PLL 引入；CPU 120MHz + NPU 125MHz 异步收敛 | 时序全绿 + CoreMark 复测 | 100MHz / 保持 27MHz |
| **M4** | 可选 | 摄像头链路 + MAC 扩 256 + DFL 硬化 | 端到端演示 | 按决赛时间裁剪 |

> M0 是量化精度的 **go/no-go 前置闸门**（硬件零投入）；M2 结束即具备参赛演示形态，M3/M4 是增强项（呼应 §10 风险 5）。

---

## 10. 风险登记（按杀伤力排序）

| # | 风险 | 缓解 |
|---|------|------|
| 1 | 120MHz + DDR3 + NPU 同位流时序（100H 芯片慢 17%） | M3 独立阶段 + 频点退路 |
| 2 | 量化精度（SiLU / DFL 窄动态域） | M0 闸门前置，硬件零投入 |
| 3 | AXI 仲裁饿死 CPU | 保底配额 + ILA 观测 |
| 4 | 无本地仿真器 | M0 期间并行落实 WSL verilator |
| 5 | 工程周期（6-10 周） | M2 结束即具备参赛演示形态，M3/M4 是增强项 |

---

## 11. 调研证据出处

**陈工（总线 / DDR3 底座）**——核心结论：DDR3 底座良好、4.6MB/s 纯属协议开销、0x10000600 空闲、两种位流从未同一位流（§1 事实 3）。关键文件：

- `cpu/rtl/rv32_soc.sv`、`cpu/rtl/rv32_memory_system.sv:78,181`（MMIO demux 与 DDR 后端选择）、`cpu/rtl/rv32_peripherals.sv:34-64`（MMIO 段与 `irq_external` 合并）
- `cpu/rtl/rv32_burst_ddr3.sv`（单 beat、半宽、串行 CDC 电平握手）、`cpu/rtl/rv32_burst_arbiter.sv`（双主轮转）
- `cpu/fpga/rv32_ddr3_ip_wrapper.sv`、`pds_cpu_100h/src` 顶层、`ipcore/ddr3_test`（256bit AXI@125MHz）
- `sw/ddr_probe.c`（4MB sweep 实测）

**林工（量化 / 导出件格式）**——核心结论：InstRec 交接件格式与 `bias_int32` 语义缺陷（§7 ★重大警示）。关键文件：

- InstRec `deploy/irmas` 交接件格式与 shape 实测
- `src/quantize_irmas.py` 流水线
- `bias_int32` 语义缺陷数值验证
- `AI_ACCEL_INSTREC_PLAN.md` §6 / §11

**DYH（模型与数据集）**——pcb-aoi 提交 1a2aa4e（模型形态与数据集，见 §1 事实 1）。