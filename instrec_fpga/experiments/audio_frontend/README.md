# audio_frontend —— F0/F1/F2/F2b 前端路线数值对照基础设施

双模式规划（八类乐器识别 + 五组活跃度）的**前端路线评估实验目录**。
不改动任何生产文件（`src/`、`scripts/`、`sim/`、`tests/`），全部产物只落在
本目录与 `reports/audio_frontend_comparison_20261104.json`。

## 四条路线

| 路线 | 采样率 | 速率转换 | FFT/hop | 窗时长/hop | Mel fmax | 说明 |
|------|--------|----------|---------|-----------|----------|------|
| F0  | 44.1k | 48k→44.1k soxr_hq（生产重采样） | 2048/512 | 46.44/11.61 ms | 22050 Hz | 生产基线（`mel_tables.json` / `features.py` 契约） |
| F1  | 48k   | 无（删重采样器） | 2048/512 | 42.67/10.67 ms | 24000 Hz | 原生 48k，Mel 表按新 Nyquist 重生成 |
| F2  | 24k   | 等波纹 FIR 2 倍抽取 | 1024/256 | 42.67/10.67 ms | 12000 Hz | 与 F1 同物理时窗；FIR 191 taps，阻带 81.2 dB |
| F2b | 16k   | 等波纹 FIR 3 倍抽取 | 1024/256 | 64.00/16.00 ms | 8000 Hz | 仅建管线对照，精度仅作参考 |

所有路线共享 `InstRec/src/features.py` 的 float 语义：
`|STFT|² → slaney Mel(64) → power_to_db(ref=max, amin=1e-10, top_db=80) →
对齐 258 帧（不足右补零 / 超出保末端）→ per-sample 标准化(eps=1e-6)`。
Hann 窗与 Mel 表生成方式与 `scripts/gen_mel_tables.py` 完全一致
（`get_window("hann", n_fft, fftbins=True)`、`filters.mel(htk=False, norm="slaney")`），
F1/F2/F2b 按各自 Nyquist 重新生成（fmax 不超 Nyquist）。

## 文件

- `frontend_variants.py` —— 四条路线的 float 域实现：配置表、Hann/Mel 表生成、
  FIR 设计（`scipy.signal.remez`）与频响测量、抽取（`resample_poly` 群延迟补偿）、
  生产语义谱图链、uint8 量化（fbgemm round-half-even）。
- `run_compare.py` —— 入口脚本（见下）。
- `reports/audio_frontend_comparison_20261104.json`（生成物）—— 资产 hash、
  配置表、FIR 实测、sanity、14 输入 × 4 路线的特征统计 / 与 F0 逐 bin 差异 /
  三模型 logits 对照、汇总与结论。

## 用法

```powershell
# 在 instrec_fpga/ 下
python experiments/audio_frontend/run_compare.py                 # 默认全集
python experiments/audio_frontend/run_compare.py --wav x.wav     # 追加输入
python experiments/audio_frontend/run_compare.py --out foo.json  # 换报告路径
```

输入信号（统一到 **48 kHz float 前端域**，与 PCM1808 物理输入一致）：
3 个 seed 固定合成信号（440 Hz 正弦 / 白噪声 / 多音混合）、3 个板载 fixture
（`tests/fixtures/*.wav`，44.1k→48k soxr_hq）、8 个真实乐器 demo 切片
（`InstRec/data/demo/irmas_test/*.wav`，只读；44.1k 立体声混单声道后升 48k）。

模型对照（均只读加载）：
- **8q**：部署量化 TorchScript `InstRec/deploy/quantized_model.pt`，
  喂 uint8 特征（`layer_contract.json` quant stub：s_in=0.0626662, zp_in=49），
  链式前向与 `scripts/golden_pipeline.py` 的 `torch_npu_reference` 相同。
- **8f**：float 八类 checkpoint `InstRec/runs/best_model.pt`（InstrumentCNN）。
- **g5**：冻结五组模型 `models/group5_v3_float_20261102/`（DualHeadInstrumentCNN），
  取特征末端 130 帧（1.5 s keep-tail 契约）。

确定性：无 wall-clock 时间戳、固定表/固定 FIR taps/seed=20261104、
torch 单线程 eval；重复运行报告 byte-identical
（`sha256 097c3204…` 两次运行一致已验证）。

## 三项 sanity（跑对照前必须全绿）

1. **S1 Mel 表**：重生成 F0 slaney Mel vs `mel_tables.json` COO 重建，max|Δ|=1.5e-5
   （在 COO 稀疏化丢弃阈内）。
2. **S2 features.py 对拍**：F0 float 链 vs `InstRec/src/features.py` 在
   `sine_440_full.wav` 上 **max|Δ|=0.0（bit 级一致）**。
3. **S3 量化对拍**：`quantize_uint8` vs `torch.quantize_per_tensor`，0 mismatch。

## 2026-11-04 运行结果摘要（14 输入均值）

| 路线 | mean\|dz\| | max\|dz\|(均值) | Pearson r | \|Δlogits\| 8q(均值) | top1 翻转(8q/8f) |
|------|-----------|----------------|-----------|---------------------|------------------|
| F1   | 0.250     | 2.608          | 0.873     | 1.243               | 1/14、1/14        |
| F2   | 0.449     | 3.095          | 0.700     | 3.889               | 6/14、6/14        |
| F2b  | 0.844     | 3.756          | 0.270     | 10.024              | 9/14、9/14        |

**结论：任何一条新路线的特征与 F0 特征不可直接互换（需重训）**——
旧模型（部署量化八类 / float 八类 / group5 v3）对 F1/F2/F2b 特征的
logits 漂移分别为 ~1.2/3.9/10.0（均值最大绝对值，8q），top1 翻转
1/6/9 of 14；group5 活跃度漂移最大 0.63/1.00/1.00。
数值上 F1 漂移最小（只删重采样 + Mel 重映射），F2 次之（Mel 重映射 +
0.94 ms hop 时基差），F2b 仅作管线参考（8 kHz fmax 使上部约 21 个
Mel 通道失去有效能量）。

## 接入将来的重训评估

1. **训练侧管线切换**：重训时把 `InstRec/src/features.py` 的固定常量换成
   对应路线参数（F1: SR=48000, F_MAX=24000；F2: SR=24000, N_FFT=1024,
   HOP=256, F_MAX=12000），Mel/Hann 表用 `frontend_variants.py` 的
   `hann_table()/mel_filterbank()` 同源生成，保证训练-部署一致。
2. **抽取 FIR 固化**：F2/F2b 的 191-tap 系数由 `design_decimation_fir()`
   确定性生成（remez 无随机性）；RTL 化时按 Q1.15 量化系数并重测阻带，
   用 `fir_response_stats()` 报告实测衰减。
3. **特征漂移回归**：重训完成后重跑 `run_compare.py`，把新模型 checkpoint
   加进 `load_models()`（或通过 `--wav` 扩输入集），对照
   `summary.<variant>.8q_logit_abs_max_mean` 是否收敛到 F0 水平。
4. **int8 契约刷新**：重训后 `layer_contract.json` 的 `s_in/zp_in` 会变，
   `run_compare.py` 自动从契约读取，无需改代码。

## 已知数据缺口

- 本机无 Medley-solos-DB 验证集原始音频；真实样本仅为 8 个 IRMAS demo
  3 s 切片（clarinet/flute/piano/saxophone/trumpet/violin 精确或同族对上，
  guitar_acoustic 超类、guitar_electric 近邻；**female singer 与
  distorted electric guitar 无样本**）。
- 因此本对照只量化特征/logits 数值漂移，**不能**给出八类精度结论；
  精度评估需重训 + Medley-solos-DB / IRMAS 验证集。
