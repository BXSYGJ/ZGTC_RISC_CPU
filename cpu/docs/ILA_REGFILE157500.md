# 157.5 MHz 当前寄存器堆候选的 ILA

## 基准与当前资格

最新目标保持冻结501.065730222分版本的157.5 MHz与3.181369715698 CoreMark/MHz不降，实际插核总资源效率严格大于0.05。0.052994789024是冻结版参考值而非当前插核下限，ILA总LUT不得扣除调试核。当前候选ABD2D7A8通过原生二态、ISA/SoC与双短测；本版配对6000轮正在执行，尚无当前实板成绩。

普通PDS 20260909-111626-8819e58d：8998 LUT、4271 FF、WNS -0.335 ns。源没有通过manifest；source-candidate.json明确保留SourceTimingConstraintsMet=false、SourceAcceptedManifest=false。独立插核仍可作为实验，但不能借源清单宣称时序合格。

## 首次完整插核：拒绝

build/ila/20260909-113837-aa96ee82完成实际Inserter、dev_map、布局布线、report_timing与位流生成。109个信号同时作为采样与Basic W/Edges触发，深度1024、采样时钟cpu_clk。原始报告解析为9942 LUT、6140 FF、WNS -0.114 ns，违反时序且比冻结基线多487 LUT；不得上板计分或替换基线。最差路径由I-cache request_address[5]进入hit_count[28]的CE。

## 当前分离触发实验

原厂Fabric_Inserter_User_Guide.pdf第45至48页明确支持数据/触发独立、Basic触发类型及单独数据连线。scripts/cpu_ila_regfile157500_split.fic.in保留以下全部采样数据及顺序：EX_PC 32位、ID_PC 32位、IF_PC 32位、流水有效5位及原8个控制位，共109位。深度仍1024，cpu_clk上升沿逐周期采样，禁用存储资格筛选与多窗口。

触发比较改为完整EX_PC[31:0]与ex_fire，共33位Basic匹配，可对指定算法地址且发生EX推进时触发。不压缩或删除原始PC数据，不以较少触发条件冒称更多波形覆盖；具体关键算法窗口需符号表与真实CSV逐次证明。

build/ila-probe/regfile157500-split-named-v2的原厂保存结果及日志逐项确认全部109个Data Channel、两次一致的33个Trigger Channel、cpu_clk、1024深度与数据/触发分离。scripts/ila_split_config.py的6项实际夹具测试通过，169个拒绝场景涵盖每个数据/触发信号、16个属性、额外通道、原始输出和实际错误索引映射。正例先通过，才计这些拒绝测试；首个成功日志的属性数量文字误写17，已改为由实际属性表长度输出。

前置失败如实保留：首次脚本因Windows路径被Tcl解析失败；第二次复用另一Inserter进程数字索引造成错误连线，被实际保存FIC检查发现，未进入PDS；改用名称FIC后首次包装又因CRLF计数失败，随后修复换行处理并重新由原厂确认。正确方案不依赖跨进程索引，不能仅凭命令返回0认定连接正确。

独立入口scripts/run_regfile_ila_split_pds.ps1重新审计原始源与命名映射，对拷贝ADF/FIC再跑原厂验证，并完成build/ila/20260909-120638-16775b06全部流程：9607 LUT、5551 FF、WNS -0.437 ns。比首次插核少335 LUT、589 FF，但比冻结版仍多152 LUT且时序失败，因此拒绝、不上板。最差路径为id_instruction[18]经有效位选择、id_operand_a及比较链到N2196_7；报告中有效位读选择N297扇出72。两份完整原始报告、位流、FIC及拷贝源绑定见build/regfile-ila-implementation-comparison.json，审计成功仅表示失败证据一致。旧ila_analyze.py不接受此分离端口配置；将来获得合格实现后仍需明确新profile、当前配对长测及真实CSV验收，不允许改名冒充旧109位触发版。

## GPIO 与应用

现有板级KEY/UART输入与LED输出继续保留。157.5 MHz GPIO诊断固件20260909-121204-18881f70已真实编译；build/run_regfile_gpio_current.py核对当前PDS的20份捕获输入并复制RTL，从实际顶层提取全部硬件参数。当前源回归build/gpio-current/20260909-121209-cf2d0924通过2976检查、343736周期、3次外部中断，以及1项43.654秒测试中的5个真实错误变体。覆盖KEY边沿、反相、错误输入、UART独立性、挂起清除、屏蔽、重置与重复中断计数。UART在仿真中加速为32周期/位，不是当前实板或实际115200波特率证明。

旧scope应用的头部时钟仍写死27 MHz，build_scope.ps1也只记录27 MHz；不能直接把该应用搬到157.5 MHz后沿用其时间轴。上板前需修正并回归应用频率来源。SCBV、电气完整依据、独立KEY实测、真实算法ILA窗口及稳定性仍待完成。无Git操作。

## 最新0.05门槛后的有界验证

两份种子2插核仍因时序失败而拒绝，但若执行周期保持冻结值，9942和9607 LUT都能满足新资源门槛；不再要求分离触发版额外节省152 LUT。当前对完整109位触发版进行唯一一次种子1验证：20260909-122820-df2f1d0b；同时运行本版双6000轮，未得最终共同资格。新Regfile157500Candidate分析器现已实现并通过含历史配置的43项回归，核对SourceCandidate、完整时序、总资源与157.5 MHz时间轴，但不证明正式计分或实板来源。分离触发版仍需独立profile，禁止混用。

种子1现已终止：9904 LUT、6146 FF、WNS -0.274 ns，失败；build/audit_regfile_ila_seed1.py已绑定实际源、FIC、位流、约束及原始报告。转向REGFILE_VALID_FANOUT.md中的独立扇出候选，停止种子扫描。本文较早“正在运行”描述保留当时含义。
