# 125 MHz / 109.375 MHz 原始基线与 FreeRTOS 下载

三套版本统一发布在 [`rtos125-integration`](https://github.com/BXSYGJ/ZGTC_RISC_CPU/tree/rtos125-integration) 分支。每套版本均提供完整归档和单独位流。

| 版本 | 对应构建 | 完整归档 | 位流 | 说明与哈希 |
| --- | --- | --- | --- | --- |
| 原始 125 MHz 基线 | `full-20261113-223256-full` | [125M_hold_clean.zip](selected-baselines-20261114/125M_hold_clean.zip) | [instrec_top_baseline125.sbit](selected-baselines-20261114/instrec_top_baseline125.sbit) | [原始基线说明](selected-baselines-20261114/README.md) |
| 原始 109.375 MHz 基线 | `full-20261114-021145-full` | [109M375_main.zip](selected-baselines-20261114/109M375_main.zip) | [instrec_top_baseline109M375.sbit](selected-baselines-20261114/instrec_top_baseline109M375.sbit) | [原始基线说明](selected-baselines-20261114/README.md) |
| 125 MHz FreeRTOS | `rtos125-20261114-175148` | [rtos125-20261114-175148.zip](rtos125-20261114-175148/rtos125-20261114-175148.zip) | [instrec_top_rtos125.sbit](rtos125-20261114-175148/instrec_top_rtos125.sbit) | [RTOS 交付说明](rtos125-20261114-175148/README.md) |

两个原始基线 ZIP 各包含实际构建使用的 202 份 RTL、IP、HEX 和约束，以及原最终时序报告、输入哈希和构建配方。RTOS 包包含固件、冻结基线、源码、重建入口及功能验证证据；源码说明见 [`../rtos/README.md`](../rtos/README.md)。

各成品均按原始 SHA256 复制归档，原始包内 manifest 和历史报告保留。基线版本的选择依据见 [`SELECTED_BUILD_VERSIONS_20261114.md`](../docs/SELECTED_BUILD_VERSIONS_20261114.md)。
