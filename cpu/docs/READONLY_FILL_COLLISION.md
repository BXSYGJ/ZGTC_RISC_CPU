# I-cache填充碰撞比较隔离

2026-09-08。本轮以已完成144 MHz双种子6000轮配对的全偏移加载地址旁路版本为基线，不混入时序失败的WB匹配预译码，也不修改生产RTL或GitHub。

## 变更与等价条件

候选文件为experiments/readonly_fill_collision/rv32_cache.sv，SHA-256 E53CA262B578C2CCBBA04833B9EFAFFD5EABDC86293087D471AEAA43BB743933。相对基线缓存BB337C68，只将I-cache两条前递标志更新中的fill_index==read_index替换为fill_index=={request_set,request_word}。D-cache、读地址选择、同步存储数组、数据前递、多路选择、LRU、错误处理和全部握手保持不变。

fill_write要求state==FILL_DATA。在该状态下，既不是IDLE/RESPONSE，也不能构成LOOKUP快命中，因此rsp_valid和req_ready均为0，read_index必然是已保存请求的索引。去掉比较器前不可能选中的新请求索引分支，尝试减少I-cache前递标志对请求就绪信号的依赖。没有关闭缓存碰撞处理、增加流水停顿、改写固件算法或缩短计分区间。此实验不同于以前只改D-cache的CACHE_COLLISION_FORWARD，结果不能相互替代。

## 已完成功能证据

scripts/test_readonly_fill_collision.py的8项测试单次完整通过，140.366秒。继承独立DB55缓存参考的逐拍请求/响应、状态、有效/脏位和已训练LRU差分，覆盖96种模式/上电初值、32种物理几何及32个参考控制、6种完整容量及6个参考控制、12种地址边界及12个参考控制；新增16种只读两路填充前递覆盖。10个LRU变异和8个只读前递变异均已编译并被运行时拒绝。额外断言实际填充时req_ready/rsp_valid为0、新旧碰撞条件逐拍相等、两路已寄存前递标志与参考相同。不是形式认证或全部输入空间证明。

独立外部ISA完成RV32UI 164次与RV32UM 32次，8个拒绝控制。构建20260908-000503-a6485ddc、20260908-000751-3db3ceff。真实缓存CPU两种预测配置保留6498/6379周期、13次陷阱和零/正/负偏移加载链覆盖；14个精确M中断用例和8种严格板级lint通过。

两种10轮CoreMark短跑为20260908-000558-8294fb7c、20260908-000611-088097c7：3205068/3211054周期，2748941/2749614条退休指令。不是超过10秒的计分长测，不产生新CoreMark/MHz或CoreMark/LUT成绩。

## SoC固件模式核对与重放

本轮重建SoC自检使用外部UART中断，当前基线目录留下的旧固件使用GPIO中断。两者C源码和脚本相同，但EXTERNAL_UART编译模式不同；反汇编已确认旧固件向0x10000208写GPIO使能，新固件向0x10000108写UART使能。旧hex哈希98870941C0571D7282B334E9BB18591C9ACDC0A84D4EE19C5D84A31DF5ACDB7C，新hex为B660B23F44F4F8E81396A8BF3546D156766EC4DC90873B6936A410CDA4B010BF。

初次重放把旧GPIO固件配上UART测试激励，基线即超时于PC=0x354；保留readonly-fill-collision-soc-replay.log和soc-paired-replay目录，不将其隐藏或误报为缓存回归。核实模式后在独立soc-paired-replay-corrected目录重新编译两套真实RTL，分别用匹配激励重放两份固件的正常/维护故障场景，共4对8次执行。每对stdout、带周期号的退休/陷阱trace均逐字节相同：GPIO正常8259周期/4611退休、故障4436周期；UART正常8238周期/4724退休、故障4721周期。正常均74检查、23 UART字节、三类中断各一次，故障均41检查。不能把不同固件之间的周期差异当成微架构收益。

## 物理结果与状态

144 MHz、PG2L200H-6FBB676、布局种子1的独立PDS构建20260908-000502-b57d9d5b已终态失败：8612 LUT、5127 FF、WNS -0.050 ns，Some Constraints Violated。相对完整基线少14 LUT、多4 FF、裕量减少55 ps，不替换基线，不将其声称为联合优化升级。位流哈希623381481998AC9825F054EBD0F631D3D7E115439E370EFDEACB561C72955E8E，但没有合格manifest，文件存在不代表时序通过。来源保持全偏移核心EC5F26DC、乘法0A318CBB、PLL4E2942F7及相同固件和20项物理输入，仅缓存变化。

build/audit_readonly_fill.py已终态通过证据一致性审计：真实布局命令、20项PDS输入、18项编译输入、完整短测结果、196项ISA结果、位流、原始时序与资源报告及SoC重放文件均一致。timing_qualified明确为false，未给本候选生成长测分数。当前完整基线仍是8626 LUT、144 MHz、WNS +0.005 ns的全偏移加载版本；该版本自己的长测结果也只是RTL/PDS投影，不是本候选或新实板分数。实板、ILA、完整电气约束和长期稳定性仍未关闭。

实际最差三条路径都从D-cache同步读存储时钟出发，分别进入D-cache状态寄存器的I3、状态寄存器CE及synchronous_writable.forward_way1/I5。I-cache局部表达式减少并不证明总体时序改善，下一步应从真实D-cache响应、下一请求资格与状态更新的依赖检查入手，不能跳过未对齐访问或错误响应的精确异常规则。

审计自身也通过2项测试（88.053秒）：8个仅在内存中篡改JSON的来源/资源/时序/布局/固件模式反例全部拒绝，真实失败实现的--require-timing门槛亦明确拒绝。没有修改PDS输入或报告来制造反例。所有作业句柄已终态，无等待中的构建或长测，详见build/readonly-fill-collision-local-state.json。
