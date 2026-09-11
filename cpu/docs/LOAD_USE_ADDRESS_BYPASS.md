# 全偏移加载地址旁路

2026-09-07。本实验在零偏移加载旁路与CSA乘法器组合上，仅修改核心的加载地址生成与依赖停顿选择；生产RTL和GitHub不变。目标是改善执行效率，同时保留频率及资源效率约束，不使用程序PC、特定数据或CoreMark专用指令识别。

## 通路及边界

load_address_bypass = ex_decode.is_load。LB/LH/LW/LBU/LHU的地址基值从branch_operand_a取得，允许正在MEM阶段完成的加载值直接作为下一次加载的基址；有效地址仍为32位模加法。前一阶段合法LOAD立即数由rv32_decode.sv对instruction[31:20]作12位符号扩展。非法解码会清除is_load，不把任意32位立即数假设成合法LOAD立即数。

BEQ/BNE保留原专用前递；普通ALU、存储、JALR、关系分支仍保持原加载依赖停顿。mem_ready、mem_flush、总线错误与精确陷阱优先级不变。无效或报错的响应不能使年轻加载提前请求，也不能影响更老指令的提交。branch_operand_a只是沿用的信号名称，不代表将加载值接回所有ALU操作数。

两种物理实现使用相同功能和时序协议：

- plain：先选取已前递的加载基址，再与立即数作普通32位加法。源为experiments/load_use_address_bypass/rv32_core_plain.sv，SHA-256 EC5F26DCA88B218B8EA1556B7DB7D73B7D77CA20A71C7C74B27DFCCB94FA51F4。
- select12：低12位加法产生进位，高20位预先计算基值加一、减一；根据符号扩展位和低位进位选择高段。非LOAD仍走原32位加法。源为experiments/load_use_address_bypass/rv32_core_select12.sv，SHA-256 169F7105BD1B9672D849ECCCF771530F361B295640D73E469139AD76AB896322。

两者均沿用经验证的CSA乘法器0A318CBB26FC16ECCFA4C556C5550BD5E816EC186C9619F01EFC0CC80DC4769E，20项PDS输入中只有核心变化，其余19项与零偏移CSA基线一致。

## 功能验证

scripts/test_load_use_address_bypass.py通过ZGTC_ADDRESS_VARIANT选择plain或select12。两种各6个方法通过，用时393.612秒和437.874秒。每种覆盖5263360次通用地址/分支检查，以及4227072次独立算术检查，共9490432次；两种合计18980864次。算术检查遍历全部4096个合法有符号12位立即数，各配8个边界地址与1024个随机地址，独立比较32位加法结果。

plain的20个和select12的25个逻辑变异均被拒绝；各自还拒绝3个无效/错误响应毒化变异及1个恢复全停顿变异。拒绝必须来自指定性质，不允许以覆盖未完成断言充当有效反例。

隔离的cached_core_tb.sv和core_selftest.S实际执行零、正、负三种偏移的相邻指针加载。指令对按16字节边界放置，避免跨I-cache行掩盖相邻依赖；两预测器各要求三类真实MEM加载前递事件均非零。两候选均通过P0/P1缓存CPU，分别6498/6379周期，13个精确陷阱与最终内存/参考模型一致；日志各显示zero_load=1、positive_load=1、negative_load=1。

各自14个精确M中断用例、74项SoC检查和41项故障SoC检查通过。每种另有196次RV32UI/M外部ISA执行与8个拒绝控制通过；逐案核验原始日志、固件、退休指令和源哈希，周期变化单独保留，不要求错误地沿用旧周期。

plain额外完成12个无缓存随机等待CPU用例（两种EarlyDRequest、两预测器、三随机种子），全部通过独立退休轨迹与最终内存比较。严格板级lint在bubble、predictor、cache三开关的8种组合全部通过，各快路径和M扩展开启，Iset=9、Dset=6、BTB索引8。第一次lint命令把BTB选项误拆成两段，在展开前失败；保留原日志，并以修正参数后的独立build/load-address-plain-strict-lint.log为通过证据，没有将命令错误归为RTL失败或隐藏它。

| 候选 | RV32UI构建 | RV32UM构建 |
| --- | --- | --- |
| plain | 20260907-214317-ad8463bd | 20260907-214528-c5d302f6 |
| select12 | 20260907-214317-d76818c3 | 20260907-214528-8cfe064d |

## 同固件实际短测

| 144 MHz十轮种子 | 零偏移CSA周期 | 两种全偏移候选周期 | 实际减少周期 | 退休指令 |
| --- | ---: | ---: | ---: | ---: |
| performance | 3234306 | 3205068 | 29238 | 2748941 |
| validation | 3241072 | 3211054 | 30018 | 2749614 |

plain构建20260907-214317-e1e449ab、20260907-214329-1f10330d；select12构建20260907-214338-2ffff7a7、20260907-214346-5e89a99d。CRC、缓存计数和固件清单相同，18项编译输入仅核心不同。两个种子都不足10秒，不能据此发布正式CoreMark成绩。

先前轨迹的非零偏移机会计数为29240/30020，但本次实际减少为29238/30018。不用机会次数替代实际仿真，也不在没有逐事件差分证据时猜测两周期差的原因。

## 144 MHz物理结果

均为PG2L200H-6FBB676、种子1、RemoteLab，Iset=9、Dset=6、BTB索引8，LoadUseBubble和各快速通路开启；PLL为同一27 MHz输入、144 MHz输出配置。

| 候选及构建 | LUT | FF | setup WNS/ns | 资格 |
| --- | ---: | ---: | ---: | --- |
| plain，20260907-214049-939f2469 | 8626 | 5123 | +0.005 | All Constraints Met |
| select12，20260907-214049-e0548f19 | 8746 | 5126 | -0.730 | Some Constraints Violated |

两者均21 DRM、4 APM。plain位流SHA-256为E0B7021195A2DA4E36DCC7381907EC75315358BAB3673426194B0C95DBD8CBD2。select12虽然算术检查和集成全部通过，但物理失败，没有合格manifest.json；不能补写通过标志或当成可部署候选。

plain最慢两条setup路径由core/wb_rd[2]到core/mem_result[18]/[22]，第三条由D-cache RAM时钟端到状态寄存器；select12最慢路径为D-cache有效位到状态寄存器使能。不能仅依据“分段加法应更快”来预先认定物理结果；这里较复杂的实现反而失败。plain仅5 ps正裕量，不是板上稳定性证明，也不能把PDS估计144.113 MHz称为实测Fmax。

## 审计与完整配对进度

build/audit_load_address.py --variant plain --require-timing和--variant select12分别验证实际快照、原始报告、原生映射、实际顶层固件路径、短测、ISA和集成日志；输出build/load-use-address-plain-qualification.json和build/load-use-address-select12-qualification.json。select12证据一致但timing_qualified=false。存在性能与验证两份PDS时，短测审计按已核验性能固件哈希选择唯一性能实现，而非任选一个目录。

plain独立6000轮性能构建20260907-220825-b5ae77d9绑定实际性能PDS，最大10000000000周期。独立验证种子PDS构建20260907-220849-49c9ad0a已终态通过，同为8626 LUT、5123 FF、WNS +0.005 ns，位流SHA-256为34050BAB20BE21A2324EF07458BEC62A52DC7B5D60771E4AEE5C3E95A923401B。成对物理源、报告和固件审计通过后，启动自己的验证长测20260907-221645-cac75965，同样绑定实际验证PDS；具体长测终态见下一段，不沿用零偏移CSA分数。

plain的两个独立完整长测现已全部终态通过，并通过build/audit_load_address_full.py --require-full。性能构建20260907-220825-b5ae77d9为6000轮、1918110244计分周期、1649428424退休指令、13.3202100278秒；验证构建20260907-221645-cac75965为6000轮、1921816141计分周期、1649775523退休指令、13.3459454236秒。双CRC正确，各自真实PDS绑定、相同固件/配置以及仅核心变化审计通过；相对零偏移CSA的独立完整运行分别减少17543998/18011998周期。

本候选自身144 MHz、8626 LUT的完整RTL投影为3.1280788050 CoreMark/MHz、450.4433479268 CoreMark、0.05221926129 CoreMark/LUT，local_full_pair_complete=true、local_gate_met=true。相对零偏移CSA版，同频执行效率提高0.914650%，资源效率提高2.072841%，减少99 LUT；但WNS从+0.163 ns缩至+0.005 ns，裕量明显下降，不能声称所有方面全面胜出。

这是本地RTL与PDS配对结果，不是实板成绩、官方认证或长期稳定性证明。已完成长测的生产候选保持隔离；新的操作数选择器实验另行测试，不能借用本版成绩。

build/audit_load_address_full.py要求两个种子的实际合格PDS与各自绑定的6000轮、至少10秒RTL结果，核验同固件、同配置和仅核心变化，再使用本候选自己的周期及面积计算本地投影。完整配对、实板重复测试、最新源ILA、独立GPIO输入、SCBV及长期稳定性均不得由短测或PDS单独代替。

审计器另有build/test_load_address_full_audit.py的8种只读内存变异：错误频率、器件、核心哈希、固件、位流、面积、时序和布局元数据，均因预期的具体原因被拒绝（1个测试方法、19.169秒）。变异只作用于加载后的对象，未修改任何真实快照。两份完整运行未齐备时，--require-full也已验证会明确拒绝；这不代替今后的完整双种子通过证据。

为提高仅5 ps的裕量，另在隔离的load-address-placement-seed2-stage和load-address-placement-seed7-stage执行144 MHz布局种子2/7筛选，现已全部终态。20份硬件输入和固件不变，原性能/验证长测目录不修改。build/audit_load_address_placement.py --require-complete同时核验实际build.tcl与原始run.log中的pnr命令、生成顶层、源码、固件、资源及位流。

| 布局种子及构建 | LUT | FF | setup WNS/ns | 结果 |
| --- | ---: | ---: | ---: | --- |
| 1，20260907-214049-939f2469 | 8626 | 5123 | +0.005 | 合格、当前独立长测绑定 |
| 2，20260907-221842-d5ac4790 | 8708 | 5135 | -0.017 | 时序失败，无合格manifest |
| 7，20260907-221902-ff1fa0db | 8677 | 5136 | +0.012 | 合格，但增加51 LUT、13 FF |

种子7位流SHA-256为6E6E3B4FC9C0A1C0B71368524FA98B0B5EE0CF1E130A9BF42D85C4FC21A0A4BC；其最慢三条路径均从D-cache RAM时钟端到状态寄存器使能。种子2最慢路径从MMIO timer_value[1]到I-cache请求地址副本；这是原始报告观察，不猜测为别的端点。

种子7只增加7 ps裕量，同时增加面积，不构成联合优势；保留种子1作为当前长测绑定版本。12 ps也不能证明长期稳定或支持更高频率。完整保存失败的种子2，不把单次布局搜索当作物理极限证明。布局实验没有独立执行效率实测，不把其面积替换进其他候选成绩。
