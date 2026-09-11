# 当前候选的原生ILA映射核查

后续更新：已对分段ALU的成功132 MHz源重新执行原生查询，并新增独立Target132Carry配置及语义拒绝测试，见ILA_TARGET132_CARRY.md。本页以下记录仍仅属于旧ALU的历史查询，不能混用。

## 已完成范围

针对除零载荷/折叠BTB阶段的原生综合ADF，调用本机cdt_ins的既有ins_list_nets接口，随后ins_open、ins_core_info -core 0 -trig 0逐通道验证。109路连接、cpu_clk采样和1024深度均被原生工具确认，保存后的FIC关键配置逐行保持。源ADF前后SHA一致，未被查询改写。

源构建build/pds/20260907-044459-34066263；ADF SHA-256 6868EA63CD22CC1EE1559E11133D107912A78991E733E33DB0758B43C7647EFA。该构建的132 MHz时序失败，因此此次结果只是离线映射核查，不是插核后PDS通过，也没有硬件波形。

## 通道语义变化

旧Target120的107位board/soc/memory_system/cache_rsp_valid[1]在本次原生可查询网表中不存在。当前真实存在的是board/soc/core/mem_fire；将其明确选为新候选的107位，含义为MEM级前进/完成事件，不是D-cache response valid，两者不得混称。其RTL定义在rv32_core.sv，受MEM有效、存储响应或维护条件约束。106位仍为fetch_complete，亦不直接等同于i_rsp_valid。

此FIC不能送入旧Target120分析模式冒充同一CSV布局，也不能只更新旧源码哈希锁。Legacy27/Target120模板、分析器与锁文件本轮没有因此被放宽；未来采用新配置必须另设显式语义映射和对应拒绝测试，并重新实现与采集。

证据目录build/ila-probe/current132-1788728560287：probe.tcl与stdout.txt为查询记录，current132.fic及verify.stdout.txt为逐通道确认，mapping-audit.json保存全部109路、20项输入快照与文件哈希。运行中的源波形没有被合成、补齐或替代。

## 后续变化边界

随后开展的ALU进位选择实验改变了ALU源码，因此上述结果不能自动覆盖后续新综合网表。实际插核前须重新查询最终选定源ADF、核对信号语义及完整配置，之后检查插核版时序/资源和真实采集。当前源实板ILA验收仍未完成。
