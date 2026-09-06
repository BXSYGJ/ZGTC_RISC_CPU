# RV32I CPU 开发工程

这是赛题一的实际 CPU 工程，不是原流水灯的改名。CPU、缓存和外设已完成集成仿真，Windows PDS 已生成 CPU 位流，RemoteLab 实板串口已返回 `ZSOC PASS`。完整自检证据及尚未覆盖的范围见 `docs/HARDWARE_SELFTEST.md`。

## 当前架构

执行效率优化的新实验为默认关闭的FAST_ICACHE_HIT，提前返回I-cache命中；功能回归和短CoreMark验证已通过，PDS资源/时序与正式实板成绩待测，见 `docs/FAST_ICACHE_HIT.md`。不将该实验与既有180 MHz位流混为同一版本。

工程总报告见 `docs/FINAL_REPORT.md`，快照打包与迁移校验见 `docs/DELIVERY.md`；当前仍有明确的最终验收缺口，不能把打包成功当作全部完成。

`取指请求 → IF 缓冲 → ID 译码/寄存器读取 → EX 执行/前递 → MEM 访存与控制提交 → WB 寄存器写回`

- 五级按序流水线；寄存器 x0 恒为零，32 位整数运算与字节/半字/字访问。
- 指令/数据接口解耦，可分别等待接受和响应。MEM 阶段阻塞时，年轻指令暂停而不重复发起存储操作。
- MEM、WB 前递到 EX；停顿时保存已前递值，防止来源指令退休后数据丢失。
- 可选load寄存前递实验默认关闭；162 MHz对照实测和216 MHz失败时序见 `docs/LOAD_FORWARD_EXPERIMENT.md`，实验未替代默认性能基线。
- 16 项直接映射 BTB 和两位饱和计数器；MEM 按序确认控制流，错误预测冲刷年轻指令。已发出的旧取指请求必须完成后丢弃，不违反握手约定。
- M-mode 精确异常、Zicsr、MRET、三类中断输入、直接/向量 mtvec、mcycle/minstret。仅实现 M-mode，不声称支持 U/S 模式、MMU、PMP 或所有可选扩展。
- FENCE 按阻塞、按序数据访问的约束实现；FENCE.I 排空前端，等待数据 Cache 写回及两级 Cache 失效，然后冲刷 BTB/流水线。已通过自修改代码测试。
- WFI 当前作为可合法唤醒的空操作，不实现时钟门控；M/A/C/F 等未实现指令产生非法指令异常。

存储接口细节见 `docs/BUS.md`，完整要求与未完成项见 `docs/ACCEPTANCE.md`。
原子性能快照、可复现预测器开关和首轮消融证据见 `docs/PERFORMANCE_MONITOR.md`；该监测逻辑在首轮实板基线后加入，不能沿用旧位流的资源计分。

## 存储系统

时钟配置与防止硬件/固件频率不一致的检查见 `docs/CLOCKING.md`。默认162 MHz基线为59.3542 CoreMark；最高已验证候选为显式LOAD_USE_BUBBLE=1的180 MHz、65.9430 CoreMark，箱3五次运行通过，见 `docs/HARDWARE_180MHZ.md`。保留箱5低频与默认基线证据，不等于绝对最高可达频率或长期稳定性已测完。

`rv32_memory_system` 集成两路组相联 I-Cache 与 D-Cache、完整突发锁定的轮转仲裁器、可综合片上 RAM 和不缓存的 MMIO 转接端口。D-Cache 使用写回/写分配及逐字节写使能，填充失败不安装有效行，写回失败保留脏行供重试。默认每个 Cache 512 字节，RAM 16 KiB，均参数化。

目前未接 DDR。实际 `rv32_soc` 使用 64 KiB 片上 RAM，连接带 FIFO 的 UART、GPIO、64 位定时器、软件中断和状态寄存器；独立 CPU 测试仍使用测试邮箱。维护错误导致粘滞故障停机，禁止 FENCE.I 退休及年轻指令副作用，复位恢复。地址与板级区别见 `docs/PERIPHERALS.md`。

## 验证

首先按 `docs/TOOLCHAIN.md` 构建真实的 `riscv32-unknown-elf-gcc` 10.2.0。工程经本机工具链清单定位编译器，缺失或目标不符会报错，不再静默使用 RV64 multilib。已完成源码构建、RV32 库检查及完整回归。

外部指令验证独立执行 `pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1`：固定上游41个 RV32UI 程序、四种配置共164次通过，另有四个拒绝控制。具体适配范围和未对齐访问排除理由见 `docs/EXTERNAL_ISA.md`，不称作官方认证。

在仓库根目录执行：

```powershell
pwsh -NoProfile -File cpu/scripts/validate.ps1
```

要求 PowerShell 7、WSL Ubuntu-22.04、Icarus、Verilator、Python 3、RISC-V bare-metal GCC/binutils。构建脚本使用 multilib GCC 的 `-march=rv32i -mabi=ilp32`，产物已核实为 ELF32、little-endian、RISC-V，不是 RV64 固件。

验证包括：

1. 译码/ALU、BTB、machine CSR 自检。
2. 汇编定向测试与可复现随机指令，预测器开关各 3 个随机总线延迟种子。
3. 独立 Python 模型逐条检查退休指令、寄存器值、精确异常及最终完整存储器；带缓存 CPU 使用两种 Cache 容量、预测器开关共四种配置，结束前先完整写回。
4. 修改 PC、指令、写回值、陷入记录的变异测试，确认检查器确实拒绝错误。
5. Verilator `--lint-only --Wall`。
6. Cache 随机读写与最终内存对比、读写错误、早/晚 last、维护失败重试；突发轮转公平性、归属锁定和应答反压验证。
7. FIFO、UART 全 256 字节收发、波特率偏差、帧错误/溢出、MMIO 反压及副作用检查。
8. 真实 C 启动清零被预先污染的 BSS，验证初始数据、软件/定时/GPIO 外部中断、串口引脚级收发，以及维护错误停机。

## Windows PDS 实现

```powershell
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile Board
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile RemoteLab
```

两条命令是不同 UART 接线环境的备选项，不需要连续运行。Board 使用板载 B24/C24；RemoteLab 使用网站仪器明确标出的 AC26/AB26。脚本使用独立构建目录、固件镜像快照，执行 ADS 综合、布局布线、时序与位流生成，拒绝未通过时序的结果。当前入口编译的是交互式 SoC 自检固件，不是 CoreMark 或最终应用。

`build/pds-latest.json` 记录位流、固件 SHA-256、器件和 UART 配置。首次 Board 构建占用 3,735 LUT、16.5 个 DRM36K 等效块；27 MHz 约束下 setup 余量 22.869 ns，最差 hold 余量 0.101 ns。报告中的 70.5816 MHz 是工具估算，不是已上板验证主频。异步引脚和输出接口未作外部同步时序签核；SCBV 提示仍保留，未猜测其值。

`build/core-tests.log` 保存汇总；`build/*.trace` 为退休/陷入记录，`build/*.memory` 为最终存储器；`build/core_selftest.dis` 可对照反汇编。以上生成物均不入库。

## 后续交付

CoreMark 两组种子已完成超过 20 秒的实板运行，CRC 全通过；27 MHz 起始基线为 9.8178 CoreMark、0.3636 CoreMark/MHz，原始证据和边界见 `docs/COREMARK_RESULTS.md`。CPU 波形应用已完成两次各256点实板采样、校验及不同输入解码，运行说明和证据见 `docs/SCOPE_APPLICATION.md`。Cache与预测器硬件消融已各配置重复两次，见 `docs/HARDWARE_CACHE_ABLATION.md`、`docs/HARDWARE_PREDICTOR_ABLATION.md`；原生JTAG ILA六个真实算法窗口及插核开销见 `docs/ILA_RESULTS.md`。仍需最高实测频率、长期稳定性和进一步优化，不代表所有 ISA、Cache 边界和比赛要求均已验收。AI 加速按用户要求暂缓，其余范围保持不变。
