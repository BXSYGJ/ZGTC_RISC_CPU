# 125 MHz InstRec + FreeRTOS

本配置以原始 `full-20261113-223256-full` 整机为基线，加入真实的 FreeRTOS 抢占调度。系统时钟125 MHz，节拍1 kHz，程序ROM和数据RAM均为16 KiB。原125 MHz位流和202份输入保留，RTOS工程通过独立构建入口使用其冻结副本。

FreeRTOS-Kernel固定为官方V11.3.3、提交`89592801dd8b73329a7583719b7e3567b50910e5`。`vendor/FreeRTOS-Kernel/PROVENANCE.json`记录37份原始文件哈希；内核源码按MIT许可证保留。机器态移植层位于`sw/port.c`、`sw/portASM.S`及`sw/portmacro.h`，PaceRV H3执行核心保持原值。

## 应用任务

| 任务 | 优先级 | 行为 |
|---|---:|---|
| recognition | 3 | 每1 ms观察NPU，复制完整结果并通过队列发布，清除已处理状态，申请下一个安全mel窗口 |
| result_uart | 2 | 阻塞接收静态结果队列，独占UART输出，记录真实top1、末通道、分数、周期、序号和节拍 |
| heartbeat | 1 | 每100 ms发布运行状态 |
| idle | 0 | FreeRTOS空闲任务 |

硬件继续执行音频、mel、原八类NPU、原生M1仲裁、共享DDR和HDMI。RTOS接入沿用XSY的125 MHz整机及CPU结果快照接口，同时复用XSY2的原生NPU所有权和安全窗口启动协议；实际分支提交、文件哈希及共同资产比较见`evidence/BRANCH_REUSE.json`。两分支的五组模型已保留在项目原目录；本RTOS配置对应125 MHz现有八类加速器。

结果处理要求`DONE`和`PROBS`同时有效且NPU空闲，所有字段先复制后ACK，队列中的消息随下一次硬件结果更新仍保持原值。超时事件进入同一结果队列。内核、任务栈和队列采用静态分配。

## 定时器与上下文

| MMIO地址 | 含义 |
|---|---|
| `0x80000030` / `0x80000034` | 64位mtime低/高字 |
| `0x80000038` / `0x8000003c` | 64位mtimecmp低/高字 |

mtime每个系统时钟增加1，mtimecmp复位全1，`mtime >= mtimecmp`产生机器定时中断。RV32重装按高字全1、低字、最终高字的顺序写入，避免瞬态比较。节拍间隔固定125000周期，后续截止时间基于前一次截止时间递增。

陷阱上下文为144字节、16字节对齐，保存通用寄存器、mepc、mstatus及任务临界区嵌套计数；内核中断处理使用独立1 KiB栈。机器ECALL请求调度，机器定时中断推进节拍并触发抢占，mret恢复选中任务。

## 构建与验证

以下命令在仓库根目录运行。固件使用已安装的Windows LLVM22.1.8；可通过`--llvm-bin`指定LLVM目录，或`--gcc-prefix`指定原生RISC-V GCC。固件构建会核验内核哈希、链接空间和镜像长度。

```powershell
python -X utf8 instrec_fpga/rtos/build_firmware.py
python -X utf8 instrec_fpga/rtos/build_firmware.py --test
python -X utf8 instrec_fpga/rtos/sim/run_timer_test.py
python -X utf8 instrec_fpga/rtos/sim/run_irq_precision.py
python -X utf8 instrec_fpga/rtos/sim/run_rtos_test.py
python -X utf8 instrec_fpga/rtos/sim/run_native_rtos.py --run-label review --firmware rtos
python -X utf8 instrec_fpga/rtos/build_system.py --stage prepare
```

`build_system.py --stage map`执行实际整机编译、综合和器件映射；`--stage full`沿用125 MHz基线的布局种子2及实现参数，生成完整位流。每轮输入、命令、结果和日志独立保存在`build/rtos/pds/`。构建入口核验生产固件与其源码/二进制一致，并拒绝将测试固件作为板端正式应用。

## 已核验与后续记录

正式固件ROM7148字节、BSS5600字节；测试固件ROM8876字节、BSS8480字节，均在16 KiB ROM/RAM范围内。

完整原生NPU联合仿真已得到真实串口输出：

```text
RTOS NPU top1=0 last_class=7 last_p=0 c=31152090 seq=1 tick=250
RTOS_NATIVE scheduling timer_irqs=250 yield_traps=259 heartbeats_while_busy=2
RESULT: PASS production FreeRTOS tasks, full native golden NPU, immutable queue result report and acknowledgement
```

卷积、池化、GAP、FC及概率逐项对照既有固定点golden。DDR读写走实际CPU桥和M3共享RTL；DDR存储器使用仿真模型。硬件定时器、上下文切换和FreeRTOS任务均由真实指令执行。定时器及MMIO已完成21+66项检查；补充精确中断测试覆盖DDR等待期间到期、半字PC恢复、CSR及ROM边界。

最终CPU压力测试已验证真实节拍和任务抢占、队列及寄存器上下文。嵌套两层临界区跨过3个硬件截止时间时中断保持屏蔽，退出后准确补齐3次节拍；17次比较寄存器重装均按125000周期递增。原125 MHz版本及回退副本的启动、自检、NPU结果输出和ACK逐项一致。

整机编译、综合和器件映射已完成，128.5/155 DRM，冻结输入核验一致；完整实现从该映射结果继续。位流及板级结果以`evidence/`和`VERIFICATION.txt`的实测更新为准。

## 回退

`ROLLBACK.ps1`将隔离工程的202份输入恢复到原125 MHz冻结字节，并移除新增定时器。参数必须指向`instrec_fpga/build/rtos/`中的工程副本；当前RTOS源码和原始位流包保持原值。`ROLLBACK.sh`保存相同PowerShell7内容供执行属性归档，Windows使用`.ps1`入口。

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $rollback = [System.IO.Path]::Combine((Get-Location).Path, 'instrec_fpga', 'rtos', 'ROLLBACK.ps1')
    $copy = [System.IO.Path]::Combine((Get-Location).Path, 'instrec_fpga', 'build', 'rtos', 'rollback_copy')
    & $rollback -Workspace $copy
    if ($LASTEXITCODE -ne 0) { throw 'Rollback failed' }
} catch {
    Write-Error $_
    exit 1
}
```
