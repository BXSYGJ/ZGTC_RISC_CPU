# 板级可重复读回诊断方案 v1（一次构建、多组实验）

日期：2026-11-10。依据：用户裁定「上板成本高，诊断必须可重复读取；不能每发现一个疑点就加几位 STS 再重建一次；先离线验证，再启动 PDS；诊断完成后再修功能」。

## 0. 现状与目标

已确证（板级）：真实帧 132,096/132,096（100%）、`err=0`、`overflow=0`、`freeze≈0.015%`、`mel_busy/win_miss/timeout` 全 0、模拟输入健康（i2s_capture `std 20,481` / 6 kHz 主峰）。仍未知：**mel 实际读到的 PCM**、**mel 产出的 feat**、**NPU 实际消费的 feat 一致性**、**该窗口的完整 logits** —— 即「200 Hz 与 6 kHz 的 top1 完全相同」发生在哪一段。

目标：**在同一位流下，多次锁定窗口、分段读回四类数据**，PC 端用 golden 逐段比较，定位第一个偏差环节。

## 1. 四类数据与存放位置（全部复用现有存储，不新增大缓存）

| # | 数据 | 大小 | 来源/落点 | 现状 |
|---|---|---|---|---|
| 1 | mel 实际读取的 PCM 窗口 | 264,192 B（132,096×2B 单声道） | DDR `PCM_L_BASE(0x0)+(win_id[0]?0x42000:0)`，即 audio_sink 已写入的左声道区 | **已存在，可直接读** |
| 2 | mel 产出的完整特征 | 16,512 B（64×258 u8） | mel_engine 内部 bank（NPU 直读）→ **追加一份写 DDR 保留区 `0x0020_0000`** | 需新增写 DMA |
| 3 | NPU 实际消费的特征证据 | 16,512 B（同上）+ 首/末地址与数据锁存 | 与 #2 同一 bank；NPU 启动时锁存首拍地址/数据作交叉证据 | 需 ~64 FF |
| 4 | 窗口编号 + 完整 logits | win_id(16b) + 8×32b | `npu_top` 内部 `logits_bus` 引出 → `logits_snap`（已实现 16 槽原子锁存）→ DDR `0x0021_0000` 或直接寄存器读 | 引出 ~32 FF，落 DDR 复用写 DMA |

保留区选择：`0x0020_0000`（64 KB 区，现为 spectrum 预留，实测未占用）+ `0x0021_0000`（logits 32 B）。均不与 `PCM_L(0x0..0xC4800)`、`PCM_R(0x84000..)`、权重（0x100000）、activation（0x400000/0x440000）、self_test（0x300000）冲突。

## 2. 接口（复用现有 UART 帧协议，不加新通道）

复用 `weight_loader` 的 256 B 帧（`0xAA55 + seq[2] + len[2] + payload + CRC16-CCITT-FALSE`，PC 回 `'K'` 流控）。新增命令（115200，core 域）：

| 命令 | 载荷 | 语义 |
|---|---|---|
| `'L'` (0x4C) | 无 | **锁定窗口**：置位 `diag_lock`——audio_sink 停止接受新 `frame_event`（不再写 DDR、`win_frame_cnt`/`win_id` 停止推进），mel/NPU 继续完成当前窗口。回 `'K'` |
| `'U'` (0x55) | 无 | 解锁，恢复正常采集（`win_id` 从锁存值继续） |
| `'R'` (0x52) | `addr[31:0]` LE + `len[15:0]` LE | 从 DDR 读 `len` 字节，按 256 B 帧回传（最后一帧不足补齐），seq 递增；`addr` 任意 28 位有效范围 |
| `'S'` (0x53) | 无 | 状态行：`DIAG win=<n> locked=<0/1> mel_done=<n> npu_done=<n> logits_valid=<0/1>` |

读路径：`'R'` 经 **m3 主口**（self_test 主口，推理期闲置）发 `len=15` 读命令，256 B/命令 → FIFO → UART 帧。**不触碰 m0/m1/m2 与 NPU 计算**。

## 3. 资源开销与对正常数据路径的影响

| 新增项 | 估算 |
|---|---|
| `'R'` 读 DMA（m3 + 256B FIFO 复用 weight_loader 的帧引擎） | ~180 LUT，0 DRM（FIFO 用分布式 RAM 或复用现有 4 KB 帧缓冲） |
| feat 追加写 DDR（mel_done 后 66 条 256 B 写，复用同一帧引擎的写方向） | ~120 LUT，0 DRM |
| logits 引出 + `logits_snap`（已存在模块） | ~80 FF |
| **关闭 UI 频谱缓存** `feat_page_buf`（16,512×8 = 132,096 bit ≈ **7.3 DRM18K**） | **−7 DRM** |

净资源：**DRM −7（146 → 139）**，LUT +~300（50% → 50.5%）。这正是当前 PNR 在 95% DRM 下反复差 1–2 千根线所需的余量。

正常路径：m0（audio 写）/m2（mel 读）/NPU feat 读**零改动**；m3 仅在 PC 发 `'R'` 时产生流量，feat 写每 2.752 s 一次（66 条命令），带宽影响 <0.01%。`'L'` 锁窗仅在诊断时使用，默认不激活。

## 4. 离线验证（PDS 之前必须全部通过）

1. **读回格式**：仿真中先由 audio_sink 写入已知 PCM（`audio_chain_full` 已有确定性 pattern），再用 `'R'` 等价逻辑读同一地址区间，PC 端与写入序列**逐字节 0 失配**；同时验证窗口编号 → 地址映射（`win_id[0]` 与 `0x0/0x42000`）。
2. **feat 落 DDR**：mel_48k/`mel_credit` 已证 mel 输出与 golden 0 失配；新增「feat 写 DDR 后读回」比对 golden_feat.hex **0 失配**。
3. **logits**：`npu_probe` 已证生产源逐层 0 LSB；验证 `logits_bus` 引出后 8 路 int32 与 `fc2_u8 - 58` 一致（已修 `npu_top` 的 `-57` 硬编码 → `FC2_LOGIT_BIAS` 参数）。
4. **PC 导出脚本**：`scripts/diag_dump.py` 实现 `'L'`/`'R'`/`'S'`/`'U'`，按 win_id 命名落盘（`build/diag/<label>/win<n>/{pcm.raw,feat.bin,logits.json,meta.json}`），并对增量窗口做 hash 比对确认「窗口被正确锁定、未被覆盖」。

## 5. 上板实验矩阵（一次烧录）

同一位流依次执行（每组：播放 → 等待窗口完成 → `'L'` 锁定 → `'R'` 导出 PCM/feat/logits → `'U'`）：

| 组 | 输入 | 期望 |
|---|---|---|
| G0 | 静音（不播放） | PCM ≈ 0；feat ≈ 常数；logits 一组值 |
| G1 | 200 Hz 满幅 | PCM 200 Hz；feat 随输入变化；logits 与 golden(200Hz) 一致 |
| G2 | 6 kHz 满幅 | 同上，且与 G1 **明显不同** |
| G3 | 已知类别音乐片段 | top1 与类别一致 |

判读：PC 端对**实际读回的 PCM** 计算 golden（`golden_pipeline` 48k 表 + 新契约），逐段比较 `PCM → feat → logits`，**第一个出现偏差的环节即为缺陷位置**（若 PCM 对而 feat 错 → mel；feat 对而 logits 错 → NPU；PCM 错 → audio_sink/窗口映射）。

## 6. 纪律

- 不叠加推测性修复：DDR3 `S_R` watchdog 改动已按本方针**回退**（板级 `mel_busy/win_miss=0` 未支持该假设），待离线/读回证据坐实后再修。
- 一次构建即包含全部诊断接口 + 资源裁剪；不再「加几位 STS 就重建」。
- 构建前完成第 4 节全部离线验证与资源估算；构建失败时按有界策略（90 min）记录未布数，不无限延长。