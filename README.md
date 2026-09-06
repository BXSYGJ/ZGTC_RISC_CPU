# ZGTC_RISC_CPU

面向全国大学生 FPGA 创新设计竞赛紫光同创赛道选题一的 RISC-V CPU 项目。

2026-09-06实板更新：实验箱2的120 MHz RV32IM候选达到3.0129645923 CoreMark/MHz、361.5557510765 CoreMark、0.03515369481 CoreMark/LUT；10285 LUT、4808 FF、WNS +0.117 ns。两次重新烧录后的4000轮性能运行结果完全一致，另一次4000轮验证种子CRC通过，计分区均超过11秒。该数值硬指标已满足；全项目验收、长期稳定性和三项物理极限仍未完成。 原始采集、复测与资源折衷见 `cpu/docs/HARDWARE_120MHZ_TARGET.md`。以下较早阶段数据保留为历史记录，不替代此最新结果。

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

默认关闭的I-cache提前响应实验已取得162 MHz同板同固件实测：0.51867635 CoreMark/MHz、0.01741102 CoreMark/LUT，分别提高41.5664%和39.3663%，代价是LUT从4751增加到4826。候选两次性能运行及一次验证种子均通过，基线第二次采集受网关回放污染已拒绝，详见 `cpu/docs/FAST_ICACHE_HIT.md`。

历史阶段（12:39）：当时尚未达到120 MHz下至少3.0 CoreMark/MHz。 原RV32I提前响应配置为0.51532210 CoreMark/MHz；定位软件乘法热点后，默认关闭的RV32IM候选取得1.24895992 CoreMark/MHz、0.02978442 CoreMark/LUT，5032 LUT及4 APM，120 MHz时序闭合。两次4000迭代性能与一次验证种子实板均通过；ISA/机器码和历史对照不同，不是同固件消融，详见 `cpu/docs/M_EXTENSION.md`。自动门槛检查仍返回未达标；三项指标均未证明达到物理极限。

新增默认关闭的重叠取指路径：同一O2 RV32IM固件短仿真周期减少17.8568%，120 MHz PDS通过，LUT从5032增至5200、WNS从+0.583 ns降至+0.362 ns。尚未上板长测，不更新正式成绩；完整回归和进一步的编译/Cache容量筛选见 `cpu/docs/FETCH_OVERLAP.md`。

随后新增默认关闭的D-cache读提前响应。选择寄存加载模式后，120 MHz时序通过；同条件短仿真周期676030→625939，布局LUT5161→5238，WNS +0.476 ns。直接前递的两次120 MHz失败结果也保留，未用仿真冒充硬件成绩。流水线事件统计、源码快照与限制见 `cpu/docs/FAST_DCACHE_READ.md`。

最新默认关闭的数据请求重叠在64项BTB组合中进一步减少4.81728%短跑周期；同源码120 MHz实现通过，短跑工作量/LUT代理指标改善4.84544%。这些是本地验证，不替代实板成绩，设计、故障注入和性能/验证位流证据见 `cpu/docs/DATA_OVERLAP.md`。

乘法器最新内部修订使用并行半字乘积：同固件短跑再减少2.30679%周期，120 MHz通过，7300 LUT、4126 FF；完整回归与性能/验证位流已完成。仍未上板、不宣布3.0目标完成，证据见 `cpu/docs/MUL_REQUEST_CAPTURE.md`。

后续加载前递版本在120 MHz通过（WNS +0.076 ns）：同源码短跑周期减少4.93389%，增加161 LUT后工作率/LUT代理指标仍提高2.77301%；完整回归及外部ISA通过。新实板长测及3.0目标仍未完成，详见 `cpu/docs/CACHE_ADDRESS_BOUNDS.md`。

随后修订BTB地址和类型存储：64项同周期候选降至6935 LUT、4080 FF，120 MHz WNS +0.141 ns；性能/验证位流和完整回归通过，尚未上板。容量扩展与失败点见 `cpu/docs/BTB_ADDRESS_BOUNDS.md`。

进一步加入默认关闭的独立DCache写命中快速响应。128项BTB与写快路径组合在120 MHz通过性能/验证实现（7183 LUT、4130 FF、WNS +0.165 ns）；相对64项关闭写快路径基线，同固件单次性能短测周期减少5.71350%，单位LUT工作率代理指标提高2.39791%。这是两参数组合且尚未上板，不能作为正式CoreMark成绩；64项写快路径时序失败也完整保留。测试与证据见 `cpu/docs/FAST_DCACHE_WRITE.md`。

异常元数据复用后，128/256项BTB的2 KiB配置性能/验证实现均通过120 MHz；256项性能短测349485周期，7441 LUT、4227 FF、WNS +0.282 ns。资源效率并未同步改善，保留旧版更小面积快照。8 KiB配置的持续短测首次低于3.0目标对应周期预算，但其120 MHz实现WNS -2.026 ns被拒绝，仍未达标；具体时序与面积结论见 `cpu/docs/TRAP_VALUE_REUSE.md`。

独立I-cache容量候选：8 KiB指令侧/2 KiB数据侧的性能与验证实现均通过120 MHz（10285 LUT、4808 FF、WNS +0.117 ns）；同源码2/2 KiB控制为7441 LUT、WNS +0.282 ns。同固件单次性能周期349485→336486，减少3.71947%，但单位LUT工作率代理下降24.85700%，不能称三项全面改善。10轮平均333871.7周期仍略超3.0对应预算；8/4 KiB虽更快却时序失败。新增几何、读写入口契约、非对称集成及外部ISA验证已通过；旧缓存差分入口读写开关不同时的覆盖缺陷已修复并重新验证。尚无新实板长测，详见 `cpu/docs/ASYMMETRIC_CACHE.md`。

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
