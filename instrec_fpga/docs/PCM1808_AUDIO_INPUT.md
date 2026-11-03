# PCM1808 外置 I2S 主机音源接入

## 已实现的接口

本版完整系统 instrec_top 改为 I2S **从接收端**。PCM1808 模块自带振荡器，输出标准 Philips I2S：48kHz LRCK、3.072MHz BCK、每声道 32 个时钟槽中的 24 位有效数据。FPGA 不再输出 BCK/LRCK。不需要接 MCK。

模块 Type-C 接 5V 电源；3.5mm 接立体声线路音源（不是裸麦克风）。数字 IO 为 3.3V。以下只适用于用户已提供的自带晶振 PCM1808 模块，其他可切主从的模块需另核对。

## MES-FMC-LPC-IO 紫卡 J2 接线

| PCM1808 | 紫卡 J2 | FPGA | 方向 |
|---|---|---|---|
| BCK | 11 / LA07_N | U20 | PCM1808 → FPGA |
| LRCK | 12 / LA07_P | T20 | PCM1808 → FPGA |
| DATA / DOUT | 20 / LA03_P | V16 | PCM1808 → FPGA |
| GND | 1、37 或 38 任一 GND | GND | 共地 |
| MCK | 不接 | — | — |
| VDD33 | 不接开发板电源 | — | 模块的 3.3V 输出 |

按排针 1 脚丝印确认奇偶列，不能凭照片左右猜针号。对应用户提供《FMC扩展卡硬件指导手册》p7。**旧 2673246E 等位流将 U20/T20 驱动为输出；新版输入位流确认烧录成功前，BCK/LRCK 先不连接。**

## 数据路径与契约

1. `i2s_slave_rx` 在 216MHz 域对三个输入分别两级同步，仅检测同步后的 BCK 上升沿，不将外部 BCK 当作 FPGA 布线时钟。LRCK=0 左、1 右；跳过 LRCK 翻转时仍属上一槽的延迟位，捕获后续 24 位中的高 16 位，低 8 位截去。
2. 只在左右都完整接收后发一次 stereo pair-valid；启动时不完整帧丢弃。完整帧缺失约 1ms 后 idle，覆盖 BCK 停止和 LRCK 卡死；恢复不需要整机复位。数据本身全零不视为时钟故障，静音沿用 audio_sink 零样本检测。
3. `pcm1808_resampler` 按 147/160 精确计数，把 48kHz 转为模型要求的 44.1kHz。每相 96 抽头低通、147 相、Q1.15 系数，左右同相；有符号乘加、round-half-even、16 位饱和。初始历史补零，滤波延迟约 1ms。
4. 每次输入最多进行 288 个 216MHz 时钟的计算，远小于一个输入帧约 4500 时钟。overrun 锁存后向现有 idle/mute 通路报告，完整帧中断后重建历史并清除。
5. 重采样后每个 pair-valid 直接写 audio_cdc_fifo，FIFO 的旧 LRCK 选相输入固定为零，避免将与输出无固定相位关系的外部 LRCK 错用为帧过滤条件。DDR/Mel/NPU 保持原采样率契约；八类和未来五类均可使用此通路。

系数用 `python scripts/gen_pcm1808_filter.py` 确定性重建。首轮完整映射中系数占 6 DRM、历史为寄存器，整机 39749 LUT、39576 FF、154.5/155 DRM、92 APM；该轮布线在 50 分钟截止时仍未完成，无新位流。当前精简源以 7104 项基表加 73 相整数校正精确重建全部 14112 项，历史改两路 128x16 同步 block RAM，以有效计数补零；联合 RTL 再次通过，实际映射资源与完整时序须以新源构建为准。

## 验证

- `python scripts/check_pcm1808.py`：生成独立整数 FIR 参考输入/输出，逐相频率响应检查，报告 `reports/pcm1808_filter_20261103.json`。
- `python sim/run_sim.py pcm1808`：真实串行引脚驱动，包含 Philips 一位延迟、24 位低位丢弃、正负满量程、随机左右声道、两轮无需 reset 的断钟恢复及逐项整数 FIR 对拍。
- `python -m pytest -q tests/test_pcm1808.py`：一秒输入严格得到 44100 对输出、双通道 DC、实际重采样后 1kHz 信号保真及 22.5kHz 混叠抑制、生成 ROM 一致性。

仿真不等于板级验收。新版必须通过完整系统资源门控，再限时 PNR 和完整 setup/hold/recovery/removal 检查；烧入后观察真实音频采样和 HDMI 波形/Mel，不能以静默补零或推理计数宣称识别准确。位流 SHA、构建结果和板测状态以 STATUS 最新条目为准。
