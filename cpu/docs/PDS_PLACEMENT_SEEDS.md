# 可复现PDS布局种子试验

## 为什么继续搜索

默认布局132 MHz性能/验证实现均WNS -0.358 ns，而先前135 MHz实现为-0.154 ns。不同频点的布局结果不单调，报告估计频率不能代替另一个约束频点的实现。此轮固定132 MHz、生产RTL和性能固件，仅改变原厂支持的全局布局随机种子，探索是否能维持执行周期并改善实际布局时序/资源。

本实验不新增流水级，不改变M指令周期，也不将某个种子通过等同于物理极限。资源效率最终仍必须由匹配实板长测与布局后LUT计算，至少0.031 CoreMark/LUT；执行效率门槛仍为3.0 CoreMark/MHz。

## 原厂接口依据

本机PDS 2022.2-SP6.4的Pango_Design_Suite_User_Guide.pdf，第114–115页描述布局随机初始位置及多种子筛选；第119页列出默认布局种子0、迭代1；第251–252页的pnr命令表列出-gplace_seed、-gplace_times等。执行本机pds_shell.exe的pnr -help再次确认-gplace_seed integer_number，不猜测不存在的pnr -seed接口。原始帮助输出保存在build/pds-seed-help/stdout.log。

这次不启用工具内部多种子自动挑选：每次run_pds.ps1单独生成不可复用的构建目录、源快照、完整报告及位流，避免只有最优种子结果却丢失失败候选。未修改hold修复、时序约束、假路径或报告解析门槛。

## 构建入口及证据

run_pds.ps1新增可选PlacementSeed非负整数参数。省略参数时仍生成原有单行pnr；显式设置1时生成pnr -gplace_seed 1。所有频点和原构建选项保持。build_pds.tcl使用唯一__PNR_COMMAND__占位符，缺失或重复会直接拒绝，避免悄悄退回默认种子。

每个构建在启动PDS前写入placement-config.json（Schema、Seed、Command），失败构建也保留；只有原有时序/资源审计全部通过才生成成功manifest.json，其Placement字段与独立配置一致。实际build.tcl、PDS stdout中的Executing : pnr及zgtc_rv32i.pds配置要相互核验，不只相信清单。

test_pds_placement_contract.ps1从实际runner AST提取参数和配置代码，检查默认及显式0/1/7/整数边界的命令与JSON一致性，拒绝负数、溢出、非整数/注入文本和缺失/重复占位符。11项通过。整数边界测试仅证明包装脚本绑定行为，不表示每个极大种子已在原厂实现引擎中实跑。CoreMark入口原14项契约检查保持通过。该测试已并入validate.ps1。

## 固定输入及当前批次

与默认132 MHz失败实现使用相同20份源输入和6000轮性能固件；M单元为AA1BF3E9AC51E8179B9C52B7ADA90DE816B219AC7263D7FB973A9289D5164C79，PLL为B1AD88A943CBEC1AF172560D7B22919E298A64FF1D033F19F7A27D23B1BD7CBB。独立132 MHz两组10轮RTL短测周期仍为3326116/3329203，尚不构成板测或≥10秒成绩。

| 种子 | 构建目录 | 当前证据 |
| --- | --- | --- |
| 默认 | build/pds/20260907-022256-82eade41 | 10348 LUT、4806 FF、4 APM、WNS -0.358 ns，拒绝 |
| 1 | build/pds/20260907-024740-19cd5c1b | 10327 LUT、4807 FF、4 APM、WNS -0.417 ns，拒绝 |
| 7 | build/pds/20260907-024806-115b991e | 10322 LUT、4806 FF、4 APM、WNS -0.480 ns，拒绝 |

两次构建均已终态退出，成功生成位流但未通过原始时序审计，没有成功manifest.json，没有烧录板卡。种子1/7相对默认减少21/26 LUT，但WNS分别恶化0.059/0.122 ns；不能报成合格资源效率，也不能将报告估计125.1251/124.1465 MHz当作板测频率。

build/placement-seed-input-audit.json逐哈希确认两个种子与默认132 MHz实现的20份源及性能固件相同，并核验实际Tcl、stdout和PDS项目中的种子值。build/divider-operand-placement-audit.json独立重解析本阶段6份原始PDS报告，核验源快照及位流/固件哈希；其中仅126 MHz候选本地时序通过，5份失败构建不补造成功清单。

完整build/validate-placement-seed.log已终态通过，包括单元、CPU、参考模型/内存比较、严格lint、原有协议/输入反例、非对称缓存集成、GPIO/ILA检查器，以及新增11项布局入口检查。三份变动PowerShell脚本通过PS7语法和UTF-8 BOM核验。该回归不能将失败物理时序变成合格，也不替代新实板长测。

## 关键路径与下一步

种子1首条最差路径从D-cache request_address[2]经存储读出、加载前递和ALU到mem_result[25]；该地址位在路径上的扇出257、对应网络延迟1.301 ns，整个数据路径布线占71.899%。种子7首条最差路径从request_address[5]到mem_next_pc[3]，数据路径布线占70.568%。这些是原始.rtr中的本次结果，不是所有配置都相同的结论。

有限种子搜索不能证明132 MHz无解，但这两次没有收益，下一步优先试验Cache地址扇出/布局局部性，而非盲目扩大随机批次。已查本机ADS_Synthesis_User_Guide.pdf第87–88页：syn_maxfan可对register/net设置扇出上限，工具通过逻辑复制减少扇出；第52页给出Verilog-2001属性语法。后续必须用实际综合网表和布局报告确认属性生效，并保留无改动基线、相同周期及面积代价，不预先宣称能改善。本次种子筛选结束时尚未添加该属性；后续已实际添加并核验原生复制，组合版本完成132 MHz实板长测，详见CACHE_ADDRESS_FANOUT.md与HARDWARE_132MHZ.md。

只有时序通过且经源/固件/报告核验的候选，才继续构建匹配验证种子位流并上板。不得将旧126 MHz的UART当作新132 MHz或新布局种子的成绩。GitHub保留用户指定的120 MHz达标提交，本轮不追加上传。
