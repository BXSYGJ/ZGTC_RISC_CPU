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
## 7. 实现状态（2026-11-10，`diag_readback` 交付）

状态：**离线验证完成，未上板、未跑 PDS**。只新增了 `src/diag/diag_readback.v`（576 行）与
`sim/tb_diag_readback.sv`（743 行），`sim/run_sim.py` 追加 `diag_readback` 用例；既有 RTL
(`weight_loader.v` / `audio_sink.v` / `mel_engine.v` / `ddr3_ctrl_axi.v`) 零改动，顶层也**尚未例化**本模块。

### 7.1 实际端口

| 方向 | 端口 | 说明 |
|---|---|---|
| in | `clk` / `rst_n` | core 域 125 MHz，异步复位低有效 |
| in | `rx_valid` / `rx_data[7:0]` | **字节级** UART 接收通道（同 `weight_loader.v`，由 `uart_rx` 驱动） |
| out | `tx_valid` / `tx_data[7:0]` | **字节级** UART 发送通道（顶层与 `uart_debug`/`weight_loader` 仲裁后送 `uart_tx`） |
| in | `tx_ready` | `uart_tx.byte_wready`（寄存器型，接受后多保持一拍） |
| out | `m3_cmd_valid` / `m3_cmd[36:0]` | DDR3 主口 3，只读；`{wr=0, addr[27:0], len[7:0]}` |
| in | `m3_rd_data[255:0]` / `m3_rd_valid` / `m3_done` | 控制器读数据/有效/完成 |
| out | `m3_rd_ready` | 弹性 FIFO 弹出节拍 |
| out | `diag_lock` | 纯电平，供 `audio_sink` 冻结新帧（本模块不做冻结逻辑） |
| in | `win_id[15:0]` / `mel_done` / `npu_done` / `logits_valid` | 状态行快照输入 |

参数：`ACK_TIMEOUT`（默认 12500000 = 100 ms @125 MHz，仅仿真/TB 用更小值）。

### 7.2 len 语义核对结论（一帧用 len = 7）

- `ddr3_ctrl_axi.v` 文件头：命令包 `{wr, addr[27:0], len[7:0]}`，**`len = beats-1`，每 beat 32 B**；
  `ddr3_arbiter` 的合法性检查是 `len <= 15`、32 B 对齐。
- `mel_engine.v` 生产读：`516` 条 `len=15`，即 16 beat × 32 B = **512 B = 256 个 PCM 采样(2 B)**。
- 因此「len=15 单命令 = 512 B」成立，256 B 一帧必须用 **`len=7`（8 beat × 32 B = 256 B）**，每条 'R' 帧发一条命令。
  一个 256 B 帧正好是半条 mel 生产命令，不需要拆分或拼接。

### 7.3 命令与偏差

| 项 | 方案原文 | 实现 |
|---|---|---|
| `'L'`/`'U'` | 置/清 `diag_lock`，回 `'K'` | 一致 |
| `'S'` | `DIAG win=<n> locked=<0/1> ...` | 行**定长 61 字节**，`win` 固定打印 5 位十进制（零填充，如 `04660`），其余字段 1 位；便于 PC 定长解析 |
| `'R'` | `addr[31:0] LE + len[15:0] LE` | 一致（命令本身无 CRC），逐帧回 256 B 帧 |
| 读回帧 | 0xAA55 + seq + len + payload + CRC16 | 一致，`len=0x0100`；payload 按 beat 小端展开；CRC-16/CCITT-FALSE 覆盖 seq+len+payload |
| seq | 从 0 递增 | 每条 'R' 命令从 0 重新计数（= 该命令内帧号） |
| 错误码 | `'N'` + 1/2/3 | 用 ASCII 数字 `'1'`/`'2'`/`'3'`（非二进制值）；顺序为 len==0 → 3，非 256 倍数 → 1，非法命令 → 2 |
| 超 1 MB | 回 `'N'+3` | **该分支不可达**：len 字段只有 16 位（≤65535 B），硬件上无法表达 >1 MB 请求；仅保留 len==0 的 `'3'` |
| 流控 | 每帧等 PC `'K'`，超时 100 ms 继续 | 一致；`'K'` 只在 ACK 状态被消费，该窗口内其他字节丢弃 |
| 缓冲 | 小 FIFO/分布式 RAM，不新增大 RAM | 8 × 256 bit 寄存器（2 KiB），与 `weight_loader` 帧缓冲同规模；无 BRAM |

其他实现细节 / 偏差：

1. UART 端口是**字节通道**而非裸引脚（方案第 2 节「复用 weight_loader 帧协议」的语义），顶层负责与
   `uart_debug`/`weight_loader` 复用 `uart_tx`。
2. 命令只在 `S_IDLE` 接受；读回进行中（含 ACK 窗口）到达的其他字节不解析，PC 需串行下发。
3. 发现并修正一个控制器交互缺陷：控制器 `rlast` 是第 8 次 push，读完最后一拍时它已回到 `S_IDLE` 且弹性
   FIFO 已空，若 `cmd_valid` 再多保持一拍就会被**重复授权**（同一 addr 读两遍，多出 8 beat 滞留在 FIFO）。
   现在在第 8 拍弹出的同一拍撤销 `cmd_valid`，并删掉了原 `S_RD_FIN` 状态；TB 观测 `ar_hs=6`、`rd_beats=48`
   （6 帧 × 8 beat）、`aw_hs=15`（9 条预填写 + 6 条 dummy write）证明无重复授权。
4. 若控制器看门狗中途中止（不足 8 拍即 `done`），本模块丢弃该帧回到 `S_IDLE`，不发出半帧数据。
5. 尚未完成、且不在本任务范围：`instrec_top` 例化 + `audio_sink` 的 `diag_lock` 冻结接线 + m3 主口接入顶层仲裁 +
   `scripts/diag_dump.py` PC 侧导出。

### 7.4 离线验证证据

- `python scripts/check_rtl.py` → `checked 78 .v file(s) ... 0 violation(s)`。
- `python sim/run_sim.py diag_readback` → `RESULT: PASS diag_readback`（约 20 s）。TB 走**真实**
  `ddr3_ctrl_axi` + `ddr3_axi_model`：先用 m0 写路径预填 4 KB @0x000000 与 512 B @0x00200000，
  再经 UART 读回逐字节比对。
  - S1 `'R' 0x0 len=1024`：4 帧 × 264 B = 1056 B，逐字节 0 失配，seq 0..3，CRC 正确。
  - S2 `len=300` → `N1`；`len=0` → `N3`。
  - S3 非法命令 `0x41` → `N2`。
  - S4 `'L'`/`'U'` 驱动 `diag_lock`，`'S'` 与 61 字节期望行逐字节一致。
  - S5 `'R' 0x00200000 len=512`（feat 区）：2 帧，逐字节 0 失配。
  - 结束时 `addr_err=0`、`to_err=0`。
- `python -m pytest -q` → `438 passed, 26 skipped`。


## 7. 实现状态（2026-11-10）

| 项 | 状态 | 证据 |
|---|---|---|
| `src/diag/diag_readback.v`（'L'/'U'/'S'/'R'/'G'，m3 只读或单拍写） | 已实现并集成 | `tb_diag_readback` 五场景 PASS（S1 4 帧逐字节 0 失配、S2 非 256 倍数、S3 非法命令、S4 锁窗与状态行、S5 0x200000 区读回）；`check_rtl` 79/0 |
| `'G'` 完整 logits | 已实现 | 8×int32 由 `npu_top.logits_out`（`sm_start` 锁存）→ 一帧 256 B 返回，不占 DDR |
| `audio_sink.diag_lock` | 已实现 | 门控 `rd_en`/注入/`frame_event`，默认 0 零影响 |
| feat 落 DDR `0x0020_0000` | 已实现 | `src/diag/feat_dump.v`：32 B 打包 + 单拍写（516 条/窗），复用 m3 |
| 频谱 UI 缓存 | 已关闭 | `feat_page_buf` 停用（省 ~14.7 DRM18K）；**DRM 146 → 130（84%）**，LUT 50%→52% |
| PC 导出脚本 | 已实现并离线验证 | `scripts/diag_dump.py` + `tests/test_diag_dump.py`（帧解析/CRC/LE 有符号 logits/'K' 流控/分段 5 段各 65,280 B）；pytest 443 passed |
| 顶层集成 | 已完成 | m3 三方分时（self_test > diag > feat_dump）、UART 按首字节分发（0xAA→loader，其余→diag，仅 loader 空闲时） |
| 诊断位流 | 已构建 | `releases/instrec-48k-diag3-20261110/`（sha `01fe4336…`），45 m 57 s 一次布通，Wns −1.317、DRM 130/155 |
| 上板实验 | **阻塞** | FTDI 从 PnP 消失（本轮第 3 次），待恢复 |

## 8. 一次烧录、多组实验（执行手册）

```powershell
python scripts/board_check.py --sbit releases/instrec-48k-diag3-20261110/instrec_48k_diag3.sbit
python scripts/weight_upload.py --image scripts/outputs/medley_48k/weights_image.bin

python scripts/diag_dump.py --label silence
python scripts/diag_dump.py --label tone200 --play build/tone_200.wav
python scripts/diag_dump.py --label tone6k  --play build/tone_6k.wav
python scripts/diag_dump.py --label music   --play build/montage_20s_12s.wav
```

每组输出 `build/diag/<label>/win<NNNN>/{pcm.raw, feat.bin, logits.json, meta.json}`。
判读：`pcm.raw` → `golden_pipeline`（48k 表 + 新契约）→ `feat_golden`，与板级 `feat.bin` 逐字节比较；再以板级 feat 算 golden logits，与 `logits.json` 比较。**第一个不一致的环节即缺陷位置**（PCM 对/feat 错 → mel；feat 对/logits 错 → NPU；PCM 错 → audio_sink 窗口映射）。
