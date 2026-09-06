# GPLL变频与时钟一致性

## 原厂依据与实现

保留板卡D18的27 MHz参考时钟，不改引脚、不用普通逻辑产生高频时钟。接口核对自 MES2L676-200HP 配套资料的 `2_5_pll_test`，以及本机PDS的 `arch/vendor/pango/verilog/simulation/GTP_GPLL.v`、`ip/module_ip/ipm2l_flex_pll/ipm2l_flex_pll_eval/ipm2l_pll/UG041001_PLL_IP.pdf` 和同目录 `createDivideParam.tcl`。仅新写原语实例连接，没有把原厂受限源文件复制到仓库。

`fpga/rv32_pll.sv` 使用内部 CLKOUTF 反馈、输入除数1、反馈乘数2，频率关系为 VCO=27×2×反馈输出除数，CPU=VCO/输出除数。原厂GPLL配置算法的VCO区间为600–1200 MHz，下表全部在范围内。

| CPU MHz | VCO MHz | CLKOUTF除数 | CLKOUT0除数 | 当前证据 |
| --- | --- | --- | --- | --- |
| 27 | 不使用PLL | — | — | 已有实板基线 |
| 54 | 1080 | 20 | 20 | 原厂模型、PDS、实板自检与长时CoreMark |
| 60 | 1080 | 20 | 18 | 原厂模型测试通过，尚未硬件验收 |
| 67.5 | 1080 | 20 | 16 | 原厂模型测试通过，尚未硬件验收 |
| 72 | 1080 | 20 | 15 | 原厂模型测试通过，尚未硬件验收 |
| 75.6 | 756 | 14 | 10 | 原厂模型和PDS通过，尚未上板 |
| 81 | 972 | 18 | 12 | PDS、性能种子两次、验证种子一次长时通过 |
| 90 | 1080 | 20 | 12 | PDS、性能种子两次、验证种子一次长时通过 |
| 99 | 1188 | 22 | 12 | 原厂模型和PDS通过，尚未上板 |
| 102.6 | 1026 | 19 | 10 | 原厂模型通过，候选频点，尚未上板 |
| 108 | 1080 | 20 | 10 | 原厂模型、PDS、性能种子两次和验证种子一次长时通过 |
| 135 | 1080 | 20 | 8 | 原厂模型、PDS通过；未上板 |
| 162 | 972 | 18 | 6 | 原厂模型、PDS通过；实板记录见 HARDWARE_FREQUENCY.md |
| 180 | 1080 | 20 | 6 | 原厂模型通过；默认CPU时序失败，load前递实验时序通过，未上板 |
| 194.4 | 972 | 18 | 5 | 原厂模型通过；PDS结果见 PDS_FREQUENCY_REFINEMENT.md，未上板 |
| 216 | 1080 | 20 | 5 | 原厂模型通过；CPU时序失败，未上板 |
| 270 | 1080 | 20 | 4 | 原厂模型通过；CPU时序失败，未上板 |

高频搜索的成功与失败实现均保留，见 `PDS_FREQUENCY_SEARCH.md`。216/270 MHz仍属于可复现的实验配置，不是允许忽略时序门槛的交付位流。

默认27 MHz仍直接使用板载时钟；其余配置通过PLL，PLL未锁定时保持CPU复位。外部复位也复位PLL；锁定释放后由原有两级复位链同步释放CPU。此版本只在构建时选择频率，不支持CPU运行中动态改频。

## 三处必须一致

1. 硬件：`run_pds.ps1 -ClockHz` 控制PLL配置，并经板级参数传入SoC的UART分频器。
2. 固件：`build_coremark.ps1 -ClockHz` 定义 CPU_CLOCK_HZ，用于周期到毫秒换算及UART报告；非默认频率进入文件名，避免覆盖旧基线。
3. 验证：`check_coremark.py --clock-hz` 显式指定预期频率，默认仍27000000；同时验证周期、毫秒、整数秒和十秒门槛。

指定固件若有 `.build.json`，PDS入口必须校验频率和镜像SHA；非默认频率缺少manifest直接拒绝。已经负向验证：54 MHz固件不能以默认27 MHz硬件构建。时序门槛除 All Constraints Met 外，还检查唯一生成CPU时钟的周期与有效同步负载，防止只约束输入27 MHz却遗漏内部倍频域。

## 验证命令

在仓库根目录、PowerShell7运行：

```powershell
pwsh -NoProfile -File cpu/scripts/run_pll_tests.ps1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ClockHz 54000000
pwsh -NoProfile -File cpu/scripts/build_coremark.ps1 -ClockHz 54000000 -Iterations 400 -ConsoleDelayCycles 800000
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -ClockHz 54000000 -UartProfile RemoteLab -FirmwareHex cpu/build/coremark_v0_i400_p800000_f54000000_rv32gcc.hex
```

PLL测试直接加载已安装PDS的原始模型，对十六个PLL频点分别检查200个输出周期的跨度、复位清锁和重新锁定；所有频点通过。测试平台先制造真实复位边沿：初版从时刻0持续置复位曾使该模型在Icarus里陷入零时间事件循环；没有改动模型，改为1 ns后拉高复位后测试正常。执行超时会明确失败，不用简化行为模型冒充原厂验证。日志 `build/pll-tests.log`。

54 MHz固件短仿真CRC通过，2733391周期、752500条退休指令；换算50毫秒，明确不计分。CoreMark testbench为加速UART仍用独立的100 MHz仿真时基和3200/100的UART模型参数，不能把这项称为54 MHz物理时钟仿真。物理时钟功能来自独立PLL原厂模型测试和实板，计时软件来自短仿真及实板报告。

## 已验证的实板频点

54、81、90、108、162 MHz结果见 `HARDWARE_FREQUENCY.md`，当前最高已实测频点为162 MHz，完整数据见 `HARDWARE_162MHZ.md`。PDS估计最高频率、PLL模型可生成频率和实际板卡通过频率是三类不同证据；这不代表找到了绝对最高频率或完成长期稳定性测试。板载27 MHz及其倍频为标称频率，尚未由独立频率计测量晶振误差。

SCBV、参考板与远程板的证据区别，以及异步I/O约束范围见 `CONFIGURATION_ASSURANCE.md`；内部时序通过不能替代配置电压和全部外部时序审核。
