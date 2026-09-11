# RV32I CPU 开发工程

## September 11, 2026 — provisional validation complete

The complete `experiments/full_fetch_commit_factored` version passes local 42-data/33-trigger ILA validation and remote hardware CoreMark V0/V1 bring-up at **153 MHz, 511.317879224 CoreMark, 3.341946923 CoreMark/MHz and 0.053811605896 CoreMark/LUT** (9502 complete LUT / 5079 FF, +0.021 ns setup WNS). The user explicitly accepts local ILA checking; remote ILA is not a gate. Further optimization is paused, AI acceleration remains deferred, and electrical/stability caveats remain documented.

Human guide: `docs/PROJECT_HANDOVER_153MHZ.md`. AI handoff: `docs/AI_HANDOFF_153MHZ.md`. Portable archive check from repository root: `python cpu/scripts/verify_153mhz_handoff.py`. The top-level RTL and older clock experiments are not the selected 153 MHz source.

All earlier entries below are historical; their running-state and no-upload statements do not override this handover.


## 当前状态

2026年9月9日更新：已冻结的 `build/wb-byte-retime-stage` 在157.5 MHz下通过性能/验证两套PDS与各自6000轮长测，取得本地资格：**501.065730222 CoreMark、3.181369715698 CoreMark/MHz、0.052994789024 CoreMark/LUT**，9455 LUT、WNS +0.026 ns。证据索引为 `build/wb-byte-retime-accepted500-baseline.json`，详见 `docs/WB_BYTE_RETIME.md` 和 `docs/ACCEPTANCE.md`。这不是160 MHz结论，也不是最新源码的实板测量。

当前最新门槛：保持500分基线的157.5 MHz与执行效率不降，插核总资源效率严格大于0.05 CoreMark/LUT，先完成ILA/GPIO与远程实测，再继续资源优化。完整109位触发版9942 LUT、WNS -0.114 ns；分离33位触发版9607 LUT、WNS -0.437 ns，均因时序失败而拒绝。完整触发种子1也以9904 LUT、WNS -0.274 ns失败，不再换种子。新的有效位扇出约束候选已通过逐拍对照、严格lint与双短测，正在PDS；原型配对6000轮继续运行，详见 `docs/REGFILE_VALID_FANOUT.md`；当前GPIO仿真2976检查、3次外部中断、5个错误变体通过。冻结基线不替换，不提前宣称实板或新计分通过。见 `docs/RESOURCE_MARGIN_ILA_PLAN.md`、`docs/ILA_REGFILE157500.md`。

原选题五项非AI任务及应用、最新源码实板、ILA分析、独立GPIO、电气依据与稳定性仍须逐项验收，AI按要求暂缓。完整目标见 `docs/COREMARK_500_PLAN.md`，验收边界见 `docs/ACCEPTANCE.md`。

## 历史优化记录

以下为各阶段记录。历史段落中的“当前”“正在运行”和较早分数不覆盖上述最新资格；具体候选以其独立证据为准。

加载/普通地址改为16位并行加法后，146.25 MHz候选以8689 LUT、5124 FF、WNS +0.107 ns通过原始物理报告与独立恢复审计；比完整父版本少154 LUT、少5 FF、裕量增加37 ps，双短测周期不变。约1016万正向组合用例、196次ISA和集成回归通过；原包装后处理异常及旧夹具失败记录保留。本候选自己的配对6000轮与严格来源审计现已通过：3.128078805 CoreMark/MHz、457.481525238 CoreMark、0.052650653152 CoreMark/LUT，同频资源效率提高1.7724%；这是本地RTL/PDS结果，尚非最新源实板成绩。148.5 MHz现已完成两套实际PDS（8677 LUT、5117 FF、WNS +0.066 ns）和双短测；双6000轮及严格配对审计现已通过：3.128078805 CoreMark/MHz、464.519702549 CoreMark、0.053534597505 CoreMark/LUT（本地RTL/PDS，尚非新版实板），详见`docs/CLOCK148500_CARRY16.md`。见 `docs/LOAD_ADDRESS_CARRY16.md`；生产RTL不变，本轮不上传GitHub。

取指地址选择器的146.25 MHz隔离工程已完成配对PDS与双6000轮长测：8843 LUT、5129 FF、WNS +0.070 ns。本地RTL投影3.1280788050 CoreMark/MHz、457.4815252381 CoreMark、0.05173374706 CoreMark/LUT；相较144 MHz完整基线，执行效率不变、吞吐增加1.5625%、资源效率下降0.92976%，保留8626 LUT基线而非宣称三指标全胜。双CRC、计分时长和实际来源绑定审计通过，首次日志节流预算不足的失败保留；不是实板成绩。见 `docs/CLOCK146250_FETCH_ADDRESS_SELECT.md`、`docs/FETCH_ADDRESS_SELECT.md`；生产RTL不变，本轮不上传GitHub。

替换路选择复用采样有效位后，144 MHz候选降至8639 LUT、5126 FF，比上一失败版少844 LUT，但WNS -0.765 ns仍失败，不采用。11项缓存测试、52个变异拒绝、196次ISA、双短测、SoC及来源审计通过；周期未变，没有新CoreMark成绩。见 `docs/CACHE_VALID_REUSE.md`；下一步检查取指地址选择器的中断/背压依赖，生产RTL与GitHub不变。

I/D缓存共同提前采样有效位完成10项缓存测试、44个变异拒绝、196次ISA、双短测和SoC重放，但144 MHz PDS以9483 LUT、5147 FF、WNS -1.212 ns失败，较D-cache单独采样父工程多734 LUT，不采用、不启动新长测。审计与反例通过只证明失败证据一致。见 `docs/CACHE_VALID_BOTH.md`；生产RTL与GitHub不变。

按ready采样有效位的候选通过144 MHz：8749 LUT、5154 FF、WNS +0.148 ns；相对连续预读版恢复时序通过，但相对8707 LUT父工程仍多42 LUT，短测周期不变，尚无新配对长测或板测。后续146.25 MHz独立工程完成双短测，但PDS以8701 LUT、5160 FF、WNS -0.231 ns失败，不采用、不启动配对长测；详见 `docs/CLOCK146250_VALID_ENABLE.md`。见 `docs/CACHE_VALID_ENABLE.md`。不上传GitHub。

I-cache填充碰撞比较隔离完成独立差分、196次ISA、双短测和GPIO/UART两种SoC固件的4对等周期重放，但144 MHz实现为8612 LUT、5127 FF、WNS -0.050 ns；少14 LUT但时序失败，不采用、不产生新计分或实板成绩。详见 `docs/READONLY_FILL_COLLISION.md`。生产版本和GitHub不变。

零偏移加载地址旁路使两种十轮CoreMark分别少28200/29290周期（-0.864366%/-0.895620%），5263360次定向比较、真实指针固件及196次外部ISA通过，但单独版144 MHz时序差65 ps；按实际乘法关键路径组合进位保存后，独立144 MHz实现恢复通过（8725 LUT、5128 FF、WNS +0.163 ns），保持短测收益并另跑196次ISA。组合配对位流已通过，自己的双种子6000轮长测正在运行，不将旧完整分数套入新资源数。见 `docs/LOAD_USE_ZERO_OFFSET.md`。

进一步的BEQ/BNE专用前递在141.75 MHz取得8526 LUT、5123 FF、WNS +0.193 ns；2105344次定向比较、196次外部ISA及CPU/SoC回归通过。两种十轮CoreMark周期不变，但SoC增加21周期，不宣称所有工作负载无代价；该新核心尚无独立双种子6000轮成绩。仅更换PLL的144 MHz性能PDS也通过（8634 LUT、5134 FF、WNS +0.210 ns），四频点厂商PLL模型与双短测通过；独立6000轮性能和验证均通过，RTL投影3.072866512 CoreMark/MHz、0.051250032 CoreMark/LUT；尚未实板。见 `docs/LOAD_USE_EQUALITY_BYPASS.md`、`docs/CLOCK144.md`。

本轮新增四个独立候选完成135 MHz时序、CPU/SoC及合计784次外部ISA核验：仅压缩LRU的分支专用前递组合为8640 LUT、5125 FF、WNS +0.361 ns；增加乘法进位保存并未进一步改善该组合的资源与时序。随后该LRU组合的实际141.75 MHz性能/验证两份PDS位流均通过（8662 LUT、5138 FF、WNS +0.033 ns）。两份独立绑定的6000轮RTL长测均通过（1952574242/1957402139周期），本候选仿真投影3.072866512 CoreMark/MHz、0.050286173 CoreMark/LUT；尚未实板，不上传GitHub。见 `docs/MUL_CARRY_SAVE.md`、`docs/CLOCK141750.md`。

本轮完成双种子非侵入退休跟踪，并实现分支专用加载前递：相对全停顿版，十轮性能少132099周期，但仍比原无停顿版多1.9615%，不宣称执行效率全面提升。候选135 MHz种子1通过（9271 LUT、5724 FF、WNS +0.119 ns），关键路径转到乘法结果；2105344次定向比较、196次外部ISA及相应拒绝控制通过。尚无该候选6000轮长测、配对位流或实板成绩，生产输入与GitHub不变。见 `docs/LOAD_USE_PROFILE.md`、`docs/LOAD_USE_BRANCH_BYPASS.md`。

关键路径后续隔离验证：缓存碰撞分解与两种并行前递核心均保持短测拍数，但135 MHz种子1分别为WNS -0.192/-0.279/-0.345 ns，未采用；三候选合计588次ISA及24个拒绝控制已审计。既有全局加载停顿参数的十轮执行代价为+6.08993%，短跑代理值约2.94585，不是正式分数，下一步先分类加载依赖再研究选择性停顿。生产源不变、不上传GitHub。详见 `docs/CACHE_COLLISION_FORWARD.md`、`docs/FORWARD_PARALLEL.md`、`docs/LOAD_USE_COST.md`。

LRU存储隔离实验完成：直接数组原生映射将576个LRU触发器替换为576位小型RAM，功能差分、短仿真及外部ISA保持基线执行拍数；但135 MHz种子1/7/5均时序失败（最佳仍差0.010 ns）。仅压缩I-cache的组合也失败，未产生新合格分数，生产输入不变、不上传GitHub。详见 `docs/CACHE_LRU_STORAGE.md`。

同步可写数据缓存H1候选在135 MHz/种子7通过：7437 LUT、4934 FF、WNS +0.014 ns，比通用H1少690 LUT。80种差分、13个功能拒绝、CPU集成及196次外部ISA通过；性能/验证位流配对与两份独立绑定本版的6000轮长仿真均通过。仅仿真投影为3.082968316 CoreMark/MHz、0.055963523 CoreMark/LUT，资源效率较通用H1提升9.2779%，完整执行拍数不变；尚未实板确认，不改生产输入，不上传GitHub。详见 `docs/CACHE_SYNCHRONOUS_WRITABLE.md`。

同步缓存H3组合在135 MHz/种子1取得7528 LUT、4930 FF、WNS +0.094 ns，性能/验证位流配对、196次ISA及两份独立6000轮长仿真均通过。仅仿真投影为3.093382502 CoreMark/MHz、0.055473783 CoreMark/LUT；相对H1执行效率提高0.337797%，资源效率降低0.875106%，不能称三指标全面改善，尚未实板确认。详见 `docs/SYNCHRONOUS_WRITABLE_H3.md`。

指令缓存16/32 KiB扩容已完成容量、CPU/SoC及392次外部ISA正例核验；10轮性能拍数分别降低1.224483%/1.412202%，但135 MHz种子1分别为9260/13610 LUT、WNS -0.191/-0.769 ns，未取得新的合格分数。已基于实际路径开始隔离MMIO载荷使能实验，生产RTL不变。详见 `docs/INSTRUCTION_CACHE_CAPACITY.md`。

MMIO载荷使能优化与16 KiB指令缓存组合在135 MHz取得9220 LUT、5726 FF、WNS +0.117 ns；性能/验证PDS配对及各自6000轮长仿真均已核验通过。仅仿真投影3.133303445 CoreMark/MHz、0.045878087 CoreMark/LUT；相对8 KiB H3执行效率提高1.290527%，资源效率降低17.297713%，仍满足0.031模型门槛，尚未实板。8 KiB同改动种子1未通过时序，不作泛化。详见 `docs/MMIO_READY_PAYLOAD.md`。

后续顺序PC预计算两候选完成69024个定向边界/优先级检查、11个编译故障拒绝、CPU/SoC和392次外部ISA核验，短测拍数不变；但135 MHz种子1的WNS分别为-0.034/-0.021 ns，均未采用。完整记录见 `docs/FETCH_PC_PRECOMPUTE.md`，不把局部逻辑调整或失败布局称为新性能成绩。

通用H1/C2完整135 MHz性能/验证6000轮通过：执行拍数与旧分立H1相同，8127 LUT下资源效率仿真投影0.05121209827（提高0.66445%），执行效率投影3.0829683161 CoreMark/MHz。标签提前读取实验保持命中拍数；只读/双缓存版本均因135 MHz时序失败而拒绝。全部隔离、未板测、不上传GitHub。详见 `docs/CACHE_TAG_PIPELINE.md`。

局部历史宽度筛选：六组H/C组合完成同固件短测；H3/C2完整6000轮性能对照再少6552000周期（0.337%），但135 MHz增加145 LUT、资源效率仿真投影下降约1.410%，不宣称全面改善。通用H1与H3的135 MHz性能/验证位流均通过（8127/8326 LUT）；H2种子1/7各差5 ps，种子5差27 ps，三者均拒绝。H2/H3共392次外部ISA通过；H3完整6000轮验证及独立绑定通过，本轮任务已全部终结，未板测、未修改生产输入、不上传GitHub。见 `docs/BTB_HISTORY_WIDTH.md`。

局部分支历史隔离候选：同固件6000轮性能RTL仿真1980380679→1946176342周期（减少1.727%，同频吞吐提高1.758%），CRC与退休指令相同，两端各自重新绑定合格PDS输入。132/135 MHz种子7性能、验证位流均通过，分别8063/8181 LUT、WNS +0.071/+0.026 ns；135 MHz种子1失败保留。完整6000轮validation仿真也通过；本轮任务全部终态。CPU差分与196次外部ISA通过；未替换生产BTB、未板测、不更新正式成绩，也不上传GitHub。见 `docs/BTB_LOCAL_HISTORY.md`。

隔离优化记录：单热ALU选择候选的53440组定向比较、六个运行变异及两种CoreMark短测通过，执行拍数不变；但132/135 MHz均时序失败且LUT增加，故不采用。20份生产输入保持原合格版本，不上传GitHub。见 `docs/ALU_ONEHOT_OUTPUT.md`。

当前本地合格候选：同步I-cache、Cache扇出32及保留ALU高段预计算版（680F03DF / 47E2A544），132 MHz/种子7为8090 LUT、5021 FF、WNS +0.102 ns；135 MHz/种子1为8222 LUT、4989 FF、WNS +0.003 ns。各自性能与验证6000轮固件的位流均已本地通过，20份输入和原始报告重新核验；18 DRM、4 APM。全回归和196次外部ISA通过，两种短测周期不变。135 MHz仅3 ps裕量，不等于长期稳定性；尚未板测，不更新正式CoreMark/LUT。旧同步Cache时序失败和D66、AC24结果保留为历史记录。后续只在用户明确要求时上传GitHub。详见 `docs/ALU_KEPT_PRECOMPUTE.md`。

只读Cache裁剪候选的132 MHz/种子1性能与验证位流均已本地通过：9236 LUT、5064 FF、WNS +0.082 ns；相对同条件C3少1041 LUT（约10.13%），多28 FF，裕量增加0.051 ns。完整回归、32种对照、13个运行控制及196次外部ISA通过，短测周期不变；三组135 MHz仍失败。全部本地任务终态，尚未上板，不更新正式CoreMark/LUT。本轮不上传GitHub。见 `docs/CACHE_READONLY_WRITEBACK.md`。

本地已测更新：折叠BTB与分段ALU版在132 MHz完成两次性能6000轮及一次验证6000轮，两次性能UART逐字节一致。执行效率3.0297205298 CoreMark/MHz（较上一132 MHz +0.5559642%），吞吐399.9231099346 CoreMark；资源效率0.03862871727 CoreMark/LUT（-0.0170873%，仍高于0.031）。10353 LUT、5023 FF、WNS +0.103 ns；主频不变，不能称三指标全部改善。完整回归和外部ISA测试集合通过，135 MHz仍未过时序。设备已释放，本轮不上传GitHub；证据见 `docs/HARDWARE_132MHZ_CARRY_SELECT.md`。以下按阶段保留历史记录，不替代本次绑定源码的结果。

当前源ILA：独立Target132Kept配置已原生确认109路、1024深度，132 MHz/种子7性能与验证插核均通过（9084 LUT、6876 FF、WNS +0.095 ns）。Windows/WSL各32项分析测试、67项PowerShell契约通过；两份位流均已终态并通过成对审计，尚无本版实板波形。见 `docs/ILA_TARGET132_KEPT.md`。

历史Target132Carry源ILA进度：Target132Carry的109路映射、专用分析语义和拒绝测试完成；默认/种子1/种子7的132 MHz插核实现均失败，最好WNS -0.082 ns，均未烧录，不影响已测非插核成绩。43项PowerShell契约、21项ILA分析、8项报告及6项频率门槛测试通过；下一步考察独立地址生成路径。见 `docs/ILA_TARGET132_CARRY.md`。

132 MHz实板更新：实验箱2完成两次性能6000轮及一次验证6000轮，执行效率3.0129694974 CoreMark/MHz、吞吐397.7119736614 CoreMark、资源效率0.03863531899 CoreMark/LUT。10294 LUT、5041 FF、4 APM，WNS +0.001 ns；相对已测126 MHz，频率/吞吐提高4.7619%、资源效率提高3.8867%，执行效率不变，增加86 LUT和234 FF。极小正时序裕量不等于长期稳定性或物理极限。设备已释放，未追加上传GitHub。详见 `docs/HARDWARE_132MHZ.md` 和 `docs/CACHE_ADDRESS_FANOUT.md`。

历史筛选：MMIO载荷、除法余数清零实验均未取得联合优势，已隔离；上一轮结束时曾恢复全部20份126 MHz生产输入。本轮在此基础上继续修改M单元与PLL，不能沿用“当前全部恢复”的说法。

这是赛题一的实际 CPU 工程，不是原流水灯的改名。CPU、缓存和外设已完成集成仿真，Windows PDS 已生成 CPU 位流，RemoteLab 实板串口已返回 `ZSOC PASS`。完整自检证据及尚未覆盖的范围见 `docs/HARDWARE_SELFTEST.md`。

2026-09-06实板更新：实验箱2的120 MHz RV32IM候选达到3.0129645923 CoreMark/MHz、361.5557510765 CoreMark、0.03515369481 CoreMark/LUT；10285 LUT、4808 FF、WNS +0.117 ns。两次重新烧录后的4000轮性能运行结果完全一致，另一次4000轮验证种子CRC通过，计分区均超过11秒。该数值硬指标已满足；全项目验收、长期稳定性和三项物理极限仍未完成。 完整证据见 `docs/HARDWARE_120MHZ_TARGET.md`；编译式仿真与失败边界见 `docs/COMPILED_SIMULATION.md`。下列实验条目是按时间推进的历史快照。

## 当前架构

126 MHz 实板更新：同一实验箱2完成两次性能6000轮和一次验证6000轮，3.0129694974 CoreMark/MHz、379.6341566767 CoreMark、0.03718986645 CoreMark/LUT；10208 LUT、4807 FF、4 APM，WNS +0.128 ns。相对上一实板120 MHz前递版，主频提高5%、资源效率提高约4.60%，增加39 LUT；执行效率微差不算结构收益。原120 MHz达标记录保留，物理极限和全项目验收仍未完成。 实板证据见 `docs/HARDWARE_126MHZ.md`，Cache结构与失败频点见 `docs/CACHE_LOOKUP_DATA.md`；未上传GitHub。

后续实板优化：加载前递的数据与执行资格解耦后，120 MHz执行效率保持3.0129645923 CoreMark/MHz，LUT从10285降至10169、WNS提高到+0.191 ns；两次性能长测及一次验证长测通过，资源效率为0.03555470067 CoreMark/LUT，提高约1.14%。135 MHz实现未通过时序，不作为新成绩。证据与新版本仍缺的ILA等验收见 `docs/FORWARD_DATA_QUALIFICATION.md`；未自动上传GitHub。下列较早配置保留历史含义。

执行效率候选依次加入提前 I-cache 响应、标准可选 M 扩展、重叠取指、提前 D-cache 读响应和 EX 提前数据请求；各功能开关默认关闭。最新内部修订减少 MUL/MULHU 响应等待并精简非加载前递资格，小缓存短跑571191周期、5398 LUT、120 MHz WNS +0.475 ns；大缓存/展开组合449230周期、7175 LUT、WNS +0.445 ns。均为本地验证，不是新实板成绩，详见 `docs/MUL_EARLY_RESPONSE.md`。历史提前访存对照和编译筛选分别见 `docs/EARLY_DATA_REQUEST.md`、`docs/COMPILER_CACHE_SCREEN.md`。

新增默认关闭的数据请求重叠：在旧响应完成的同一拍接受下一请求，仍只保留一笔未完成事务。64 项 BTB 同固件短跑周期423289→402898，120 MHz同源码实现7293→7308 LUT，WNS +0.432 ns；短跑工作量/LUT代理指标改善约4.84544%。尚无新实板长测，详见 `docs/DATA_OVERLAP.md`，不宣布3.0目标完成。

随后将乘法器改为请求拍锁存并行半字乘积，避免直接提前32×32级联导致的时序失败。短跑402898→393604周期，120 MHz实现7308→7300 LUT、4232→4126 FF、WNS +0.528 ns；最终完整回归、14组精确中断、外部ISA及性能/验证位流均通过。未上板，不更新正式成绩，详见 `docs/MUL_REQUEST_CAPTURE.md`。

缓存地址边界、分指令类握手、MMIO请求寄存和响应数据保持修订使直接加载前递在120 MHz通过：同源码B1/B0短跑393604→374184周期，LUT为6846/7007、FF为4138/4146，工作率/LUT代理指标提高2.77301%，B0 WNS仅+0.076 ns。完整回归及外部ISA通过；未上板，不更新正式成绩或宣布3.0达标，见 `docs/CACHE_ADDRESS_BOUNDS.md`。

预测表地址范围压缩及类型存储修订继续降低64项候选面积：120 MHz、6935 LUT、4080 FF、WNS +0.141 ns，短跑仍374184周期；性能/验证位流、最终回归和外部ISA已通过。256项及大Cache的时序失败保留，不冒充新实板成绩，详见 `docs/BTB_ADDRESS_BOUNDS.md`。

新增可选LTO、链接松弛及1—10次持续执行短测，默认编译行为不变。已测组合均未超过原O3 + unroll；10次性能平均373566.3周期/迭代，仍不足以满足3.0目标。新增清单/固件一致性防护和14项测试，证据与使用边界见 `docs/COMPILER_OPTIONS.md`。

新增独立DCache写命中快速响应，默认关闭，保留旧值响应、字节掩码、背压和复位语义。128项BTB + 写快路径组合通过120 MHz性能/验证实现：7183 LUT、4130 FF、WNS +0.165 ns；同固件单次性能短测由64项关闭写快路径基线374184降至352805周期（减少5.71350%），单位LUT工作率代理指标提高2.39791%。这是两参数组合而非单变量消融，64项仅开启写快路径的实现WNS -0.082 ns，不能采用。完整回归、扩展定向测试与外部RV32I/M通过，尚无新实板成绩；详见 `docs/FAST_DCACHE_WRITE.md`。

进一步复用MEM级异常元数据，新增3249项定向检查及八个错误来源反例。128/256项BTB、每侧2 KiB的性能/验证实现均通过120 MHz，分别为7221/7441 LUT、4143/4227 FF、WNS +0.256/+0.282 ns；性能短测为352805/349485周期。较快执行或较大时序裕量伴随资源效率下降，保留此前较小面积快照，不宣称全面替代。每侧8 KiB的10迭代性能平均332794.9周期，但该8 KiB实现WNS -2.026 ns被拒绝，不能算3.0达标；实现与验收边界见 `docs/TRAP_VALUE_REUSE.md`。

独立I-cache容量候选：8 KiB指令侧/2 KiB数据侧的性能与验证实现均通过120 MHz（10285 LUT、4808 FF、WNS +0.117 ns）；同源码2/2 KiB控制为7441 LUT、WNS +0.282 ns。同固件单次性能周期349485→336486，减少3.71947%，但单位LUT工作率代理下降24.85700%，不能称三项全面改善。10轮平均333871.7周期仍略超3.0对应预算；8/4 KiB虽更快却时序失败。新增几何、读写入口契约、非对称集成及外部ISA验证已通过；旧缓存差分入口读写开关不同时的覆盖缺陷已修复并重新验证。接口兼容性、失败路径与全部证据见 `docs/ASYMMETRIC_CACHE.md`，不替代实板成绩。

工程总报告见 `docs/FINAL_REPORT.md`，快照打包与迁移校验见 `docs/DELIVERY.md`；当前仍有明确的最终验收缺口，不能把打包成功当作全部完成。

`取指请求 → IF 缓冲 → ID 译码/寄存器读取 → EX 执行/前递 → MEM 访存与控制提交 → WB 寄存器写回`

- 五级按序流水线；寄存器 x0 恒为零，32 位整数运算与字节/半字/字访问。
- 指令/数据接口解耦，可分别等待接受和响应。MEM 阶段阻塞时，年轻指令暂停而不重复发起存储操作。
- MEM、WB 前递到 EX；停顿时保存已前递值，防止来源指令退休后数据丢失。
- 可选load寄存前递实验默认关闭；162 MHz对照实测和216 MHz失败时序见 `docs/LOAD_FORWARD_EXPERIMENT.md`，实验未替代默认性能基线。
- 默认16项、可配置2–256项的直接映射 BTB 和两位饱和计数器；MEM按序更新，错误预测冲刷年轻指令，旧取指请求仍必须完成后丢弃。64/128项通过本地回归及120 MHz PDS，资源和执行效率折衷见 `docs/BTB_CAPACITY.md`，尚非新实板成绩。
- M-mode 精确异常、Zicsr、MRET、三类中断输入、直接/向量 mtvec、mcycle/minstret。仅实现 M-mode，不声称支持 U/S 模式、MMU、PMP 或所有可选扩展。
- FENCE 按阻塞、按序数据访问的约束实现；FENCE.I 排空前端，等待数据 Cache 写回及两级 Cache 失效，然后冲刷 BTB/流水线。已通过自修改代码测试。
- WFI 当前作为可合法唤醒的空操作，不实现时钟门控；M 扩展仅在 ENABLE_M=1 时开启；默认关闭的 M 及未实现的 A/C/F 指令产生非法指令异常。

存储接口细节见 `docs/BUS.md`，完整要求与未完成项见 `docs/ACCEPTANCE.md`。
原子性能快照、可复现预测器开关和首轮消融证据见 `docs/PERFORMANCE_MONITOR.md`；该监测逻辑在首轮实板基线后加入，不能沿用旧位流的资源计分。

## 存储系统

时钟配置与防止硬件/固件频率不一致的检查见 `docs/CLOCKING.md`。默认162 MHz基线为59.3542 CoreMark；最高已验证候选为显式LOAD_USE_BUBBLE=1的180 MHz、65.9430 CoreMark，箱3五次运行通过，见 `docs/HARDWARE_180MHZ.md`。保留箱5低频与默认基线证据，不等于绝对最高可达频率或长期稳定性已测完。

`rv32_memory_system` 集成两路组相联 I-Cache 与 D-Cache、完整突发锁定的轮转仲裁器、可综合片上 RAM 和不缓存的 MMIO 转接端口。D-Cache 使用写回/写分配及逐字节写使能，填充失败不安装有效行，写回失败保留脏行供重试。默认每个 Cache 512 字节，RAM 16 KiB，均参数化。

目前未接 DDR。实际 `rv32_soc` 使用 64 KiB 片上 RAM，连接带 FIFO 的 UART、GPIO、64 位定时器、软件中断和状态寄存器；独立 CPU 测试仍使用测试邮箱。维护错误导致粘滞故障停机，禁止 FENCE.I 退休及年轻指令副作用，复位恢复。地址与板级区别见 `docs/PERIPHERALS.md`。

## 验证

首先按 `docs/TOOLCHAIN.md` 构建真实的 `riscv32-unknown-elf-gcc` 10.2.0。工程经本机工具链清单定位编译器，缺失或目标不符会报错，不再静默使用 RV64 multilib。已完成源码构建、RV32 库检查及完整回归。

外部指令验证独立执行 `pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1`：固定上游41个 RV32UI 程序、四种配置共164次通过，另有四个拒绝控制。具体适配范围和未对齐访问排除理由见 `docs/EXTERNAL_ISA.md`，不称作官方认证。

在仓库根目录执行：

```powershell
pwsh -NoProfile -File cpu/scripts/validate.ps1
```

要求 PowerShell 7、WSL Ubuntu-22.04、Icarus、Verilator、Python 3、RISC-V bare-metal GCC/binutils。构建脚本使用 multilib GCC 的 `-march=rv32i -mabi=ilp32`，产物已核实为 ELF32、little-endian、RISC-V，不是 RV64 固件。

验证包括：

1. 译码/ALU、BTB、machine CSR 自检。
2. 汇编定向测试与可复现随机指令，预测器开关各 3 个随机总线延迟种子。
3. 独立 Python 模型逐条检查退休指令、寄存器值、精确异常及最终完整存储器；带缓存 CPU 使用两种 Cache 容量、预测器开关共四种配置，结束前先完整写回。
4. 修改 PC、指令、写回值、陷入记录的变异测试，确认检查器确实拒绝错误。
5. Verilator `--lint-only --Wall`。
6. Cache 随机读写与最终内存对比、读写错误、早/晚 last、维护失败重试；突发轮转公平性、归属锁定和应答反压验证。
7. FIFO、UART 全 256 字节收发、波特率偏差、帧错误/溢出、MMIO 反压及副作用检查。
8. 真实 C 启动清零被预先污染的 BSS，验证初始数据、软件/定时/GPIO 外部中断、串口引脚级收发，以及维护错误停机。

## Windows PDS 实现

```powershell
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile Board
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile RemoteLab
```

两条命令是不同 UART 接线环境的备选项，不需要连续运行。Board 使用板载 B24/C24；RemoteLab 使用网站仪器明确标出的 AC26/AB26。脚本使用独立构建目录、固件镜像快照，执行 ADS 综合、布局布线、时序与位流生成，拒绝未通过时序的结果。当前入口编译的是交互式 SoC 自检固件，不是 CoreMark 或最终应用。

`build/pds-latest.json` 记录位流、固件 SHA-256、器件和 UART 配置。首次 Board 构建占用 3,735 LUT、16.5 个 DRM36K 等效块；27 MHz 约束下 setup 余量 22.869 ns，最差 hold 余量 0.101 ns。报告中的 70.5816 MHz 是工具估算，不是已上板验证主频。异步引脚和输出接口未作外部同步时序签核；SCBV 提示仍保留，未猜测其值。

`build/core-tests.log` 保存汇总；`build/*.trace` 为退休/陷入记录，`build/*.memory` 为最终存储器；`build/core_selftest.dis` 可对照反汇编。以上生成物均不入库。

## 后续交付

CoreMark 两组种子已完成超过 20 秒的实板运行，CRC 全通过；27 MHz 起始基线为 9.8178 CoreMark、0.3636 CoreMark/MHz，原始证据和边界见 `docs/COREMARK_RESULTS.md`。CPU 波形应用已完成两次各256点实板采样、校验及不同输入解码，运行说明和证据见 `docs/SCOPE_APPLICATION.md`。Cache与预测器硬件消融已各配置重复两次，见 `docs/HARDWARE_CACHE_ABLATION.md`、`docs/HARDWARE_PREDICTOR_ABLATION.md`；原生JTAG ILA六个真实算法窗口及插核开销见 `docs/ILA_RESULTS.md`。仍需最高实测频率、长期稳定性和进一步优化，不代表所有 ISA、Cache 边界和比赛要求均已验收。AI 加速按用户要求暂缓，其余范围保持不变。

独立直接分支提前恢复候选完成196次ISA、随机/精确中断/SoC回归及双短测，性能/验证周期降低1.6708%/1.7059%；实际148.5 MHz PDS为8798 LUT、5120 FF、WNS -0.176 ns，仍拒绝，不替换已合格carry16基线，不公布候选完整分数或上传GitHub。详见 `docs/EARLY_DIRECT_REDIRECT.md`。

8位分组地址进位候选在不改变直接分支方案周期和退休轨迹的前提下通过约1016万算术组合、196次ISA及8次SoC回放；实际148.5 MHz为8825 LUT、5121 FF、WNS -0.091 ns，仍拒绝。独立146.25 MHz两个实际布局种子分别以WNS -0.036/-0.191 ns拒绝，均不采用。后续RAM分支地址域单行候选已通过8192个地址探测、24组原/新交接配对、8种严格lint、2次缓存CPU独立参考和相同双短测；新196项ISA与8次SoC已通过，但实际146.25 MHz为8737 LUT、5121 FF、WNS -0.167 ns，拒绝，见 `docs/DCACHE_RAM_DOMAIN.md`。随后独立有效位分组候选通过219399次定向检查、14组缓存配对、原196项ISA及额外I9/D6目标98对196次、8次SoC和相同双短测；实际为8771 LUT、5132 FF、WNS -0.036 ns，仍拒绝，见 `docs/DCACHE_VALID_BANKS.md`。没有新候选完整分数。见 `docs/EARLY_DIRECT_CARRY8.md`；生产RTL不替换，不自动上传GitHub。

缓存入口错误分类寄存重排候选通过16组边界/错误配对、14组完整缓存配对、常规196项ISA、实际I9/D6额外98对196次、4组SoC配对及周期完全相同的双短测；实际146.25 MHz为8989 LUT、5170 FF、WNS -0.194 ns，仍拒绝。最差路径转到地址高位的MMIO/RAM路由控制，见 `docs/CACHE_ERROR_RETIME.md`。不替换合格基线，不产生新完整分数，不自动上传GitHub。

MMIO影子请求候选通过60组协议配对、24组原交接配对、常规196次ISA、目标配置98对196次ISA、8次SoC及周期不变的双短测；实际146.25 MHz为8876 LUT、5177 FF、WNS -0.292 ns，时序门禁拒绝。最差路径转到早期分支比较及I-cache控制，见 `docs/MMIO_SHADOW_ACCEPT.md`。不替换合格基线、不产生新完整分数、不自动上传GitHub。

早期分支并行字节比较候选通过786624组比较输入、7424项分支场景、常规196次ISA、目标98对196次ISA、8次SoC及周期不变的双短测；实际146.25 MHz为8961 LUT、5176 FF、WNS -0.372 ns，拒绝。原生比较结构确实保留，但最差路径延伸至PC更新进位链，见 `docs/EARLY_COMPARE_BYTE.md`。不替换合格基线、不产生新完整分数。

陷阱向量结果边界候选从实际网表确认并隔离了重定向选择与向量加法链，原/新589824项向量检查、常规196次ISA、目标98对196次ISA、8次SoC及周期不变的双短测通过；实际146.25 MHz为8933 LUT、5169 FF、WNS -0.109 ns。相对父候选减少28 LUT、7 FF、裕量改善0.263 ns，但仍拒绝资格，见 `docs/TRAP_VECTOR_BOUNDARY.md`。不替换合格基线、不产生新完整分数。

整字加载地址直接前递候选完成两种6000轮完整仿真及同固件实际PDS来源绑定：146.25 MHz、8895 LUT、5185 FF、WNS +0.055 ns，性能/验证分别1885980108/1888935654周期，CRC均正确且各超过10秒。仅就本地RTL/PDS而言为3.181369716 CoreMark/MHz、465.275321 CoreMark、0.052307512 CoreMark/LUT；相对既有148.5 MHz carry16基线执行效率提高1.7036%、吞吐提高0.1627%，但资源效率下降2.2921%，不是全面优于旧基线。见 `docs/WORD_LOAD_ADDRESS.md`。生产RTL不替换，没有新上板结论，不自动推送GitHub。

以已通过的3.181370版本CPU为基础，151.2 MHz定时比较拆分布局种子2的双固件PDS及各自绑定的6000轮完整仿真均已通过：8979 LUT、5176 FF、WNS +0.033 ns；本地RTL/PDS为3.181369716 CoreMark/MHz、481.023101 CoreMark、0.053572013 CoreMark/LUT，三项门槛同时达标。双种子CRC、超过10秒的计时间隔、完整周期/退休/缓存事件及34项物理、28项完整结果拒绝控制通过；此前纯升频和布局种子1的失败报告保留。见 `docs/TIMER_COMPARE_SPLIT.md`，接受基线为 `build/timer-compare-split-seed2-accepted-baseline.json`。后续升频不得降低相对本版的任一效率，不替换生产RTL、不冒充实板结果、不自动推送GitHub。
