# 原始 125 MHz 与 109.375 MHz 基线

本目录保存此前已选定的两个原始基线，与选择记录提交 `e2cb30fb01dcdbd826149216c58868198afc7455` 对应。发布分支为 [`rtos125-integration`](https://github.com/BXSYGJ/ZGTC_RISC_CPU/tree/rtos125-integration)；三个版本的总入口见[下载索引](../RTOS_AND_BASELINES_20261114.md)。

| 版本 | 原构建 | 完整 ZIP 下载 | 位流下载 |
| --- | --- | --- | --- |
| 125 MHz | `full-20261113-223256-full` | [125M_hold_clean.zip](https://github.com/BXSYGJ/ZGTC_RISC_CPU/raw/refs/heads/rtos125-integration/instrec_fpga/releases/selected-baselines-20261114/125M_hold_clean.zip) | [instrec_top_baseline125.sbit](https://github.com/BXSYGJ/ZGTC_RISC_CPU/raw/refs/heads/rtos125-integration/instrec_fpga/releases/selected-baselines-20261114/instrec_top_baseline125.sbit) |
| 109.375 MHz | `full-20261114-021145-full` | [109M375_main.zip](https://github.com/BXSYGJ/ZGTC_RISC_CPU/raw/refs/heads/rtos125-integration/instrec_fpga/releases/selected-baselines-20261114/109M375_main.zip) | [instrec_top_baseline109M375.sbit](https://github.com/BXSYGJ/ZGTC_RISC_CPU/raw/refs/heads/rtos125-integration/instrec_fpga/releases/selected-baselines-20261114/instrec_top_baseline109M375.sbit) |

每个原始 ZIP 提供 `inputs/` 中实际使用的 202 份源码、IP、HEX 和约束，以及 `TIMING.rtr`、`INPUTS.json`、`BUILD_RESULT.json`、`SOURCE_BUILD_RECIPE.tcl` 和 `PACKAGE_MANIFEST.json`。原始 recipe 保留当时的绝对路径，迁移工作区时须对应调整；包内源文件和成品均保留原值。

| 成品 | 字节数 | SHA256 |
| --- | ---: | --- |
| `125M_hold_clean.zip` | 2,819,827 | `ad412610e43e1ca588b2f8b3f59ff6b1e5b7bdf14e73abb9a04225dd42ed3f37` |
| `instrec_top_baseline125.sbit` | 3,791,112 | `20bbda7e0194917111e76c7b797bc196bc8fdf6f02f00598f2eb297a6b76b157` |
| `109M375_main.zip` | 2,948,962 | `ce7045c73c9ab5bbf3fd16d259073b9fcfed0bfd43e5bef368c61b23c3dc96f7` |
| `instrec_top_baseline109M375.sbit` | 3,791,112 | `bb484f2153523d8045631abe9d314e6ddffd658b01be0b35f2d76edc20d7f576` |

原始时序结果如下，完整报告保存在各 ZIP 中。

| 版本 | slow setup WNS/ns | slow setup TNS/ns | slow hold WNS/ns | fast hold WNS/ns |
| --- | ---: | ---: | ---: | ---: |
| 125 MHz | -1.414 | -346.334 | +0.052 | 0.000 |
| 109.375 MHz | -1.633 | -33.413 | -0.127 | -0.136 |

选择记录及七个历史构建的比较见 [`SELECTED_VERSIONS_20261114.json`](../../experiments/pacerv_shared_system/evidence/SELECTED_VERSIONS_20261114.json)。125 MHz FreeRTOS 的实现和验证记录另见 [`../../rtos/README.md`](../../rtos/README.md)。
