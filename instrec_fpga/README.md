# PaceRV CPU＋NPU八类音频识别固定源码

器件：PG2L100H-6IFBG676，盘古100Pro+。源版本：2026-11-03 17:23，提交`0c138d4f`；原始完整位流hash前缀`1497faf4`。本分支保留必要源码、IP、约束、ROM、固件、模型、权重和工具，生成位流及过程日志不纳入交付。

- [中文技术报告](docs/TECHNICAL_REPORT.md)
- [模型训练与复现](training/README.md)
- [版本及原始验证信息](SOURCE_LOCK.json)

## 构建

在本目录执行，Python 3.12及PowerShell 5.1以上；PDS 2022.2-SP6.4和有效许可证通过`PDS_ROOT`、`PANGO_LICENSE_FILE`指定。一次只能运行一个PDS。

```powershell
python scripts/verify_release.py
python scripts/check_rtl.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1
```

构建清单只有`full`，顶层`src/ctrl/instrec_top.v`，CPU依赖已本地化。ROM均已提供。修改固件时配置`RV32_TOOLCHAIN`并执行：

```powershell
python scripts/build_rv32_sw.py --no-m
```

CPU使用RV32I，ROM/RAM各8 KiB。原始冻结源码已通过PDS compile；本分支整理不代表重新布局布线或生成新位流。全构建后检查`build/instrec-latest.json`中的Wns；仅产生位流不能证明时序收敛。

## 使用

PCM1808以48 kHz主机模式输出BCK/LRCK/DATA，FPGA U20/T20/V16为输入，另接公共GND。音频经147/160 FIR转换至44.1 kHz。视频输出为1080p60，界面显示波形、Mel频谱、中文类别及八类置信度。

串口工具需要`pip install pyserial`。下载时复用现有JTAG服务，不终止或重复启动cdt_js／cdt_cfg。使用自行构建的位流：

```powershell
python scripts/board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 15 --expect "RV32 BOOT" "RV32 MMIO OK" "RV32 ISA OK" "DDROK"
python scripts/weight_upload.py --port COM5
```

KEY0复位后须重新上传权重。类别顺序为单簧管、失真电吉他、女声、长笛、钢琴、次中音萨克斯、小号、小提琴。离线INT8测试准确率77.37%；原始完整位流core慢角setup WNS=-1.071ns，板级真实音源分类准确率未统计，具体测试口径见技术报告。

`SHA256SUMS`覆盖交付文件；新改动后需有意更新清单。`SOURCE_LOCK.json`保留清理前后来源，`VALIDATION.json`记录历史compile与本次整理验证。原厂IP许可证及综合指令保留。
