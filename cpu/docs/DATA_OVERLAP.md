# 数据请求重叠：执行与资源效率验证

2026-09-06。新增 `DATA_OVERLAP=0` 参数，默认保留旧串行行为；本轮不更改指令集、核心算法、CoreMark 源码或缓存替换策略。新候选仅完成本地验证，不替代已确认的实板成绩，不宣称达到 3.0 CoreMark/MHz 或物理极限。

## 电路改动与时序边界

旧路径在数据响应消费后，要等下一拍 `data_active` 清零才允许新请求。本轮允许旧响应 `valid && ready` 的同一上升沿接受后续数据请求：

- D-cache 使用原有 `READ_OVERLAP` 状态交接机制，不再仅限只读缓存。新请求锁存仍发生在时钟沿；写命中仍按原顺序提交，不把写操作改成组合副作用。
- memory_system 的 `data_issue` 在旧响应即将消费时开放；完成旧事务先清 `data_active`，新请求随后置位并更新 `data_mmio`，确保同拍交接时新事务保有响应归属。
- 旧响应的路由由旧的寄存 `data_mmio` 决定，时钟沿后才切到新事务；支持 Cache→MMIO、MMIO→Cache 及 Cache→Cache。不是多笔未完成事务或乱序发射。
- 响应背压期间不允许交接，返回数据/错误保持；目的端未就绪则按旧方式等待。维护请求阻止新事务，已有事务完成后才启动刷新。
- CPU 原有 `ex_fire`、异常冲刷和早期请求失败回退规则不变；完整差分回归继续检查错误访问和年轻指令冲刷。

## 配置与复现入口

参数从板级顶层、SoC 传到 memory_system；CoreMark/SoC/ISA 脚本用 `-DataOverlap 1`，缓存差分脚本用 `-DataOverlap` 开关。运行名、PDS 清单和短跑清单记录该值。配置字 bit18 为 DATA_OVERLAP，64 项 BTB、大缓存候选为 `0e6606fd`，关闭时为 `0e6206fd`；128 项开启为 `0e7606fd`。默认历史值不变。完整字段见 PERFORMANCE_MONITOR.md。

`compare_coremark.py --variable DataOverlap` 只接受此开关发生变化；时钟、固件、BTB 容量、其他开关及源码快照仍须一致。旧清单无此字段按 0 解释。比较器不接受短跑作为正式成绩。未验证的新网表不能复用历史 ILA 映射，插核脚本明确拒绝此开关。

从仓库根目录执行：

```powershell
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -DataOverlap 1 -BtbIndexBits 6 -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -EnableM 1 -LoadUseBubble 1 -CacheSetBits 6 -Optimization O3 -UnrollLoops -ClockHz 120000000 -Profile
pwsh -NoProfile -File cpu/scripts/validate.ps1
wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 /mnt/d/AAAFPGA/ZGTC_RISC_CPU/cpu/scripts/test_memory_overlap_controls.py
```

前一命令加 `-ValidationRun` 使用验证种子；改 `-DataOverlap 0` 生成控制组。上述默认只有 1 次迭代，不足 10 秒。PDS 使用另外的 4000 次、UART 触发固件，不能将短跑 ELF 冒充板上固件。

## 同固件短跑

共同条件：RV32IM、O3 + unroll、I/D 各 2 KiB，预测、FastI、FetchOverlap、FastD、EarlyD、LoadUseBubble 均开启。所有表中固件时钟元数据为 120000000，仿真时钟模型不是实板频率测量。周期来自固件 CSR 计时，退休窗口计数另列，不能混用。

| BTB 项数 | DATA_OVERLAP | 种子 | CSR 周期 | CSR 退休指令 | 唯一运行 ID |
| --- | ---: | --- | ---: | ---: | --- |
| 64 | 0 | 性能 | 423289 | 276244 | 20260906-160101-cbeb8fe1 |
| 64 | 1 | 性能 | 402898 | 276244 | 20260906-160539-292e5923 |
| 64 | 1 | 验证 | 403286 | 276457 | 20260906-160142-6f44a47f |
| 128 | 1 | 性能 | 395317 | 276244 | 20260906-160223-4960789c |
| 128 | 1 | 验证 | 395822 | 276457 | 20260906-160303-35d57752 |

三份性能短跑固件实际 SHA-256 均为 `1037851449BD28133F1F8DA81D836C8832C4B30D0046A3CBFA94622A1BCCA202`，两份验证种子为 `62858310E2C98F2DFC0B42288190428EE5E00BD23F83543C33FDDFF446D96175`。均已校验实际字节及 CRC。早期 `20260906-155018-666f83a4` 使用默认 27 MHz 固件元数据，尽管周期相同，不纳入本表严格同固件比较。

64 项对照/候选的退休分析窗口均为 276220 条指令，窗口周期分别 423241/402850，比 CSR 区间各少 48。memory_wait 从 36967 降到 16040；muldiv_wait 为 19473/19371，fetch_wait 为 23284/23295，frontend_empty 为 42341/42722。计数事件可能重叠，不能直接相加归因。新交接减少访存空拍，但没有消除前端停顿。

128 项只是本轮进一步短跑筛选；不能用 BTB_CAPACITY.md 旧源码的 LUT 数计算本候选资源效率，也未制作这一组合的本轮 PDS 位流。

## 120 MHz 同源码实现

器件 PG2L200H-6FBB676、27 MHz 参考、PLL 120 MHz、8.333 ns 目标、RemoteLab UART。性能构建共同使用 4000 次固件，SHA-256 `904AF093D8B05014FFFB9DAAADD08666A949280B9BDCD98D62B8835ED5E9B454`。

| DATA_OVERLAP | 构建 ID | WNS/ns | 布局后 LUT | FF |
| ---: | --- | ---: | ---: | ---: |
| 0 | 20260906-160118-cb0703b9 | +0.486 | 7293 | 4232 |
| 1 | 20260906-155328-871b5d78 | +0.432 | 7308 | 4232 |

两者 20 份源码/约束文件清单及实际哈希相同，且在本轮收尾核验时与工作区对应文件一致；实际位流、固件及快照字节均已核验。旧 BTB 轮次 7240 LUT 的结果不是本轮同源码控制组，不能替换 7293 这一分母。

- 执行效率：相同短跑工作量周期减少 4.81728%，同频工作率增加 5.06108%。
- 时钟：均通过所设 120 MHz 约束，候选裕量减少 0.054 ns，不将其写成实测最高频率提升。
- 资源效率：LUT 增加 0.20568%；以短跑工作率除以布局 LUT 的代理指标改善 4.84544%，不是正式 CoreMark/LUT。
- PDS 的 All Constraints Met 只覆盖已设置约束；SCBV 未设置警告与板级 IO 电气验收仍未消除。

性能位流 SHA-256：

- 关闭：`A7CD74B1B55E8DA591F65B47D730D6AEDDB8B6C3A633483EEFCE35590054ED46`。
- 开启：`C450E4EF61C6E730EFD4476049B1A10C92590658B5069497317AC66839C81025`。

验证种子构建 `20260906-160808-f36d9eb6` 也通过 120 MHz，WNS +0.432 ns、7308 LUT、4232 FF；20 份源码/约束与性能构建一致，实际字节哈希已核验。4000 次验证固件 SHA-256 为 `0913A391B44B037868C9D0FB24482759518428295EF59E04DD19F6664A41BAE1`，位流 SHA-256 为 `1F9C2CBEB1735ED6EB9AF5C4A28063A626B39632CB101C0A5B6A702E40C346A6`。生成位流不等于已在板上验证。

## 正确性与负对照

- 全回归日志 `build/validate-data-overlap.log` 通过：既有单元、CPU 差分、16 KiB 内存比较、UART/IRQ/错误处理、Verilator 严格 lint 和校验器反例。新增 EarlyD × FastD × LoadUseBubble 八种配置，Cache 几何/预测开关，另测 2 KiB/128 项和无 Cache 配置。
- RW 重叠缓存单元通过 6094 项检查、720 条后端命令：连续读、读→部分写、部分写→读、写→写、背压、错误恢复和脏行刷新。
- 响应归属单元：提前读路径 125 项、寄存读路径 129 项检查；每组 8 请求/8 响应、4 次交接，覆盖 Cache/MMIO 切换、旧错误后新成功响应、MMIO 写副作用一次和最终写回。
- `test_memory_overlap_controls.py` 的 3 个测试方法、6 组运行通过：关闭交接必须命中握手断言；颠倒清除/置位顺序必须命中新事务归属断言；正确 RTL 的提前/寄存两种路径均通过。变异仅使用临时文件，不修改正式 RTL。
- 初次负对照只触发 watchdog，暴露测试台静态 check 任务被并发调用覆盖参数的问题。改为 automatic 后，负对照在指定断言立即失败，正对照仍通过；不将最初 watchdog 当作充分证据。该测试已接入 validate.ps1。
- 比较器 23 项、CoreMark 校验器 15 项通过，覆盖新字段类型、旧清单兼容、配置字解析和混杂变量拒绝；8 个修改后的 PowerShell 入口通过语法和 UTF-8 BOM 检查。
- 外部 RV32UI：41 个测试、164 组运行及 4 个拒绝对照，目录 `build/isa/20260906-160437-6a0cd048`。RV32UM：8 个测试、32 组运行及 4 个拒绝对照，目录 `build/isa/20260906-160626-6ad13c8c`。使用 DATA_OVERLAP=1、BTB64，仍不是完整 ISA 认证。

完整回归之后，只修改了测试台断言重入方式并增加永久负对照入口；这部分以正负对照单独复验，未借用原日志声称新测试已在那一次全回归内执行。

## 尚未完成

新位流尚未远程板卡下载与长时性能/验证采集，不能发布新 CoreMark/MHz。120 MHz 的 3.0 硬目标仍未完成。新设计对应 ILA 探针映射、GPIO 独立输入、SCBV 与 IO 电气约束验收仍需继续，不因本轮本地优化自动完成。
