# CURRENT —— 当前状态单页

> 更新：2026-11-10。**本页是摘要，权威细节以 `instrec_fpga/docs/DEV_SNAPSHOT_HANDOFF_20261110.md` 为准。**
> 历史日志看 `STATUS.md`；快照总览看 `docs/SNAPSHOT_INDEX.md`；权威源地址簿看 `docs/project_map.md`。

## 1. 主线目标

把八类乐器识别从 44.1 kHz + 147/160 重采样迁移到**原生 48 kHz**，使用 `deploy/medley_48k` INT8 模型完成板级真实识别验收。
验收顺序：①数据随输入变化、帧数/溢出/超时可解释 → ②同窗 golden 对拍 → ③已知类别音乐验证效果。

## 2. 当前阻塞

| # | 现象 | 已排除 / 进展 |
|---|---|---|
| 1 | **PCM 窗口 60~75% 的 32 B 页从未被写**（每 4 页仅 1 页含数据，4964/8256 页与从未写过的 stride gap 逐字节相同 = 上电残留） | 读路径正常（自检区 0x300000 读回正确）；`err_cnt` 仅 0~1 ⇒ **静默丢页**。候选 ①`audio_sink.page_go` 在写 FSM 忙时丢弃 ②`ddr3_ctrl_axi` 写超时发 done 但丢命令；仿真（DLY 4~20000、`audio_chain_full`）无法复现，需计数遥测区分 |
| 2 | 模拟输入无信号：播放 200 Hz 满幅后 `std` 仍 933.8、logits 与静音窗完全相同 | 与 #1 独立；待查播放设备路由 / 线缆 / PCM1808 VINL,VINR |
| 3 | 已烧位流 `report_timing` 为 `Some Constraints Violated`，WNS −1.402 ns + 多条 hold 违规（最差 `u_npu/u_store1 → lane_bank[6].mem`） | 与音频写路径无关；但**该位流的 NPU 数值不得作为结论依据** |

- 已恢复（不再算阻塞）：DDR3 启动自检 `@0x00300200` 失败 —— m3 `rd_ready` 由 `st_m3_sel` 改 `!st_done`，本轮位流 `st_fail=0`。
- 已恢复：diag 长读随机停帧 —— 属传输层（遥测插帧 + 主机流水线 + S_ACK 吞字节）；重写协议后 3×264192 B、`holes=0`、sha 全同、`RESULT: STABLE`。

## 3. 下一步（按优先级）

1. 加计数器遥测（`page_go` 计数 / 写完成页数 / `audio_err_cnt` / `cmd_to_err`）重建位流，**一次烧录**区分丢页候选 ①②。
2. 排查模拟输入无信号（播放路由 / 线缆 / PCM1808 输入），使 PCM 随播放变化。
3. 位流交付前必读 `report_timing/*.rtr` 的 WNS；当前 −1.402 + hold 违规的位流不可用于数值结论，须先收敛。
4. 输入有信号且时序收敛后，再做同窗 PCM/logits 与 48k golden 对拍；feat 对拍需 `FEAT_DUMP_ON_M3=1` 位流。

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
