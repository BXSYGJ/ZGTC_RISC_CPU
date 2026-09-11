# Cache请求载荷就绪窗口采样

后续同步读Cache阶段已把本文测试对象固定到D66历史夹具；当前生产源码由 `scripts/test_cache_synchronous_read.py` 逐周期对照固定D66基线，不移用本文历史PDS/实板结论。阶段说明见 `CACHE_SYNCHRONOUS_READ.md`。

本轮从已测132 MHz分段ALU版本继续，基线实现为 `build/pds/20260907-051442-9813d121`。20份实现输入仅 `rtl/rv32_cache.sv` 改变；基线Cache为AC24EDFB，候选为C3BF25D04A223B502EFF329D2DD95BFDD7F4F559506A5DF878F38D29DDDEC8F4。仍要求执行效率不少于3.0 CoreMark/MHz、资源效率至少0.031 CoreMark/LUT，并继续提高频率，不把有限实验称为物理极限。

## 设计与边界

原先请求地址、写数据、字节使能和读写方向四类寄存器与事务状态共用 `req_valid && req_ready`。本候选在 `req_ready` 时采样四类载荷，而状态、错误资格、miss/flush事务标记仍严格只在真实握手时更新。目的为从复制后的地址寄存器CE负载中去掉上游有效资格路径；并未增加流水级、提前响应或改变缓存容量。

空闲载荷不具有事务含义。响应回压、取数/写回忙状态、刷新均不允许覆盖；重叠响应与新请求同周期时，旧事务用旧寄存器完成，新载荷在时钟沿后生效。空闲输入变化可能增加翻转活动，本轮没有功耗测量，不能称功耗优化。

## 定向验证

新增 `sim/cache_ready_payload_tb.sv`，把现有512笔随机事务及错误/刷新/重叠测试连接到候选和接受时采样的基线，逐周期比较ready/valid/error、有效响应、有效后端命令、写回数据、计数器及状态/valid/dirty/LRU。参考RTL从候选严格逆变换，要求SHA-256精确还原AC24EDFB，防止与候选一起漂移。

`sim/cache_tb.sv` 的CHECK_REQUEST_CAPTURE=2显式表示就绪窗口采样；模式1仍是历史分拆索引夹具的接受时采样，不放宽历史合同。模式2在无req_valid期间主动改变所有载荷，地址始终含非对齐及高位非法模式，覆盖空闲、忙、响应回压及刷新，不以输入保持不变冒充保持验证。

32种配置（16/32地址位宽、只读/读写、快读开关、快写开关、重叠开关）均通过；所有四类载荷检查采样/保持/复位，要求空闲、忙、回压、刷新及适用时重叠覆盖。9个实际编译的变体分别破坏采样资格、忙/刷新保持、重叠采样、事务资格、数据/字节使能/写方向或对齐位，均运行失败。原捕获测试也通过，历史分拆索引负例继续保留。该对照是测试轨迹等价，不是全状态形式证明；小几何与实用I8KiB/D2KiB需由SoC回归及编译式仿真补充。

首次测试因Icarus不允许final块调用task而编译失败，已改为final块内直接断言；保留 `build/test-cache-ready-payload-initial-compile-failure.log`，不计入负例成功。有效运行见 `build/test-cache-ready-payload.log`。

## 当前状态

完整 `build/validate-cache-ready-payload.log` 已终态通过，包含CPU/参考模型/内存比较、严格lint、GPIO、ILA及证据负例。性能短测 `20260907-071218-3b9a6a92` 为3307565周期/2748941条，验证短测 `20260907-071225-b5e10208` 为3308242周期/2749614条；实际固件、18份输入、执行文件、UART/result哈希与解析结果均重验，两份UART各自与已测132 MHz基线的匹配短测逐字节相同。只改Cache，当前没有执行拍数收益；均不足0.03秒，不计正式成绩。见 `build/cache-ready-payload-short-audit.json`。

外部RV32UI构建 `20260907-071240-341bd6ac` 41个测试/164次运行、RV32UM构建 `20260907-071414-9be8f037` 8个测试/32次运行及各4个拒绝控制均通过。196组结果与同参数基线精确相同，逐一读取成功/拒绝日志并核验HEX和16份RTL哈希。固定配置为p0_c0_s4、p1_c0_s4、p0_c1_s1、p1_c1_s4，ICacheSetBits=8；不声称此脚本覆盖DCacheSetBits=6，更不叫完整ISA认证。见 `build/cache-ready-payload-external-isa-audit.json`。

| 默认布局 | 构建ID | LUT | FF | WNS/ns | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| 132 MHz | 20260907-071123-ab4567ba | 10312 | 5049 | -0.055 | 拒绝 |
| 135 MHz | 20260907-071149-c0c798be | 10343 | 5037 | -0.175 | 拒绝 |

两组仍使用4 APM。逐份重读原始run.log/rtr，与resource-summary相等；20份冻结输入各自通过清单核验，只有Cache与基线不同。均无成功manifest，虽工具生成sbit也不得烧录。没有把131.0616/131.8913 MHz报告估值当作硬件实测频率。详见 `build/cache-ready-payload-default-terminal-audit.json`。种子1复核结果见下一节，默认布局失败记录继续保留。

原生网表确认两类Cache地址副本CE改接req_ready，153/63个地址寄存器，逐个syn_maxfan=64并保持同位D/CE/CLK/复位一致。D-cache基线CE的直接LUT输入含新请求地址高位，候选直接CE驱动由旧状态/响应/flush组成；这只是原生连接审计，不是全上游锥形式证明，也不是实际路由扇出保证。见 `build/cache-ready-payload-native-enables.json`。

132 MHz唯一失败路径转到只读I-cache的beat，经缓存数据读出与仲裁写数据进入RAM暂存；布线占86.229%，beat报告扇出2053。135 MHz最差路径为D-cache返回值经加载前递、ALU进位到mem_result。下一结构方向是验证只读Cache永不写回后静态去除其无效写回载荷读口，以及单独考察ALU高半段保留；尚未实现。原始路径保留于 `build/cache-ready-payload-critical-paths.json`。

没有新的实板测量，不用短仿真或失败布局面积更新正式成绩。源码与构建进度见 `build/cache-ready-payload-local-state.json`。本轮不提交、不推送GitHub。

## 种子1复核与待上板候选

| 布局种子1 | 构建ID | LUT | FF | WNS/ns | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| 132 MHz性能种子 | 20260907-072316-20241afd | 10277 | 5036 | +0.031 | 本地通过，尚未上板 |
| 135 MHz性能种子 | 20260907-072343-c7dd0ade | 10258 | 5052 | -0.242 | 拒绝，不得烧录 |

两组均为4 APM，原始构建脚本、run.log和placement-config确认实际使用 `pnr -gplace_seed 1`；与默认布局及已测基线相比没有放宽约束。成功132 MHz位流SHA-256为 `9FE80FCC657433F4D7F3ECCB4506825FBBCD8497C7372052697666828BA0DA24`，6000轮性能固件仍是 `65416C7D16CCDF6B46B881B1BE21C37D54156A674056BA01DBC43DC8F9F0216E`。原始报告、资源、20份快照、固件、位流及成功manifest重验通过；135 MHz不生成成功manifest。见 `build/cache-ready-payload-seed1-terminal-audit.json`。

相对已测132 MHz分段ALU基线10353 LUT/5023 FF/WNS +0.103 ns，本候选少76 LUT（约0.7341%），多13 FF，正时序裕量减少0.072 ns。这个比较同时改变Cache RTL与布局种子，不能把全部差异单独归因于使能分离，也不能称三指标都改善。短仿真周期不变；在新实板性能/验证长测前，不把旧UART与较少LUT拼成新的正式资源效率成绩。

匹配6000轮验证种子 `20260907-073359-03854fd7` 已终态通过：10277 LUT、5036 FF、WNS +0.031 ns，与性能实现完全相同。验证位流SHA-256 `CC045B6A91EB74936D1B1287148742310431E648B105BD77ECF3DC9C7261CA32`；两组原始报告、20份冻结输入、位流、各自种子/时钟/轮次固件及成功manifest均独立重验。见 `build/cache-ready-payload-matched-pair-audit.json`。会话72748已退出0，无需重启。本页C3候选已封存；随后生产源开始只读写回载荷专项修改，详见 `CACHE_READONLY_WRITEBACK.md`，不影响这对冻结构建。尚未预约或烧录本候选，不更改历史实板成绩，全部目标仍未完成。
