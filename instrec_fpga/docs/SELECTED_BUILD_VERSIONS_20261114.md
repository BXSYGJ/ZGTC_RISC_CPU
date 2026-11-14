# 按用户要求选用的125MHz与109.375MHz版本

用户于2026-11-14要求停止继续追求时序闭合，当前一轮133421完成后收尾，回到已有125MHz与约109.5MHz版本。该档实际DDR用户时钟为109.375MHz。以下以原始最终报告比较，保留报告中的违例数值。

主选为109.375MHz的`full-20261114-021145-full`：已完成版本中，setup总负裕量绝对值最小，setup失败端点最少。125MHz备选为`full-20261113-223256-full`，该版本的快慢角hold均通过。

| 实际系统频率 | 原构建 | slow setup/ns | setup TNS/ns | setup失败端点 | slow hold/ns | fast hold/ns |
|---|---|---:|---:|---:|---:|---:|
| 125MHz | 191537 | -2.419 | -2252.108 | 3822 | -0.108 | -0.121 |
| 125MHz | 213918 | -1.262 | -801.129 | 2669 | +0.024 | -0.029 |
| **125MHz备选** | **223256** | **-1.414** | **-346.334** | **1136** | **+0.052** | **0.000** |
| 125MHz | 232600 | -2.437 | -1683.575 | 3820 | -0.008 | -0.058 |
| 125MHz | 010622 | -1.438 | -214.737 | 710 | -0.119 | -0.128 |
| **109.375MHz主选** | **021145** | **-1.633** | **-33.413** | **155** | **-0.127** | **-0.136** |
| 109.375MHz | 111645 | -1.839 | -737.311 | 1799 | -0.160 | -0.162 |

125MHz的213918具有该档最好的最差setup裕量；010622具有该档最小setup TNS。223256兼顾较小setup违例和快慢角hold通过，因此作为125MHz的默认备选。完整比较包含所有七个已完成PG100整机版本，202份冻结输入逐份核验，原位流和报告SHA256见[机器记录](../experiments/pacerv_shared_system/evidence/SELECTED_VERSIONS_20261114.json)。

## 直接使用

主选压缩包：[109M375_main.zip](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/build/pacerv_shared_system/selected_versions_20261114/109M375_main.zip)。

主选位流：[instrec_top.sbit](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/build/pacerv_shared_system/selected_versions_20261114/109M375_main/instrec_top.sbit)。SHA256：`bb484f2153523d8045631abe9d314e6ddffd658b01be0b35f2d76edc20d7f576`。

125MHz备选压缩包：[125M_hold_clean.zip](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/build/pacerv_shared_system/selected_versions_20261114/125M_hold_clean.zip)。

125MHz备选位流：[instrec_top.sbit](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/build/pacerv_shared_system/selected_versions_20261114/125M_hold_clean/instrec_top.sbit)。SHA256：`20bbda7e0194917111e76c7b797bc196bc8fdf6f02f00598f2eb297a6b76b157`。

每包的`inputs/`包含原位流实际使用的202份RTL、IP、HEX及约束；`TIMING.rtr`是原最终报告；`INPUTS.json`记录输入哈希；`SOURCE_BUILD_RECIPE.tcl`保留原工程绝对路径供追溯；`PACKAGE_MANIFEST.json`记录包内文件哈希。两个ZIP均重新打开并逐文件核对哈希，合计404份冻结输入一致。

125MHz的最差setup裕量备选原位流：[213918 instrec_top.sbit](D:/AAAFPGA/ZGTC_RISC_CPU_XSY/instrec_fpga/build/pacerv_shared_system/pds/full-20261113-213918-full/generate_bitstream/instrec_top.sbit)。原始输入位于同一构建目录的inputs。

当前83.333333MHz源码及133421实验另行保留。后续使用上述已选包内源码与IP，即对应其原位流版本。

## 本轮收尾

133421已经结束：用时719.426秒，退出1。compile/synthesize/dev_map完成；500ps时钟树hold修复参数超出PDS允许的0至200ps范围，pnr在入口报错，report_timing/gen_bit_stream未执行，未生成新最终报告或位流。202份冻结输入保持原值。当前PDS进程0，时序修复和PDS构建到此结束；原持续时序验收目标状态为paused。用户选择的125MHz及109.375MHz使用入口以本页为准。

构建终态与日志哈希见[BUILD_CLOSEOUT_20261114.json](../experiments/pacerv_shared_system/evidence/BUILD_CLOSEOUT_20261114.json)。两个所选ZIP重新打开，404份冻结输入及全部包内文件哈希验证通过。
