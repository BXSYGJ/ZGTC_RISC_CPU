# 无复位 LRU 替换状态存储

2026-09-07。隔离实验，生产 RTL 与已发布的120 MHz达标版本不变；不自动提交或上传 GitHub。目标是保留执行拍数，同时降低资源和时钟负载；不能把仿真、综合映射或失败布局当成实板成绩。

## 依据与三个版本

基线为 MMIO_READY_PAYLOAD 的16 KiB I-cache、2 KiB D-cache、H3预测器组合：135 MHz/种子1，9220 LUT、5726 FF、WNS +0.117 ns。缓存源为同步可写 DB55CBF5；所有实现保持同一固件、相同顶层参数与约束。

两路缓存的替换顺序始终是先选无效路，只有两路均有效才读取 LRU。复位清空 valid，第一次填充/命中训练 LRU 后才可能需要替换有效路。因此未训练集合的 LRU 可以是任意值，但不能改变实际替换、总线事务、响应或计数器；不以读取任意值冒充有效元数据。

| 隔离版本 | 缓存 SHA-256 | 改动 |
| --- | --- | --- |
| 初版 | F2926B7381C10913A86C68CAACEB65D4ECF3F84BF7B28D85C3E710DD52983554 | 无复位数组，展开为全位向量，写入使用同步 rst_n 条件 |
| async_guard | 68E8F634F89052B8CB9F79B7BCD446466D8DFEFE32B6870A593FBE4066318F4D | 保留展开观察别名；空异步复位分支，与现有无复位数据存储形式一致 |
| direct_array | BB337C68B20A715B88026F3919411163AD21A8127B4587C8A547EC9B44369193 | 去掉 RTL 全位观察别名；实际逻辑只按 request_set 访问一个数组元素 |

初版严格 Verilator lint 因 SYNCASYNCNET 失败，未新增豁免。async_guard 与 direct_array 使用规范模块文件名后通过严格单元和板级 lint；直接对另名文件做单元 lint 时的 DECLFILENAME 提示单独保留，不掩盖源代码警告。

## 物理实现与原生映射

| 135 MHz性能布局 | 种子 | LUT | FF | WNS/ns | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 初版 20260907-165219-fb141911 | 1 | 9255 | 5725 | -0.309 | 时序失败且 lint 未通过，拒绝 |
| async 20260907-165948-fd7caf53 | 1 | 9271 | 5716 | +0.040 | 本地时序通过，未取得资源联合优势 |
| direct 20260907-171227-4139296b | 1 | 8578 | 5123 | -0.088 | 降资源但时序失败，不能计分 |
| direct 20260907-172032-86d26a96 | 7 | 8484 | 5126 | -0.010 | 仍不满足135 MHz，拒绝 |
| direct 20260907-172102-992cfc76 | 5 | 8520 | 5123 | -0.084 | 时序失败，拒绝 |
| I-only generated 20260907-173607-5c0c6603 | 1 | 8602 | 5192 | -0.092 | 时序失败，拒绝 |

原生网表核验：基线与 async 各有576个 LRU 触发器；direct 为两个 GTP_RAM256X1SP 加一个 GTP_RAM64X1SP，共576位，LRU触发器为零。分配表确认 I-cache 为512×1、D-cache 为64×1。测试观察连线只存在于测试台，不重新引入到实现 RTL。此映射证据不是原生网表全功能等价证明。

直接数组种子1比同种子基线少642 LUT、603 FF，但最差路径是同步D-cache读数据经加载前递/有效地址返回缓存状态选择，不是 LRU RAM 本身。没有降低目标频率、放宽时序约束或增加假路径。种子7和5均已终态失败；种子7最接近仍差0.010 ns，不按四舍五入判定通过。改变布局种子的行不得称为同种子比较。

## 回归与测试台修复

async 和 direct 各完成96种模式/任意上电值组合（每种包括三次已训练后的复位）、32种物理几何及32个独立参考对照、12种地址越界/别名候选及12个参考对照、10个已编译功能变异拒绝。完整16/32 KiB容量覆盖保留所有集合的已训练LRU比较。

初始容量测试有真实的测试台缺口：没有发送重叠请求却要求重叠覆盖；I10逐集合逐拍循环还触及120秒超时。修复是添加原有 overlap_stream/slow_overlap_stream 激励并初始化其 snapshot_commands 前置状态，未删除覆盖断言。全位观察和已训练/双有效位掩码改用逐拍向量比较，语义仍覆盖所有需要比较的集合；单次120秒限额不变。容量测试正确要求 PASS instruction capacity 及 READY_PAYLOAD 完成标记，不再误用普通缓存的文本标记。旧失败日志保留，不将中途 PASS 行当作整个 unittest 成功。

修复后两版本完整5项 unittest 已终态通过。新增每个全容量场景的独立基线对照后，最终复跑也均终态通过，每版包含6个容量候选和6个参考场景；依据进程退出码及最终 OK，不依赖单独的中途 PASS 行。

两版本 CPU/SoC、独立参考与严格 lint 均通过。外部RV32UI/RV32UM共392次正例执行与16个拒绝控制的原始日志、固件、输入哈希已审计，所有执行拍数和退休指令均与 MMIO I9 基线相同；不是完整 ISA 认证。

同132 MHz、10轮固件的短仿真逐字节 UART、结果、配置均与对应 MMIO I9 基线一致：性能3199743周期/2748941退休，验证3206720/2749614，CRC正确。每份18项仿真输入只允许缓存源变化，20项PDS输入同样只允许缓存变化。短跑不能作为新的 CoreMark/MHz 成绩，不能把旧6000轮拍数和本版LUT拼接计分。

## 只读 LRU RAM 隔离复核

进一步仅把 I-cache 的512位 LRU放入RAM，D-cache的64位保持带复位寄存器，检验是否可以缓解读数据临界路径的布局压力。过程中的失败也保留：

- readonly_ram 源 F0F2CF0E6C21607D7D5A595E6891885DD934216049B8F2A4129AFA1317CC3D1F 在 Icarus 完整测试通过，但 PDS 在20260907-173221-2cba0b28拒绝过程循环的局部 integer，旧版Verilator的大几何板级 lint 也报 BLKLOOPINIT，故不能使用。第一次单元调用误加本机Verilator4.038不支持的 --timing 选项，单独记录为工具调用错误，不归咎RTL。
- 改为逐项生成复位寄存器后，第一份源 E209A6E20428456A1F270E38D926EA97B19EC7DFECC0F87A973F305C52EF44C9 的尺寸转换语法仍被PDS拒绝，失败源保存在20260907-173453-b4f9b014的冻结目录。仅在该进程终态、其他测试尚未启动时，改成索引位段访问。
- 最终 readonly_generated 源为3F63552E74211634F67802048FDE0D24D6F397B0F4F92BFDC0D552FD696636DC。原生网表为两个GTP_RAM256X1SP和64个GTP_DFF_C，确认没有把D-cache状态也压入RAM。

最终源的完整5项差分测试、CPU/SoC与严格板级lint、独立196次ISA及8个拒绝控制均通过。适配生成式写索引的反例最初同时匹配复位与更新两处，修复为仅定位更新使能，不改功能RTL；重跑全部测试终态通过。两种短测与基线逐字节UART和完整结果一致。三个可完成集成测试的候选合计588次ISA正例、24个拒绝控制，不重复统计中间失败源。

最终I-only布局仍为WNS -0.092 ns，最差路径仍从D-cache读数据返回D-cache状态使能。本轮没有新的135 MHz联合合格候选，不运行无合格PDS绑定的计分长测，也不把旧长测拍数配新LUT。下一轮应针对加载前递/有效地址/缓存控制反馈路径，而非继续把存储映射成功当作时序改善。

## 本地证据和后续

- experiments/cache_lru_storage：隔离缓存源及配置；被替代的生成式尺寸转换源仍保存在失败PDS的冻结输入中。
- scripts/test_cache_lru_storage.py：默认 direct_array；可用 --candidate async_guard 独立检查第二版本。
- build/cache-lru-storage-async-audit.json、cache-lru-storage-direct-seed1-audit.json：短测、物理、输入绑定和原始报告审计。
- build/cache-lru-storage-native-final-audit.json、cache-lru-storage-isa-audit.json、cache-lru-storage-generated-isa-audit.json：原生映射及ISA原始证据。
- build/cache-lru-storage-generated-seed1-audit.json及direct-seed7/direct-seed5审计：失败时序、输入、固件和位流原始证据；另有错源反例拒绝日志。
- build/cache-lru-storage-local-state.json：当前任务句柄、失败记录及后续状态。

如果直接数组有135 MHz合格布局，再生成同源验证种子位流、分别运行绑定本版输入的6000轮长仿真（MaxCycles=10000000000），之后才形成新的本地仿真投影；实板验证另行闭环。SCBV、独立GPIO输入、本版ILA波形和长期稳定性未因本实验自动完成。仍保留至少3.0 CoreMark/MHz和0.031 CoreMark/LUT门槛；有限种子筛选不证明物理极限。
