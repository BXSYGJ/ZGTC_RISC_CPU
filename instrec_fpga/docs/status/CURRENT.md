# CURRENT —— 当前状态单页

> 更新：2026-11-10。**本页是摘要，权威细节以 `instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md` 为准。**
> 历史日志看 `STATUS.md`；快照总览看 `docs/SNAPSHOT_INDEX.md`；权威源地址簿看 `docs/project_map.md`。

## 1. 主线目标

把八类乐器识别从 44.1 kHz + 147/160 重采样迁移到**原生 48 kHz**，使用 `deploy/medley_48k` INT8 模型完成板级真实识别验收。
验收顺序：①数据随输入变化、帧数/溢出/超时可解释 → ②同窗 golden 对拍 → ③已知类别音乐验证效果。

## 2. 当前阻塞

| # | 现象 | 已排除 / 进展 |
|---|---|---|
| 1 | 诊断位流烧录后 DDR3 自检失败：`DDR3 ERR @00300200`，随后 `weight_upload.py` 无回复 | diag3（sha `01fe4336…`）、diag4（sha `4c46193b…`）均失败；`st_done` 门控已加仍失败；当前源码 `FEAT_DUMP_ON_M3=0` 的位流尚未构建成功（90 min 超时，Unrouted 2580–2649，需重跑） |
| 2 | `top1` 对 200 Hz 与 6 kHz 满幅测试音完全相同（`top1=3`，`last_p` 相同） | mel 每窗正常完成、NPU 每窗完成；已排除播放链路、模拟输入、I2S/CDC、零帧门槛、窗口步长、mel 读口仲裁、mel_filter COO 表。未定位 mel 实际读到的 PCM / feat 是否随输入变化 |

## 3. 下一步（按优先级）

1. 按诊断增量做二分：`diag_readback` 例化（m3 端口 + UART 分发）、`npu_top.logits_out` 引出、`audio_sink.diag_lock`、`feat_dump`、`feat_page_buf` 关闭——相对正常基线 `instrec-48k-injfix-20261109`（`2726f0cd…`）/ `instrec-48k-melstat-20261110`（`f7552f2a…`）逐项排除。
2. 恢复诊断位流后，按“一次烧录、多组实验”（静音 / 200 Hz / 6 kHz / 已知类别音乐）逐组锁窗导出，PC 算 golden 逐段比较。
3. 诊断完成后再修功能，不叠加推测性修复。

## 4. 不要改错的关键契约

- 48 kHz 窗口：259 帧 × hop512 = 132,096 帧 = 2.752 s；8256 页；`WIN_FRAMES` 18 位。
- 输入量化：`zp_in=47`、`inv_s_in=236403274`、`QUANT_IN_FRAC_BITS=36`；特征域 `[0,177]`。
- 层契约：conv1 `zp_in=47`，其余 conv `zp=0`，`fc2 zp_out=58`，shift 37..53，镜像 691,040 B。
- 旧 44.1k 基线（勿混用）：`zp_in=49`、`inv_s_in=267723430`、`fc2 zp_out=57`。
- DDR 地图与命令格式见当前快照 §4。

## 5. 工作纪律

- 改 RTL 前 `check_rtl`（0 violation），提交前全量 `pytest`。
- 一次只跑一个 `pds_shell.exe`；PDS 有界 90 min；成功位流归档 `releases/<新名>/`。
- 不 push；JTAG 侧 `cdt_js` 只复用、不强杀、不新起第二个。
- 失败构建/被否位流不覆盖。

## 6. 本页维护规则

每次更新当前快照后，只同步本页的“阻塞/下一步/契约”三节；不要在本页写变更史。
