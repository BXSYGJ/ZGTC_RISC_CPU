# 外设双版本计分口径

## 2026-09-09用户补充要求

最终分别报告精简外设版本（不包含全部外设）与包含GPIO、UART等外设的完整版本。完全移除MMIO是额外的对照实验，不是用户要求所有精简版本都必须采用的实现方式。每个CoreMark候选都独立验证时钟、CoreMark/MHz与CoreMark/LUT；完整外设版不得降低已接受的跑分，表现更好时可正常作为新跑分基线。不得把完整版本的运行时间与精简版本的LUT占用拼成一个成绩。

频率最低157.5 MHz，执行效率不低于500000000/157165009 CoreMark/MHz，资源效率严格大于0.05。最终采用同一位流对应的完整实现总LUT，不以估算的UART/GPIO开销做减法。器件、CPU、缓存容量、预测器、编译参数、固件、测量条件及ILA是否计入须分别列明。无外设并不等于移除处理器运行所必需的主存和缓存。

## 已有完整外设版本

当前DC90363D核心、GPIO、UART及42数据/33触发通道的最小ILA已完成实板CoreMark双种子验证：配置157.5 MHz、501.0657302224314 CoreMark、3.181369715697977 CoreMark/MHz、9374总LUT、0.053452712846429634 CoreMark/LUT。证据为build/hardware/regfile-fanout-minimal-20260909-box5/hardware-coremark-qualification.json。此版本是合法的完整外设跑分版本，不因含GPIO而排除。

GPIO诊断固件不运行CoreMark，因此仅作为此硬件的功能测试附件；不能把诊断固件中的循环时间换算为CoreMark。20260909-145944-09291bba的源绑定物理审计已通过：157.5 MHz、9374 LUT、WNS +0.078 ns。实验箱5的9条命令、360字节完整响应验证输入空闲值、使能回读及UART跳变负对照；未独立驱动KEY，故不宣称实板按键中断正例完成。

## 无外设实验

experiments/peripheral_partition使用独立rv32_soc顶层，实际不实例化rv32_peripherals或rv32_uart；GPIO、UART输出固定为无活动值，外部软件/定时器/GPIO中断均关闭。保留CPU的mcycle/minstret CSR、缓存和64 KiB RAM。访问不存在的MMIO地址返回总线错误，不模拟一个永远就绪的假UART来让旧固件蒙混运行。

专用CoreMark移植层自动启动，输出文本、周期数、退休数和状态写入普通RAM对象benchmark_result。输出及提交均在计时区间之外，两次fence.i调用本核心已有的缓存维护路径，先写回结果数据再提交完成标志；缓存写回后仿真直接读取RAM。普通fence不保证脏缓存回写，首版因此无法观察到完成状态，失败记录保留。这个RAM对象不是新增MMIO外设。核心算法使用固定上游提交1f483d5b8316753a742cbf5590caf5bd0a4e4777的未改动源码。

run_bare_coremark.ps1默认运行10次迭代，也支持BuildOnly生成6000次长测固件；长测使用run_bare_compiled.ps1。已有157.5 MHz固件的性能/验证长测周期1885688608/1886895258，但同频PDS尚未通过。144 MHz诊断构建以7756 LUT、WNS +0.105 ns通过PDS，却没有该固件完整运行或实板读回，且降低了频率，不具备联合优化资格。

撤回把157.5 MHz的501.143188 CoreMark与144 MHz资源配对的旧计算。正确公式是CoreMark=iterations*clock_hz/cycles，CoreMark/MHz=iterations*1000000/cycles；不能保留旧总分再除以新频率。qualify_bare_pair.py要求频率、固件、RTL、原始物理报告和完整CRC运行逐项绑定后才计算本地投影，且不将投影标成实板成绩。

## UART/定时器精简候选（157.5 MHz）

experiments/uart_timer_only只移除GPIO控制器，保留UART/FIFO、定时器/中断、状态与性能快照，可使用真实UART做后续实板读回；不含ILA。完整GPIO/UART与精简ILA的已接受工程不变。该候选仍需独立完成157.5 MHz时序、6000次双种子与板卡验证，不以降频代替优化。

初始快照build/uart-timer-only/20260909-201805-7ed77aa1已通过39次MMIO比较与3项故障注入。独立十轮性能/验证短测分别为3151519/3156276周期，退休指令、CRC与全部缓存事件和参考短测一致；short-qualification.json绑定两边原始输出、可执行模型、固件和RTL哈希。

零串口延时的6000轮性能/验证运行均完成CRC校验，但周期1887570281/1890603705高于接受参考，因此拒绝替换。157.5 MHz两个实际物理试验为9004 LUT、WNS -0.085 ns和8986 LUT、WNS -0.252 ns，均未通过；不能据此填入最终资源效率。失败记录见该stage的zero-delay-rejection.json。

对照发现，零延时编译配置使static_memblk相对原完整成绩固件前移96字节。恢复基线的ConsoleDelayCycles=2700000后，数据布局相同；性能二进制同为28916字节，仅三个区间外标记写入字节不同。匹配配置的本候选长测已独立启动，不能用这项二进制比较替代真实运行或时序证明。后续继续保持157.5 MHz目标，不采用降频达标的替代方案。

## ILA与尚未完成事项

按照用户最新范围，ILA只需本地PDS验证，不再为远程平台33/42通道兼容问题继续改核。现有三算法窗口来自真实RTL仿真，不冒称PDS调试RAM实际采集。远程GPIO、应用及稳定性工作分别验收。

scope的9600波特率普通实现20260909-151637-4e588209实际WNS -0.364 ns、9080 LUT，明确拒绝上板；不能借用115200波特率CoreMark或GPIO版本的成功时序。其原生CPU网表不与已通过V0逐字节相同，不能复用完整原生等价证明标志。后续须独立优化并重新验证。
