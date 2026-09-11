# 替换路选择复用采样有效位

## 电路变化

规范源experiments/cache_valid_reuse/rv32_cache.sv，SHA-256 EE88049C2B8FB3F8BD94A8C42B184CBE3181269DC40DCDA49DFD8784E4C653B1。独立工程build/cache-valid-reuse-stage，144 MHz、种子1、PG2L200H-6FBB676；生产RTL不变。

相对上一版I/D共同采样候选，只有replacement表达式中的两个有效位条件从valid[way0]/valid[way1]改为lookup_valid0/lookup_valid1。保留无效way0优先、无效way1次之、两路都有效才使用LRU的规则。I/D采样、回填、复位、标签/数据RAM、握手与流水拍均不改。

有效位说明缓存行是否包含有效数据；替换路选择决定未命中时覆盖哪一路。旧版命中判断使用已采样位，替换判断却重新按保存地址读取整组有效位数组，形成重复选择树。本版在原来的LOOKUP消费阶段复用同一份采样结果。

replacement只在LOOKUP未命中分支被状态机用于victim、victim_base和写回/回填决策；并不保证忙态的采样位始终等于有效位数组。新增检查在每次LOOKUP，包括命中与未命中时，逐拍比较候选替换路和独立原始参考。不将这种阶段限定等价误称为任意时刻的组合逻辑等价。

物理对照仍使用144 MHz通过的D-cache采样父工程：20项物理输入中只有缓存不同，CPU、PLL、布局种子、硬件参数和匹配144 MHz固件不改。另单独核验上一版失败候选的原始快照和报告，用于解释本次选择表达式改动的效果。

## 功能验证

定向替换路/LRU测试2项2.176秒通过；完整scripts/test_cache_valid_reuse.py共11项150.260秒通过。继承96种模式/任意LRU初值与每例3次训练复位、32个物理配置及32个参考、6个全容量及6个参考、12个地址边界及12个参考、32个可写配置和16个只读前递/重叠配置；仅末拍错误及正常重试激励保留。

编译后的拒绝反例共52个：原有44个采样/错误/数据选择/LRU反例，加8个只读/可写替换条件及路选择反例。旧LRU测试中涉及被改表达式的变异锚点只在本子类内转换，仍注入同一种“忽略无效路优先级”错误；未修改公共参考或其他候选测试。

每次LOOKUP的替换路比较补充既有控制、响应、内存事务、训练LRU、采样保持和有效位等价检查。编译失败、看门狗或单纯覆盖不足不算成功拒绝；这些动态测试不是形式证明。

RV32UI构建20260908-034441-c560802b完成164次，RV32UM 20260908-034749-2924b347完成32次，共8个拒绝控制；不是完整ISA认证。缓存CPU在两种预测配置下为6498/6379周期、13次陷阱，零/正/负偏移加载旁路及独立退休/内存比较通过。14个精确M中断、8种严格板级lint通过。

固定GPIO/UART固件在通过的父工程与候选上正常/故障共4对8次重放，stdout和逐周期轨迹相同：GPIO正常8259周期、4611退休，故障4436周期；UART正常8238周期、4724退休，故障4721周期。不是实际GPIO输入或板测证据。

两组10轮CoreMark短测与父工程完整结果/profile逐项相同：性能20260908-034545-3b5d447c为3205068周期、2748941退休；验证20260908-034558-5dae9df6为3211054周期、2749614退休。没有执行周期收益，不足10秒、不计分。没有本候选配对长测或实板成绩，不借旧分数除以新面积。

## 原生结构与物理检查点

| 原生缓存模块 | 上一失败版LUT/MUX/DFF原语 | 本候选LUT/MUX/DFF原语 |
| --- | --- | --- |
| I-cache | 3186 / 411 / 1181 | 2412 / 207 / 1181 |
| D-cache | 843 / 248 / 484 | 847 / 274 / 484 |

上述是原生网表实例数，不等于最终布局LUT面积。I-cache减少774个LUT原语和204个MUX原语，但D-cache增加4个LUT原语和26个MUX原语，不能只挑I-cache数字宣布整体优化成功。

PDS构建20260908-034337-09aaadef终态失败：8639 LUT、5126 FF、WNS -0.765 ns，Some Constraints Violated。相对上一失败版9483 LUT、5147 FF、-1.212 ns，少844 LUT、少21 FF，时序改善447 ps，但144 MHz仍未通过。

相对已通过的D-cache采样父工程8749 LUT、5154 FF、+0.148 ns，少110 LUT、少28 FF，但时序恶化913 ps；相对8626 LUT、5123 FF的完整基线则仍多13 LUT、多3 FF。本候选不采用、不启动其配对长测，不以面积下降掩盖频率失败。

第一条实际路径从外设timer_value[0]经64位定时器比较进位链、CPU ex_serial及前端背压逻辑，到i_req_address[12]（扇出257），再经过有效位选择树进入I-cache read_valid0的D端逻辑。15级逻辑，逻辑2.573 ns、布线4.860 ns，布线占65.384%；最差前三条均为定时器到I-cache有效位预读寄存器。没有关闭定时器或中断、没有把路径设为假路径。

下一步应针对取指地址选择器切断不必要的响应ready依赖，而不是继续只缩减有效位选择树。CPU当前i_req_address由fetch_overlap在next_pc和fetch_address之间选择；fetch_overlap依赖fetch_complete，后者依赖i_rsp_ready，因此完整的中断/前端背压链进入地址选择。

可检验的候选是用寄存状态fetch_sent选择地址，同时保持i_req_valid和全部握手逻辑不改：在i_req_valid为1时，若fetch_sent为0，则i_rsp_ready和fetch_overlap必为0；若fetch_sent为1，则i_req_valid为1要求fetch_overlap也为1。因此在有效请求阶段两个选择条件相同。无效请求阶段的地址会改变，必须验证cache的ready空闲预读、等待接收时的稳定性、响应背压、冲刷/维护、异常/中断及重叠取消，不能宣称逐周期全接口等价。后续已实现这一选择器优化，独立144 MHz候选以8793 LUT、5125 FF、WNS +0.195 ns通过；功能、动态差分和来源审计通过，但仍未替换完整基线、没有新长测或板测。详见FETCH_ADDRESS_SELECT.md。

已核对FETCH_PC_PRECOMPUTE.md及旧候选：旧实验改变PC+4加法位置/分组，仍保留fetch_overlap地址选择器，与此方向不同；不重复旧实验或抹去其失败结果。

Icarus仍提示独立命名generate块的Anachronistic用法；功能编译与严格Verilator板级lint通过，未在PDS运行中更改源快照。

## 审计与未闭环项

来源审计build/audit_cache_valid_reuse.py通过：规范源精确差异、20项物理输入、18项编译输入、真实布局命令、固件/位流、原始时序/资源、196项ISA日志与SoC重放一致。结论timing_qualified=false、full_score_available=false，审计通过不等于时序通过。

审计反例2项134.305秒通过，拒绝10个来源/面积/时序/布局/重放元数据反例，其中包含上一失败版资源和缓存快照被篡改的情况；--require-timing符合原始物理失败结论。

位流SHA-256 C6B2945F643FF4B0D9E673B6E71D6EE92838A07C7C34C5AE618B33522F4F6FBA，原生网表SHA-256 AF511E507EAEF01F11FFAAC2068B344C3C9ABEB2A7F8531D84B886012C085C77。机器记录见build/cache-valid-reuse-qualification.json及build/cache-valid-reuse-local-state.json。

本轮已启动会话均已结束，保留失败物理产物，不启动新长测、不采用本候选。生产RTL与GitHub不变，完整基线仍保留；实板、ILA、独立GPIO、电气/SCBV、应用、稳定性及多指标继续优化仍未完成。
