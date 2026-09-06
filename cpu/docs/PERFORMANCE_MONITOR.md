# 性能快照与配置观测

本接口服务于性能消融和后续 ILA 对照，不替代 ILA，也不把计数器当作完整波形。自首轮实板基线之后加入；旧位流资源/成绩仍由 `COREMARK_RESULTS.md` 的 SHA 标识，不能直接归属于当前新增监测逻辑。

## MMIO 寄存器

| 地址（hex） | 内容 |
| --- | --- |
| 10000400 | 写 bit0=1 且 byte0 有效时原子锁存全部计数；读返回 32 位快照序号 |
| 10000404 | 只读硬件配置 |
| 10000410/414 | 锁存 mcycle 低/高 32 位 |
| 10000418/41C | 锁存 minstret 低/高 32 位 |
| 10000420 | I-cache hit_count |
| 10000424 | I-cache miss_count |
| 10000428 | D-cache hit_count |
| 1000042C | D-cache miss_count |
| 10000430 | D-cache writeback_count |

在外设端命令valid/ready握手的同一时钟沿采集 288 位；数据读取只读快照，不会重新取活计数器。复位清零，快照序号每次命令加 1，按 32 位回绕。计数器自身不会被快照清零。只读地址写入、未知地址、未对齐访问报错且不改变快照；写控制寄存器的其他字节、写 bit0=0 均不触发。 当前MMIO请求缓冲使CPU入口接受可能早于这个时钟沿；采样点仍在外设实际接受处，详见CACHE_ADDRESS_BOUNDS.md。

当前配置字定义（2026-09-06）：bit0 为分支预测开启；bit1 为 Cache 旁路；bit2 为 LOAD_USE_BUBBLE；bit3 为 I-cache 提前响应实际开启；bit4 为 ENABLE_M；bit5 为 FETCH_OVERLAP；bit6 为 D-cache 提前读响应实际开启；bit7 为 EARLY_D_REQUEST；[11:8] 为数据Cache的 CACHE_SET_BITS；[15:12] 为独立指令Cache索引位数，0表示继承数据Cache的位数，非零合法值为1–8；[17:16] 为固定 CACHE_WORD_BITS=2，即每行 4 个字；bit18 为 DATA_OVERLAP；bit19 为 D-cache 提前写响应（Cache 旁路时强制为 0）；[23:20] 为 BTB 索引位数，0 兼容历史默认 4，非零合法值为 1–8；[31:24] 为后端 RAM 字地址位数。Cache 的两路结构不是用固定数值 2 这一字段编码。

默认配置仍为 0e020401，历史实验低位定义不变。新 64 项 BTB、大缓存组合开启 DATA_OVERLAP 后为 0e6606fd，关闭为 0e6206fd；128 项开启后为 0e7606fd。旁路模式强制 bit3 和 bit6 为 0，其余相关开关表示参数设置，不保证对应路径在工作负载中触发；Cache 几何字段保留不表示仍有 Cache。DATA_OVERLAP 默认关闭，细节见 DATA_OVERLAP.md。FAST_DCACHE_WRITE也默认关闭；64项BTB、B0、提前读写均开启时配置字为0e6e06f9，128项为0e7e06f9，语义及证据见FAST_DCACHE_WRITE.md。 ICACHE_SET_BITS默认0继承CACHE_SET_BITS；两侧相等时高半字节编码0以保持历史配置字不变。256项BTB、B0、全部快速选项开启时，I=8 KiB/D=2 KiB为0e8e86f9，I=8 KiB/D=4 KiB为0e8e87f9，两侧8 KiB仍为0e8e08f9。命令行及验收边界见ASYMMETRIC_CACHE.md。

Cache 的 hit/miss 按进入 lookup 的访问分类计数，缺失后重做 lookup 不再记成 hit；I-cache 包含随后被流水线丢弃的推测取指，不能把 I 访问数直接当作退休指令数。writeback_count 统计成功完成的脏行写回，包含维护触发写回。计数器为 32 位，区间差以模 2^32 计算；过长区间发生多次回绕不能恢复，当前短时和约 20 秒基准均需检查数值合理性。 有界标签修订在lookup之前拒绝物理高地址、未对齐及只读写入请求，这些失败访问不增加hit/miss，也不逐出脏行；不能直接与历史先miss后后端报错的计数比较。

## 计分区与统计区

CoreMark port 在 start_time 的周期读取之前锁存起点、在 stop_time 的周期读取之后锁存终点。五个 Cache 差值覆盖稍宽于算法计时的区间，包括少量计数读取/保存指令；不是零开销、严格逐周期同区间统计。正式周期分数仍由原有 64 位 CSR 时间差计算，printf 仍在计时区之外。

报告新增 `ZGTC config=... ihit=... imiss=... dhit=... dmiss=... writebacks=...`。解析器可用 `--expected-config` 拒绝缺少配置、配置不符或超出 32 位范围的数据，也拒绝无 Cache 配置却出现非零 Cache 计数；旧基线日志没有该行，只有不指定 expected-config 时才可作为旧格式读取。

## 可复现配置

预测器关闭、Cache开启的200迭代位流 `build/pds/20260906-054530-890e77ff` 已在箱5两次长时通过，SHA-256 `B92F6C36F4E9822C728A28CE3D5552B5ECF7F4D379E0ED24FEAA619679549BB0`。固件SHA与 `HARDWARE_CACHE_ABLATION.md` 相同；同箱预测开启使周期减少16.1019%，详见 `HARDWARE_PREDICTOR_ABLATION.md`，不再仅依赖短时仿真消融。

```powershell
pwsh -NoProfile -File cpu/scripts/run_soc_tests.ps1 -ExternalUart -Predictor 0 -CacheSetBits 1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -Predictor 1 -CacheSetBits 4
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -Predictor 0 -CacheSetBits 4
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile RemoteLab -Predictor 0 -CacheSetBits 4
```

CacheSetBits 控制组数，容量为 2^CacheSetBits × 2 路 × 16 字节。改小容量不等于关闭 Cache；真正的 Cache 开关已由 CacheEnabled 参数和独立无缓存桥实现并完成实板消融，见 `HARDWARE_CACHE_ABLATION.md`。Predictor 参数贯通 PDS 包装层、板顶层、SoC 和 CPU，默认仍开启；构建 manifest 保存配置参数。

当前验证：外设自检 3,811 项，包含全部快照字、初始零值、冻结读取、序号、字节使能与错误写无副作用；C SoC 自检实际执行快照命令验证序号及周期增长。默认配置的 CoreMark 单次仿真仍通过 CRC，输出 I hit/miss=872504/10968、D hit/miss=69430/1233、writebacks=587。这是仿真区间统计，不是新增监测版本的实板长时成绩。

## 首轮预测器消融（单次仿真）

同一固件、相同 512 字节 I/D Cache、相同 CoreMark 性能种子，预测器开关均通过算法 CRC，计时区退休数均为 752500。开启/关闭的周期分别为 2747075/3278139，开启使周期减少 16.2002%，吞吐比为 1.19332。两次仅约 0.10/0.12 秒，不能作为正式 CoreMark 成绩。

关闭时 I hit/miss 为 1048002/11373；D hit/miss 仍为 69430/1233，writebacks 仍为 587。I 访问数的减少与更少的错误路径取指一致，但当前未计数 BTB 命中或逐分支错误预测，不能直接从该表声称预测准确率。原始 UART 和 JSON 为 `build/coremark_v0_i1_bp1_cs4.*`、`build/coremark_v0_i1_bp0_cs4.*`。

监测版默认配置已通过 Windows PDS，构建 `build/pds/20260906-043034-5a67e48f`，位流 SHA-256 `417F4790BA5C3837AE0C1B9768B903348B363891407B8AF32583B9757907267D`；27 MHz 内部时序通过，setup WNS 24.475 ns，最差 hold WHS 0.100 ns。实际资源为 4084 LUT、3489 FF、16.5 DRM36K 等效块。该版新增寄存器/计数逻辑，旧基线资源与成绩不得套用；尚未进行此版本的实板长时计分。
