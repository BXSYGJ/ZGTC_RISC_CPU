# 无MMIO外设对照实验

本目录不替换已经通过的完整外设工程。rv32_soc.sv移除UART、GPIO、外设定时器、中断控制及性能快照MMIO；保留CPU的mcycle/minstret、缓存、主存和不存在地址的错误响应。编译测试刻意不提供rv32_peripherals.sv与rv32_uart.sv，运行期间出现任意MMIO请求均判失败。

CoreMark算法源码按upstream-lock.json逐文件验证固定提交。专用移植层自动启动，不等待UART命令。结果进入普通RAM中的benchmark_result；使用本核心fence.i实现的缓存维护路径，先写回文本和计数，再写完成状态并再次维护，测试台读取实际主存而非伪造UART。普通fence只保证访存顺序，不能当作强制写回脏缓存指令。所有结果写回在计时结束后。

run_bare_coremark.ps1默认执行性能种子10次；-ValidationRun选择验证种子。此入口仅做短程正确性，不具备正式计分资格。随后用verify_bare_result.py审计生成目录，验证CRC、计数、时间换算、源文件和固件哈希。算法输出中不足10秒的提示必须保留，不能把该短测当成正式成绩。

待完成：双种子短测、外设缺席/非法MMIO回归、完整时长性能、PDS物理实现、无UART结果实板回读方式及同配置三指标报告。正式比较不得直接沿用完整外设版的执行周期，也不得将删除外围模块的理论LUT差额当作布局布线结果。

无外设版的物理顶层必须保留并实际观察CPU与存储系统，例如通过明确计入资源的最小调试观察逻辑。不能将所有输出接常数后接受综合器删除处理器所得的虚假低资源结果；必须核对原生网表内完整CPU、寄存器堆、缓存及主存仍在。现有仿真顶层尚不是通过验收的板级物理顶层。

详细口径见docs/PERIPHERAL_VARIANT_MEASUREMENT.md。

## 2026-09-09 频率与构建绑定纠错

144 MHz 的 PDS 构建 `20260909-194559-786ec275` 通过时序（7756 LUT，WNS +0.105 ns），但没有本构建的完整运行结果，不是新跑分版本。此前将 157.5 MHz 仿真的 501.143188 CoreMark 与这个构建配对的计算已撤回；降低频率也不满足用户的优化非退化约束。

`run_bare_coremark.ps1` 自动生成 `coremark.build.json`，同时将 `ClockHz` 传给编译器和 Icarus 顶层。`run_bare_compiled.ps1` 把相同频率传给 Verilator 顶层并记录元数据。

`run_bare_pds.ps1` 现在必须显式指定 `-BuildName <构建目录名>`，不再按最近修改时间选择固件。它从该构建复制经过哈希检查的 RTL，禁止混入其他实验的核心；`-ClockHz` 必须与固件和编译选项一致。低于 157.5 MHz 的物理实验会被标记为频率退化，不会自动取得优化资格。

`qualify_bare_pair.py <固件构建目录> <PDS结果目录>` 在同频率、同固件、同 RTL、真实 PDS 报告与完整 CRC 运行都匹配后，才计算本地 RTL/PDS 投影。公式为 `CoreMark = iterations * clock_hz / cycles`、`CoreMark/MHz = iterations * 1000000 / cycles`、`CoreMark/LUT = CoreMark / post_route_luts`；它仍不会把本地投影标为实板成绩。`test_metric_binding.py` 包含拒绝真实跨频率构建配对的回归。
