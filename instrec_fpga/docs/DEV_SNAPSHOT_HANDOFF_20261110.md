# 开发快照 / 交接文档（2026-11-10）

**一句话现状**：48 kHz 原生前端 + `deploy/medley_48k` INT8 模型已全链接入，数值侧全部 0 LSB；**板级 `top1` 对 200 Hz 与 6 kHz 测试音完全相同**，第一个偏差环节尚未定位。诊断基础设施（一次构建 + 可重复读回）已实现并通过离线验证；诊断位流因 **DDR3 启动自检在 `0x00300200` 失败** 暂不可用。

---

## 1. 目标与验收定义

把八类识别系统从「44.1k + 147/160 重采样」迁移到**原生 48 kHz**，使用模型侧交付的 `dist/deploy/medley_48k` INT8 模型完成板级真实识别验收。

验收（用户已明确定义，按序）：
1. 真实帧数接近每窗预期（132,096）、溢出与超时可解释、**数据随输入变化**；
2. 通过后做**同窗 golden 对拍**（板级 PCM/feat/logits 与 `golden_pipeline`）；
3. 最后用**已知类别音乐**验证识别效果。

## 2. 工作方针（用户 2026-11-10 裁定，必须遵守）

1. **先离线验证诊断方案**，确认窗口编号/地址/数据顺序/导出脚本正确后才启动 PDS。
2. **一次加入可复用诊断接口**（复用 UART/MMIO、DDR、特征存储；支持锁窗、暂停覆盖、分段读回），不新增多块大缓存；改动前说明资源开销与是否改变正常数据路径。
3. **资源裁剪与诊断合成一次构建**（频谱 UI 缓存可关，推理存储保留）。
4. **一次烧录、多组实验**（静音 / 200 Hz / 6 kHz / 已知类别音乐），逐组锁窗导出，PC 算 golden 逐段比较。
5. **诊断完成后再修功能**，不叠加推测性修复（此前 DDR3 `S_R` watchdog 改动已因此回退，commit `9e478c65`）。

其他纪律：简体中文；每次提交前 `check_rtl`（0 violation）+ `pytest -q`；位流归档 `releases/<新名>/`；XSY 本地提交不 push；不请求用户拔插硬件；PDS 有界 90 min。

## 3. 当前阻塞（接手者先看这里）

### 3.1 板级 DDR3 自检失败（诊断位流不可用）
- 现象：烧 `releases/instrec-48k-diag3-20261110`（sha `01fe4336…`）或 `diag4`（sha `4c46193b…`）后 UART：
  ```
  DDR WAIT STS 0x00000000
  NPU GO
  DDR3 SELFTEST...
  DDR3 ERR @00300200
  DDR3 STS 00000000
  ```
  随后 `weight_upload.py` 无回复（`UPLOAD FAILED`）。
- 已排除：`st_done` 门控（diag4 已加，仍失败）⇒ 不是「自检期间 diag/feat_dump 抢 m3」。
- 当前源码状态：`FEAT_DUMP_ON_M3` **参数默认 0**（`src/ctrl/instrec_top.v` 顶部），即 feat_dump 的 m3 请求被摘除；`st_done` 门控保留。**尚未构建出该状态的位流**（一次尝试 90 min 超时，`build/pds/20261110-155539-87fbff7d`，Unrouted 2580–2649 @ iteration 209–211，布局退化，需重跑）。
- **对照基线**：`releases/instrec-48k-injfix-20261109`（sha `2726f0cd…`）与 `instrec-48k-melstat-20261110`（sha `f7552f2a…`）**DDR3 自检正常**，且不含 diag 相关改动。诊断位流相对它们的增量：`diag_readback` 例化（m3 端口 + UART 分发）、`npu_top.logits_out` 引出、`audio_sink.diag_lock`、`feat_dump`、`feat_page_buf` 关闭。**下一步建议按这个增量逐项二分**（每次构建约 45–90 min）。

### 3.2 `top1` 恒定（本任务的真问题）
- 200 Hz 与 6 kHz 满幅测试音 → **`top1=3` / `last_p` 完全相同**；mel 每窗正常完成（`mel_busy=0/win_miss=0/timeout=0`，实测全窗 STS 采样 17 次全 0），NPU 每窗完成（32.36 M cycles）。
- 已排除：播放设备/音量/素材、模拟输入（`i2s_capture` 实采 `std 20,481` / 6 kHz 主峰）、I2S 接收与 CDC、零帧注入门槛、窗口步长（0x84000→0x42000 已在位流中）、`FEATURE_FRAME_MAJOR=1`、mel bank 读口仲裁、`mel_filter` COO 表（`mel_48k` 逐字节 0 失配）。
- 未定位：mel 实际读到的 PCM / 产出的 feat 是否随输入变化。**这就是诊断读回要做的事。**

## 4. 已确证的数值契约（不要改错）

| 项 | 值 |
|---|---|
| 窗口几何 | 259 帧 × hop512 = **132,096 帧 = 2.752 s @48k**；8256 页（14 位）；`WIN_FRAMES` 须 18 位 |
| 输入量化 | `zp_in=47`、`inv_s_in=236403274`（`s_in=0.0709686279296875`）、`QUANT_IN_FRAC_BITS=36` |
| 特征域 | `[0,177]`（Q4.12 极值 z=8 → 8×15.94+49），**255 不可达** |
| 层契约 | conv1 zp_in=47、其余 conv zp=0、`fc2 zp_out=58`、shift 37..53、镜像 **691,040 B** |
| 旧基线（44.1k，勿混用） | `zp_in=49`、`inv_s_in=267723430`、`fc2 zp_out=57` |
| DDR 地图 | `PCM_L` 0x0 / 0x42000（双窗）、`PCM_R` 0x84000、feat 0x200000（新增）、权重 0x100000、activation 0x400000/0x440000、self_test 0x300000 |
| DDR 命令 | `{wr, addr[27:0], len[7:0]}`，`len=beats-1`，**每 beat 32 B**；256 B 帧 `len=7`，512 B `len=15` |

## 5. 已修复的真实缺陷（有证据，勿回退）

1. **shift-36**：`src/mel/standardize.v` + `golden_pipeline.py` 的 z(Q4.12)×inv_s_in(Q8.24) 曾 `>>24`（应 >>36），特征 ~50% 饱和。
2. **NPU 旧 zp**：`npu_top` 的 `conv_zp_in=49`、`fc2 ZP_OUT=57`、`logits_bus-57` → 参数化 47/58/`FC2_LOGIT_BIAS`；`npu_probe` 从 `npu_full_end/*_candidate.v` 切到生产 `src/npu/` 后 **sine440 全层 0 LSB**（`zeros49` 仅 probs 差 274，softmax 定点近似）。
3. **零注入门槛**：`audio_sink.inject_tick` 加 `sd_idle_sync`；仿真全窗口 `real=132095/132096`、`real=132096 inj=0`；板级 `STS 00020400` ⇒ frames 100%、err/overflow=0、freeze 0.015%。
4. **mel 窗口步长**：`mel_engine.PCM_WIN_STRIDE` 0x84000→0x42000（与 `audio_sink.WIN_BYTES` 对齐）。
5. **I2S 采集链**：命令捆包 37 位对齐、wrapper `_a` 族接线、TB BCK 频率、TB 采集起点。

## 6. 诊断基础设施（已完成、离线验证过）

- `src/diag/diag_readback.v`：`'L'` 锁窗 / `'U'` 解锁 / `'S'` 61 B 状态行 / `'R' addr(4B LE)+len(2B LE)` 分段读 DDR（m3，256 B/帧，`'K'` 流控）/ `'G'` 回 8×int32 logits（不占 DDR）。`tb_diag_readback` **S1–S6 全 PASS**。
- `src/diag/feat_dump.v`：feat 32 B 打包 → m3 单拍写 `0x200000`（516 条/窗）；由 `FEAT_DUMP_ON_M3` 控制（当前 0）。
- `audio_sink.diag_lock`：门控 `rd_en`/注入/`frame_event`，默认 0 无影响。
- `npu_top.logits_out/logits_valid`：`sm_start` 锁存，observation only。
- `instrec_top`：m3 三方分时（self_test > diag > feat_dump，且 `st_done` 门控）、UART 按首字节分发（0xAA→loader，其余→diag，仅 loader 空闲）、`feat_page_buf` 禁用（**DRM 146→130 / 84%**，LUT 50→52%）。
- `scripts/diag_dump.py` + `tests/test_diag_dump.py`（帧解析/CRC/LE 有符号 logits/`'K'` 流控/分段 5×65,280 B，**5 项离线测试**）。
- 手册见 `docs/DIAG_READBACK_PLAN_20261110.md` §8。

**一次烧录多组实验**（位流可用后）：
```powershell
python scripts/board_check.py --sbit <可用位流>
python scripts/weight_upload.py --image scripts/outputs/medley_48k/weights_image.bin
python scripts/diag_dump.py --label silence
python scripts/diag_dump.py --label tone200 --play build/tone_200.wav
python scripts/diag_dump.py --label tone6k  --play build/tone_6k.wav
python scripts/diag_dump.py --label music   --play build/montage_20s_12s.wav
```
判读：`pcm.raw` → `golden_pipeline`（48k 表 + 新契约）→ feat/logits，逐段比较，**第一个不一致处即缺陷位置**。

## 7. 环境

- PDS：`H:\GG\pango\PDS_2022.2-SP6.4`，license `D:\0000\111\001\Pango\Lisence\pds_windows_c03532573d51_2029-09-04.lic`（**须配合 TAP-Windows 虚拟网卡 `NetworkAddress=C03532573D51`**，否则 host mismatch；`ip.lic` 是 FlexLM 格式，PDS 不认）。
- 仿真：`python sim/run_sim.py <case>`（Verilator `H:\GG\bin\verilator.bat`）；全量 `pytest -q` 当前 **443 passed + 26 skipped**；`check_rtl.py` 79 .v / 0 violation。
- 构建：`powershell -File scripts/run_pds_full.ps1 -BuildSet full`（`pnr` 必须裸，禁止任何 PnR 参数——见 `test_build_tokens.py`）。
- 播放：`resolve_play_device()` 按名称匹配 Realtek（waveOut 索引 4→0→4 漂移），音量置满；**用立体声素材**。
- FTDI 会反复从 PnP 掉线（USB 描述符/端口重置错误），`pnputil /scan-devices` 需管理员；恢复前无法烧录。

## 8. 文件索引

**RTL**：`src/ctrl/instrec_top.v`（集成/分时/UART 分发/`FEAT_DUMP_ON_M3`）、`src/ctrl/sys_ctrl.v`（STS 4 态遥测）、`src/ctrl/uart_debug.v`（STS 8 hex）、`src/ctrl/self_test.v`、`src/ctrl/logits_snap.v`（未接线生产）、`src/diag/{diag_readback,feat_dump,top_i2s_capture,i2s_capture_ctrl}.v`、`src/audio/{audio_sink,i2s_slave_rx,audio_cdc_fifo}.v`、`src/mel/{mel_engine,mel_filter,standardize}.v`、`src/npu/npu_top.v`、`src/ddr3/ddr3_ctrl_axi.v`

**脚本**：`scripts/{gen_mel_tables,golden_pipeline,gen_weight_image,diag_dump,i2s_capture,i2s_capture_check,board_check,weight_upload,board_48k_run,run_pds_full,gen_golden_refs}.py|ps1`、`scripts/build_sets.json`、`scripts/build_full.tcl`

**仿真**：`sim/run_sim.py`、`sim/tb_{audio_chain,diag_readback,mel_engine,mel_engine_48k,i2s_capture,i2s_rx_phy,integration_lab,logits_snap,uart_app_boot,ui_scene,npu_chain,ddr3_subsys,ddr3_aw_timeout}.sv`

**数据**：`scripts/outputs/medley_48k/{weights_image.bin,layer_contract.json}`、`scripts/outputs/mel_tables_48k.json`、`src/mel/mel_coo_48k.hex`、`data/i2s_capture/montage_music_20261106/`

**位流**：`releases/instrec-48k-injfix-20261109`（DDR3 正常，frames 100%）、`instrec-48k-melstat-20261110`（+mel 状态位）、`instrec-48k-diag3-20261110` / `diag4`（**自检失败**）、`instrec-48k-model-20261107`、`instrec-48k-gapfix-20261108`、`instrec-48k-melwin-20261109`、`i2s-capture-20261106`

**外部只读**：`D:\0000\111\001\Pango\InstRec\deploy\medley_48k\`（`quant_stub.json`：s_in/zp_in=47）、`runs/medley_48k\`、`data/cache_48k\`、`data/demo/irmas_test\`

## 9. 建议的第一步

1. 用 `FEAT_DUMP_ON_M3=0` 的当前源码重跑构建（有界 90 min），确认 `DDR3 SELFTEST` 是否恢复：
   - 恢复 ⇒ 根因 `feat_dump` 的 m3 写路径；再逐项加回 `diag_readback` 例化验证读路径。
   - 仍失败 ⇒ 依次摘除 `diag_readback` 例化 → `npu_top.logits_out` → `audio_sink.diag_lock` → `feat_page_buf` 关闭，二分定位（每次都跑 `pytest` 与 compile 门控）。
2. 位流可用后按 §6 手册做四组实验，用 `diag_dump.py` 导出并与 golden 对拍，定位 PCM/feat/logits 的第一处偏差。
3. 依证据修功能；**不要**在此之前叠加推测性 RTL 修复。