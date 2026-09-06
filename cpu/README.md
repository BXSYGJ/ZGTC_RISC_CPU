# RV32I CPU 开发工程

这是赛题一的实际 CPU 工程，不是原流水灯的改名。CPU、缓存和外设已完成集成仿真，Windows PDS 已生成 CPU 位流，RemoteLab 实板串口已返回 `ZSOC PASS`。完整自检证据及尚未覆盖的范围见 `docs/HARDWARE_SELFTEST.md`。

2026-09-06实板更新：实验箱2的120 MHz RV32IM候选达到3.0129645923 CoreMark/MHz、361.5557510765 CoreMark、0.03515369481 CoreMark/LUT；10285 LUT、4808 FF、WNS +0.117 ns。两次重新烧录后的4000轮性能运行结果完全一致，另一次4000轮验证种子CRC通过，计分区均超过11秒。该数值硬指标已满足；全项目验收、长期稳定性和三项物理极限仍未完成。 完整证据见 `docs/HARDWARE_120MHZ_TARGET.md`；编译式仿真与失败边界见 `docs/COMPILED_SIMULATION.md`。下列实验条目是按时间推进的历史快照。

## 当前架构

执行效率候选依次加入提前 I-cache 响应、标准可选 M 扩展、重叠取指、提前 D-cache 读响应和 EX 提前数据请求；各功能开关默认关闭。最新内部修订减少 MUL/MULHU 响应等待并精简非加载前递资格，小缓存短跑571191周期、5398 LUT、120 MHz WNS +0.475 ns；大缓存/展开组合449230周期、7175 LUT、WNS +0.445 ns。均为本地验证，不是新实板成绩，详见 `docs/MUL_EARLY_RESPONSE.md`。历史提前访存对照和编译筛选分别见 `docs/EARLY_DATA_REQUEST.md`、`docs/COMPILER_CACHE_SCREEN.md`。

新增默认关闭的数据请求重叠：在旧响应完成的同一拍接受下一请求，仍只保留一笔未完成事务。64 项 BTB 同固件短跑周期423289→402898，120 MHz同源码实现7293→7308 LUT，WNS +0.432 ns；短跑工作量/LUT代理指标改善约4.84544%。尚无新实板长测，详见 `docs/DATA_OVERLAP.md`，不宣布3.0目标完成。

随后将乘法器改为请求拍锁存并行半字乘积，避免直接提前32×32级联导致的时序失败。短跑402898→393604周期，120 MHz实现7308→7300 LUT、4232→4126 FF、WNS +0.528 ns；最终完整回归、14组精确中断、外部ISA及性能/验证位流均通过。未上板，不更新正式成绩，详见 `docs/MUL_REQUEST_CAPTURE.md`。

缓存地址边界、分指令类握手、MMIO请求寄存和响应数据保持修订使直接加载前递在120 MHz通过：同源码B1/B0短跑393604→374184周期，LUT为6846/7007、FF为4138/4146，工作率/LUT代理指标提高2.77301%，B0 WNS仅+0.076 ns。完整回归及外部ISA通过；未上板，不更新正式成绩或宣布3.0达标，见 `docs/CACHE_ADDRESS_BOUNDS.md`。

预测表地址范围压缩及类型存储修订继续降低64项候选面积：120 MHz、6935 LUT、4080 FF、WNS +0.141 ns，短跑仍374184周期；性能/验证位流、最终回归和外部ISA已通过。256项及大Cache的时序失败保留，不冒充新实板成绩，详见 `docs/BTB_ADDRESS_BOUNDS.md`。

新增可选LTO、链接松弛及1—10次持续执行短测，默认编译行为不变。已测组合均未超过原O3 + unroll；10次性能平均373566.3周期/迭代，仍不足以满足3.0目标。新增清单/固件一致性防护和14项测试，证据与使用边界见 `docs/COMPILER_OPTIONS.md`。

新增独立DCache写命中快速响应，默认关闭，保留旧值响应、字节掩码、背压和复位语义。128项BTB + 写快路径组合通过120 MHz性能/验证实现：7183 LUT、4130 FF、WNS +0.165 ns；同固件单次性能短测由64项关闭写快路径基线374184降至352805周期（减少5.71350%），单位LUT工作率代理指标提高2.39791%。这是两参数组合而非单变量消融，64项仅开启写快路径的实现WNS -0.082 ns，不能采用。完整回归、扩展定向测试与外部RV32I/M通过，尚无新实板成绩；详见 `docs/FAST_DCACHE_WRITE.md`。

进一步复用MEM级异常元数据，新增3249项定向检查及八个错误来源反例。128/256项BTB、每侧2 KiB的性能/验证实现均通过120 MHz，分别为7221/7441 LUT、4143/4227 FF、WNS +0.256/+0.282 ns；性能短测为352805/349485周期。较快执行或较大时序裕量伴随资源效率下降，保留此前较小面积快照，不宣称全面替代。每侧8 KiB的10迭代性能平均332794.9周期，但该8 KiB实现WNS -2.026 ns被拒绝，不能算3.0达标；实现与验收边界见 `docs/TRAP_VALUE_REUSE.md`。

独立I-cache容量候选：8 KiB指令侧/2 KiB数据侧的性能与验证实现均通过120 MHz（10285 LUT、4808 FF、WNS +0.117 ns）；同源码2/2 KiB控制为7441 LUT、WNS +0.282 ns。同固件单次性能周期349485→336486，减少3.71947%，但单位LUT工作率代理下降24.85700%，不能称三项全面改善。10轮平均333871.7周期仍略超3.0对应预算；8/4 KiB虽更快却时序失败。新增几何、读写入口契约、非对称集成及外部ISA验证已通过；旧缓存差分入口读写开关不同时的覆盖缺陷已修复并重新验证。接口兼容性、失败路径与全部证据见 `docs/ASYMMETRIC_CACHE.md`，不替代实板成绩。

工程总报告见 `docs/FINAL_REPORT.md`，快照打包与迁移校验见 `docs/DELIVERY.md`；当前仍有明确的最终验收缺口，不能把打包成功当作全部完成。

`取指请求 → IF 缓冲 → ID 译码/寄存器读取 → EX 执行/前递 → MEM 访存与控制提交 → WB 寄存器写回`

- 五级按序流水线；寄存器 x0 恒为零，32 位整数运算与字节/半字/字访问。
- 指令/数据接口解耦，可分别等待接受和响应。MEM 阶段阻塞时，年轻指令暂停而不重复发起存储操作。
- MEM、WB 前递到 EX；停顿时保存已前递值，防止来源指令退休后数据丢失。
- 可选load寄存前递实验默认关闭；162 MHz对照实测和216 MHz失败时序见 `docs/LOAD_FORWARD_EXPERIMENT.md`，实验未替代默认性能基线。
- 默认16项、可配置2–256项的直接映射 BTB 和两位饱和计数器；MEM按序更新，错误预测冲刷年轻指令，旧取指请求仍必须完成后丢弃。64/128项通过本地回归及120 MHz PDS，资源和执行效率折衷见 `docs/BTB_CAPACITY.md`，尚非新实板成绩。
- M-mode 精确异常、Zicsr、MRET、三类中断输入、直接/向量 mtvec、mcycle/minstret。仅实现 M-mode，不声称支持 U/S 模式、MMU、PMP 或所有可选扩展。
- FENCE 按阻塞、按序数据访问的约束实现；FENCE.I 排空前端，等待数据 Cache 写回及两级 Cache 失效，然后冲刷 BTB/流水线。已通过自修改代码测试。
- WFI 当前作为可合法唤醒的空操作，不实现时钟门控；M 扩展仅在 ENABLE_M=1 时开启；默认关闭的 M 及未实现的 A/C/F 指令产生非法指令异常。

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
