# ZGTC_RISC_CPU

> **当前活跃主线（2026-10-27）：`instrec_fpga/`** —— InstRec 8 类乐器识别在盘古 100Pro+（PG2L100H）上的
> 纯 FPGA 移植（I2S → DDR3 → Mel 引擎 → INT8 NPU → HDMI UI）。
> 恢复开发请先读 `instrec_fpga/docs/STATUS.md` 与仓库根 `AGENTS.md`；本文件以下内容为 RV32IM SoC 历史记录
> （200H 153 MHz/511 分为历史成绩；100H 可交付点为 120 MHz/383 分，见 `cpu/docs/MIGRATION_100H_20261025.md`）。

## September 11, 2026 — provisional validation complete

The complete `cpu/experiments/full_fetch_commit_factored` version passes local 42-data/33-trigger ILA validation and remote hardware CoreMark V0/V1 bring-up at **153 MHz, 511.317879224 CoreMark, 3.341946923 CoreMark/MHz and 0.053811605896 CoreMark/LUT** (9502 complete LUT / 5079 FF, +0.021 ns setup WNS). The user explicitly accepts local ILA checking; remote ILA is not a gate. Further optimization is paused, AI acceleration remains deferred, and electrical/stability caveats remain documented.

Human guide: `cpu/docs/PROJECT_HANDOVER_153MHZ.md`. AI handoff: `cpu/docs/AI_HANDOFF_153MHZ.md`. Portable archive check from repository root: `python cpu/scripts/verify_153mhz_handoff.py`. The top-level RTL and older clock experiments are not the selected 153 MHz source.

All earlier entries below are historical; their running-state and no-upload statements do not override this handover.


2026-09-07 WB匹配预译码实验已完成：8方法、1048576组状态转换、12组随机等待及24份逐字节相同的轨迹/内存、196次ISA逐案同周期核验通过；但144 MHz种子1为8658 LUT、5139 FF、WNS -0.046 ns，物理失败。新状态位移走原WB比较慢路径并不代表最终频率提高，当前保留完整配对的全偏移加载旁路基线。详见 `cpu/docs/WB_MATCH_PREDECODE.md`；生产RTL及GitHub不变。

2026-09-07操作数选择器对照已完成：优先选择/独热选择保持原双短测与196次ISA逐案结果；144 MHz种子1分别为8738 LUT、WNS +0.011 ns及8704 LUT、WNS -0.021 ns。前者仅多6 ps裕量但增加112 LUT，后者时序失败，不替换已完整配对的全偏移加载旁路版。定向矩阵、故障拒绝、CPU/SoC及严格lint证据与结构检查修正见 `cpu/docs/LOAD_OPERAND_SELECT.md`。生产RTL及GitHub不变。

2026-09-07全偏移加载旁路完整配对已完成：144 MHz、8626 LUT、WNS +0.005 ns；自身6000轮性能/验证为1918110244/1921816141周期，双CRC和真实PDS绑定审计通过。本地RTL投影3.1280788050 CoreMark/MHz、450.4433479268 CoreMark、0.05221926129 CoreMark/LUT。相对零偏移CSA，同频执行效率提高0.914650%、资源效率提高2.072841%，但时序裕量下降；不是实板成绩。详见 `cpu/docs/LOAD_USE_ADDRESS_BYPASS.md`。后续优先选择/独热选择实验独立验证，本轮不上传GitHub。

2026-09-07全偏移加载旁路实验：普通加法版本144 MHz通过（8626 LUT、5123 FF、WNS +0.005 ns），相对零偏移CSA双种子十轮实际减少29238/30018周期；196次ISA及边界/错误响应检查通过，已启动独立完整配对，尚无本候选实板成绩。12位预计算版本功能正确但WNS -0.730 ns，保留为物理失败对照。见 `cpu/docs/LOAD_USE_ADDRESS_BYPASS.md`。本轮不上传GitHub。

2026-09-07零偏移CSA完整配对已完成：自身6000轮性能/验证分别1935654242/1939828139周期，双CRC及真实PDS绑定审计通过。144 MHz、8725 LUT的本地RTL投影为3.0997271464 CoreMark/MHz、0.05115882053 CoreMark/LUT；相对相等分支144 MHz版执行效率提高0.874123%，资源效率下降0.177974%，不是全面替代。见 `cpu/docs/LOAD_USE_ZERO_OFFSET.md`；不替代既有实板记录。

历史本地合格候选（同步Cache阶段）：同步I-cache、Cache扇出32及保留ALU高段预计算版（680F03DF / 47E2A544），132 MHz/种子7为8090 LUT、5021 FF、WNS +0.102 ns；135 MHz/种子1为8222 LUT、4989 FF、WNS +0.003 ns。各自性能与验证6000轮固件的位流均已本地通过，20份输入和原始报告重新核验；18 DRM、4 APM。全回归和196次外部ISA通过，两种短测周期不变。135 MHz仅3 ps裕量，不等于长期稳定性；尚未板测，不更新正式CoreMark/LUT。旧同步Cache时序失败和D66、AC24结果保留为历史记录。后续只在用户明确要求时上传GitHub。详见 `cpu/docs/ALU_KEPT_PRECOMPUTE.md`。

只读Cache裁剪候选的132 MHz/种子1性能与验证位流均已本地通过：9236 LUT、5064 FF、WNS +0.082 ns；相对同条件C3少1041 LUT（约10.13%），多28 FF，裕量增加0.051 ns。完整回归、32种对照、13个运行控制及196次外部ISA通过，短测周期不变；三组135 MHz仍失败。全部本地任务终态，尚未上板，不更新正式CoreMark/LUT。本轮不上传GitHub。见 `cpu/docs/CACHE_READONLY_WRITEBACK.md`。

本地已测更新：折叠BTB与分段ALU版在132 MHz完成两次性能6000轮及一次验证6000轮，两次性能UART逐字节一致。执行效率3.0297205298 CoreMark/MHz（较上一132 MHz +0.5559642%），吞吐399.9231099346 CoreMark；资源效率0.03862871727 CoreMark/LUT（-0.0170873%，仍高于0.031）。10353 LUT、5023 FF、WNS +0.103 ns；主频不变，不能称三指标全部改善。完整回归和外部ISA测试集合通过，135 MHz仍未过时序。设备已释放，本轮不上传GitHub；证据见 `cpu/docs/HARDWARE_132MHZ_CARRY_SELECT.md`。以下按阶段保留历史记录，不替代本次绑定源码的结果。

当前源ILA：独立Target132Kept配置已原生确认109路、1024深度，132 MHz/种子7性能与验证插核均通过（9084 LUT、6876 FF、WNS +0.095 ns）。Windows/WSL各32项分析测试、67项PowerShell契约通过；两份位流均已终态并通过成对审计，尚无本版实板波形。见 `cpu/docs/ILA_TARGET132_KEPT.md`。

历史Target132Carry源ILA进度：Target132Carry的109路映射、专用分析语义和拒绝测试完成；默认/种子1/种子7的132 MHz插核实现均失败，最好WNS -0.082 ns，均未烧录，不影响已测非插核成绩。43项PowerShell契约、21项ILA分析、8项报告及6项频率门槛测试通过；下一步考察独立地址生成路径。见 `cpu/docs/ILA_TARGET132_CARRY.md`。

132 MHz实板更新：实验箱2完成两次性能6000轮及一次验证6000轮，执行效率3.0129694974 CoreMark/MHz、吞吐397.7119736614 CoreMark、资源效率0.03863531899 CoreMark/LUT。10294 LUT、5041 FF、4 APM，WNS +0.001 ns；相对已测126 MHz，频率/吞吐提高4.7619%、资源效率提高3.8867%，执行效率不变，增加86 LUT和234 FF。极小正时序裕量不等于长期稳定性或物理极限。设备已释放，未追加上传GitHub。详见 `cpu/docs/HARDWARE_132MHZ.md` 和 `cpu/docs/CACHE_ADDRESS_FANOUT.md`。

历史筛选：MMIO载荷、除法余数清零实验均未取得联合优势，已隔离；上一轮结束时曾恢复全部20份126 MHz生产输入。本轮在此基础上继续修改M单元与PLL，不能沿用“当前全部恢复”的说法。

126 MHz 实板更新：同一实验箱2完成两次性能6000轮和一次验证6000轮，3.0129694974 CoreMark/MHz、379.6341566767 CoreMark、0.03718986645 CoreMark/LUT；10208 LUT、4807 FF、4 APM，WNS +0.128 ns。相对上一实板120 MHz前递版，主频提高5%、资源效率提高约4.60%，增加39 LUT；执行效率微差不算结构收益。原120 MHz达标记录保留，物理极限和全项目验收仍未完成。 详见 `cpu/docs/HARDWARE_126MHZ.md`；本轮不上传GitHub，以下按阶段保留历史记录。

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
