# PG200 DDR3 时钟约束审计

## 来源与实际失配

原始官方配套资料：

`D:/AAAFPGA/MES2L676_200_ref/盘古200Pro+开发板（MES2L676-200HP）配套资料/2_Demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/pnr/ddr_test.fdc`

源文件 SHA-256：`BAC418DAC60D9F8CC2850E8D70F9C4822BF39EF648DDE0878103E87671E96E9F`。

该文件第19–23行将 `free_clk`、`ref_clk`、`rst_clk`、`phy_dq_clk_0` 和 `phy_dq_clk_1` 分别声明为异步组。用户时钟 `ddrphy_sysclk` 与分频后的 `phy_dq_sysclk_*` 保留时序关系，包括DDR IP的两拍多周期路径与0.4ns跨时钟不确定性。

最初remote准备脚本移除了历史CPU约束中的全部 `set_clock_groups`。在独立run `remote-20261113-184602-full` 的实际路由报告中，IP内部 `rst_clk` 到两个PHY时钟及其分频时钟被当成同相同步恢复路径分析：慢速角恢复WNS分别为−4.386、−3.259、−4.797和−3.452ns。官方生成IP在 `ddr3_test_ddrphy_top.v` 第428行起包含 `ips2l_ddrphy_rst_clk_phase_adj_v1_0`，并通过独立GPLL的动态相位调节生成 `rst_clk`；第476行及第623行附近包含域内复位同步模块。官方约束针对这些专用初始化／PHY域的相位与复位契约设置异步组。

## 本次修复

`constraints/pg200_ip_cdc.fdc` 原样保存官方四条适用于本harness的异步组声明。`free_clk` 没有在本harness中实例化，因此省略对应声明。约束加载顺序为 DDR时钟／管脚 → IP异步组 → UART/LED/复位管脚。

这些命令保留了CPU、共享桥、仲裁器、控制器和UART共同使用的 **ddrphy_sysclk → ddrphy_sysclk** 同步检查。约束没有给CPU数据路径增加例外，没有把CPU时钟列为独立异步组。`ddrphy_sysclk ↔ phy_dq_sysclk_*` 也保留官方的多周期和不确定性设置。PG200历史 `cpu/constraints/ddr3.fdc` 的多组声明把所有DDR派生域彼此分开；本次使用官方较精确的四条声明。

## 0.150ns用户时钟预算

首轮使用单clock对象形式：

`set_clock_uncertainty {0.150} -setup -hold [get_clocks {ddrphy_sysclk}]`

部分同域路径的实际报告显示0.300ns。后续改用明确的时钟对，记录用户指定的预算作用范围：

`set_clock_uncertainty {0.150} -setup -hold -from [get_clocks {ddrphy_sysclk}] -to [get_clocks {ddrphy_sysclk}]`

PDS还包含系统抖动、PLL抖动和生成时钟关系的处理。明确时钟对之后，详细路径中仍同时观察到0.150ns和0.300ns的实际扣除；单靠命令形式不能解释全部路径的预算组成。报告保留实际扣除值，并同时检查setup、hold、recovery、removal和pulse-width汇总。最终是否收敛以十张汇总表及各路径实际预算为准。

`remote-20261113-190733-full` 的最差同域setup路径实际扣除0.150ns，WNS为+0.052ns，十张汇总表均无失败端点。其他详细路径也出现0.300ns扣除。该版首次远程烧写成功但90秒UART采集为零字节；同平台原H3控制位流能够输出CoreMark，后续独立PG200适配因此补充自动上电复位和PHY初始化时序。

新适配的 `board_clk27` 只连接上电复位计数器，通过 `boot_resetn` 进入IP已有的复位同步逻辑。`pg200_remote.fdc` 为该启动域单独声明异步组，CPU及DDR数据路径继续在 `ddrphy_sysclk` 内检查。新适配须重新生成报告和位流，前一版的+0.052ns数值只属于前一份冻结输入。
