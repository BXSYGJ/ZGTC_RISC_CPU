# 当前157.5 MHz精简ILA的本地验证

## 最新范围

2026-09-09用户明确：ILA在本地PDS验证即可，不需要远程平台ILA验证。因此，远程网页只解析触发通道的问题不再是验收前置条件；停止Platform42兼容分支，保留已经通过的RegfileFanout157500Minimal配置。GPIO功能、应用场景与CPU性能分别验证，GPIO专项测试不作为CoreMark性能测评的前置条件。

赛题PDF第10页的基础任务要求集成基础外设，UART与GPIO以“如……等”举例；第11页分别列出执行效率、时钟频率和资源效率，没有明确GPIO必须参与CoreMark计时，也没有规定删减外设后的正式LUT口径。当前不删除已验证工程中的GPIO，不混用不同硬件配置的跑分、时序或LUT数量。

## 本地PDS结构与时序

当前CPU源为DC90363D426754F032EC04DB6F4BE76DA439CCA149E372853EE2D64536D20FCE，其余19份实现输入锁定。精简ILA保持完整EX_PC32位，加五级有效、ID/EX/MEM推进、MEM冲刷和取指完成，共42位采样；33位Basic触发比较EX_PC与ex_fire，深度1024，cpu_clk逐拍采样。实际Inserter输出确认全部命名连线，不跨进程复用数字索引。

| 固件 | PDS插核目录 | CPU时钟 | 总LUT | FF | WNS |
| --- | --- | --- | --- | --- | --- |
| CoreMark性能V0 | build/ila/20260909-131103-bd14dfaf | 157.5 MHz | 9374 | 4984 | +0.078 ns |
| CoreMark校验V1 | build/ila/20260909-134154-631c0e9f | 157.5 MHz | 9374 | 4984 | +0.078 ns |

两份原始时序均All Constraints Met，包含调试时钟域；20份源、固件、ADF、原生网表、FIC和位流有独立哈希。源普通实现本身WNS -0.157 ns的失败事实保留，不能将其伪装为通过。SCBV告警及异步I/O外部契约仍未关闭，内部时序通过不替代电气依据。

## 算法波形及来源

当前源真实RTL仿真分别在链表、矩阵、状态机函数入口取得1024拍窗口；源绑定ELF与HEX一致，短测总周期3151519、退休2748941与无观察端口参考相同。数据位顺序与上述42位采样一致，完整EX_PC用于定位实际函数，检查有效/推进和相邻级传递关系。

| 窗口 | WB事件数/1024拍 | 局部退休事件率 |
| --- | --- | --- |
| core_bench_list | 728/1024 | 0.7109375 |
| core_bench_matrix | 481/1024 | 0.4697265625 |
| core_bench_state | 552/1024 | 0.5390625 |

CSV、SVG和16拍放大图位于build/ila-pipeline-rtl/regfile-fanout-minimal；审计入口build/audit_regfile_fanout_pipeline_capture.py。本轮在扩展分析器后重新核验通过，64项新旧ILA回归也通过。

这些波形明确标为RTL ONLY，不是实板ILA导出，也不宣称读取了调试核内部采样RAM。它们支持分析CPU局部流水占用、停留与退休事件；不能推算整段CoreMark IPC，也不能把所有停留归因为某种数据冒险。没有采集ID_PC、IF_PC、mem_load、mem_sent等信号，不填造缺失信息。

## 实板性能与功能分开

上述V0/V1各6000轮已在实验箱5完成实板运行，全部CRC与周期/退休均与对应完整RTL一致。性能501.065730222 CoreMark、3.181369715698 CoreMark/MHz、0.053452712846 CoreMark/总LUT，包含本次ILA，不扣除调试核。原始证据见build/hardware/regfile-fanout-minimal-20260909-box5。本次实板只运行CoreMark，不冒充当前ILA实采；最新范围已不要求远程ILA。

GPIO诊断使用独立固件E789A7AE5F6778739A6F5CEAF33CF16DCBBC64B9AC198BB3647C67F1332B0318和同一CPU硬件，不能将其当作CoreMark固件计分。其42/33命名映射已通过，独立插核20260909-145944-09291bba正在实现，结果必须另外核对。

## 已停止的远程兼容实验

Platform42保留42个采样信号，但为了网站同宽要求扩展为42位Basic W/Edges触发。实际前端解析器离线验证与44个错误控制通过；PDS20260909-143925-a8cdcbe3为9422 LUT、5134 FF、WNS -0.464 ns，时序失败，未上板。失败关键路径由EX操作数经early_pair_condition/early_taken进入I-cache地址。

用户取消远程ILA要求后不再推进该分支，不启动已准备的V1实现，不降频或替换已通过42/33镜像。文件只作为有界实验历史保留，没有Git提交或推送。

