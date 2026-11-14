# 125 MHz InstRec + FreeRTOS

GitHub 发布分支为 [`codex/rtos125-integration`](https://github.com/BXSYGJ/ZGTC_RISC_CPU/tree/codex/rtos125-integration)。已验收的位流和完整交付 ZIP 位于 [`../releases/rtos125-20261114-175148/`](../releases/rtos125-20261114-175148/README.md)，该目录提供直接下载入口、原始 SHA256 和文件清单。

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

映射ROM的地址连线核验使用`z3-solver`，固定依赖见`requirements-verification.txt`。在执行PDS映射及完整构建前，向运行这些脚本的Python环境安装该文件中的依赖：

```powershell
python -X utf8 -m pip install -r instrec_fpga/rtos/requirements-verification.txt
```

```powershell
python -X utf8 instrec_fpga/rtos/build_firmware.py
python -X utf8 instrec_fpga/rtos/build_firmware.py --test
python -X utf8 instrec_fpga/rtos/sim/run_timer_test.py
python -X utf8 instrec_fpga/rtos/sim/run_irq_precision.py
python -X utf8 instrec_fpga/rtos/sim/run_rtos_test.py
python -X utf8 instrec_fpga/rtos/sim/run_native_rtos.py --run-label review --firmware rtos
python -X utf8 instrec_fpga/rtos/build_system.py --stage prepare
```

`build_system.py --stage map`执行实际整机编译、综合和器件映射，并检查映射后的ROM初始化；`--stage full`在ROM内容核验通过后，沿用125 MHz基线的布局种子2及实现参数生成位流。三个ROM存储体分别直接加载线性、偶字和奇字HEX文件；构建入口先核对它们与链接后二进制的一致性。每轮输入、命令、结果和日志独立保存在`build/rtos/pds/`。

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

综合审计发现，原先经临时数组复制的ROM写法使PDS生成的正常取指内容全零；失效网表和逐位证据保存在`evidence/MAPPED_ROM_AUDIT.json`，该轮布局布线已经停止。RTOS配置已改成三个实际ROM各自直接加载HEX，新整机映射使用136.5/155 DRM、36964 LUT、94 APM。全部ROM字及补零区、22位实际地址选择、8个存储实例的控制信号均核验通过；从指令库及数据ROM重建的7148字节固件哈希一致。独立厂商模型和12项真实篡改检查也已通过。

最终源码已通过`verify_system.py --require-complete`统一复验，9/9项验收通过。固定seed2/hold8的编译、综合、映射、布局布线、时序报告及位流生成全部完成，退出状态为0，当前PDS进程为0。位流为3791112字节，SHA-256为`525d08ea4b903de7604453b0457f131c0aa79d00e9611a4e43de6ba84a5eaf00`，位于`build/rtos/pds/20261114-162656-direct_rom_final-map/generate_bitstream/instrec_top.sbit`。

最终路由资源为36749 LUT、39739 FF、1378分布式RAM、136.5 DRM及94 APM。最终独立时序报告的系统slow setup WNS为-11.834 ns，像素slow setup WNS为-1.140 ns，slow hold为+0.020 ns，fast hold为-0.035 ns（5个失败端点）；配置保持125 MHz系统时钟和148.5 MHz像素时钟。原始最终报告随交付包保留。

机器当前枚举到的串口均为蓝牙端口，FTDI/CP2102设备为0，板级实测待设备连接。全项目Python回归另记录430通过、13跳过、10失败及47错误，旧外部训练资产路径与既有契约断言的归因见`evidence/PROJECT_REGRESSION.json`。RTOS专项及完整NPU对照的实际命令、输入、输出和退出码见`VERIFICATION.txt`。

## 从新检出重做功能核验

`baseline125`的202份输入、DDR IP和固定版本内核已随工程纳管。新检出后可直接使用上述固件及整机构建入口；`import_sources.py`用于最初导入资产，日常构建使用已冻结的文件。

整机映射或完整实现结束后，将`$pdsRun`设为`build_system.py`输出的项目绝对路径，执行以下入口：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $verification = [System.IO.Path]::Combine((Get-Location).Path, 'instrec_fpga', 'rtos', 'verify_system.py')
    python -X utf8 $verification --pds-run $pdsRun --require-complete
    if ($LASTEXITCODE -ne 0) { throw 'RTOS verification failed' }
} catch {
    Write-Error $_
    exit 1
}
```

此命令重新构建生产及测试固件，执行定时器、精确中断、原版CPU、RTOS任务、隔离副本回退，以及原版／RTOS完整原生NPU对照。验证器从本轮运行重新生成证据，比较实际输入、权重、逐层golden、串口结果及周期，随后调用`collect_evidence.py`。完整实现时保留`--require-complete`；映射阶段的功能评审可省略该参数。

各轮命令、输出和旧证据副本保存在`build/rtos/verify/<时间>/`，本轮报告归档到`evidence/`。该流程使用本次检出的源码和新生成的仿真输入，历史报告中的绝对路径无需复用。

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
