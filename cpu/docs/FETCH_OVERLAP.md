# 可关闭的重叠取指路径

2026-09-06。FETCH_OVERLAP默认0，原有基线行为保留。新候选已通过本地回归、短CoreMark CRC和120 MHz PDS。**尚未上板长测，不产生新的正式CoreMark成绩；120 MHz下3.0 CoreMark/MHz目标仍未达标。**

## 电路变化

- rv32_core在旧取指响应真正握手时，直接用已经保存的next_pc发出下一请求。取指PC、预测目标与下一条响应保持对应；若下一请求未被接收，转回原有寄存保持路径。不是增加第二个未完成事务。
- rv32_cache增加READ_OVERLAP，仅用于只读I-cache。旧响应握手的同一个边沿可锁存下一请求，不再必须经过空闲周期。D-cache行为不变。与FAST_ICACHE_HIT=1组合时，热命中可连续每周期完成一条响应。
- 响应背压时不提前接收第二个请求；同步冲刷与FENCE.I屏障禁止重叠发起，已经发出的旧事务仍按原规则排空/丢弃。flush_valid优先于新请求。
- 各级参数透传到SoC、板级、PDS和ISA测试。运行时配置寄存器新增bit5=FETCH_OVERLAP；默认I/D各512 B、预测开启、M开启、提前I-cache响应开启时为0e020439。关闭重叠时仍是0e020419。
- run_ila_pds拒绝直接复用未验证的旧网表探针映射。compare_coremark新增显式--variable FetchOverlap；默认仍检查FastICacheHit单变量，禁止同时改变ISA、机器码、频率或另一个前端选项。

## 同固件短仿真

固定GNU RV32 GCC 10.2.0，标准2000字节CoreMark数据集，性能种子，一次迭代。O2两次的固件SHA-256均为5F3964C9DC64E034E8F28AC08E9386B5222842B2E7F303732E6EDAE85D773DC2，退休指令严格相同。

| O2、M开启、I/D各512 B | 关闭重叠 | 开启重叠 |
| --- | ---: | ---: |
| CSR计时周期 | 799975 | 657125 |
| 退休指令 | 309824 | 309824 |
| CPI | 2.58203044 | 2.12096222 |
| I-cache命中 / 缺失 | 331436 / 10788 | 351890 / 12844 |

周期减少17.8568%，同一短工作负载的每周期吞吐提高21.7386%。I-cache缺失也增加，不能只选有利计数。验证种子重叠配置为657792周期、310272退休，标准CRC全部通过。短运行不足十秒，只用于筛选，不按1e6/cycles发布CoreMark/MHz或按120 MHz换算为实板分数。

不改变固件的PC直方图窗口为657052周期、309800退休，全部唯一映射到ELF符号，计数守恒。该窗口从iterate首次退休到stop_time退休之前，边界与CSR计时不同，不能混用。

原始证据：
- build/coremark_v0_i1_rv32gcc_rv32im_bp1_cs4_cache1_fastihit.result.json
- build/coremark_v0_i1_rv32gcc_rv32im_bp1_cs4_cache1_fastihit_fetchoverlap_profile_20260906-125404-9c310b92.*
- build/coremark_v1_i1_rv32gcc_rv32im_bp1_cs4_cache1_fastihit_fetchoverlap.result.json

## 120 MHz实现及资源代价

两套4000迭代O2固件分别构建，性能构建20260906-125758-fcf83a96，验证构建20260906-130321-b50d5273。两者均为PG2L200H-6FBB676、RemoteLab UART，CPU约束周期8.333 ns，All Constraints Met。

| 指标 | 旧M候选 | 重叠候选 |
| --- | ---: | ---: |
| 布局后LUT | 5032 | 5200 |
| 布局后FF | 3746 | 3746 |
| DRM / GPLL / APM | 16 / 1 / 4 | 16 / 1 / 4 |
| setup WNS，ns | +0.583 | +0.362 |

LUT增加3.3386%，时序余量减小；仍在120 MHz闭合，但没有证明最高可工作频率提升。PDS的125.4548 MHz估计不是实板测得的最高频率。新候选CoreMark/LUT尚缺同板长测，不能把短仿真收益冒充资源效率实测。SCBV未设置警告仍保留，外部接口时序和电气检查并未因该优化自动完成。

性能位流SHA-256：B6D08A073C044CE2A9ECDFB7062B61A29D896210584B0E0926842B97D4DFBC1D。

验证位流SHA-256：51552A9722324758CD5F756E5B9D86E13F6C7F4B59C227A18CDADCD70A1124EA。

## 验证范围

- cache_ro_overlap单元3350次检查通过：64条连续热响应每周期一条、计数一次、背压保持、错误响应后恢复、flush优先，以及原有随机事务/填充错误覆盖。
- cached_core_tb增加请求/响应守恒与最多一个未完成取指断言；保留请求地址稳定、寄存器退休差分、13类陷阱和完整16 KiB最终内存比较。新增重叠配置覆盖两种Cache规模、预测开关、提前响应开关、两种load-use模式以及uncached后端。
- 新增重叠模式下的10组M执行中断/取消测试。SoC GPIO/UART中断与维护故障路径通过。
- 上游RV32UM：8条指令测试乘4种配置，32次运行和4个拒绝控制通过，build/isa/20260906-125820-bb32791a。
- 上游RV32UI：41个测试乘4种配置，164次运行和4个拒绝控制通过，build/isa/20260906-125915-74f04999。上述外部测试启用M、提前I-cache响应与重叠、LoadUseBubble=0；不能冒充全部参数组合的ISA认证。
- build/validate-fetch-overlap.log为完整回归成功记录，包含原有基线与新的重叠回归，Verilator严格lint通过。随后扩展单变量比较器，独立13项比较器测试和12项CoreMark解析器测试再次通过。

## 编译与Cache容量筛选

以下均为M开启、重叠开启、提前I-cache响应开启的一次性能种子短仿真，CRC通过。容量指I-cache和D-cache各自容量。

| 编译 | 每个Cache容量 | 周期 | 退休指令 |
| --- | ---: | ---: | ---: |
| O2 | 512 B | 657125 | 309824 |
| O3 | 512 B | 700416 | 296234 |
| O2 | 2 KiB | 574581 | 309824 |
| O3 | 2 KiB | 552409 | 296234 |

O3在小Cache中虽然少执行指令却更慢，不能直接替换O2。增大Cache后O3更快，但需要单独评估增加的资源与时序代价；当前这张表不是正式分数或最终选择。扩大容量使用已有CacheSetBits=6参数，没有改动上游CoreMark算法源码。

2 KiB、O3候选也完成独立120 MHz PDS：build/pds/20260906-131111-119748a8，6926 LUT、4141 FF，16 DRM/1 GPLL/4 APM，WNS +0.382 ns，时序通过。位流SHA-256为DB19CF9D8DE597A75F575CAD5BDC091B1285F9D486F41049C2228E0480C24E17。该候选验证种子短仿真553653周期、296831退休，CRC通过；大Cache板级参数的严格Verilator lint通过。

与512 B、O2重叠候选比较，2 KiB、O3的短工作负载吞吐提高约18.96%，但LUT增加约33.19%。因此这个配置并非三指标全面占优，不能仅据运行更快就设为默认。编译选项与容量同时改变，不能称为Cache单变量消融；短周期与LUT的组合也不能替代实板CoreMark/LUT。下一步先量化分支错误预测和访存停顿，再比较改进路径，避免仅靠扩大Cache消耗逻辑资源。

## 复现与待办

在仓库根目录运行：

```powershell
pwsh -NoProfile -File cpu/scripts/validate.ps1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -EnableM 1 -FastICacheHit 1 -FetchOverlap 1 -Profile
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -EnableM 1 -FastICacheHit 1 -FetchOverlap 1 -ValidationRun
pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1 -EnableM 1 -FastICacheHit 1 -FetchOverlap 1 -Suite rv32um
```

13:05左右，先前独立Chrome的9236调试端口断开，重新检查确认连接被拒绝；新建9240端口的Chrome启动被执行工具策略拒绝。本轮未申请/烧录板卡，不绕过该策略。恢复允许的浏览器入口后，需用匹配固件在同一PG2L200H上比较重叠开关，完成至少两次性能长测和验证种子长测，再运行硬目标门槛与三指标比较。

当前仍以M_EXTENSION.md中的1.2489599204 CoreMark/MHz作为已确认120 MHz实板记录，不用本节仿真替代。后续仍需降低CPI、保留执行效率/频率/资源效率的折衷，并补齐验收账本中的硬件与文档缺项；未宣称物理极限。
