# inject-window-20261115 — 串口注入位流（绕开模拟回环）

**一句话**：这版位流让主机通过 UART 直接把一整个 132096 样本 PCM 窗口写进
DDR3（PCM 窗口 A，`0x000000`），再触发一次 mel→standardize→量化→NPU，
完全不经过 `DAC → 3.5 mm → PCM1808 → I2S` 这条模拟链。

## 为什么需要

`DAC → 3.5 mm → PCM1808` 这一段在本台架上反复出问题：端点静音、间歇掉线、
松线导致频率减半、几分钟后整条链静音。之前所有「上板准确率」数字
（IRMAS 5/18、demo 1/8）都被这条链污染，不能用来评判 FPGA 或模型。
注入通路把变量减到零：送进去的是什么，板子算的就是什么。

## 位流

- 文件：`artifacts/instrec_top_inject.sbit`
- SHA-256：`07de58cd716bd1dea8c6c5d77b5cb18fe07c017b032b45852f95be400a84316f`
- 构建集：`full`（top `instrec_top`），`run_pds_full.ps1 -BuildSet full -PlacementSeed 7`
- 构建目录：`build/pds/20261115-134647-30d968c5`（不入库）
- 六阶段全 OK，`Unrouted 0`，总耗时 50m29s，PnR 33m06s
- 时序：`ddrphy_sysclk` WNS −1.576 ns / WHS +0.110 ns（`clk`、`pix_clk` 收敛）

## 时序说明（照实记录）

这版比 seed85 交付版（WNS −0.809）差，因为多了注入逻辑且落在另一个布局上。
**用途是功能验证与调试，不是时序最优交付基线**；时序最优交付仍以
`releases/seed85-timing-20261114/` 为准。

## 新增 diag 命令

| 命令 | 作用 |
|---|---|
| `I` | 进入注入模式：`weight_loader` 的写入基址从 `0x100000` 切到 `0x000000` |
| `X` | 退出注入模式 |
| `T` | 触发一次 mel（读窗口 A），随后 NPU 自动跑 |
| `L`/`U` | 冻结/恢复 audio_sink 写入（注入期间必须 `L`，防止数据被覆盖） |

`weight_loader` 只加了一个 `inject_sel` 输入 + 基址 mux，以及 `img_done`
懒惰清零（允许同一上电周期连续上传：权重 → PCM 窗口），
没有复制第二份 loader——复制整个 loader 会把设计推回 `Route-0008`。

## 使用方法

```powershell
# 1. 烧录
python scripts/flash_bitstream.py --sbit releases/inject-window-20261115/artifacts/instrec_top_inject.sbit

# 2. 上传 48k 权重（注入模式下权重仍在 0x100000，不受影响）
python scripts/board_e2e.py --stage weights --skip-boot-upload --image scripts/outputs/medley_48k/weights_image.bin

# 3. 注入一条音频并和 golden 逐位对比
python scripts/inject_audio.py --wav <任意wav> --golden
```

流程：`U` 解锁 → `L` 冻结音频写入 → `I` 注入模式 →
1032 帧 × 256 B（264192 B，约 26 s，CRC/ACK 与权重上传同协议）→
`X` → `T` 触发 → `G` 读 logits。`--golden` 会用参考实现算同一窗口。

## 上板验证（2026-11-15）

模型自带 8 类 demo，每条注入后板级 logits 与 golden **8 通道逐位相同**：

| 片段 | 真值 | 板级 top1 | 结果 |
|---|---|---|---|
| clarinet | 0 | 0 | OK |
| distorted electric guitar | 1 | 1 | OK |
| female singer | 2 | 2 | OK |
| flute | 3 | 0 | MISS（golden 同样判 0，模型自身误差） |
| piano | 4 | 4 | OK |
| tenor saxophone | 5 | 5 | OK |
| trumpet | 6 | 6 | OK |
| violin | 7 | 7 | OK |

**板级准确率 7/8 = 87.5%，板级 == golden 8/8。**
连续 8 次注入全部 0 重传、25.6–25.9 s/条，证明「权重→注入」的
连续上传路径（frame_cnt 懒惰清零修复）稳定工作。

⇒ 结论：FPGA 数字链（mel / standardize / 量化 / NPU）与参考实现等价，
此前所有准确率失真均来自模拟回环，与 FPGA 无关。

## 复现

```powershell
pwsh -NoProfile -File scripts/run_pds_full.ps1 -BuildSet full -PlacementSeed 7
```
