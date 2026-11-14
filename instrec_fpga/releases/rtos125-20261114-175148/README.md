# 125 MHz InstRec + FreeRTOS 交付

本目录归档已验收提交 `12d79828b8c67920f14750a23400a122bd0597c8` 的最终位流与原始交付 ZIP。发布分支为 [`rtos125-integration`](https://github.com/BXSYGJ/ZGTC_RISC_CPU/tree/rtos125-integration)；源码、构建和验证入口见 [`../../rtos/README.md`](../../rtos/README.md)。

| 文件 | 大小 | 下载 |
| --- | ---: | --- |
| `instrec_top_rtos125.sbit` | 3,791,112 字节 | [直接下载位流](https://github.com/BXSYGJ/ZGTC_RISC_CPU/raw/refs/heads/rtos125-integration/instrec_fpga/releases/rtos125-20261114-175148/instrec_top_rtos125.sbit) |
| `rtos125-20261114-175148.zip` | 5,027,483 字节 | [直接下载交付 ZIP](https://github.com/BXSYGJ/ZGTC_RISC_CPU/raw/refs/heads/rtos125-integration/instrec_fpga/releases/rtos125-20261114-175148/rtos125-20261114-175148.zip) |

ZIP 包含 586 个文件，提供位流、固件、源码、冻结基线、重建配方、最终原始时序报告及验证证据。归档包内 manifest 的 585 条记录已逐项重新读取、核对长度与 SHA256，manifest 本身构成第 586 个文件。

```text
instrec_top_rtos125.sbit
SHA256 525d08ea4b903de7604453b0457f131c0aa79d00e9611a4e43de6ba84a5eaf00

rtos125-20261114-175148.zip
SHA256 ed0ae7eac1a2c49879551fbd742abceb40572a154fb925e9d5f7e199484dd56d
```

系统配置为 125 MHz、FreeRTOS-Kernel V11.3.3、1 kHz 节拍、recognition/result_uart/heartbeat 三应用任务、静态结果队列。正式固件 ROM 为 7,148 字节。

专项验收 9/9 通过，最终统一功能复验的 13 条命令全部退出 0，覆盖原版、RTOS 抢占/队列/临界区、定时器、精确中断、全容量 ROM、完整原生 NPU golden 对照和隔离副本回退；综合、映射、布局布线、时序报告与位流生成均完成。证据见 [`ACCEPTANCE.json`](../../rtos/evidence/ACCEPTANCE.json)、[`FUNCTIONAL_VERIFICATION.json`](../../rtos/evidence/FUNCTIONAL_VERIFICATION.json) 和 [`VERIFICATION.txt`](../../rtos/VERIFICATION.txt)。

最终报告保留系统 slow setup -11.834 ns、fast hold -0.035 ns，当前板级验证状态为待实测。全项目旧资产与契约回归的独立结果保存在 [`PROJECT_REGRESSION.json`](../../rtos/evidence/PROJECT_REGRESSION.json)。
