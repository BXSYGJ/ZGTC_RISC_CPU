# CoreMark 编译参数与缓存容量筛选

2026-09-06。本记录是短仿真筛选，不是有效 CoreMark 分数，也没有证明任何物理极限。

## 约束与复现

上游 CoreMark 算法不修改；保持构建脚本已有的固定版本和完整性校验。使用已安装的 RV32 GCC 10.2.0、RV32IM。`build_coremark.ps1` 与 `run_coremark_test.ps1` 新增默认关闭的 `-UnrollLoops`，启用后对全部 C 源文件一致添加 `-funroll-loops`，文件名加 `_unroll`，构建及运行清单记录布尔值 `UnrollLoops`。编译器报告中记录完整 flags。

这不是 `-funroll-all-loops`。本机 GCC 查询确认 `-O3 -funroll-loops` 开启循环展开及寄存器重命名，但没有开启全部循环展开。保留默认 O2，不凭优化等级名称断言更快。

## 四格对照

均为性能种子、1 次迭代、M=1、FastICacheHit=1、FetchOverlap=1、FastDCacheRead=1、LoadUseBubble=1、EarlyDRequest=0、Predictor=1。CacheSetBits=4/6 分别对应 I/D 各 512 B/2 KiB。全部 CRC 检查通过，运行时间不足 10 秒。

| I/D 各自容量 | 优化 | 周期 | 退休指令 | I-cache 缺失 | 运行 ID |
| --- | --- | ---: | ---: | ---: | --- |
| 512 B | O3 | 669391 | 296234 | 22670 | 20260906-140838-e0b8ff33 |
| 512 B | O3 + unroll | 662738 | 276244 | 24645 | 20260906-140920-da15d4ec |
| 2 KiB | O3 | 518174 | 296234 | 1900 | 20260906-141001-1fcbd7cc |
| 2 KiB | O3 + unroll | 505190 | 276244 | 2952 | 20260906-141040-1bc32dc3 |

证据为 `build/` 内上述唯一 ID 的 `.run.json`、`.result.json`、`.profile.json`、`.uart`、`.hex` 和 `.elf`；外层日志为 `coremark-unroll-cs4-u0.log`、`coremark-unroll-cs4-u1.log`、`coremark-unroll-cs6-u0.log`、`coremark-unroll-cs6-u1.log`。

## 执行效率与代价

使用 GNU readelf 检查不可变短跑 ELF：O3 的 `.text` 为 0x43ec = 17388 字节，O3 + unroll 为 0x69b4 = 27060 字节，增加约 55.62%。退休指令减少 19990 条，但 I-cache 缺失增加，所以不能按指令数降幅推算周期收益。

同一小缓存架构的 O2 对照为 625939 周期、309824 条退休指令，仍快于上述两个小缓存 O3 版本。缓存增大有明显周期收益，但不能用此前不同 RTL 构建的 LUT 数代替本组合的资源测量。尚未给此四格组合制作新的长测位流及完成正式板卡长测/验证种子全矩阵，故不宣布默认切换。

## 与提前访存组合的单点筛选

新增 EarlyDRequest=1，其余保持 2 KiB、O3 + unroll 条件时，初版运行 `20260906-143328-4e68180f` 得到 458524 周期、276244 条退休指令。最终地址选择修正后，性能种子 `20260906-144318-e10567dd` 仍为 458524 周期、276244 条退休指令；验证种子 `20260906-144400-8f7a4bbf` 为 459259 周期、276457 条退休指令。两组短跑 CRC 均通过，清单 EarlyDRequest=1、UnrollLoops=true，reportable_duration=false。

这是另一项硬件变量，不能与四格结果混成单纯编译收益。上述原始快照当时尚未完成对应的 120 MHz PDS 实现与实板长测；不能借用 512 B O2 组合的时序和 LUT 数作为其验收证据。

后续独立修订加入乘积提前响应和非加载前递资格精简后，该 2 KiB 编译组合的两种种子短跑为 449230/449971 周期，性能种子 120 MHz PDS 通过（7175 LUT、WNS +0.445 ns）。它不是上述原始 RTL 的结果，失败中间版本与同频资源折衷见 `MUL_EARLY_RESPONSE.md`；仍缺新实板长测，不能宣布达成 3.0。

120 MHz 至少 3.0 CoreMark/MHz 的用户目标仍未达到；不能把短跑周期直接换算为正式成绩。
