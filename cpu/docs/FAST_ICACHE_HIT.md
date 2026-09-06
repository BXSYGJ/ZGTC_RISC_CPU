# I-cache命中提前响应实验

日期：2026-09-06。状态：默认关闭，功能仿真通过；现已取得162 MHz同板同固件对照、候选性能重复两次和验证种子一次。120 MHz性能种子4000次运行也已采集，但该频率的重复与验证种子尚待补齐。尚未达到新增的120 MHz、3.0 CoreMark/MHz目标，详见PERFORMANCE_TARGET.md。历史180 MHz寄存前递成绩仍独立保留。

## 目的与时序

原I-cache命中路径为IDLE接收请求、LOOKUP查找、RESPONSE应答。实验在只读Cache的LOOKUP命中周期直接给出有效数据；若接收端ready为1，该拍完成并回到IDLE，省去专门的RESPONSE等待周期。若ready为0，边沿将相同数据锁存到应答寄存器并进入RESPONSE，继续保持valid/data，直至一次握手完成。

参数为FAST_ICACHE_HIT，默认0；只传给I-cache的FAST_READ_HIT。D-cache写回、存储字节合并、缺失填充和错误处理保持原行为。填充完成后的LOOKUP也可提前返回，但请求只计一次miss；正常命中只计一次hit。读错误、只读写请求和非法对齐不会走提前成功路径。

配置寄存器bit3标识提前响应真正启用。缓存关闭时该位强制0；默认缓存和预测开启时，旧配置为0e020401，实验为0e020409，同时开启load寄存前递则为0e02040d。解析器拒绝缓存关闭却报告bit3开启的矛盾配置。

## 已执行验证

- 原有Cache读写5906项、只读3188项仍通过。新增只读提前响应3234项，含热行LOOKUP拍响应、立即消费后不重复应答、不访问后端、计数只增加一次，以及原有背压保持、读错误、early/late last、失效和512次随机访问。
- 完整validate.ps1通过，增加提前响应与两种load前递模式的8组CPU差分、GPIO/UART中断及维护失败SoC测试、Cache旁路测试和两种模式严格Verilator检查。默认模式结果保持原测试基线。
- 固定上游RV32UI的41个测试、4种配置共164次通过，4个预期拒绝控制通过。记录目录为build/isa/20260906-111427-055e88d6；不是官方ISA认证。
- 1次迭代CoreMark性能种子为1931551周期、752500退休，验证种子为2052594周期、805806退休，均CRC正确，配置0e020409。UART仿真加速，两个运行均短于10秒，检查器明确不输出正式CoreMark分数。

CPU自检中的循环与中断等待会因时序变化影响退休数，不能把自检总周期减少比例冒充CoreMark执行效率改善。以下改用相同工具链、固件、主频与板卡的正式长度性能运行作比较。

## 162 MHz同板对照

实验箱5，PG2L200H；GCC 10.2.0、RV32I、O2、2000字节数据集、性能种子1000次迭代。两份位流中的固件SHA-256均为C9F398822D9186AB93F9D28FA6A38CBE5CA47126BDC4D8D683D5255ACEA7FB30，唯一受控逻辑开关为FastICacheHit。默认load前递保持0。

| 指标 | 提前响应关闭 | 提前响应开启 |
| --- | ---: | ---: |
| 实际工作频率/MHz | 162 | 162 |
| 周期数 | 2729377421 | 1927984580 |
| 退休指令数 | 752528394 | 752528394 |
| 时长/秒 | 16.84800877 | 11.90113938 |
| CoreMark/MHz | 0.3663839205 | 0.5186763475 |
| CoreMark/LUT | 0.01249298992 | 0.01741101705 |
| CoreMark | 59.35419512 | 84.02556830 |
| 布局后LUT | 4751 | 4826 |
| 布局后FF | 3509 | 3531 |
| DRM36K等效 | 16.5 | 16.0 |
| setup WNS/ns | +0.317 | +0.312 |

执行效率提高41.5664%，资源效率提高39.3663%；LUT增加1.5786%，时序余量略减。没有提高此对照的主频，不宣称提高了绝对Fmax。DRM占用是PDS报告的整体等效量，不等于可寻址RAM容量。

候选两次独立重编程后的性能运行，其周期、退休数、缓存计数和CRC一致。验证种子1000次为2049301525周期、805870321退休、12.65000941秒，四项CRC为e3c1/0747/8d84/26c2；验证种子吞吐不作为性能分数。

原计划A1/B1/A2/B2：A2发生网关旧数据回放与START截断，整段保留为rejected-session，未从中截取看似正确的末段作成绩。对已结束程序再次发送G没有响应，另存noresponse记录，不算一次成功测试。因此当前是基线一份有效新采集、候选两份有效新采集，不冒充两组完整AB配对。A1启动READY未完整观察到，清除缓冲后取得唯一完整新命令响应；此限制已记录。实验箱5已释放。

本地证据：build/hardware/fastihit-pair-r1.json、fastihit-box5-sessions.json，以及coremark-box5-f162-fastihit0-r1、coremark-box5-f162-fastihit1-r1、coremark-box5-f162-fastihit1-r2、coremark-box5-f162-fastihit1-validation-r1对应的UART文件。比较工具compare_coremark.py重新解析原始PDS时序/资源，校验位流和固件哈希，拒绝不同固件、频率、退休数或不足十秒的配对；不自行证明板卡身份。

PDS目录：关闭20260906-112359-993c0c5f；开启20260906-112413-5fdde146；验证20260906-112859-fcac17b2。180 MHz提前响应与寄存前递组合另有20260906-113540-76846db7，WNS +0.117 ns、4910 LUT、16 DRM；只有PDS实现证据，尚无该位流实板成绩。

## 运行入口

在仓库根目录使用PowerShell 7：

```powershell
pwsh -NoProfile -File cpu/scripts/run_cached_tests.ps1 -FastICacheHit
pwsh -NoProfile -File cpu/scripts/run_soc_tests.ps1 -FastICacheHit 1 -ExternalUart
pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1 -FastICacheHit 1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -FastICacheHit 1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -FastICacheHit 1 -ValidationRun
```

run_pds.ps1支持显式-FastICacheHit 1并记录到manifest。run_ila_pds.ps1拒绝此新模式，因为已有ILA网表映射尚未在新实现中核验。所有实验日志与仿真产物使用_fastihit后缀，避免覆盖关闭模式的结果。
