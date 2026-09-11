# Cache索引扇出与拆分请求寄存器

## 目标与基线

以已测132 MHz、3.0129694974 CoreMark/MHz、0.03863531899 CoreMark/LUT的全地址maxfan64版本为基线。本轮试图减少寄存器复制的FF代价、改善时序裕量，并尝试135 MHz；不得把仿真、综合或失败布局当作新实板成绩。已测版本见HARDWARE_132MHZ.md。

## 第一阶段：只约束索引线，拒绝采用

将syn_maxfan=64从32位request_address寄存器移到request_set/request_word两条索引线，不改功能逻辑。源码SHA-256 3445B9D7705C063A892E110859927D06217DF8039DC41625BCBB36860AA311F6，已逐字节隔离到experiments/cache_index_fanout/rv32_cache.sv。

原生网表中属性位于wire上，DFF仍带PAP_PRESERVE。两个缓存的地址FF仍为153/62、最大直接负载引脚次数仍为64，36个D恒为0的位仍存在。由此只能得出本例未消除保留开销，不能泛化为任何网线属性都无效。

原有审计器针对DFF上的PAP_MAX_FANOUT字段，因此严格模式正确拒绝这种新网表表示。没有把属性缺失直接改成通过；新增显式--inspect-only只观察复制连接，输出cell_attribute_validation=not_checked，继续检查副本D/CE/CLK/C/INIT及Q唯一性。原严格默认不放宽。观察结果为build/cache-index-maxfan64-native-inspection.json，不等同于完整属性约束认证。

| 配置 | LUT | FF | APM | WNS/ns | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| 已测全地址132 MHz | 10294 | 5041 | 4 | +0.001 | 保留原实板成绩 |
| 索引线132 MHz | 10203 | 5042 | 4 | -0.090 | 拒绝上板 |
| 索引线135 MHz | 10299 | 5032 | 4 | -0.267 | 拒绝上板 |

失败构建分别build/pds/20260907-033714-26d51a80、20260907-033740-b7127057，均已终态，均无成功manifest.json。虽然132 MHz少91 LUT，但FF没有减少且时序失败，不能算合格资源效率提升。完整validate-cache-index-maxfan64.log终态通过；功能通过不覆盖物理失败。

## 第二阶段：独立保存标签、索引与低位

现把保存的请求地址拆成三个独立寄存器：request_index仅保存字索引与组索引，带syn_maxfan=64；saved_request_tag保存标签；saved_request_alignment保存低2位。32位request_address仍存在，但变为三个字段拼接并在高位补零的组合线，保留原有命令地址及查找接口。

三个字段在同一个req_valid && req_ready边沿采样，同一复位条件清零，忙态和背压期间不接受新请求就保持。高位补零范围由ADDRESS_BITS决定，不将输入高位非法地址静默变成有效请求；原来的越界、非对齐和只读写错误检查仍直接检查req_address。无新增流水级、无新增Cache/CPU停顿周期。

候选源码SHA-256 3CBF9F55E63BC492A1866D4609DCEA8106F2517FD273C9EC81B76DFC5B6644AC。它与已测132 MHz版本不同，尚不能沿用该版本的实板成绩或ILA哈希锁。

## 原生综合网表观察

拆分后，request_index上的DFF属性及副本控制连接独立核验通过。request_index和saved_request_tag分别作为明确选择的寄存器族统计；不把局部索引数量直接冒充全地址总数。原生证据为build/cache-split-index-maxfan64-native-audit.json。

| 模块 | 索引FF | 标签FF | 低位FF | 合计 | 恒零FF |
| --- | ---: | ---: | ---: | ---: | ---: |
| rv32_cache | 131 | 4 | 0 | 135 | 0 |
| rv32_cache_1 | 40 | 6 | 0 | 46 | 0 |

两模块合计由215降至181，即减少34个请求寄存器。36个恒零FF已消除，但比原版多了2个正常索引副本，因此不是总数减少36。索引最大直接负载引脚次数仍为64。该统计来自综合VM，不替代布局后整个CPU的FF/LUT，也不证明时序改善。

## 验证与一次测试模型纠正

cache_tb新增默认关闭的CHECK_REQUEST_CAPTURE：在每个边沿独立跟踪接受请求时截断/补零后的完整地址，验证重构值、忙态保持及复位。test_cache_request_capture.py覆盖16/32位地址、只读/读写、快速读开关、快速写开关、重叠开关的32种组合，外加标签置零、索引移位、低位抹零、忽略ready和错误高位扩展5个反例。低位抹零主要保护内部完整地址重构约定，不声称只改该内部位一定造成外部事务错误。

初次32组合测试有8项失败：旧overlap_stream假定每拍返回一个热读，却被新测试用于FAST_READ_HIT=0。使用已测基线RTL复现同一失败，记录在build/cache-split-request-baseline-probe.json。没有删除快速读的逐周期断言；为慢读新增按req/rsp握手计数、带响应背压的64请求流，快速读继续走原严格检查。修订后32种组合及5个反例通过，记录为test-cache-split-request-fixed.log。

两组132 MHz、10轮短测分别3326116/3329203周期、2748941/2749614退休指令，CRC通过，与基线相同。目录build/compiled/20260907-035723-86ae0666、20260907-035730-ebf110cf。短测不能证明≥10秒板测得分。

## 物理终态与恢复

| 配置 | LUT | FF | APM | WNS/ns | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| 拆分132 MHz | 10161 | 4977 | 4 | -0.523 | 时序失败，不上板 |
| 拆分135 MHz | 10297 | 4994 | 4 | -0.220 | 时序失败，不上板 |

拆分候选132 MHz构建build/pds/20260907-035627-125327e3、135 MHz构建build/pds/20260907-035654-6744ffb7均已失败终态，无成功manifest.json。132 MHz虽然比已测版本减少133 LUT、64 FF，却损失0.524 ns时序裕量，不能采用其面积配合旧成绩计算新的合格资源效率。完整validate-cache-split-index-maxfan64.log终态通过；它验证功能，不覆盖布局失败。

两份实验源码分别保存在experiments/cache_index_fanout与experiments/cache_split_index，SHA与实际PDS快照一致。生产rtl/rv32_cache.sv已恢复为AC24EDFB561B454437519B452E5F6F90AA4C7DC538400D919919BC011877D633；全部20项RTL、PLL及约束输入逐项匹配已测132 MHz性能实现。四组失败构建的原始rtr/run.log独立重解析与resource-summary一致，输入快照、位流及固件哈希见build/cache-index-split-terminal-audit.json，不伪造成功清单。

恢复后test_cache_request_capture.py明确对隔离拆分源码运行32组合/5反例，另对真实生产源码运行16/32位地址和只读/读写的4组合。三个测试方法全部通过，记录build/test-cache-request-restored.log；原生网表审计8项、缓存查找控制2项通过，validate.ps1语法及UTF8 BOM检查通过。保留新增验证，但不让默认工程引用失败实验。

本轮没有预约新板卡，没有提交或上传GitHub。当前源ILA、独立GPIO输入、SCBV/电气约束、长期稳定性和执行效率进一步优化仍未完成。
