# 125 MHz RTOS仿真

在`instrec_fpga`目录运行。默认后端直接调用Ubuntu-22.04中的Verilator 5.040，通过`wsl.exe --exec`执行工具。`--backend iverilog`使用Windows原生Icarus，适合短用例；完整CPU任务测试用Verilator运行更快。

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $baselineRunner = [System.IO.Path]::Combine((Get-Location).Path, 'rtos', 'sim', 'run_baseline.py')
    $rtosRunner = [System.IO.Path]::Combine((Get-Location).Path, 'rtos', 'sim', 'run_rtos_test.py')
    python -X utf8 $baselineRunner --label baseline125
    if ($LASTEXITCODE -ne 0) { throw '125 MHz baseline failed' }
    python -X utf8 $rtosRunner --label rtos125 --progress
    if ($LASTEXITCODE -ne 0) { throw 'FreeRTOS CPU validation failed' }
} catch {
    Write-Error $_
    exit 1
}
```

`run_baseline.py`执行`rtos/baseline125`中的原始ROM、原始8 KiB存储封装和八份PaceRV执行核心。它检查原固件启动、IMC和共享DDR自检、运算结果，以及NPU结果接收、清除和下一次启动。原固件的周期和退休指令数由运行结果记录，回退测试可以逐项比较。

`run_rtos_test.py`执行测试版FreeRTOS固件、16 KiB ROM、16 KiB RAM和实际机器定时器。时钟周期固定8 ns；内核、任务、寄存器上下文切换、本地存储和MMIO均在真实RTL中执行。测试覆盖：

- 1 kHz机器定时器中断、ECALL调度、`mret`返回和固定125000周期的比较值增量。
- 嵌套临界区跨过多个tick；中断屏蔽、恢复和积压tick补处理由固件断言与硬件观测共同核验。
- 两个同优先级、循环中没有主动让出的寄存器检查任务，确认时钟抢占后两者均持续前进。
- FreeRTOS消息队列传递、空队列等待超时，以及完整NPU窗口的结果发布。
- CPU发起的正常推理、加速器超时和恢复后的推理；两个结果采用不同top1、末通道和概率值。事件后的实时计数器改变，软件仍需上报事件捕获时的周期数。
- 共享DDR请求反压、延迟响应、读回和串口反压。

此处NPU和DDR是事务级外围模型；完整原生NPU与golden的验证由另外的整机用例提供。

每次运行先冻结输入，再在`build/rtos/sim/<标签>-<时间>/`写入`RESULT.json`、`VERIFICATION.txt`和逐命令日志，记录实际命令、输入SHA-256、字面输出及退出状态。源固件后续重编译会生成新内容，已冻结运行的输入保持独立。

RTOS封装通过`PROG_HEX`直接初始化数据ROM，通过`PROG_EVEN_HEX`和`PROG_ODD_HEX`分别初始化两个取指bank。压力测试会核对并冻结`prog.hex`、`prog_even.hex`和`prog_odd.hex`，再检查全部4096个实际ROM字的一致性。自定义固件可用`--firmware`及可选的`--firmware-even`、`--firmware-odd`指定这三个文件。

定时器和中断测试的自定义镜像由`rom_banks.py`按`$readmemh`字地址拆分；`@地址`、注释和换行均按格式解析。IRQ和ROM边界用例使用含奇数字地址`@`指令的镜像，并检查全部8192个字的bank重建结果；对应报告同时保存冻结镜像和RTL的SHA-256。

回退副本可通过`run_baseline.py --source-dir <恢复后的目录> --label rollback125`验证；该目录应包含原来的`src/cpu`布局。此命令读取副本并产生新的仿真证据。
