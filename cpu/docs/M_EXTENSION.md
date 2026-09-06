# 默认关闭的M扩展与120 MHz实测

2026-09-06。状态：已实现标准RV32M的八种运算，默认ENABLE_M=0，保留严格RV32I基线。M开启候选已完成120 MHz PDS、两次4000迭代性能实板运行和一次4000迭代验证种子。当前为1.2489599204 CoreMark/MHz，仍未达到用户要求的3.0；不声称物理极限或完整ISA认证。

后续内部修订：MUL/MULHU 直接从稳定乘积寄存器提前响应，精确延迟和中断窗口新增检查，详见 `MUL_EARLY_RESPONSE.md`。本文下述实板数据属于原始 M 候选，不是后续乘法器/前递修订的实测分数。

再后续修订改为四份并行半字乘积在请求沿寄存，算术、背压和14组精确中断通过，120 MHz实现通过；结构及失败对照见 `MUL_REQUEST_CAPTURE.md`。下述32×32乘积后校正结构及实板分数仍是原始M版本的历史记录。

## 为什么增加M扩展

对原RV32I O2程序进行不修改固件的仿真退休PC直方图采集。窗口从iterate第一条退休开始，到stop_time第一条退休前结束，共752476条指令、1931499周期；所有PC均唯一归属ELF符号，计数守恒。__mulsi3占432424条，即57.4668%。这不是软件乘法的周期占比，也不把分析窗口冒充CSR精确计时窗口；原UART计时为1931551周期、752500退休，加入分析器前后完全一致。

赛题PDF要求支持RV32I，并未在已读两页中禁止扩展；本候选保持其语义，额外提供标准M运算。编译选项明确为-march=rv32im，不能把收益称为同一RV32I机器码的流水线消融结果。严格RV32I模式仍可编译、测试与实现，之前的原始成果不覆盖。正式提交时应披露ISA与编译选项；若赛事另有更严格解释，需据该解释验收。

原厂标准来源：riscv/riscv-isa-manual仓库src/unpriv/m-st-ext.adoc。本地下载快照build/riscv-m-extension-spec.adoc，SHA-256为99D3708B844072F626E33B427E7B1825CEBC0743EFDF6F7A5CA58205DD4C7C42。使用其乘法高/低位、符号组合、除零和有符号溢出规定，未发明自定义指令。

## 电路与流水线语义

- rv32_muldiv提供单个在途请求、寄存响应、反压保持和cancel。MUL/MULH/MULHSU/MULHU共享32×32无符号乘法，下一拍修正有符号高32位；实测PDS映射为4个APM，不能隐藏这部分专用资源。
- DIV/DIVU/REM/REMU使用32步迭代除法，按绝对值做无符号迭代，最后修正商和余数符号。有符号商向零截断；除零商全1、余数原被除数；最小负数除-1返回最小负数、余数0。
- EX使用已经完成前递的操作数，只有依赖消除且旧指令可推进时才发起一次计算。计算期间保持EX指令，响应满足条件后才进入MEM/WB，因此数据相关指令继续使用原前递路径。
- 旧指令冲刷或当前M指令出现精确异常/中断时取消在途运算。被取消结果不得写寄存器；mret回到原M指令重新计算，且只退休一次。
- M关闭时译码仍拒绝funct7=1；misa=40000100。M开启时misa=40001100，向misa写0也不能虚假关闭已实现功能。配置bit4表示M硬件，提前I-cache、默认load前递时完整配置0e020419。

## 验证证据

- muldiv_tb共11263项检查：八种运算、边界数全组合、2048组固定种子随机数、输入锁存、忙时禁止新请求、背压稳定、一次消费、各阶段cancel与复位。
- 精确中断集成测试：除法启动后0/1/15/30拍中断，以及乘法启动后中断，两种load前递模式共10组；强制检查mepc、mcause、取消前不退休、返回后仅一次退休、相关运算结果、错误分支路径无副作用和misa。
- 固定上游RV32UM八项×四种缓存/预测配置=32次通过；LoadUseBubble=1另32次通过。两组各自包含4个预期拒绝控制。目录build/isa/20260906-121756-d5456238和20260906-123208-61ea9383。
- M开启兼容RV32UI：41项×四配置=164次及4个拒绝控制通过，目录build/isa/20260906-122810-986d3606。未对齐访问按原精确异常策略处理，不声称透明未对齐支持。
- 完整validate.ps1通过：保留RV32I的逐退休独立参考、13个陷入、完整16 KiB内存比对、Cache/FENCE.I/SoC中断测试；新增M单元、中断测试和两种load模式的严格Verilator检查。原有差分模型仍只建模RV32I，M正确性证据来自上述独立算术参考、上游程序和中断定向测试，不能说M已通过同一Python全指令差分。
- CoreMark单次迭代短仿真性能种子799975周期/309824退休，验证种子800083周期/310272退休，CRC正确，均不输出正式分数。原RV32I同配置短仿真1931551周期/752500退休；两份机器码不同。

## 120 MHz板测与资源

实验箱2、PG2L200H，Chrome独立9236端口；两次重编程后的性能运行，周期/退休/Cache计数/CRC完全一致。首次启动有网关历史数据，原始boot-session保留并清空，未当作本项目输出。有效成绩均来自新G命令后的唯一完整START到FINISHED；板卡已关闭UART并释放。

| 指标 | 当前RV32IM候选 |
| --- | ---: |
| 工作频率 | 120 MHz |
| 迭代数 | 4000 |
| 周期数 | 3202664821 |
| 退休指令数 | 1239406977 |
| 实际计时时长 | 26.6888735083秒 |
| CoreMark | 149.8751904516 |
| CoreMark/MHz | 1.2489599204 |
| CoreMark/LUT | 0.02978441782 |
| 布局后LUT / FF | 5032 / 3746 |
| DRM / GPLL / APM | 16 / 1 / 4 |
| 约束周期 / setup WNS | 8.333 ns / +0.583 ns |

验证种子4000次：3203909286周期、1241340196退休、26.69924405秒，CRC e3c1/0747/8d84/5249正确。不把验证种子吞吐当性能分数。两份位流时序和资源一致。

与此前实验箱7上的120 MHz RV32I、4000迭代记录相比，执行效率增加142.3649%、CoreMark/LUT增加121.7504%、LUT增加9.2963%，额外使用4个APM。该对比更换了ISA/机器码与板卡，不是同板同固件单变量消融。没有证明最高可工作频率提高。存储仍是64 KiB片上RAM、I/D各512 B两路Cache，无DDR。

性能PDS目录20260906-122330-65496d16；位流SHA-256 E9AAF260C9B3BA1A37BE78BBA18B84ACDD77A0223F7E70E2ADEB0B02EF2D00A0；固件9CF3A9F6B28733F48B0D8C9E97EDCA6C0A91389E6CC19E8D5BCCB9212CAAD4EF。

验证PDS目录20260906-123329-95e31ebd；位流SHA-256 A7995140D0D1BCC1980FA5FF97EA9408869EBF4DA5C98AF57A79243B6DB9FF8C。

本地原始证据：build/hardware/coremark-box2-f120-rv32im-r1.uart、coremark-box2-f120-rv32im-r2.uart、coremark-box2-f120-rv32im-validation-r1.uart与对应-session.txt、-boot-session.txt；租约与位流身份记录f120-m-box2-sessions.json；严格数值检查f120-rv32im-target-assessment.json明确为target_not_met。

## 下一步与入口

仍需约2.402倍同频提升。当前每轮约309852条退休指令、CPI约2.584；在相同指令量下达到3.0需要CPI约1.0758，意味着必须显著改进连续取指、数据访问和分支停顿，不能仅再提高时钟。新M程序窗口中__mulsi3已经消失，core_state_transition、core_bench_list分别占退休指令约22.46%、21.00%，尚未把各类停顿周期归因。

运行入口（仓库根目录PowerShell 7）：

```powershell
pwsh -NoProfile -File cpu/scripts/run_muldiv_core_tests.ps1
pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1 -EnableM 1 -Suite rv32um -FastICacheHit 1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -EnableM 1 -FastICacheHit 1 -Profile
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -EnableM 1 -FastICacheHit 1 -ValidationRun
```

-Profile使用本次ELF符号自动确定边界，按PC统计退休，记录固件/ELF/符号/直方图哈希与唯一输出目录；未计分。profile_coremark.py对重复PC、错误总数、错误边界、模糊符号有拒绝或明确标记，4项变异测试通过。M分析目录前缀coremark_v0_i1_rv32gcc_rv32im_bp1_cs4_cache1_fastihit_profile_20260906-123651-4340b72a；原RV32I分析为coremark_profile_O2.profile.json。

run_pds.ps1接受-EnableM 1并在manifest记录SupportedIsa；拒绝把标为RV32IM的固件放进M关闭硬件。比较工具不会把改变M开关算成I-cache单变量消融。旧ILA映射对M开启明确拒绝，必须重新核验网表；SCBV、电气IO证明及原验收账本中的未完成项仍保留。
