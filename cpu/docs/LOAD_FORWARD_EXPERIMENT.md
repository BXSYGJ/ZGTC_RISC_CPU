# Load 前递时序实验

2026-09-06：实验选项 `LOAD_USE_BUBBLE=1` 默认关闭，已贯穿core、SoC、板级构建、CoreMark与外部ISA测试。本页保留162 MHz同频负收益分析；后续180 MHz候选已在箱3完成性能重复、验证种子及两次持续运行，65.9429948 CoreMark，见 `HARDWARE_180MHZ.md`。原默认模式与其历史硬件证据保留，不混用成绩。

## 改动与目的

已有216 MHz失败布局中的关键路径从MEM地址寄存器经load数据选择、EX前递和ALU到MEM结果寄存器。实验模式在EX依赖MEM load目标寄存器时保持EX，允许load先进入WB；下一周期使用WB寄存结果。MEM非load仍可前递，MEM load数据不再连接至EX前递数据选择。

异常和重定向仍优先冲刷流水线；仅当目标寄存器非零且指令实际使用对应源寄存器时才判定依赖。默认模式保留原MEM load直接前递。

## 已验证范围

运行 `cpu/scripts/run_cached_tests.ps1` 的默认、`-Uncached`、`-LoadUseBubble`、`-LoadUseBubble -Uncached` 四种调用，总计12组。每组均逐条对照软件参考模型，检查退休指令、13次trap及最终16 KiB内存。

| Cache集合位数 | 预测器 | 默认周期 | 实验周期 |
| --- | --- | ---: | ---: |
| 1 | 关闭 | 5483 | 5489 |
| 1 | 开启 | 5356 | 5363 |
| 4 | 关闭 | 4709 | 4709 |
| 4 | 开启 | 4587 | 4587 |
| 无cache | 关闭 | 5767 | 5767 |
| 无cache | 开启 | 5641 | 5641 |

异步定时中断可改变忙等循环的退休条数，因此每条轨迹分别对照参考模型，不把不同模式退休数相等当作通过条件。该短自测的周期相近不意味着CoreMark无性能损失。

实验模式覆盖检查要求：至少一次load完成时EX保持、至少一次WB load结果前递、零次MEM load直接前递。默认模式仍要求原MEM及load前递覆盖。四路组合日志分别保存于 `cpu/build/cached-tests.log`、`uncached-core-tests.log`、`cached-load-bubble-tests.log`、`uncached-load-bubble-tests.log`。

## 构建与身份区分

`run_pds.ps1`、`run_coremark_test.ps1`、`run_isa_tests.ps1` 使用 `-LoadUseBubble 1` 开启，省略仍为0。CoreMark运行配置新增bit2，默认缓存与预测器开启时实验值为 `0e020405`，原模式仍为 `0e020401`；检查器严格匹配请求配置。构建清单记录 `LoadUseBubble`，实验CoreMark仿真文件名增加 `_loadbubble`，不覆盖默认结果。ILA构建器拒绝实验模式，以免复用未经验证的旧内部信号映射。

## CoreMark与PDS实测

性能与验证种子的1次迭代仿真均CRC通过。性能种子默认2733391周期，实验2733694周期，两者退休752500条；实验验证种子2910514周期。短仿真不计为有效CoreMark成绩。

实验外部ISA运行 `build/isa/20260906-093431-81311775` 通过41项×4配置=164次，并正确拒绝四个负控；仍不称为官方ISA认证。

默认模式用更新后的同一适配器再次运行 `build/isa/20260906-094427-8f09321a`，同样164次及四个负控通过。

| 项目 | 默认162 MHz | 实验162 MHz |
| --- | ---: | ---: |
| 1000次性能运行周期 | 2729377421 | 2729630350 |
| 退休指令 | 752528394 | 752528394 |
| 运行秒数 | 16.8480087716 | 16.8495700617 |
| CoreMark | 59.3541951192 | 59.3486953279 |
| CoreMark/MHz | 0.3663839205 | 0.3663499712 |
| 布局后LUT | 4751 | 4808 |
| CoreMark/LUT | 0.0124929899 | 0.0123437386 |
| 布局setup WNS/ns | +0.317 | +0.378 |

实验性能种子在实验箱5重新烧录后独立运行两次，周期、退休和缓存计数完全一致；CRC为e9f5/e714/1fd7/8e3a/d340。证据 `build/hardware/coremark-box5-f162-loadbubble-r1/r2.uart`、对应JSON与会话记录。实验162 MHz性能bitstream构建目录 `build/pds/20260906-093309-e1cffc24`，SHA-256为 `2FBE7D7233F6979F2E4AFDF5FC78FD79A9986866E0FAB3FBA424416813CB26DC`。

216 MHz实验布局 `build/pds/20260906-093659-5569b9ac` WNS=-0.446 ns，仍失败；门禁拒绝且不生成接受清单，未上板。其最长路径已转为I-cache请求地址经tag比较到miss计数器CE，5级逻辑，逻辑1.354 ns、布线3.186 ns。报告估计197.0443 MHz不能当作实际验证频率。

因此当前162 MHz下实验版本并未改善得分或面积效率，继续保持默认关闭。后续可细化中间频率并分析缓存控制高扇出，但不能仅依据估计Fmax宣布优化成功。

后续本地细化已完成：180 MHz实验版内部约束通过而默认版失败；194.4 MHz两者仍失败，详见 `PDS_FREQUENCY_REFINEMENT.md`。这是新的布局证据，不是新的上板成绩，默认模式与162 MHz实测主结果仍不变。

162 MHz实验验证种子在箱5完成1000次：2906679878周期、805870321条退休指令、17.9424683827秒，CRC为18f2/e3c1/0747/8d84/26c2。构建 `build/pds/20260906-094236-a6ccc0cb` 与性能种子实现的资源、WNS一致；bitstream SHA-256为 `11411107BDCF2BA749B581CE29B94716160184D014820B7B4B8684478189A511`。原始输出和检查结果位于 `build/hardware/coremark-box5-f162-loadbubble-validation-r1.*`。

三次硬件运行及bitstream、UART哈希汇总在 `build/hardware/load-forward-experiment.json`。本轮测试后已关闭串口并明确释放设备，不保留预约。

## 回归与剩余验收

本轮完整 `cpu/scripts/validate.ps1` 已通过：单元测试、六组随机核心差分、上述12组缓存/无缓存差分、SoC及故障测试、参考检查器变异测试，以及默认/实验核心模式的严格Verilator lint。两个修改后的PowerShell脚本语法与UTF-8 BOM检查通过，限定工程文件的 `git diff --check` 通过。

本轮参数接入后的完整回归再次通过，并增加实验板级顶层严格lint。实验实现尚未完成长时间稳定性测试或全部中间频率扫描；不可沿用旧bitstream的测试声称实验架构已覆盖所有硬件场景。
