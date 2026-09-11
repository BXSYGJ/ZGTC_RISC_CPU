# 循环提前旁路的同PC直接匹配

## 前提与改动

上一轮CPU判零消冗候选在157.5 MHz以9585 LUT、WNS -0.411 ns失败，不继续叠加。下一轮返回已冻结的732509AD CPU，只改两槽循环预测器。

规范源码experiments/loop_predictor_pending_pc_match/rv32_btb.sv，SHA256 97D0E8FB6FBB695AD44533A1530632528CCEB0FC1555422986110061BB466686；父预测器74F4600463529ECA9520CD23D240AEAC75BB95B506932E4EB80544DFD8AEF896。唯一替换为：

- 原条件：update_target<update_pc && loop_update_match && loop_fetch_index==loop_update_index
- 新条件：update_target<update_pc && fetch_pc==update_pc

其余train_update、invalidate、条件分支、taken和向后分支保护不变；训练侧仍使用原loop_update_match，计数、方向、提前方向、置信度和分配状态完全不变。

## 等价依据与限制

此旁路只在外层prediction_hit、条件分支与loop_use同时成立时影响预测。loop_use已确认有效循环表项的PC标签等于fetch_pc；原条件再要求更新使用同一槽且PC标签匹配update_pc。在prediction_hit与train_update的地址宽度、对齐保护下，两侧完整PC相等，与直接比较一致。逆方向中完整PC相等也意味着折叠索引和循环槽索引相同，且匹配同一有效标签。

这是对有效二态状态和现有参数约束的逻辑推导，不声称任意X/Z状态整模块形式等价，也不提前声称面积或时序改善。保留高位范围、非对齐、同槽不同PC、不同槽、无效更新、失效、前向更新和非条件分支反例。

## 已完成

scripts/test_loop_predictor_pending_pc_match.py：3项4.460秒通过；精确一行差异可恢复父源码。复用原独立软件参考和时钟边沿前后向量，五种索引/地址/哈希配置共58107行、116214次查询全部通过；11个实际运行错误变体均被拒绝，包含缺少/反转PC比较。

隔离工程build/loop-predictor-pending-pc-match-stage已建立，冻结基线CPU732509AD和另外18份硬件输入不变，仅替换BTB。8种严格板级lint、缓存CPU独立参考及5个PowerShell入口解析/BOM检查通过。

双短测20260909-080638-cb95472b / 20260909-080656-d2049e3c为3141619 / 3146376周期，各比冻结基线少9900周期，退休2748941 / 2749614、CRC fcaf / c64e；完整结果与原始UART逐字节等于两槽旁路父版。ISA 98对/196次和8项错误输入拒绝、SoC 4对/8次保持精确周期、轨迹、内存与外设结果。额外映像哈希和实际BTB源路径也纳入证据审计，反例套件5项445.553秒通过，21个源路径/映像/元数据和原始证据篡改均被拒绝。

PDS 20260909-080806-ca492baf已终态失败：157.5 MHz、布局种子2，9547 LUT、5328 FF、WNS -0.317 ns。相比两槽旁路父版9475 LUT增加72 LUT，WNS退化0.059 ns。20份物理输入、顶层、完整性能固件、网表和位流均已绑定原始报告核验；没有合格manifest。最差路径从mem_result[2]到id_instruction使能和取指缓存存储状态使能。没有运行完整6000轮或验证固件PDS，不替换冻结基线。

实际综合网表4966022F647F201C82280F54C508299EE218113023426778FA91BD026938FA4A中，同PC比较映射为N81.eq进位链，末级仍比较fetch_pc/update_pc的[31:30]。因此另行准备有地址范围/对齐保护的位段比较候选419D7806；不修改本次正在实现的源码或把它的结果归给新候选。

物理证据控制4项32.476秒通过，8项原始固件、规范源、顶层和元数据篡改被拒绝，实际--require-timing入口拒绝晋升。

不替换157.5 MHz的已冻结501.065730222本地基线；后续严格保留执行效率提升、主频不降和资源效率不降三项门槛。GitHub保持不动，AI暂缓，其余原始非AI任务未宣布整体完成。
