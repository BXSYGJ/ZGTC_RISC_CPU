# 只读Cache写回载荷静态裁剪

后续阶段提示：本文D66为历史本地合格基线，完整源码保存在 `experiments/cache_readonly_writeback/rv32_cache.sv`。当前同步读块RAM候选另见 `CACHE_SYNCHRONOUS_READ.md`；原ready-payload测试现针对固定D66夹具，新测试逐周期比较当前生产源码与D66，不把本文实现在后续改动后仍称为当前源。

本轮基于就绪窗口采样C3BF25D0版本，其132 MHz种子1性能实现 `20260907-072316-20241afd` 与验证实现 `20260907-073359-03854fd7` 已独立终态通过：10277 LUT、5036 FF、WNS +0.031 ns。二者仍未上板，不能替代AC24EDFB版本的实板成绩。C3完整源保存在 `experiments/cache_ready_payload/rv32_cache.sv`，固定SHA-256为C3BF25D04A223B502EFF329D2DD95BFDD7F4F559506A5DF878F38D29DDDEC8F4。

## 唯一实现改动

当前候选Cache为D66A1DAF2969E316084221C0FFE86772AD1B8ADD0540C0989ED215121F3CCE8B；20份实现输入相对C3只有Cache不同，且只有一条assign改变：READ_ONLY非零时w_data固定为零，读写Cache仍从storage[{victim,beat}]读取。w_valid、cmd_write、状态机、写保护、地址检查、容量、响应时刻和请求资格均未改变。

依据上一轮实际132 MHz失败路径，只读I-cache的beat到写回数据再到后端RAM暂存形成高扇出长布线路径；源实例READ_ONLY=1，原生实例i_hit_count连接确认其为I-cache。静态删除这个无有效事务使用的读口，而不是设置假路径、降低时钟或屏蔽写回控制错误。新实现是否真正减少逻辑和路由仍须原生网表与PDS报告验证。

## 不变量与测试边界

从复位状态作源码级归纳：dirty清零；唯一置脏赋值要求READ_ONLY==0，其他赋值均清零。只读配置下dirty因此保持零。进入WB_CMD的两个入口分别为缺失替换的valid&&dirty和FLUSH_SCAN的valid&&dirty，均不可成立；WB_DATA/WB_ACK只能从该写回链进入。因此合法复位启动后不会发出有效写回，w_data的非握手取值不影响接口行为。此为针对当前RTL的推理，非工具生成的全状态形式证明，不覆盖状态位物理翻转故障。

现有逐周期miter继续与固定AC24EDFB基线比较所有有效协议数据、握手、错误、计数与缓存元数据。参考逆变换明确包含就绪采样和只读载荷两处，仍要求完整参考哈希精确匹配；另外要求当前源撤销这一条assign后与C3夹具逐字节一致，防止参考随候选漂移。

32种位宽/只读性/快读/快写/重叠组合通过。只读组合逐周期断言dirty、写回计数均为零，不发有效写命令或写数据，并检查w_data恒零。保留9个就绪窗口反例，新增4个编译后运行控制：恢复只读旧载荷、误清零读写载荷、只读有效写命令、只读置脏。恢复旧载荷只违反静态裁剪目标，并不被宣称为原设计功能错误；另三项检查协议/内容/保护损坏。共13个运行控制均被拒绝，4个unittest方法通过，日志 `build/test-cache-readonly-writeback.log`。

## 本地筛选结果

同种子1的两组实现已终态，完整 `build/validate-cache-readonly-writeback.log` 也以PASS结束。相对C3同频、同种子、同参数、同固件比较：20份输入只有Cache不同，Cache仅一条assign不同，规范化构建路径后的顶层Verilog逐字节相同。没有修改时钟约束或借用别的固件成绩。

| 频率/种子 | C3 LUT/FF/WNS | 只读裁剪 LUT/FF/WNS | 状态 |
| --- | --- | --- | --- |
| 132 MHz / 1 | 10277 / 5036 / +0.031 ns | 9236 / 5064 / +0.082 ns | 本地通过，未上板 |
| 135 MHz / 1 | 10258 / 5052 / -0.242 ns | 9345 / 5060 / -0.005 ns | 仍失败，禁止烧录 |

132 MHz构建 `20260907-074248-6dd640cf` 的位流SHA-256为 `82F81634B7C8F149D185702B7BC877FCD27DCFB00D9D05D038FC12725C54BD2E`。同频少1041 LUT（约10.13%），增加28 FF，WNS改善0.051 ns，仍使用4 APM。135 MHz构建 `20260907-074313-45e7cb23` 没有成功manifest；0.005 ns违规不按四舍五入当作通过。原始run.log/rtr、资源清单、快照与成功构建固件/位流均重验，见 `build/cache-readonly-writeback-seed1-terminal-audit.json`。

两组原生综合网表都删除I-cache的w_data输出及256个GTP_RAM256X1SP副本，原有1056个GTP_RAM64X1DP保留；D-cache仍有536个GTP_RAM64X1DP，写有效与写回计数输出保留。D-cache的写回数据在旧/新网表中都已被拆成优化网，不凭缺少w_data端口名称推断写回被清零。综合LUT在132 MHz为9862→8790，135 MHz为9852→8873；这些不是布局后的资源分母。见 `build/cache-readonly-writeback-native-audit.json`。

双种子10轮短测 `20260907-074344-9236bf17` / `20260907-074351-e903d236` 分别3307565/3308242周期、2748941/2749614退休指令；18份输入、执行文件、固件、UART/result哈希与独立解析均核验，每份UART各自与匹配C3短测逐字节相同。没有执行拍数收益，也不把约0.025秒短测当作正式成绩。见 `build/cache-readonly-writeback-short-audit.json`。

外部UI `20260907-074416-464ba325` 41个测试/164次运行、UM `20260907-074550-d4f64df6` 8个测试/32次运行及各4个拒绝控制通过。196组结果与C3基线精确一致，逐份核对成功/拒绝日志和HEX，16份RTL输入哈希匹配。固定四配置p0_c0_s4、p1_c0_s4、p0_c1_s1、p1_c1_s4，ICacheSetBits=8；没有声称该脚本使用DCacheSetBits=6或完成全ISA认证。见 `build/cache-readonly-writeback-external-isa-audit.json`。

135 MHz额外两组复核均失败：默认布局 `20260907-075525-f5e3cd17` 为9304 LUT/5067 FF/WNS -0.307 ns；种子7 `20260907-075552-fda8c2f0` 为9328 LUT/5040 FF/WNS -0.088 ns。与种子1的20份源、固件和规范化顶层一致，实际pnr命令与placement-config核验；均无成功manifest，不得烧录。记录见 `build/cache-readonly-writeback-layout-followup-audit.json`。这三组有限布局不能证明135 MHz的物理极限，但也不能把最好-0.005 ns算作通过。

## 匹配验证位流与交接

132 MHz/种子1的验证实现 `20260907-080659-d397823a` 已完成，与性能实现同为9236 LUT、5064 FF、WNS +0.082 ns。验证位流SHA-256为 `8FD19C6D3B704A3DD7CBABD3A4AB71F63867A902DAFD271726417DBB20C694F0`。两份6000轮固件各自核对种子/时钟/迭代清单与实际字节，20份冻结输入与当前生产源一致，规范化顶层与配置参数一致，原始PDS报告和位流哈希均重验。见 `build/cache-readonly-writeback-matched-pair-audit.json`。这是PDS构建成对通过，不表示执行了新的6000轮实板长测。会话23110已退出0，本轮全部PDS及测试任务均终态。

本轮只读检查确认19474仍由Chrome监听且CDP版本元数据可访问，19507没有监听；没有启动浏览器、打开网站、预约或烧录板卡，也未验证当前网站登录是否仍有效。此前新端口启动被拒绝的限制未被绕过。因用户后续AGENTS要求另开端口，下一次板测需确认是否可直接复用用户先前授权的19474会话；不通过代理端口、替换启动工具或更换浏览器规避限制。

## 后续结构方向

四组当前路径均从D-cache请求地址副本出发，布线占约65%至78%。132 MHz最差终点为mem_result；三组135 MHz最差终点分别是MMIO strobe CE与Cache状态CE，并非都在ALU终点。原始路径摘要和报告SHA-256见 `build/cache-readonly-writeback-critical-paths.json`，不再仅凭旧路径泛化下一改动。

优先检查这些返回数据/新请求资格路径的扇出与捕获使能。更大结构方向是同步RAM读口：在ready窗口提前选择新请求地址，保留现有命中拍数，并显式处理填充末拍、同址读写、连续重叠及回压；不能为了更容易实现存储映射而默认增加命中气泡、牺牲3.0执行效率门槛。这些后续方案尚未实现，也没有推算成成绩。

具体哈希与下一步见 `build/cache-readonly-writeback-local-state.json`。尚无新实板成绩，不将旧UART与9236 LUT拼成新的CoreMark/LUT；资源效率0.031下限及完整验收要求不变。本轮不提交、不推送GitHub。
