# 顺序取指PC预计算实验

## 测量驱动的目标

参考为MMIO ready-payload与16 KiB I-cache组合：135 MHz种子1、9220 LUT、5726 FF、WNS +0.117 ns。其最差路径并非单纯PC+4，而是next_pc[16]经预测器折叠索引、模式计数器、方向选择再进入next_pc高位进位。11级逻辑，逻辑2.261 ns、布线4.738 ns；fetch_index[2]扇出132。路径见build/mmio-ready-payload-i9-physical-audit.json。

因此不能仅凭端点把瓶颈归因于32位加法。本实验尝试把顺序PC预计算保留在预测选择之前，观察PDS是否仍合并为预测后进位；是否有效必须由原生网表和布局测量证明。

## 两种独立候选

- kept：保留完整32位next_pc+4组合信号，两处fetch_prediction/next_pc的非跳转分支复用该信号，其他逻辑不变。
- grouped：低2位保持，bit9:2加1，更高8/8/6位分别以低位全1归约作为进位；保持32位模加语义，不假定PC低2位为零、不截断高地址。分组旨在缩短进位依赖，不新增流水拍或状态。

候选仅改变rv32_core.sv，20项物理输入的其余19项与MMIO参考完全相同；DB55同步可写缓存、H3/C2预测器、2080 MMIO、参数及固件不变。core SHA-256分别为7D1F39C60EC2F8062E99653CE2B2BFBB6803C8668EB5E62C5227BC5876A25CE2、25C68E899A0F2D4F5E09A7129EF9B3BFA9C1EBB638601C797B751BB0EADA8206。

## 已完成验证

scripts/test_fetch_pc_precompute.py对原始基线与两候选、预测器开/关共6次真实核心编译运行，每次11504例，总计69024例。覆盖全部64种预测命中/方向、flush、维护阻塞、取指活跃与完成组合；全32位回绕、所有位位置的进位边界、未对齐低位及10000个确定性随机值；逐拍检查next_pc与fetch_prediction，不仅检查独立加法表达式。

11个真实编译的语义故障均被功能断言拒绝，包括忽略命中、丢失目标、丢失预测PC更新、清除低位、错误增量和错误分组进位。原始文件哈希固定，并且仅反向替换声明及两处引用后逐字等于原始核心。初次候选末尾意外多一个空行导致严格同源检查拒绝，已删去该空行，没有放宽比较。

两候选性能/验证10轮短测均与MMIO参考逐字节UART、精确固件、周期及全部结果相同：3199743/3206720周期、2748941/2749614退休指令，CRC通过，132 MHz配置。build/fetch-pc-{kept,grouped}-short-audit.json核验18项快照只改变核心，不是正式长测分数。

## 物理测量结果

135 MHz、种子1性能PDS均已终态：kept构建20260907-162818-25c8eda7为9310 LUT、5736 FF、WNS -0.034 ns；grouped构建20260907-162915-37de1a7f为9273 LUT、5731 FF、WNS -0.021 ns。相同6000轮性能固件、参数、约束和种子，20项源码仅核心不同。两者均未通过，不生成新合格分数；负裕量不四舍五入为通过，也不因此证明其他布局不可能。

kept最差路径改为D-cache DRM输出到core/N442_4[21]，逻辑3.506 ns、布线3.271 ns；grouped最差路径为D-cache request_address[6]到缓存state_reg[5]的CE，经过effective_address[31]，逻辑2.365 ns、布线4.600 ns。局部PC路径重组没有带来本次整体时序改善，且LUT均多于参考9220；暂不替换已通过的MMIO版。完整原始路径和哈希见build/fetch-pc-{kept,grouped}-physical-audit.json。

CPU/SoC、参考轨迹与内存、旁路、独立快速读写/重叠、随机指令、lint和外部RV32UI/RV32UM两批均终态通过；392次正例与16次拒绝的独立源码/固件/周期审计见build/fetch-pc-precompute-isa-audit.json。

Icarus对kept声明赋值上的综合属性提示忽略；仿真仅验证功能。随后检查PDS原生网表，kept的sequential_fetch_pc[31]确实由GTP_LUT6CARRY产生，输入含next_pc[31]和前级进位；grouped的同位由GTP_LUT3产生，输入含next_pc[30]/[31]和归约中间节点。build/fetch-pc-precompute-native-observations.json保留精确实例及网表哈希；这是网表驱动观察，不是全网表等价证明，也不能按命名输出数量推断丢失位宽，因为PDS会使用别名和跨层级优化。

新候选未替换生产输入、未上板、未上传GitHub。状态与后续结果见build/fetch-pc-precompute-local-state.json。当前有限试验不证明物理极限；下一步应优先研究扩容造成的资源代价与实际数据侧路径，而非在失败PC候选上直接报告更高主频。
