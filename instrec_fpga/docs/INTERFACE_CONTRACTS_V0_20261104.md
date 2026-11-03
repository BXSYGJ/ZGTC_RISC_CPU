# v0 接口契约（DDR 图 / MMIO / UART APP / UI 场景 / 数值快照真源）

日期：2026-11-04。性质：HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104 第 6 节「首次交接后执行顺序」第 2 条要求的 v0 接口文档。其中 UART APP 协议与 UI 场景 ABI 已由独立实验模块实现并仿真通过（src/boot/uart_app_boot.v、src/ui_scene/）；MMIO 扩展与 DDR 地址图为下一轮集成前必须冻结的草案。本文档与实现冲突时以实现+TB 断言为准并回写本文档。

## 1. UART APP 协议 v0（已实现，src/boot/uart_app_boot.v + sim/tb_uart_app_boot.sv）

帧格式（字节流，115200 8N1，BAUD_DIV=1085@125MHz）：

```
SOF0=0xA5, SOF1=0x5A, type(1B), seq(1B), len_lo(1B), len_hi(1B),
payload[len], crc32(4B little-endian, 覆盖 type..payload)
```

| type | 名称 | 语义 |
|---|---|---|
| 0x01 | APP_CHUNK | payload ≤512B 镜像数据，顺序写入 IRAM（偏移=已提交字节数，从 0 起） |
| 0x02 | APP_EXEC | payload 12B = entry(4B LE) + total_len(4B LE) + image_crc32(4B LE) |
| 0x03 | APP_ABORT | 清会话（写指针/CRC/app_ready），回 ACK |
| 0x04 | APP_RESET | v0 与 ABORT 同语义 |

应答：ACK = `'K'(0x4B) + seq`；NAK = `'N'(0x4E) + seq + reason`。
reason：1=CRC 错，2=seq 乱序/重复，3=超容量（total_len>4096 或写入越界），4=未就绪/格式错（EXEC len≠12、entry 越界/未 4 字节对齐、未知 type、app_ready 后再收 CHUNK/EXEC）。

已实现语义澄清（相对原始草案）：
- seq 接受条件为 `seq == exp_seq`；被拒帧不推进 exp_seq，故其重传天然可被接受（S2 场景验证）；「重传 NAK」仅适用于已接受帧的重复或跳号。
- 试写机制：payload 边收边写入 IRAM 并喂 running CRC；坏帧零提交（字节数与镜像 CRC 均不推进），重传同址覆盖，最终镜像精确。
- IRAM：4KiB（1024×32b，小端字节道）；加载期取指仲裁留给集成阶段；本模块暴露同步读口 + app_ready/app_entry 执行门控。
- 第二阶段（DDR 桥/取指 cache）不在 v0 范围；本协议镜像头省略，entry/len/crc 由 EXEC 帧显式携带。

TB 覆盖（52 检查，全部 PASS）：正常加载（跨 512B 边界）、坏 CRC 重传恢复、seq 跳号恢复、坏 EXEC 三型拒绝、中途 ABORT 重载、超容量。

## 2. UI 场景 ABI v0（已实现，src/ui_scene/ + sim/tb_ui_scene.sv）

描述符表：32 槽 × 8 word（32B/槽），双 bank；glyph 序列 RAM 512×8b 同样双 bank。

槽布局（word0..7）：

```
word0: type[7:0], flags[15:8], visible[16]
word1: x[11:0], y[23:12]            （画布 640×360，等比 1080p 几何）
word2: w[11:0], h[23:12]
word3: color[23:0] (RGB888)
word4: value[15:0]                   （BAR 千分比 0..1000；TEXT 字符数）
word5: glyph_ptr[8:0]                （glyph 序列 RAM 起始索引）
word6,7: reserved
```

type：0=HIDDEN, 1=TEXT, 2=BAR, 3=RECT。

CPU 写口（线性地址，固定路由 back bank）：`0x000–0x0FF` 描述符 word（wr_be[3:0]）、`0x100` COMMIT、`0x200–0x3FF` glyph 字节。COMMIT 写入后渲染器在帧边界（vsync 上升沿）原子切换 active bank 并置 commit_ack（下次 COMMIT 写清除）。active bank 对 CPU 只读。

渲染语义（已实现并固化）：
- 四拍像素流水（对齐 ui_renderer 约定）：拍 0 槽覆盖判定+最小槽号选择 → 拍 1 glyph 序列读 → 拍 2 字模 ROM 读 → 拍 3 输出寄存；de/hs/vs 同 4 拍对齐。
- 槽几何由 blanking 期 256 拍轮询预取（帧头 7200 拍 >> 256 拍，切换帧保证收敛）。
- 覆盖语义为「覆盖矩形独占」：槽未点亮像素为黑，不透出更低优先级槽；v1 若需文字叠图形须改墨水模型（已记为已知限制）。
- 槽号小者优先级高（后画大号，小号最终可见）。
- BAR 填充判定 `dx*1000 < value*w`。
- TEXT glyph 数超 glyph 序列长度时地址按 512 取模回绕（9bit 自然语义，参考模型一致）。

字模：`src/ui_scene/glyph16x32.hex`，128 ASCII × 32 行 × 16bit（$readmemh 路径按 work_dir 根写）。v0 glyph ID = ASCII 码。

TB 覆盖（两场景 921,600 像素逐拍比对 Python 参考帧，全部 PASS）：写 back bank 期间渲染输出与旧帧逐像素一致（bank 隔离）、COMMIT 后整帧原子生效、两场景帧差异非零。

## 3. MMIO 扩展 v0（草案，下一轮实现）

在现有 rv32_cpu_subsys 映射（0x8000_0000–0x8000_0028，见 src/cpu/rv32_cpu_subsys.sv 头注释）之上追加：

```
0x8000_0030 W  LOGIT_IDX   [4:0]  索引：0..7 八类 logits；8..12 五组 activity；13 dominance
0x8000_0034 R  LOGIT_VAL   当前索引值。八类为 int32 原值（B 线实测范围 [-57..169]）；
                              五组 activity 为定点 sigmoid 域（Q16，量化契约待五组 INT8 定版）
0x8000_0038 R  SNAP_META   [7:0] frame_id, [15:8] mode_id, [23:16] epoch, [31:24] valid_count
0x8000_003C W  SNAP_CTRL   [0] 快照锁存请求（NPU done 时硬件锁存完整向量，CPU 置位后读）
```

约束：结果寄存器必须是同帧完整快照（锁存握手），禁止只暴露末概率 lane；UI 提交同一 frame_id 的完整向量。mode_id/epoch 随模式切换状态机（REQUEST→完成/受控 abort→清旧结果→选镜像→新窗→RUN）递增，切换后结果必须带新 mode/epoch。

## 4. DDR 统一地址图 v0（草案，标注来源与待核对项）

DDR3 主口现役分配：m0=audio/PCM、m1=NPU 权重、m2=mel、m3=self_test。已知区段（来源：路由/控制器实测，集成前逐一核对）：

| 区段 | 地址 | 来源/状态 |
|---|---|---|
| NPU 权重镜像 A（八类） | 0x0010_0000 起，691,040 B | 板测 WOK 实测；镜像 B（五组 716,976 B 纯权重）位置待定 |
| activation 回放区 A/B | 0x0A40_0000–0x0A3F_FFFF / 0x0B40_0000–0x0B45_FFFF | native 仿真契约；曾与 spectrum 区 0x200000 重叠，集成时重排 |
| 整层 activation | A/B 区按层分段 | replay 契约 |
| PCM 环形窗/测试音频 | m0 区 | 生产 PCM 已 DDR；测试流需独立区（与 I2S 注入源共用） |
| APP 代码/大资源（阶段二） | 待分配 | 依赖 CPU DDR 桥立项；单 out-standing、非缓存数据+小只读 Icache |

新增主设备（CPU/显示）不得绕接现有主人区间；读命令发出前必须预留接收 FIFO credit（DDR IP 读通道不可反压）。

## 5. 模型描述符 v0（草案，M3 冻结）

```
struct model_desc {
  u32 magic "MDSC", u8 version=1, u8 mode_id (0=八类 1=五组),
  u16 contract_crc,           // 层契约 hash 截断
  u8[32] contract_sha256,     // layer_contract / group5_contract 全文 hash
  u16 in_frames, u16 in_bins, // 输入几何（八类 258×64、五组 130×64）
  u8 zp_in,                   // 八类 49；五组待定
  u32 weight_base, u32 weight_len, u32 weight_crc32,
  u8 head_kind,               // 0=softmax8 1=sigmoid5(+dominance)
  u8 reserved[...]
}
```

约束：第一版只允许审核过的两套模型；非法 mode/CRC 不匹配/前端几何不兼容必须显式拒绝（MMIO 错误码），不静默回退。

## 6. 数值快照真源约定（M0 基线，已产出）

reports/npu_probe_baseline_20261104.json 为固定 feature→NPU 全链的权威 golden 真源：
- 4 个确定性向量（sine440 / zeros49 静音锚点 / rand20261104 / sine440_twolevel），逐层 12 层快照（SHA256+统计），RTL=golden_pipeline=已归档 golden_ref 三方逐位一致。
- 板上三层注入（feature→PCM→I2S）比对的**第一判据**：注入 feat 后比对 fc2_u8 / logits_int32 / probs_q16；逐层回溯用 conv/pool/gap 快照（布局=RTL 输出流序 row,group,col,lane，与 DDR 激活回放对齐）。
- 4 向量 cycles 均 31,115,245（数据无关，权重 DMA 主导）。
- 单类主导 probs 饱和 65535 与 zeros49 的 1 LSB 舍入残差属已知语义，不作缺陷。
- 已知缺口：尚无不同类别的真实样本向量（现有 fixtures 仅正弦变体与静音）；取得真实八类样本后须扩充向量集再重跑。

## 7. 音频前端对照结论（A 线，reports/audio_frontend_comparison_20261104.json）

F0(44.1k 基线)/F1(原生48k)/F2(24k)/F2b(16k) 四路管线已建立并位级复现 F0；14 输入对照：F1 logits 漂移最小（|Δ|≈1.24，top1 翻转 1/14），F2 次之（≈3.89，6/14），F2b 仅作参考（≈10.0，9/14）。**三条路线均不可直接沿用旧权重，重训是硬前提**。数据缺口：无 Medley-solos-DB 验证音频（仅 IRMAS demo 切片、缺 2 类）；F2 抽取 FIR 未做 Q1.15 定点化重测。

## 8. 本轮实现状态矩阵

| 接口 | 状态 | 证据 |
|---|---|---|
| UART APP 协议 v0 | RTL 实现 + 6 场景 TB PASS | sim/run_sim.py uart_app_boot；52 检查 |
| UI 场景 ABI v0 | RTL 实现 + 2 场景像素级 TB PASS | sim/run_sim.py ui_scene；921,600 像素比对 |
| MMIO logits 快照 | 草案（本文 §3），未实现 RTL | 下一轮 C/D 集成 |
| DDR 地址图 | 草案（本文 §4），待核对重排 | 集成负责人下一轮 |
| 模型描述符 | 草案（本文 §5），M3 冻结 | — |
| 数值快照真源 | 已产出 4 向量×12 层 | reports/npu_probe_baseline_20261104.json |
| 前端对照管线 | 已产出 14 输入×4 路线 | reports/audio_frontend_comparison_20261104.json |

回归基线：check_rtl 73 .v / 0 violation；pytest 443 passed / 4 skipped；未跑 PDS、未碰 JTAG/串口、未改生产 src 既有文件（src/cpu、src/ui、src/ctrl 零改动）。
