# 加载及相等分支操作数选择器实验

2026-09-07。基线为已完成独立6000轮双种子的全偏移加载旁路版：144 MHz、8626 LUT、5123 FF、WNS +0.005 ns。本实验只改变供加载地址与BEQ/BNE使用的特殊操作数选择，尝试减少级联选择级数；不改变生产RTL，也不上传GitHub。

## 等价改写意图

基线branch_operand_a/b先取得通用forwarded_a/b，再由MEM加载专用选择覆盖。通用操作数内部已有WB及MEM优先级选择，因此特殊操作数跨越两套选择条件。新实现直接按合法且匹配的MEM、WB、EX原操作数顺序选择，未使用或编号为零的源操作数仍强制为零。

MEM合法条件包括mem_valid、mem_writes、非零目的寄存器和无mem_exception。mem_value已包含字节/半字扩展，并在非加载时等于mem_result，所以两种bubble配置都可使用同一特殊选择器。普通ALU、关系分支、存储、JALR、CSR、乘除法继续使用原通用操作数和原停顿；有效响应、错误冲刷、精确异常和请求发出控制没有修改。

- priority：显式MEM优先于WB，再选择EX原值，用条件选择表达。
- onehot：把MEM、WB与EX选择转换为互斥掩码，再作按位与/或；WB必须排除MEM已选中，EX必须排除前两者。

这是待验证的等价改写，不是形式化等价认证或更快的预设结论。除该选择器区域外，只增加一个文件末尾LF。此差异在源码哈希中完整保留，结构检查明确只接受这一个LF，不宽泛忽略空白，更没有修改已生成的物理快照。

| 候选 | 核心SHA-256 |
| --- | --- |
| priority | 75CB8752316D7D2710174BA8E3B3DD74DAB535CEA4D4432567C6E6220129915E |
| onehot | DFF62DB6E9FB8178D70449DDBF58381241870D0338CEB77DFC3D3E995BE9B879 |

源位于experiments/load_operand_select/rv32_core_priority.sv和rv32_core_onehot.sv；两独立stage以load-operand-select-开头。20项PDS输入中，除核心外其余19项与基线相同，单独核验其实际生成顶层、固件路径和参数。

## 验证及结构检查修正

scripts/test_load_operand_select.py复用独立地址/分支检查与毒化测试，不使用新选择器自身作为参考模型。每种均完成两种bubble配置的5263360次检查，以及全部4096个有符号加载立即数的4227072次地址算术检查，合计9490432次。priority拒绝22个逻辑变异，onehot拒绝25个；各自另有3个错误/无效响应毒化变异和1个恢复全停顿变异。

初次各7个方法中，6个功能方法通过，1个严格结构检查因文件末尾额外一个LF失败；完整运行分别551.290/605.266秒，原失败日志保留。随后结构检查明确限定这一已核实且已计入哈希的单个LF，两候选各独立重跑该方法通过（0.030/0.024秒）。RTL、固件、物理快照和其他功能断言均未改变；不能把原日志说成一次7/7全绿的运行。证据为build/test-load-operand-priority.log、build/test-load-operand-onehot.log与build/test-load-operand-structure-correction.log。

为复用既有测试，只给地址测试助手增加candidate_path/project_path可覆盖入口，默认路径不变。原默认地址候选的缓存正例/全停顿拒绝及两bubble通用矩阵重新通过（2方法，113.231秒），见build/test-load-address-default-helper-regression.log。

两候选均通过真实零/正/负偏移相邻指针固件、两预测器CPU参考和内存差分、13个精确陷阱、14个M中断用例、74项SoC检查及41项故障SoC检查。板级严格lint各覆盖bubble/predictor/cache的8种组合，不抑制警告。

每种另外完成196次外部RV32UI/M执行和8个拒绝控制；逐案退休指令、周期、固件与全偏移旁路基线完全一致，不冒充完整ISA认证。

| 候选 | RV32UI构建 | RV32UM构建 |
| --- | --- | --- |
| priority | 20260907-224636-2c805e11 | 20260907-224914-b5c76305 |
| onehot | 20260907-224659-a30a0628 | 20260907-224937-e82bf140 |

## 同固件短测

两种十轮种子均保持3205068/3211054周期，退休指令2748941/2749614，CRC及全部缓存计数与基线一致。priority构建20260907-224615-90747345、20260907-224628-206f9c3e；onehot构建20260907-224640-f69c3173、20260907-224655-fe520530。

build/audit_load_operand_select.py要求完整短测result对象以及每个ISA结果与基线相等，并核验18项仿真输入仅核心改变。短测都不足10秒，不据此生成新的完整或实板CoreMark成绩。

## 144 MHz实际物理结果

| 候选及构建，种子1 | LUT | FF | WNS/ns | 结果 |
| --- | ---: | ---: | ---: | --- |
| 原全偏移旁路，20260907-214049-939f2469 | 8626 | 5123 | +0.005 | 完整双种子本地基线 |
| priority，20260907-224520-6880a9f2 | 8738 | 5126 | +0.011 | 合格，但无联合优势 |
| onehot，20260907-224542-73b14b5c | 8704 | 5147 | -0.021 | 时序失败，无合格manifest |

priority位流SHA-256为DF4A3EEC47994030DD75BBE60ED7316CCBE5DC79B30938843A4CDFC4C943F89E。全部专用资源与基线相同；审计检查原生映射而非只相信资源清单。

priority最慢三条路径从D-cache RAM时钟端到mem_cause[2]、mem_exception、mem_next_pc[1]；onehot则到D-cache状态寄存器使能。路径来自各自原始时序报告，不能凭代码行数或逻辑形式猜测瓶颈。

priority只增加6 ps时序裕量，却增加112 LUT、3 FF，固定144 MHz的短测周期又未改善；因此不替换原版，也不为它自动再跑完整成绩。onehot的功能正确不抵消时序失败，生成位流不等于可部署。两种结果和失败点都保留。有限选择器/布局搜索不证明物理极限。

## 审计与后续

priority使用build/audit_load_operand_select.py --variant priority --require-timing，onehot不要求通过时序但核验真实失败报告；两份审计均完成，分别输出build/load-operand-select-priority-qualification.json和build/load-operand-select-onehot-qualification.json。审计包含实际顶层固件路径、20项物理快照、原始时序/资源、原生LRU/APM映射、双短测、逐案ISA日志与8种板级lint。

保持已完整配对的全偏移旁路版为当前候选。后续优先研究实际加载地址/异常和D-cache控制路径，同时保留无效/错误响应的请求隔离与精确陷阱，不删计数器、不忽略负时序、不混用旧分数与新面积。新源实板长测、ILA、GPIO独立输入、SCBV和长期稳定性仍未完成。
