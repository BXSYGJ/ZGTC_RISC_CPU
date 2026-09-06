# I-cache命中提前响应实验

日期：2026-09-06。状态：默认关闭，已通过功能仿真；尚未取得该模式的PDS资源、时序与不少于10秒的实板成绩。此次提交是工程开发检查点，不将历史180 MHz位流的结果归给此实验。

## 目的与时序

原I-cache命中路径为IDLE接收请求、LOOKUP查找、RESPONSE应答。实验在只读Cache的LOOKUP命中周期直接给出有效数据；若接收端ready为1，该拍完成并回到IDLE，省去专门的RESPONSE等待周期。若ready为0，边沿将相同数据锁存到应答寄存器并进入RESPONSE，继续保持valid/data，直至一次握手完成。

参数为FAST_ICACHE_HIT，默认0；只传给I-cache的FAST_READ_HIT。D-cache写回、存储字节合并、缺失填充和错误处理保持原行为。填充完成后的LOOKUP也可提前返回，但请求只计一次miss；正常命中只计一次hit。读错误、只读写请求和非法对齐不会走提前成功路径。

配置寄存器bit3标识提前响应真正启用。缓存关闭时该位强制0；默认缓存和预测开启时，旧配置为0e020401，实验为0e020409，同时开启load寄存前递则为0e02040d。解析器拒绝缓存关闭却报告bit3开启的矛盾配置。

## 已执行验证

- 原有Cache读写5906项、只读3188项仍通过。新增只读提前响应3234项，含热行LOOKUP拍响应、立即消费后不重复应答、不访问后端、计数只增加一次，以及原有背压保持、读错误、early/late last、失效和512次随机访问。
- 完整validate.ps1通过，增加提前响应与两种load前递模式的8组CPU差分、GPIO/UART中断及维护失败SoC测试、Cache旁路测试和两种模式严格Verilator检查。默认模式结果保持原测试基线。
- 固定上游RV32UI的41个测试、4种配置共164次通过，4个预期拒绝控制通过。记录目录为build/isa/20260906-111427-055e88d6；不是官方ISA认证。
- 1次迭代CoreMark性能种子为1931551周期、752500退休，验证种子为2052594周期、805806退休，均CRC正确，配置0e020409。UART仿真加速，两个运行均短于10秒，检查器明确不输出正式CoreMark分数。

CPU自检中的循环与中断等待会因时序变化影响退休数，不能把自检总周期减少比例冒充CoreMark执行效率改善。下一步应使用相同工具链、固件、主频与板卡进行开关对照，并取得新的布局后LUT，分别计算CoreMark/MHz和CoreMark/LUT；组合命中路径可能损失时序余量，不能只看仿真周期。

## 运行入口

在仓库根目录使用PowerShell 7：

```powershell
pwsh -NoProfile -File cpu/scripts/run_cached_tests.ps1 -FastICacheHit
pwsh -NoProfile -File cpu/scripts/run_soc_tests.ps1 -FastICacheHit 1 -ExternalUart
pwsh -NoProfile -File cpu/scripts/run_isa_tests.ps1 -FastICacheHit 1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -FastICacheHit 1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -FastICacheHit 1 -ValidationRun
```

run_pds.ps1支持显式-FastICacheHit 1并记录到manifest，但本页不是该实现已经通过的声明。run_ila_pds.ps1拒绝此新模式，因为已有ILA网表映射尚未在新实现中核验。所有实验日志与仿真产物使用_fastihit后缀，避免覆盖关闭模式的结果。
