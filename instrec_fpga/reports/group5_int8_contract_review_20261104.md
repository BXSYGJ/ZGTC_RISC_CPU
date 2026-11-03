# Group5 INT8 契约评审报告（2026-11-04）

评审人：模型契约评审工程师（CodeArts 会话）
评审对象：2026-11-03 遗留的未跟踪五组（弦乐/木管/铜管/打击/键盘拨弦）双头活跃度模型 INT8 契约候选资产
工作目录：`instrec_fpga/`（InstRec/ 只读，未触碰 cpu/、ai_pcb/、pcb-aoi/、releases/、obj_dir/）

---

## 1. 资产清单与 hash

| 资产 | SHA256 | 规模 |
|---|---|---|
| `scripts/golden_pipeline_group5.py` | `f2e635ae5f165c3941022759cfc9907635eec191c1e009bff9c667a9a00d674f` | 1296 行 |
| `scripts/eval_group5_int8.py` | `c1d2f6b35a5c7719729ba47228ec5dfc621c177406833bdfa279e03d542e11ef` | 382 行 |
| `scripts/outputs/group5_contract.json` | `4c097ba7b48ed28e94c348cb2cc7b78b8e06cca3627059f4260317f2bfc65943` | 87KB |
| `scripts/outputs/group5_weights_image.bin` | `2c59459a71a9070bc88f10e2da2f6021a0583910081136a6f2fa6c954bfb9354` | 725,760 B（CRC32 `7A728502`，payload_checksum_128 `24293dd4f98388e01f9057aff63c13d7`） |
| `reports/group5_int8_calibration_20261103.json` | `0ebba5bb26bee6c5e817d9294664f17595574e88b93873e6d675f99f576b2a71` | 验收报告 |

来源链完整且逐环 hash 锁定：ckpt `5ada8db6…`（`InstRec/runs/group5_v3/best_model.pth`，只读）→
`models/group5_v3_float_20261102/float_state.npz` `0fb65934…`、`reference_vectors.npz` `584fb765…`
（manifest.json 资产表逐项复核一致）→ contract 的 `model_id` 记录上述全部 hash +
特征源 `all_features.npy` `2fda04f6…`（`calibration.features_sha256`）。

**结构完整性结论：通过。** 契约 8 层（conv1-4 / fc1 / fc2 / dom_fc1 / dom_fc2），逐层
`s_in/zp_in/s_out/zp_out/M[]/shift[]/bias_int32[]/weight_shape/in_shape/out_shape/image_offset/
segment_bytes/padding_value/zp_in_correction.wsum` 齐全；镜像布局字段（header 32B + 8×64B 契约表 +
0x400 起 32B 对齐段）与 `image_layout` 一致；`sum(segment_bytes)=724698 + 1024 首层偏移 + 对齐 = 725760`
与文件实际长度、`image_total_bytes` 三方一致。校准元数据（8001/35185 行、seed 20261102、
out_domain=sat、feat_sat=6.5、p99.99）齐备。

## 2. 量化语义与八类契约的同型性（逐项）

| 项 | 八类（golden_pipeline.py / gen_weight_image.py） | 五组（golden_pipeline_group5.py） | 同型性 |
|---|---|---|---|
| requant 舍入 | `sat_int8(RHE(acc*M>>>shift)+zp_out)`，`round_half_even_shift` 位级 RHE | `sat_u8(RHE(acc*M>>>shift)+zp_out)`，**同一函数逐行相同** | ✅ 同型（容器 u8/s8 差异见第 5 节 A4） |
| M/shift | `compute_m_shift`，M∈[2^30,2^31) Q0.31，shift∈[0,63] | **逐行相同**；实测 shift∈[34,42]⊂6bit，M∈[1074752778,2146735807] | ✅ 同型 |
| zp 语义 | zp_in=49 正偏移，padding_value==zp_in，`-zp_in*Σw` 修正（wsum 记录） | zp_in=98，padding_value=98，`zp_in_correction.wsum` 同机制；fc2 zp_out=128 / dom_fc2 zp_out=94，其余层 0 | ✅ 同型 |
| BN 折叠 | torch FX 融合（eval 语义） | 手工同公式：`w·γ/√(var+eps)`、`b·γ/√(var+eps)+β-γ·mean/√(var+eps)` | ✅ 数学同型 |
| 输入量化 | `sat_u8(RHE(z*inv_s_in>>24)+zp_in)` Q8.24（design.md 3.7） | 同路径；inv_s_in=404073701（Q8.24），zp_in=98 | ✅ 同型 |
| bias_int32 | astype 损坏教训（AGENTS.md 记录） | 从 float_state BN 折叠后 **RHE 重建**，内置 round-trip 断言 | ✅ 修正了八类缺陷路径 |
| 双头处理 | 单头 fc1/fc2 | activity(fc1→fc2) + dominance(dom_fc1→dom_fc2) 共享 GAP 向量、分段布局（activity 先）、契约 `dual_head` 字段 | ✅ 契约显式声明 |
| GAP | 8×16=64 taps，>>6，RHE，恒等量化 | 4×8=32 taps，**>>5**，RHE，恒等量化（`gap_contract` 显式声明差异） | ✅ 几何差异已声明 |
| 浮点 MAC 精确性 | — | float64 BLAS + rint == 纯 int64 tensordot（每次调用交叉验证，实测 conv1-4 全 0 LSB） | ✅ 证明成立 |

五类新增（八类没有、均有代码内论证与数据支撑）：输出域语义饱和 clip（fc2 ±14 sigmoid 界 /
dom_fc2 24-span softmax 窗 / 输入 ±6.5 z 域）、conv1-4 p99.99 百分位校准。这些是校准策略层差异，
不改变 RTL 契约语义（requant/zp/GAP 位级语义不变）。

## 3. 评估运行结果（本次全量复现，与 2026-11-03 遗留报告逐位一致）

`python scripts/eval_group5_int8.py --report build/review/eval_run1.json`（8906 全 val 行，
Python 3.12.7 / numpy 2.1.2 / torch 2.14.1+cpu；float 前向 62.3s，int8 前向 659.1s）：

- **验收判定 PASSED**：dominant-group agreement `0.970581630361554` ≥ 0.97 且 macro-F1 降幅 `-0.007487` ≤ 0.02
- macro-F1：float `0.873074` → int8 `0.865587`（Δ `-0.007487`）；micro-F1：`0.899713` → `0.896462`；
  subset accuracy：`0.753986` → `0.749270`
- 逐类 F1（float → int8）：strings `0.9673→0.9646`、woodwinds `0.8414→0.8383`、
  brass `0.7284→0.7264`、percussion `0.9284→0.8996`、keys `0.8999→0.8991`
- percussion callout（稀疏类，389 val 正样本）：F1 Δ `-0.0288`（recall `0.8663→0.8175`）——单类超 0.02，
  验收口径为 macro-F1
- dominance（7934 masked 行）：MAE vs GT `0.054531→0.054155`（int8 反而略优），
  MAE int8-vs-float `0.009353`；dominant acc `0.866650→0.874338`
- no_active：比率 `1.089%→1.404%`（97→125 行），二元一致 `0.995060`；
  行级活跃集一致 `0.940602`
- logit 域 max Δ：activity `66.14`、dominance `48.66`（sat clip 语义预期，非缺陷）；
  概率域健康信号：dom max|Δprob| `0.0218`

**确定性验证（四重证据）**：
1. eval 全量双跑：剔除 `timing_sec` 后两份报告全字段一致，metrics 字典 sha16 均为 `cd3010f0b7049940`，
   全报告 sha16 均为 `69176c1c9e89bdcc`（注：报告含计时字段，文件级 hash 必异，属正常）；
2. 本次 run1 与 2026-11-03 遗留校准报告（`0ebba5bb…`）的全部指标逐位一致——遗留报告可信；
3. `npu_forward_group5` 对 reference 5 样本与 val 前 3 行复算：同进程两次 logits sha16 一致
   （`51692b7a…`/`c620530d…`）；
4. 生成器重跑（`--outdir build/review --weights-dir build/review/weights_group5`）：contract 与 image
   **byte-identical**（SHA256 与候选相同），验证了契约 `determinism: byte-identical on re-run` 声明。

**golden 复算（任务 2.3）**：reference_vectors 5 样本 int8 前向与契约内
`reference_sample_check` 逐元素相等（round(6) 表 exact 相等，max|dlogit| act `21.355563` /
dom `20.557297` 与记录一致）；与 float 模型并排前向：activity 决策 24/25 一致（与记录一致），
dom 概率 max|Δ| `0.0218`。val 前 3 行（17284/17285/17286）int8 vs float logit 对照：偏差集中于
饱和区（如 row 17286 float `-67.27` vs int8 `-14.06`，fc2 ±14 clip 下界），argmax/决策不受影响，
属声明的无损 clip 语义。

**一致性核对（任务 3）**：
- contract 逐层 `weight_shape` 与 `float_state.npz` 8 个权重张量 shape 全一致，
  `weight_bytes == float 权重元素数` 全一致；bias/M/shift 长度 == 各层输出通道数全一致；
- 镜像 725,760 B == `image_total_bytes`；SHA256/CRC32/payload_checksum_128 独立重算全部一致；
  镜像 header（magic IRW1 / 8 层 / ver 1 / total 725760 / payload 725728）解析一致；
- `deploy/weights_group5/`（上次会话副产物，40 个 npy）与本次生成器重跑产物 **byte-identical**，
  其 manifest 的 contract/image hash 字段与候选一致（仅 outdir 路径字段不同，属预期）；
- weight image round-trip 解析（bias/M/shift 与契约记录逐项断言）通过；int64 纯整数 MAC
  交叉验证 conv1-4 全 0 LSB。

## 4. 验证命令与中间产物

```
python build/review/recompute_check.py                              # 复算/完整性/确定性
python scripts/eval_group5_int8.py --report build/review/eval_run1.json   # 全量 ×2
python scripts/eval_group5_int8.py --report build/review/eval_run2.json
python scripts/golden_pipeline_group5.py --outdir build/review --weights-dir build/review/weights_group5
python -m pytest -q                                                 # 443 passed, 4 skipped
```

中间产物落在 `build/review/`（eval_run1/2.json、重跑 contract/image/weights_group5、
recompute_check.py），符合"正常中间输出"约定；候选五文件保持原样未改动（hash 见第 1 节，评审前后一致）。

## 5. 缺陷/风险清单（分级）

### 阻塞转正
无。

### 需修正 / 转正后必须跟进
- **R1（格式偏离，集成期风险）**：`pack_contract_entry` 的 zp_in/zp_out 打包从八类 signed `'b'`
  改为 unsigned `'B'`（fc2 zp_out=128 超 int8 正域，必须无符号——理由成立且代码内有记录），但
  `FORMAT_VERSION` 仍为 1、magic 仍为 `IRW1`，与八类镜像"同版本号不同 entry 编码"。任何复用八类
  解析代码的 RTL weight_loader / 板级校验工具会把 128 读成 -128。**要求**：M2 接线前同步解析端；
  建议主线提交时在 STATUS.md 挂显式告示（或后续 bump FORMAT_VERSION=2）。
- **R2（缺测试防线）**：五组契约没有任何 pytest 冻结用例（八类有 443 测试防线）。建议随转正补
  最小冻结测试：锁 contract `4c097ba7…` / image `2c59459a…` hash + reference_sample_check 关键数值
  + requant RHE 语义断言。
- **R3（验收余量薄）**：dominant agreement `0.97058` 对 0.97 阈值余量仅 +0.0006（58 行翻转裕量）；
  no_active 比率相对 +29%（97→125 行）。板级 mel 前端若与 golden 有 LSB 级偏差可能跌破 0.97，
  上板验收需重跑本评估口径。模型侧已尽力（p99.9/minmax 变体更差，有校准数据支撑）。

### 可接受
- **A1**：logit 域 max Δ 66.1/48.7 —— sat clip 语义预期（脚本 note 已声明概率域为健康信号：
  dom max|Δprob| 0.0218、activity 决策一致 24/25、全量 agreement 在验收内）。
- **A2**：percussion 单类 F1 Δ -0.0288 超 0.02 —— 验收口径为 macro-F1（-0.0075）；389 正样本的
  稀疏类摆动，脚本已单独 callout。
- **A3**：GAP >>5（4×8=32 taps）、u8 输出容器、奇宽 floor pool（130→65→32，奇尾丢弃）——
  与八类的几何/容器差异全部在契约中显式声明，RTL 按契约实现即可（属 M2 改造范围，非契约缺陷）。
- **A4**：int8 全量前向 659~728s（批 32）——评估性能可接受。
- **A5**：`DEFAULT_CACHE_DIR` 指向仓库外只读路径 `InstRec/data/group5_cache_v3`，契约已用
  `features_sha256=2fda04f6…` 锁定数据来源；缓存缺失时需回 InstRec 重建，属已知部署约束。

## 6. 结论：**转正提交**

理由：
1. 五资产结构完整、来源链逐环 hash 锁定（ckpt→float_state→contract→image→eval 报告）；
2. 量化语义与八类契约核心五项（RHE requant / M-shift 6bit / zp 填充与修正 / BN 折叠 / 输入 Q8.24）
   逐行核实同型，且修正了八类 bias astype 损坏路径；
3. 位级一致性全绿：int64 交叉验证 0 LSB、镜像 round-trip 断言、reference 逐元素复现；
4. 确定性全绿：生成器重跑 byte-identical、eval 双跑 metrics sha 一致、遗留报告逐位复现；
5. 验收标准通过（agreement 0.9706 ≥ 0.97 且 macro-F1 Δ -0.0075 ≤ 0.02），R1-R3 均为
   转正后的集成/跟进事项，不构成对候选资产本身的否定。

**建议提交清单**（提交由主线执行，本评审未做任何 git add/commit）：
- `scripts/golden_pipeline_group5.py`
- `scripts/eval_group5_int8.py`
- `scripts/outputs/group5_contract.json`
- `scripts/outputs/group5_weights_image.bin`
- `reports/group5_int8_calibration_20261103.json`
- `reports/group5_int8_contract_review_20261104.md`（本报告）
- `deploy/weights_group5/`（40 个 npy + manifest.json：生成器默认输出、与镜像 byte-identical、
  含 round-trip 防损坏断言；八类 `deploy/weights` 有被跟踪先例——是否随本次提交由主线决定，
  `.gitignore` 无 deploy 排除规则）

## 7. 回归

`python -m pytest -q`：**443 passed, 4 skipped**（71.1s）——与主线基线一致，无回归。
