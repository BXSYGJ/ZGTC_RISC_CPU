# PaceRV CPU + NPU 八类音频识别 · 固定源码版

版本：`2026-11-03-afternoon`；基准提交：`0c138d4f`（2026-11-03 17:23）。本目录作为后续技术报告的唯一源码基准，保持固定，不跟随主线五类迁移或演示修改。

## 功能组成

| 功能 | 源码位置 |
|---|---|
| PCM1808 I2S从接收、48→44.1 kHz双声道重采样、跨时钟FIFO | `src/audio/` |
| PCM缓冲、权重及激活访问、DDR3仲裁 | `src/audio/audio_sink.v`、`src/ddr3/` |
| 2048点FFT、64带Mel、dB与整窗标准化、64×258特征量化 | `src/mel/` |
| 共享16路卷积、池化、GAP、FC、重标定、八类softmax | `src/npu/` |
| RV32I控制核、8 KiB ROM / 8 KiB RAM、MMIO请求与结果回读 | `src/cpu/`、`sw/rv32/` |
| 中文识别结果、八类置信度、输入波形、Mel频谱 | `src/ui/`、`src/hdmi/` |
| 系统启动、DDR自检、UART权重加载与运行日志 | `src/ctrl/` |

顶层：`src/ctrl/instrec_top.v`，器件：`PG2L100H-6IFBG676`，开发板：盘古100Pro+。八类顺序为单簧管、失真电吉他、女声、长笛、钢琴、次中音萨克斯、小号、小提琴。CPU运行C固件，真实NPU执行推理。

## 目录与使用

保留源代码、原厂IP、约束、ROM、固件、权重与必要工具；没有过程文档、测试台、旧顶层、五类模型或预设置信度曲线。`SOURCE_LOCK.json`记录原始来源、清理映射及该版本的实际验证数据；`SHA256SUMS`校验定版文件。原厂IP及许可证保持原字节，清理不改变应用代码token与综合指令。

在本目录执行：

```powershell
python scripts/verify_release.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1
```

需PDS 2022.2-SP6.4和有效许可证，以环境变量`PDS_ROOT`、`PANGO_LICENSE_FILE`配置。一次只运行一条PDS构建。已经包含固件ROM；需要重编固件时，配置`RV32_TOOLCHAIN`后执行：

```powershell
python scripts/build_rv32_sw.py --no-m
```

`artifacts/instrec_top.sbit`是下午该版原始位流，SHA-256前缀`1497FAF4`。CPU程序及所有ROM已嵌入位流，八类权重仍经串口装载。KEY0复位后需要重新装载权重：

```powershell
python scripts/board_check.py --sbit artifacts/instrec_top.sbit --port COM5 --seconds 15 --expect "RV32 BOOT" "RV32 MMIO OK" "RV32 ISA OK" "DDROK"
python scripts/weight_upload.py --port COM5
```

UART工具需要`pyserial`。本版PCM1808在48 kHz主机模式输出BCK、LRCK、DATA；对应紫卡J2针11、12、20（FPGA U20、T20、V16），另接公共GND。FPGA三线均为输入，音频接收及FIR工作在27 MHz域，模型计算域为125 MHz。不要混用早期由FPGA输出BCK/LRCK的位流。

定版功能按上述源码范围组织技术报告；实测性能与验证结论引用`SOURCE_LOCK.json`和`VALIDATION.json`，不由“功能定版”推导准确率或时序指标。
