# 当前132 MHz分段ALU版ILA

## 配置与语义

新增显式配置Target132Carry；Legacy27与Target120的源锁、通道语义和默认选择保持不变。新源锁ila_target132_carry_sources.json绑定20份生产RTL/PLL/约束，来源为已实测132 MHz性能构建20260907-051442-9813d121。错误频率、配置、空源锁或不同修订均在启动PDS之前拒绝，不用更新旧锁来冒充同一映射。

新FIC仍是109通道、1024深度、cpu_clk上升沿采样，关闭存储资格和多窗口。106位为fetch_complete；107位改为board/soc/core/mem_fire，明确不是D-cache response valid。其RTL定义为MEM级有效且相应访存/维护条件满足，代表该级前进事件。分析输出键使用mem_fire及mem_load_sent_without_mem_fire_cycles，不再对107位使用d_response名称；后者是已发送load尚未完成的局部代理计数，不自动归因于cache miss。

新增mem_fire必须伴随mem_valid、相邻下一拍wb_valid必须有上一拍mem_fire两项检查。反向mem_fire必然产生下一拍wb_valid并不成立，因为异常会抑制写回，因此没有增加该错误断言。原ID到EX的PC/valid传递、EX到MEM valid传递和fire/valid检查继续执行。

## 原生查询

build/ila-probe/carry132-1788731219100对当前真实综合ADF执行ins_open、ins_list_nets、ins_core_info和ins_save，逐路确认全部109个名称。源ADF SHA-256 04189EF831FA12A7C2B68E71B49AC8D90F88F6A16E4D9B4588B6FF329DD7D314，查询前后相同；原生保存未改变模板关键属性。证据mapping-audit.json与retry.stdout.txt。首次命令因Windows反斜杠被Tcl解释而失败，已停止本次启动的查询进程；改为正斜杠参数后原生查询成功，失败日志也保留。

此前ILA_NATIVE_REMAP.md绑定的是旧ALU/失败132 MHz源，不能覆盖本次；本页重新查询的是当前已测成功源。原生名称查询本身仍不等于插核实现成功或实板采集。

## 自动验证

- Target120和Target132Carry各20项PowerShell前置拒绝检查通过，共40项；不会启动插核或实现进程。
- Windows与WSL均通过21项ILA Python测试方法：旧Legacy27/Target120仍通过，新增9项方法覆盖新语义、MEM传递、跨配置拒绝、六类产物哈希、重算哈希后的错误FIC、20份错误源码修订、错误配置/时序及缺少manifest的CLI调用。使用合成夹具只证明分析器检查，不把夹具当硬件波形。
- 三份既有Target120真实CSV重读通过，每份1024样本及7份绑定产物继续校验；没有把它们标为新132 MHz采集。
- 新测试已接入validate.ps1。四个修改或新增的PowerShell脚本通过解析与UTF-8 BOM检查。本轮CPU RTL未改动，不声称重新跑完CPU/ISA全套回归。

## 构建与当前边界

三组当前源插核实现均已结束，均因132 MHz时序失败而拒绝。构建目录保留工具产生的原始名称；审计时间使用UTC，不从目录名称推断当前日期。

| 布局 | 构建目录后缀 | 布局后LUT | FF | WNS / ns |
| --- | --- | ---: | ---: | ---: |
| 默认 | 20260907-055121-8d195379 | 11373 | 6941 | -0.340 |
| 种子1 | 20260907-060314-b1f66931 | 11310 | 6907 | -0.082 |
| 种子7 | 20260907-060332-926b6345 | 11327 | 6875 | -0.096 |

全部为4 APM。三组都没有成功manifest，也未烧录；临时sbit文件存在不代表合格。种子1/7使用已有PDS的pnr -gplace_seed接口，原生run.log确认实际调用，ADF/网表/固件/源清单逐字节与同一生产源相同，完整探针属性保持。placement.json与build.tcl保存参数，seed-input-audit.json保存同源核验，三个terminal-audit.json独立重读原始rtr/run.log并保留失败结论。

插核从已综合ADF/网表开始，run.log没有新的综合LUT计数，因此新增显式parse_ila_reports解析入口，将synthesis_luts保留为null，只使用该插核实现实际布局后的CLMA+CLMS LUT。普通parse_reports继续要求综合计数，新ILA入口拒绝混入另一个综合阶段日志；没有把非插核综合数补写到插核日志。8项报告测试与6项频率门槛测试通过，生产版原始132 MHz硬件计分重算与原报告完全相同。

布局种子参数的负值、超int范围、带分号字符串三项拒绝测试通过，已接入validate.ps1；连同两配置各20项，共43项PowerShell契约检查通过。种子1/7只改变布局，不修改RTL或减小109通道、1024深度要求。后续合格实现仍必须完成真实板卡烧录、独立UART长测和原始CSV导出，不能仅凭离线检查标记HardwareValidated。

专用新端口19507的Chrome启动请求被exec_command工具策略拒绝，未返回具体规则名。没有换工具或权限绕过，没有因此预约板卡；本轮尚无新ILA实板采集。该外部限制不阻止本地插核、源码绑定和测试推进。

调用入口为run_ila_pds.ps1 -Profile Target132Carry -SourceBuild <已封存成功源构建>；分析入口为ila_analyze.py <原始CSV> --profile Target132Carry --manifest <匹配ILA构建manifest.json> --symbols <匹配固件nm符号> --output <输出目录>。分析器强制匹配源锁、原始时序、六份产物哈希和FIC完整通道/采样属性，仍明确hardware_origin_verified_by_analyzer=false，物理来源须有独立操作证据。

## 匹配固件与后续优化

build/ila-support/carry132-20260906下的firmware.symbols与firmware.dis来自当前6000轮132 MHz性能ELF；先用同工具链objcopy重建binary，再经bin_to_hex重建64 KiB HEX，与原位流固件完整SHA-256 65416C7D...F0216E匹配。47个有长度代码符号包含core_bench_list、matrix_test、core_state_transition；provenance.json绑定ELF、构建清单、HEX、符号和反汇编。该目录不是硬件捕获。

原生产版最差路径有16级逻辑，逻辑2.780 ns、布线4.243 ns；由D-cache地址副本经返回数据、forwarded_a、独立地址加法器进入下一次请求捕获使能。插核默认布局的同类路径布线5.053 ns，占67.445%，末端使能扇出140。rv32_core.sv:124的effective_address仍单独计算forwarded_a+immediate，不会因rv32_alu.sv分段而自动得到同一结构。build/alu-carry-select-next-critical-path.json保留原始路径和报告哈希；下一候选优先考察地址生成/捕获使能，而不是宣称继续换种子必然收敛。结构变化仍需单独定向、系统回归、正式PDS和新源ILA映射，不把此分析当作已实现收益。

132 MHz非插核实板结果仍见HARDWARE_132MHZ_CARRY_SELECT.md，未受此次插核失败推翻。全项目与三指标物理极限未完成；本轮不进行Git提交或上传。
