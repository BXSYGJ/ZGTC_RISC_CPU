# 编译式RTL长测入口

日期：2026-09-06。该入口运行实际SoC RTL，不是指令级模拟器，也不替代实板、PDS或官方认证。

## 目的与边界

新增scripts/run_coremark_compiled.ps1、scripts/run_coremark_compiled.py和sim/coremark_compiled.cpp，使用本地Verilator 4.038编译RTL，按真实时钟沿驱动复位、UART输入G和输出位采样。保留CPU/Cache/总线/外设的逐拍行为，不跳过算法、串口延迟或停顿；固件通过原INIT_FILE加载，不注入计算结果。配置来自既有CoreMark运行清单或PDS实现清单。

编译使用独立build/compiled/<ID>目录，保存RTL、驱动、解析器与运行器快照，固件、可执行程序及UART/结果哈希。输入不从coremark-latest.json猜测，也不覆盖历史硬件记录。新的PDS清单绑定检查核对实际RTL快照、固件字节和时钟；没有PDS快照的短仿真配置明确记录ImplementationInputsBound=false。此检查不是PDS时序检查，仍需原硬件门槛工具。

新UART文件以ZGTC RTL_SIMULATION_ONLY标记；硬件read_case入口遇到该标记直接拒绝，check_performance_target.py不能将它作为实测证据。模拟结果保存measurement_kind=rtl_simulation_not_hardware、modeled_duration_at_least_10s，不输出iterations_per_second系列分数字段。删除标记的伪造不在自动工具可证明的来源边界内，必须保留原始采集证据。

## 运行示例

在PowerShell 7调用cpu/scripts/run_coremark_compiled.ps1，显式传入-ConfigurationManifest与-FirmwareManifest；后者必须为实际.hex旁的.build.json。-MaxCycles是整个模拟过程的周期上限，包含启动、串口逐字符延迟与输出，不仅是计分区。短跑必须显式-AllowShort；默认不足10秒拒绝。路径由PowerShell原生转换后作为独立参数交给WSL Python，不使用Bash拼接命令。

## 交叉验证

I8 KiB/D2 KiB、256项BTB、RV32IM、O3-unroll-relax配置，用与Icarus相同的固件逐字段核对周期、退休数、CRC、配置和全部缓存统计；四项均完全一致。

| 种子 | 迭代 | 周期 | 编译式运行ID |
| --- | ---: | ---: | --- |
| performance | 1 | 335421 | 20260906-211213-810accf5 |
| validation | 1 | 335557 | 20260906-211256-432e4ebe |
| performance | 10 | 3326116 | 20260906-211304-8a88b523 |
| validation | 10 | 3329203 | 20260906-211312-d0ab9802 |

增加UART来源标记及输入快照检查后，性能10轮重跑20260906-211808-a2c438bf仍与Icarus完全一致。后来加入的PDS输入绑定需按对应运行器快照区分，不能追认已启动旧运行器执行了新代码。

## 负向测试

test_coremark_compiled.py目前8项方法，含全部开关类型/范围、容量继承/旁路、固件哈希与格式、M配置、种子/迭代/时钟、模拟成绩去除、硬件证据拒绝、输入与可执行程序变异及PDS输入绑定。test_coremark_compiled_harness.py用临时替身模型编译实际C++驱动，检查合法G发送与UART解码、八种错误状态及六类错误参数；替身只证明驱动的错误处理，不冒充真实RTL功能覆盖。两组终态通过。

Verilator 4.038对非空INIT_FILE与空串比较产生WIDTH警告。没有更改RTL来压制它，也没有放过全部warning：编译保留全部警告，运行前逐条检查，仅接受rv32_burst_ram.sv中确切INIT_FILE比较行对应的NEQ字符串宽度告警；其他位置/类型/运算符均拒绝。存在对应负向测试。

## 最终集成检查

validate-compiled-hardware-final.log已终态通过，包括既有单元/CPU/参考轨迹/内存比对、严格lint、非对称容量集成及编译式证据守卫。C++驱动替身测试的validate调用在该进程启动后才加入，因此另行执行该测试并终态通过，不声称旧进程执行了后加的调用。最终定向检查为8项编译式守卫、3项驱动方法（含多个反例）、26项硬件比较、17项CoreMark解析及7项性能门槛测试，均通过；新增PowerShell入口及validate语法和UTF8 BOM检查通过。

## 4000轮模拟超时记录

性能20260906-211900-96090de1与验证20260906-211922-9fdcf2d0均在1800000000总周期上限处终止：已进入结果串口输出，但还没有完整CRC/FINISHED，不能算成功。固件为实际板测使用的ConsoleDelayCycles=2400000版本，每字符等待也必须逐拍模拟。原日志、固件和失败状态保留，没有删除保护、裁掉延迟或从半截结果拼出成绩。

如需重跑同镜像，必须使用足以覆盖启动、计分与全部串口输出的更大-MaxCycles；目前没有自动重跑。远程实板随后可直接完成该镜像的长测，其证据独立记录，不将实板成功改写成这两次仿真通过。
