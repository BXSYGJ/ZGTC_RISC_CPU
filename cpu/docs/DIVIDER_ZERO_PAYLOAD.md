# 除零响应载荷的空闲采样

## 动机

BTB旋转4的功能收益已在相同固件短测中确认，但132/135 MHz正式时序失败。132 MHz最差路径到M单元response_data[31]，包含从D-cache经前递的操作数B及其请求资格逻辑。该报告提示可尝试把数据写入与请求生效分开，不是仅凭RTL推测已经解决物理路径。前阶段原始证据见BTB_FOLDED_INDEX.md。

## 实现及协议边界

仅将response_data <= req_operation[1] ? req_operand_a : 32'hffffffff从IDLE中“有请求且除数为0”分支移到既有无条件IDLE载荷采样块。状态机仍仅在有效M除零请求接受后进入RESPONSE；MUL、DIV/REM运算、取消、复位和输出valid资格未改变，无新增周期。

空闲时数据寄存器可以随输入变化，但rsp_valid必须为0。IDLE采样后的除零除法返回全1，除零余数返回原被除数；忙态和RESPONSE背压期间不允许被新输入覆盖。正常除法最终仍由DIVISION_RESULT写入，乘法响应路径保持原样。不能将空闲载荷变化描述成接受了新请求。

修改前M源码AA1BF3E9AC51E8179B9C52B7ADA90DE816B219AC7263D7FB973A9289D5164C79；修改后1079EF43882452422508E2247AF93699B357E3EAAF0B3118A8C95E5434457DC5。BTB继续使用旋转4/F467693E候选，Cache保持已测AC24EDFB源码。

## 定向验证

新增默认关闭CHECK_IDLE_RESPONSE，独立检查IDLE边沿的载荷及无请求样本覆盖。test_divider_zero_payload.py运行全部8种运算、边界值、随机值、响应时延、背压、取消和复位，共12544项原有检查；额外验证请求资格误加回、余数错误、忙态覆盖三个反例均可观察地失败。已通过，日志test_divider_zero_payload-folded.log。

既有test_divider_operand_capture.py继续通过；run_muldiv_core_tests.ps1使用BTB8/EarlyD/FetchOverlap，精确M中断场景通过，日志divider-zero-payload-core.log。该定向通过尚不替代本轮完整回归和新物理实现。

## 短测与在途实现

两种10轮短测CRC通过：性能3307565周期/2748941退休，验证3308242/2749614，分别为build/compiled/20260907-044436-179410b2、20260907-044441-9c0edd87。与上一阶段折叠旋转4完全一致，不把空闲数据采样改变称作执行拍数再提升。

## 默认布局终态

| 配置 | LUT | FF | APM | WNS/ns | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 132 MHz | 10262 | 5040 | 4 | -0.008 | 时序失败，不上板 |
| 135 MHz | 10272 | 5047 | 4 | -0.231 | 时序失败，不上板 |

构建分别为build/pds/20260907-044459-34066263和20260907-044527-94c40bf3，均已终态且无成功manifest。132 MHz虽比前阶段改善0.182 ns，但仍有8 ps负裕量；不得四舍五入成0或放宽约束冒充通过。135 MHz则比前阶段恶化0.062 ns，不声称所有实现都改善。原始报告、位流、固件和源码独立核验记录为build/divider-zero-payload-terminal-audit.json。

完整validate-divider-zero-payload.log终态通过；新源码外部RV32UM为8项/32次、RV32UI为41项/164次，各四类拒绝控制通过，报告build/isa/20260907-045129-405a46aa及20260907-045204-7925dcc3。不称完整ISA认证。

## 原生写使能逻辑证据

独立读取修改前后132 MHz综合VM，32个response_data FF各自共享的CE网络由N422变为N431。仅在rv32_muldiv模块内部，沿LUT输入保守追踪、遇到寄存器输出或模块输入停止：旧网络包含32个req_operand_b位，新网络为0；两个图中分别访问56/14个网络且没有未解析叶子。此统计不是整个芯片的传递依赖闭包，也不证明每条结构路径都可逻辑激活，不代替形式等价或布线时序。

证据build/divider-zero-payload-native-enable-cone.json包含两个VM哈希和分析函数原文。重新接入一个除数位能够被检测，删去CE驱动会得到未解析网络而非伪造“不依赖”，控制结果见build/divider-zero-payload-native-enable-controls.json。

## 后续布局种子

保持同一20份生产输入、132 MHz固件和约束的PlacementSeed=1/7均已失败终态：build/pds/20260907-045753-3793ccde为10235 LUT/5057 FF、WNS=-0.095 ns；20260907-045821-28ba584c为10256 LUT/5041 FF、WNS=-0.111 ns。全部无成功manifest，原始报告、快照、固件及实际pnr -gplace_seed命令独立核验见build/divider-zero-payload-seed-audit.json。没有烧录，也没有把近零负值当成通过。下一步为ALU_CARRY_SELECT.md的新算术路径实验，其新源码与本页全回归状态不能混用。
