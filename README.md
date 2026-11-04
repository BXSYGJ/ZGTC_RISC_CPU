# PaceRV 作品交付：RTL与最终技术报告

最终技术文档为用户提供的[《PaceRV_作品技术报告(1).docx》](instrec_fpga/docs/PaceRV_作品技术报告(1).docx)，原文件逐字节保留。

## 源码划分

| 部分 | 目录 | 内容与入口 |
|---|---|---|
| 裸CPU：性能版 | `instrec_fpga/rtl/bare_cpu/performance_155250/` | RV32IMC核、缓存、存储、外设与PLL，19份RTL |
| 裸CPU：效率版 | `instrec_fpga/rtl/bare_cpu/efficiency_145125/` | H3 Base RV32IMC及对应存储实现，19份RTL |
| 整个系统应用 | `instrec_fpga/rtl/system_application/` | CPU控制、音频、Mel、NPU、DDR3、中文HDMI与原厂IP，131份RTL |

裸CPU两个版本均包含`rtl/rv32_core.sv`（核接口）、`rtl/rv32_soc.sv`（CPU子系统）及`rtl/rv32_board_top.sv`（板级封装），PLL位于`fpga/`。模块保持原名及原始字节，每个版本单独作为源文件集使用。

应用系统顶层为`instrec_fpga/rtl/system_application/src/ctrl/instrec_top.v`，其中CPU为RV32I控制配置，核及封装位于`src/cpu/`，音频、Mel、NPU、DDR3和显示按子目录组织；`ipcore/`收录应用依赖的Verilog及加密Verilog。应用源文件集与两个裸CPU源文件集各自独立，选择一个源文件集进行集成，避免同名模块重复加载。

## 来源与配置

裸CPU分别取自远程DYH分支提交`4ef1ea1be32c110024dd59f08f1342b325c9df59`的`cpu/Original_155250/source/`及`cpu/H3_Base_145125/source/`。应用RTL取自本分支此前固定的完整CPU＋NPU八类系统，功能基准提交`0c138d4f`，保持原RTL内容。

CPU实现参数见[RTL_MANIFEST.json](instrec_fpga/docs/RTL_MANIFEST.json)的`cpu_parameters`：启用M、C、预测器、缓存与相应流水优化。155.25 MHz和145.125 MHz用于标识所选源码版本。实例化时显式设置参数；RTL文件中的通用默认值保持原样。`rv32_board_top`接收CPU时钟，`rv32_pll`用于生成相应时钟。

`rtl/`目录仅包含`.v`、`.sv`和`.vp`源文件。固件、ROM初始化表、网络权重、约束及PDS工程配置属于完整工程集成资产，此次按要求交付RTL；应用中保留原`src/...hex`引用，集成时从工程根目录提供相应初始化数据。原完整工程可通过Git提交`cdc4969e`取得，所需ROM列表和权重身份记录在清单中。GTP_*器件原语由PDS器件库提供，原厂加密IP按原授权使用。

[RTL_MANIFEST.json](instrec_fpga/docs/RTL_MANIFEST.json)记录全部169份RTL的路径、来源和SHA-256，以及最终Word文件身份；`instrec_fpga/SHA256SUMS`用于逐文件核验交付内容。训练代码、模型、C固件、工具脚本、位流和旧Markdown报告已从此次交付分支的文件清单移出。
