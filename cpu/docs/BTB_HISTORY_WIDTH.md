# 局部历史长度与计数器宽度筛选

日期：2026-09-07。本轮在 `BTB_LOCAL_HISTORY.md` 的一位历史、两位计数器候选上继续优化执行效率，同时检查相同135 MHz下的面积和时序。全部实验隔离，生产20份输入保持 `scripts/ila_target132_kept_sources.json`，不上传GitHub，不把仿真或PDS当作新实板成绩。

## 设计与范围

`experiments/btb_history_width/rv32_btb.sv` 增加两个实验参数：HISTORY_BITS=1/2/3，COUNTER_BITS=1/2。三位局部历史保存同一分支最近三次方向，因此索引的是8组计数器，不是3组。两位计数器保留弱/强置信度，一位计数器只保留上次训练结果。先训练旧历史对应的银行，再移入新结果；新分配、标签冲突或条件类型变化会初始化全部银行。接口、索引折叠、标签、目标、合法地址和对齐条件保持。

每项历史与计数器的抽象状态量为 H + C×2^H 位；这不包含标签、目标、有效位、条件类型，也不能直接换算成 FPGA LUT/FF。

## 单元和工具兼容性

`scripts/test_btb_history_width.py` 的独立模型覆盖3种历史×2种计数器×3种索引宽度×2种地址宽度×2种散列开关，共72组。每个16位地址配置2383条向量、32位配置2379条，覆盖饱和、交替及三位历史模式、标签冲突、条件类型切换、复位、失效、未对齐和越界。H1/C2参考模型与原测试的12组原始向量完全一致。

16个实际编译的错误变体被运行时比较拒绝；另保留两个在测试输入下外部输出等价的控制。最初把“无条件分支也移动历史”列为必拒绝反例是不正确的：合法两态输入下，无条件预测不查询该历史，而切回条件类型时会重新分配。因此它不应被包装成已发现的功能故障，也不据有限测试宣称所有四态输入都等价。越界目标反例进一步使用不同的低位目标，避免非法高位截断后恰与旧目标相同、错误被掩盖。

72组、16个拒绝变体及2个输出等价控制通过；六组H/C的严格Verilator lint也通过。计数器RAM保持不清零，复位只让有效位失效；统一异步复位使用方式消除了SYNCASYNCNET警告，没有增加lint豁免。新测试已接入 `scripts/validate.ps1`，入口通过PowerShell语法和UTF-8 BOM检查。本次不冒称重新跑完生产工程全部回归。

初版使用 `HISTORY_BITS'(pattern)` 的定宽转换；Icarus与Verilator接受，但本机PDS Fabric Compiler 2022.2-SP6.4在该位置给出Verilog-4005，并连带报告PATTERN_INDEX未声明。失败构建 `build/btb-history-width-h3-c2-stage/build/pds/20260907-120749-3d24c217` 保留，没有资源报告或位流。原模板保存在 `experiments/btb_history_width/sized_cast_rejected.sv`。

修订采用等价的 `pattern[HISTORY_BITS-1:0]` 常量位切片。重新通过全部单元和严格lint后，为三组C2建立新的portable阶段；六次同固件RTL短跑与对应初版UART逐字节相同。新写法已通过PDS实际编译、综合、映射和布局布线，不把初版语法失败算作时序失败。

## 相同固件十轮实测仿真

所有初版六组各跑performance和validation，18份编译输入仅BTB不同；固件、工具、其他硬件参数、CRC和退休指令均对照核验。H1/C2通用银行写法与上一轮分立银行写法UART完全一致。以下不是不少于10秒的成绩。

| H / C | 抽象状态位/项 | 性能周期 | 验证周期 | 相对旧H1/C2性能节省周期 |
| --- | ---: | ---: | ---: | ---: |
| 1 / 1 | 3 | 3333189 | 3330693 | -82116 |
| 1 / 2 | 5 | 3251073 | 3258866 | 0 |
| 2 / 1 | 6 | 3324130 | 3329903 | -73057 |
| 2 / 2 | 10 | 3246237 | 3248531 | 4836 |
| 3 / 1 | 11 | 3318361 | 3323086 | -67288 |
| 3 / 2 | 19 | 3239409 | 3247040 | 11664 |

C1三组变慢，因此本轮优先实现C2的三组；尚未测量C1的PDS面积/频率，不能据短测把它们从全局多指标最优集合中排除。H3/C2相对旧H1/C2短测少0.358774%的周期，这只是筛选证据，最终比较使用重新执行的同固件长测。

portable候选BTB SHA-256：

- H1/C2：`A747330DEBE365E2EF0733B0DA96A2FB0C219DDF2B827B9EE7682C9AC8B4AB6B`。
- H2/C2：`B922FF1758C8173019D4DB09A16627F2799E492EBCB73D07C4B06DBCE120DE60`。
- H3/C2：`826FE9F54C9460492FF6AE4E0A0BCF8C875E18AC4ED816203C9EEF7E2276D1C4`。

阶段为 `build/btb-history-width-hN-c2-portable-stage`。参数与来源记录在 `build/btb-history-width-portable-inputs.json`。

## 135 MHz 实现与取舍

以下均PG2L200H-6FBB676、6000轮固件、同一工具流程；只在种子列明确改变布局种子。完整原始报告、固件、位流、20份输入、顶层和种子重新核验。

| 候选 / 固件 | 种子 | 构建 | LUT | FF | WNS ns | 状态 |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| 旧分立H1/C2 / performance | 7 | 20260907-113004-a2173e97 | 8181 | 5009 | +0.026 | 旧合格对照 |
| 通用H1/C2 / performance | 7 | 20260907-121146-2f590aa4 | 8127 | 5014 | +0.027 | 本地通过 |
| 通用H1/C2 / validation | 7 | 20260907-122422-b9531dbb | 8127 | 5014 | +0.027 | 本地通过 |
| H2/C2 / performance | 7 | 20260907-121120-189eb52e | 8157 | 5023 | -0.005 | 拒绝 |
| H2/C2 / performance | 1 | 20260907-122358-b2309b90 | 8058 | 4993 | -0.005 | 拒绝 |
| H2/C2 / performance | 5 | 20260907-123444-873b6216 | 8095 | 5021 | -0.027 | 拒绝 |
| H3/C2 / performance | 7 | 20260907-121051-dd8cff31 | 8326 | 5070 | +0.058 | 本地通过 |
| H3/C2 / validation | 7 | 20260907-121933-1cb0ff5f | 8326 | 5070 | +0.058 | 本地通过 |

通用H1/C2相对旧分立实现少54 LUT、多5 FF；短测执行拍数不变。H3/C2相对旧分立实现多145 LUT、多61 FF；相对通用H1/C2多199 LUT、多56 FF。H3执行更快但面积更大，不能宣称三指标全面改善。H2的-0.005 ns不能四舍五入为通过，也不能把失败位流的135 MHz用作有效分数。种子5也以-0.027 ns终态失败，本轮H2的三种种子都不采用；这不证明所有布局或频率都不可行。

已终态实现均18 DRM、4 APM。原生综合内存报告确认H1/H2/H3分别有2/4/8组256×2模式计数器，历史为256×1/2/3；这里的银行数不是专用DRM块数。资源分母仍为布局后的CLMA+CLMS LUT，不重复加Distributed RAM。

H3性能位流SHA-256：`559619ABC9B67DC3C3DC19A366B0BF208F69C0B65F221B7FFEB4D9672C74CAF4`；验证：`29FF71250D5D399F1F6FA8D5E2CD35090098D7F4708583AF3914A532A8A82ED3`。通用H1性能：`545C27DFF194DEE84910F9287ACC12EA47BD7545BA1BDE0F354A32D3697D1432`；验证：`474B8F02B505991D0CA30CD8EA9338D3635C654823381D4C4602A3252228A8A1`。

## CPU 和外部 ISA

H2/C2、H3/C2分别通过完整的非对称缓存集成流程：预测器开关、三种I/D-cache几何、CPU轨迹与内存参考、SoC/UART、独立提前读写、旁路和严格板级lint。两者各164次RV32UI、32次RV32UM及8个拒绝控制通过，合计392次正例和16个拒绝。重新核验每份原始日志、固件、16份RTL、适配器和固定上游输入；这些测试的退休指令和周期与生产基线一致，不是完整ISA认证。

## 135 MHz 同固件完整性能长测

通用H1/C2完整135 MHz性能和验证均已通过独立源码/固件/PDS绑定：性能1946176342周期、1649428424退休，验证1951421059周期、1649775523退休；两种6000轮CRC均通过。性能与旧分立H1/C2周期相同，少54 LUT后的资源效率仿真投影为0.05121209827 CoreMark/LUT（提高0.66445%），执行效率投影3.0829683161 CoreMark/MHz。此处是本版重新仿真得到的投影，仍非实板成绩。

通用H1本轮性能构建：`build/btb-history-width-h1-c2-portable-stage/build/compiled/20260907-125619-06bc3b1e`；验证构建：`build/btb-history-width-h1-c2-portable-stage/build/compiled/20260907-125643-f0c2d1d0`。证据：`build/generic-h1-full-comparison-audit.json` 与 `build/generic-h1-full-validation-audit.json`。

本次重新执行旧分立H1/C2和H3/C2的相同135 MHz、6000轮性能固件，两个编译任务从开始就绑定各自合格PDS清单。不要拿上一轮132 MHz固件或旧板上UART代替这次对照。

| 项目 | 旧分立H1/C2 | H3/C2 |
| --- | ---: | ---: |
| 周期 | 1946176342 | 1939624342 |
| 退休指令 | 1649428424 | 1649428424 |
| CRC | 通过 | 通过 |
| 模型时间 | 14.4161210519 s | 14.3675877185 s |
| CoreMark/MHz仿真投影 | 3.0829683161 | 3.0933825020 |
| CoreMark仿真投影 | 416.2007226784 | 417.6066377703 |
| 同一位流LUT分母 | 8181 | 8326 |
| CoreMark/LUT仿真投影 | 0.05087406462 | 0.05015693463 |

只改BTB，少6552000周期（0.3366601401%），同频吞吐增加0.3377973692%。资源效率投影下降约1.410%，仍高于0.031的模型门槛；这不是实板门槛已经完成的证明。不能把旧H1分数直接除以新H3面积，也不能把旧H1长测冒记到通用H1源码名下。

H3完整性能构建：`build/btb-history-width-h3-c2-portable-stage/build/compiled/20260907-122000-9a56d7bd`。旧H1同固件对照：`build/btb-local-history-stage/build/compiled/20260907-122032-42575ea1`。完整H3验证种子仿真 `build/btb-history-width-h3-c2-portable-stage/build/compiled/20260907-122938-00b55c68` 已通过：6000轮、1944389649周期、1649775523条退休指令，模型时间14.4028862889秒，CRC通过，并重新绑定对应验证PDS的20份输入、固件和位流。验证种子不用于产生性能分数。

## 证据与未完成项

- `build/btb-history-width-short-audit.json`：初版六组、12次同固件短测；源模板已冻结到sized_cast_rejected.sv。
- `build/btb-history-width-portable-short-audit.json`：修订后三组、6次UART逐字节复验。
- `build/btb-history-width-physical-audit.json`：三个种子7实现、原生模式银行、原始语法失败。
- `build/btb-history-width-followup-audit.json`：通用H1与H3性能/验证成对核验、H2种子1及5失败。
- `build/btb-history-width-isa-audit.json`：两候选392次正例及16次拒绝日志与来源。
- `build/btb-history-width-full-comparison-audit.json`：完整性能同固件对照和独立PDS绑定，所有投影明确非实板。
- `build/btb-history-width-full-validation-audit.json`：完整6000轮验证通过、独立绑定通过；验证结果不生成性能分数。

本轮全部PDS与长仿真任务均已终结，状态记录见 `build/btb-history-width-local-state.json`，无遗留运行任务。短测审计按固件Iterations=10选择构建，避免把后来新增的6000轮长测误当作短测。
- 同名 `build/audit_btb_history_width_*.py` 保留复查脚本；`build/btb-history-width-local-state.json` 保存任务接续状态。

本轮没有修改生产BTB或PLL，没有启动浏览器、操作板卡或上传GitHub。新候选仍需独立实板长测、GPIO独立输入、SCBV电气确认和对应源码ILA；不沿用Target132Kept的旧绑定。135 MHz小正裕量不是长期稳定性或物理极限。继续提升频率前还须核实并扩展PLL/运行器支持的频点，不能把当前不在白名单中的138 MHz直接写成有效时钟。
