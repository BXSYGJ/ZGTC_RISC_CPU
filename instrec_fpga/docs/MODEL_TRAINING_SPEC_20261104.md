# 模型训练规格说明（交模型负责人）

日期：2026-11-04。性质：**重训任务的完整规格与验收契约**，执行人为模型负责人；训练完成后的架构适配、分模块仿真与上板由 FPGA 侧按附录 B 流程执行（模型未交付前不启动任何新构建/烧板）。

入口文档：[HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104.md](HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104.md)、[INTERFACE_CONTRACTS_V0_20261104.md](INTERFACE_CONTRACTS_V0_20261104.md)。实时状态认 STATUS.md。

---

## 0. 为什么必须重训（两条硬理由，均已被实验钉死）

1. **前端域更换（本规格的核心动机）**：板上 PCM1808 原生输出 48 kHz。当前部署链路为迁就 44.1 kHz 训练域，硬件里挂了一条 147/160 多相 FIR 重采样（代价：4.5 片上 DRM + 一条已知的时序长路径 + 额外调试面）。A 线实验（`reports/audio_frontend_comparison_20261104.json`，14 输入×4 路线）证明：旧模型不能直接喂 48 kHz 前端的特征（logits 漂移 |Δ|≈1.24、top1 翻转 1/14，F1 路线已是漂移最小者），**重训是硬前提**。
2. **域错配已实测**：旧 float 模型在 IRMAS 域样本上仅 2/8 正确（`reports/float_vs_quant_domain_diag_20261104.json`）。正式部署类别表是 Medley-solos-DB 8 类，评估必须在 Medley 测试 split 上做，不得用 IRMAS 样本的准确率替代。

另注：FPGA 侧 standardize 量化移位 bug（>>24 应为 >>36）已修复并全链验证（commit 793b8d0a），**特征域数值语义已与浮点 QuantStub 严格一致**——新模型导出后不需要再担心这层，golden 侧对拍设施全部现成。

## 1. 数据：全部现成，明确不需要重新采集

| 任务 | 数据集 | 本机位置（只读） | 规模 |
|---|---|---|---|
| 八类 | Medley-solos-DB（公开集，train/val/test split 见 metadata） | `D:\0000\111\001\Pango\InstRec\data\cache\`（按 uuid 的特征 npy）+ `Medley-solos-DB_metadata.csv` | 8 类，split 按官方 subset |
| 五组 | 同 Medley 音源的多标签活跃度标注 | `InstRec\data\group5_cache_v3\` | 44091×64×130，35185 train / 8906 val（split/labels/dominance/mask 齐） |

约束：
- split 严格沿用现有 metadata 的 subset 划分，按录音来源隔离，禁止相邻窗口跨 train/test 泄漏；
- 校准（量化）只用训练 split；调参只用验证 split；测试 split 只在冻结候选后报一次；
- 若认为需要补数据（例如打击乐正例稀少），先在报告中列为外部依赖，不得静默混入新源。

## 2. 前端契约（训练=部署逐项一致，这是 FPGA 验收的对拍基准）

### 2.1 八类（模式一）——F1 原生 48k 路线

| 参数 | 值 | 与现部署（F0）的差异 |
|---|---|---|
| sr | **48000** | 44100→48000，删除 147/160 重采样 |
| n_fft / win_length / window | 2048 / 2048 / hann | 不变 |
| hop_length | 512 | 不变（帧率 93.75 fps，窗口时长 42.67ms） |
| n_mels | 64 | 不变 |
| n_frames | **258**（输入几何 (1, 64, 258)） | 不变；约 2.75s 上下文（原 2.99s，帧数不变时长略缩） |
| f_min / f_max | 0 / **24000** | fmax 22050→24000（新 Nyquist），**Mel 表必须重生成** |
| power / top_db | 2.0 / 80.0 | 不变 |
| normalization | per_sample | 不变（RTL db_norm/standardize 链已按此实现并 bit-exact） |

训练前处理实现直接改 `InstRec/src/features.py` 的 SR/F_MAX 常量（librosa.load(sr=48000) + melspectrogram(fmax=24000)），其余不动。参考实现（48k 域 Mel 重生成+F0 对照）：本仓 `experiments/audio_frontend/frontend_variants.py` 的 F1 路线，已验证位级可复现。

### 2.2 五组（模式二）

group5_v3 的 float 与 INT8 契约**在 44.1k 域已评审转正**（`reports/group5_int8_contract_review_20261104.md`，macro-F1 0.866，RHE 语义与八类逐行同型）。但双模式**共享同一前端**（一套 FFT/Mel/归一 RTL），采样率必须统一为 48k，因此五组需要按 2.1 的前端重训/微调一版：
- 输入几何沿用 64×130（帧数不动，窗口时长 1.38s，比原 1.51s 略缩；若实验证明需要保持时长可改 142 帧，但**帧数一旦改动必须显式通知 FPGA 侧**——NPU 调度几何参数要同步）；
- 双头结构不变（5 sigmoid activity + dominance head），标注/mask/评估口径全部沿用 group5_v3 管线；
- 原 44.1k INT8 契约保留为回退基线（若 48k 版精度不达标，双模式可退回「44.1k 前端+重采样」架构，代价是恢复 FIR 重采样模块——这是架构回退开关，不是默认路线）。

## 3. 网络结构约束（RTL 算子白名单，越界=返工）

NPU 是固定算子集的卷积加速器，训练结构必须落在白名单内：

**允许**：Conv2d 3×3（padding=1，含 bias）与 1×1；BatchNorm2d（部署时折叠入 conv）；ReLU；MaxPool2d 2×2 stride2；GAP（自适应平均池化到 1×1）；Linear（小 FC 头）；Dropout（仅训练期）。

**禁止**：深度可分离卷积、stride≠1 卷积、非对称核、全局 MaxPool、注意力/SE、残差拼接、任何动态形状算子。

结构骨架固定为现有 `InstrumentCNN` 形态（4×ConvBlock+GAP+FC，输入 (1,64,258)，四级 2×2 池化 258→129→64→32→16——**池化级数不得增减**，NPU 调度已按此固化）。唯一自由度是各层通道数：

| 候选 | 通道 (C1..C4) | 说明 |
|---|---|---|
| S0 基线 | 48/96/192/256 | 精度优先参考，已知可收敛 |
| S1 | 24/48/96/128 | 资源/DDR 流量减半，**首选尝试** |
| S2 | 16/32/64/96 | 更小，作为 S1 精度不足时的下界探针 |

规则：通道数为 16 的整数倍（MAC lane 对齐）；C4≤256（wdma/FC 硬件上限）；最终选择以「Medley test macro-F1 达标+完整 top 资源预算」共同裁定，FPGA 侧会在候选冻结后出 16/8lane 对照数据。八类与五组可用不同通道档（各自独立训练优先，共享骨干仅在实验胜出后考虑）。

## 4. 量化导出规格

沿用 InstRec 现有 PTQ 流程（`deploy/quantization_config.json` 同型），硬性要求：

1. per-channel int8 权重、per-tensor quint8 激活输入（QuantStub）；
2. 校准只用训练 split，固定 seed，双跑导出 hash 必须一致（可重建性是验收项）；
3. requant 一律 round-half-even（部署 RTL 已按此实现，golden 对拍设施现成）；
4. **必须随交付报告 QuantStub 的 {scale, zero_point}**：FPGA 侧 standardize 的 zp_in/inv_s_in 目前是按旧契约写死的参数，新模型的这两个数会变（zp_in 不再是 49），这是架构适配的第一输入；
5. 交付前自检：同结构 float vs INT8 的 macro-F1 差 ≤ 2 个百分点；任何单类 recall 下降 >5 个百分点须附解释。

## 5. 验收门槛（冻结判据，测试 split 只报一次）

八类（Medley test split）：
- macro-F1：S0 结构不低于旧 44.1k 模型的重测参考值；S1/S2 相对 S0 掉 ≤3 个百分点（规划 §4.4 准则）；
- 报告逐类 recall、混淆矩阵、balanced accuracy、静音/未知音行为；
- INT8 相对同结构 float：macro-F1 差 ≤2pt。

五组（沿用 group5_v3 评估口径）：
- 逐类 precision/recall/F1、macro/micro-F1、PR-AUC、多活跃/无活跃覆盖；dominant agreement 不低于 44.1k 版（0.9706）减 0.5 个百分点；
- 打击乐稀少类单独列支持数与置信区间，不用总分掩盖。

阈值（sigmoid 0.5 起步）在验证 split 上定并版本化，测试集不得参与调阈。

## 6. 交付物清单（交回 FPGA 侧的最小集合）

| # | 交付物 | 形式 | 用途 |
|---|---|---|---|
| 1 | float checkpoint | .pt | 精度复测/蒸馏 teacher |
| 2 | INT8 量化模型 | TorchScript .pt | 部署真源 |
| 3 | 类别表 | class_names.json（**names 顺序逐字对齐 `InstRec/deploy/class_names.json`**，中文名列一并更新） | 类表误读是历史事故源（曾把 idx6 读成小号） |
| 4 | QuantStub 参数 | {scale, zero_point}（json 或写在 2 的配置里） | standardize 参数化适配 |
| 5 | 评估报告 | json+md（§5 全部门径） | 验收证据 |
| 6 | 训练配置 | seed/超参/数据 manifest hash | 可重建性 |
| 7 | （八类）通道档结论 | S0/S1/S2 的 val 曲线摘要 | lane/资源权衡输入 |

交付方式：放 `InstRec/runs/<新名字>/` 或 `instrec_fpga/models/<新名字>/`（后者会被 FPGA 侧 hash 冻结入库），**不得覆盖任何既有 runs/best_model.pt 或 group5_v3 资产**。

## 7. 已知风险与边界（如实记录，不要静默处理）

- 48k 域 Mel 高频段（22.05k~24k）新增约 3~4 个有效 bin，对高音乐器（小号/失真电吉他）大概率有益、对低音乐器中性，但**以实测为准**；
- 五组 130 帧@48k 的窗口缩短 0.13s，打击活跃度的响应时延会变快，若评估变差优先怀疑此处；
- IRMAS 样本**只允许**做跨域 sanity（修复后期望「分化但多错」），不得写进任何验收数字；
- 若训练中想改 n_frames 或池化级数：先停下，通知 FPGA 侧评估调度改动——这两项是硬件固化几何。

---

## 附录 A：旧资产处置

- `runs/best_model.pt`、`group5_v3`、44.1k INT8 契约（五组）全部保留为基线/回退，不覆盖不删除；
- 板上现存任何位流（含 1497FAF4）均含 shift-24 旧 bug，其分类行为在新模型验收中无参考价值；
- `releases/pacerv-instrec8-20261103/` 冻结包只读，重训成果一律进新目录。

## 附录 B：模型交付后的 FPGA 侧流程（本侧执行，模型负责人无需跟进）

按用户裁定的顺序，逐级推进、逐级出证据，任何一级不过不进下一级：

1. **契约适配**：重生成 48k Mel 表（fmax 24k）→ `gen_weight_image.py` 重导 layer_contract.json / weights_image.bin → standardize.v 的 zp_in/inv_s_in 参数化改写 → golden_pipeline 同步；
2. **分模块逐个仿真**（每个模块独立 TB+golden，全过才并全链）：mel 前端（新表 0 失配）→ conv1（新权重 hex 逐字节）→ conv2~4/pool/GAP/FC（npu_probe 固定特征全链）→ softmax/快照 → UART APP/UI 场景/logits_snap（既有 34 TB 全套）；
3. **全链联合仿真**：native DDR 模型 + 真实音频特征 + IRMAS 跨域 sanity（期望分化）；
4. **唯一 PDS**：资源门控（DRM≤124/155、LUT≤70%、APM≤70% 目标）→ 限时 PNR → 完整十表时序（逐时钟域判读，不以 WNS 首行为准）；
5. **板级三层注入**：feature 注入 → PCM 注入 → 板内串行 I2S 注入，逐级与新 golden 对拍（判据=新 npu_probe 基线），差异必须导出实际字节定位；
6. **PCM1808 真实音乐双模式验收** + 1h 耐久。

版本纪律：新位流用新归档名（`releases/<版本>/`），不覆盖 `build/instrec-latest.sbit` 以外的既有验收产物；每级证据落 `reports/`，STATUS/CHANGELOG 同步，XSY 分段 commit（不自动 push）。
