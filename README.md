# ZGTC_RISC_CPU

面向全国大学生 FPGA 创新设计竞赛紫光同创赛道选题一的 RISC-V CPU 项目。

## DYH 分支

`DYH` 是个人开发分支。当前首先建立 PG2L200H 目标器件、MES2L676-200HP 板卡、
WSL 仿真与 PDS 实现流程的可复现基线。`cpu/` 已加入五级 RV32I 流水线、BTB、
M-mode 异常/中断、两路 I/D Cache、突发片上存储后端和独立参考模型验证；
UART/GPIO/定时器与 C 启动已完成 SoC 仿真，Windows PDS 已生成 CPU 位流；RemoteLab 实板交互自检已返回 `ZSOC PASS`。CoreMark 两组长时实板 CRC 已通过，性能基线 9.8178 CoreMark；CPU 波形采集应用已在实板独立恢复 0x55/0xAA 两组输入，见 `cpu/docs/SCOPE_APPLICATION.md`。同板同固件 Cache 开关各两次长时消融已完成，开启后周期减少45.8007%，见 `cpu/docs/HARDWARE_CACHE_ABLATION.md`。预测器硬件消融周期减少16.1019%，见 `cpu/docs/HARDWARE_PREDICTOR_ABLATION.md`；原生JTAG ILA已捕获六个真实算法窗口，见 `cpu/docs/ILA_RESULTS.md`。最高实测频率、长期稳定性和进一步优化仍在推进。

## 目录

当前最高已验证候选为180 MHz寄存前递模式，性能重复两次、验证种子一次和4000次持续运行两次均通过；默认162 MHz基线保留。三个指标分开报告：

| 配置 | CoreMark/MHz | CoreMark/LUT | CoreMark | 布局后LUT |
| --- | ---: | ---: | ---: | ---: |
| 默认162 MHz | 0.36638392 | 0.01249299 | 59.3542 | 4751 |
| 寄存前递180 MHz | 0.36634997 | 0.01346050 | 65.9430 | 4899 |

180 MHz方案执行效率微降，资源效率提高，不能只按主频称全面优化。两组来自不同实验箱，详细证据与限制见 `cpu/docs/HARDWARE_180MHZ.md`。尚未证明绝对Fmax或多小时稳定性。

存储使用64 KiB片上RAM，由PDS实现为DRM/BRAM资源；上述实现的总DRM占用为16.5个DRM36K等效，不能把该总数直接当作CPU可寻址容量。I/D Cache各512 B，**当前未接DDR控制器或外部DDR内存**。

另有默认关闭的I-cache提前响应实验，完整回归和164次外部ISA测试通过；两种CoreMark种子短仿真CRC通过，但尚无该模式的PDS资源/时序和正式实板成绩。不能沿用历史位流分数，详见 `cpu/docs/FAST_ICACHE_HIT.md`。

| 路径 | 内容 |
| --- | --- |
| `pds_minimal_blink_200h/` | 已通过仿真、PDS 全流程和远程实板验证的双向流水灯基线 |
| `cpu/` | 正在开发的 CPU 工程，需求与未完成项见 `cpu/docs/ACCEPTANCE.md` |

最小例程的环境要求、引脚定义、运行命令和验证结果见
[`pds_minimal_blink_200h/README.md`](pds_minimal_blink_200h/README.md)。

CPU 开发状态见 [`cpu/README.md`](cpu/README.md)。在仓库根目录运行
`pwsh -NoProfile -File cpu/scripts/validate.ps1` 可复现当前全部 CPU 仿真与参考模型验证。
首次运行先按 `cpu/docs/TOOLCHAIN.md` 构建真实 RV32 GNU 工具链；该工具链已在本机完成构建和回归，不以 RV64 编译器别名替代赛题要求。

## 开发约定

- 日常开发与验证提交到 `DYH` 分支。
- RTL、testbench、约束和可复现脚本纳入版本控制。
- PDS 数据库、中间产物、日志、仿真输出、位流及本地许可证不提交。
- 合并前至少执行 RTL 自检；涉及器件实现的修改还应完成 PDS 时序检查。

## 许可证

本仓库采用 [MIT License](LICENSE)。
