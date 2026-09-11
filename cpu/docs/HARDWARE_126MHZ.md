# 126 MHz 联合指标实板验证

## 结果与适用范围

本轮是在满足资源效率至少 0.031 的前提下提升已验证频率，不替代原 120 MHz 达标记录，也不宣称物理极限或全项目验收完成。板卡为同一实验箱2/PG2L200H，未插 ILA。

| 指标 | 前递版 120 MHz | Cache 查找版 126 MHz |
| --- | ---: | ---: |
| 配置频率 | 120 MHz | 126 MHz |
| CoreMark/MHz | 3.0129645923 | 3.0129694974 |
| CoreMark | 361.5557510765 | 379.6341566767 |
| CoreMark/LUT | 0.03555470067 | 0.03718986645 |
| 布局后 LUT | 10169 | 10208 |
| FF / APM | 4821 / 4 | 4807 / 4 |
| setup WNS | +0.191 ns | +0.128 ns |
| 性能迭代数 | 4000 | 6000 |

频率提高 5%，吞吐提高约 5.00017%，资源效率提高约 4.59901%；增加 39 LUT、减少 14 FF。两次性能和一次独立验证种子长测均通过，计分区约 15.8 秒。频率源由 PLL 配置、原厂模型、PDS 时钟约束与固件计数一致性支持，没有独立仪器测量时钟。PDS 估计 128.0738 MHz 不是已验证 Fmax。

每 MHz 成绩的微小差别仅约 0.0001628%；迭代数和编译时钟/串口等待常量不同，不把它宣传为结构执行效率提升。10 轮短跑周期仍相同。本轮明确收益是提升配置频率和单位 LUT 吞吐，执行效率基本保持。

## 三次独立运行

时间列保留采集器原始 UTC 时间（当地北京时间为次日凌晨），不修改服务器记录。

| 运行 | 发 G 时间 UTC | 周期 | 退休指令 | 计分秒数 | CRC |
| --- | --- | ---: | ---: | ---: | --- |
| performance-r1 | 2026-09-06T17:14:49.142Z | 1991390887 | 1649428424 | 15.8046895794 | 通过 |
| validation-r1 | 2026-09-06T17:16:55.392Z | 1993862590 | 1649775523 | 15.8243062698 | 通过 |
| performance-r2 | 2026-09-06T17:18:26.659Z | 1991390887 | 1649428424 | 15.8046895794 | 通过 |

每次先重新烧录对应镜像，串口连续三次空读后才发送 G。第二次性能是在验证运行后重新烧录，不是同一缓存输出重复保存。三次编程完成终态、发送请求、每包 bytesRead/hex/data、空读区间和释放状态全部保留。逐包检查真实字节数和 UTF-8 解码文本，未裁剪、重排或去重输出。没有串口读取解析错误，没有混入启动残留的被排除运行。

两次性能原始 UART 逐字节一致，SHA-256 91E2369DBD90618759690DF04FFD7E3E188DC28BBDC1DCB57812E0F695DB3428；验证 UART 为 30F1F9C8C2940659C74AD5BF93D4586EAAE12E81BC31A0852F19CCC301C21568。性能种子 e9f5/e714/1fd7/8e3a，6000 轮 final CRC a14c；验证为 18f2/e3c1/0747/8d84，final CRC 18e1。

网页打印的 Iterations/Sec=400 来自整数秒计算，不能当作精确成绩。本报告用 6000*126000000/1991390887 得到 379.6341566767 CoreMark。

## 实现和源快照

- 性能：build/pds/20260907-010518-97b194c6。
- 验证：build/pds/20260907-010828-91645cd6。
- 性能位流 SHA-256：F4FE2DBF43FDF6042B3479E1D5C7A0DDA303583D83509EAD632084DD56EF43A8。
- 验证位流 SHA-256：FECC5B1C8C7561A0CA03B600557C448F4B0DD91AC78E76A218EB3935109F6509。
- 性能固件 SHA-256：4A97B21E183CE5E686A44F88F4F61F5A02077FAF7F75C6879148758BE6B37301。
- 验证固件 SHA-256：6F923297D5F5C0B1E109ADA982BBBB43238EAB3420B77759D6E7EA68F8DFFE0B。

两份实现的 20 份生产输入快照完全相同；烧录前还核对当前源文件与快照一致。Cache 源为 D5D6D3C2FDC5A877F04A664A46F38DBFB0CEC6DFB53F59E0C2941A15A253D757，Core 源为 C4F0EF80E634F153F5BF1CB2B0F9BB314432333BF9DC93E1A8E9F6E1C2CC2346，新增 126 MHz 分频后的 PLL 源为 F284E5F8A70D0C394601ABFD48A6408AB7803B919A09C065D452CAB584920481。两份原始 PDS 报告均 All Constraints Met，10208 LUT/4807 FF/4 APM，WNS +0.128 ns。

I-cache 8 KiB、D-cache 2 KiB，两路、16 字节行；BTB 256 项，RV32IM，配置字 0e8e86f9。FastI、FetchOverlap、FastD 读写、EarlyDRequest、DataOverlap 开启，LoadUseBubble 关闭。GCC 10.2.0，RV32IM/ILP32、O3、循环展开和链接松弛；无 LTO，无上游算法/种子修改。6000 轮和串口等待 2520000 周期统一编译到对应固件，串口等待在计分区外。

PLL 为 27 MHz 输入、I=1/M=2/F=21/OUT0=9；CPU 约束周期 7.936 ns。原厂模型已验证所有 18 个支持频点的输出和复位重锁，126 MHz 的 200 周期跨度为 1587.342870 ns。

## 验收入口与证据

check_frequency_candidate.py 显式要求 --clock-hz 126000000，独立重读原始 PDS 报告、验证源快照/位流/固件哈希、从原始 UART 解析配置与完整 CRC、检查不少于 10 秒，并用整数交叉乘法检查至少 3.0 CoreMark/MHz 和 0.031 CoreMark/LUT。性能两次均返回 numeric_target_pass。验证种子只作为正确性/时长验证，不混入性能计分。

原 check_performance_target.py 的 CLI 保持固定 120 MHz，不增加放宽频率的选项。使用旧 120 MHz 构建/UART 冒充显式 126 MHz 的反例已实际拒绝；旧 120 MHz 固定门槛重验仍通过。

原始记录位于 build/hardware，统一前缀 cache-lookup-f126-box2：

- performance-r1/r2.uart、各自 -session.json 与 -target.json。
- validation-r1.uart、-session.json 与 -verified.json。
- -audit.json：三次烧录/采集及已释放预约的完整流程。
- cache-lookup-f126-provenance.json：源哈希、23 份证据文件哈希、原始运行和前递版对照。

额外串口标签已关闭，用户原有 Chrome 登录保留，页面确认未申请设备。没有保存密码或访问令牌，没有 Git 提交/推送。

## 回归及复现

Cache RTL 的完整回归、外部 RV32UI 41 项/164 次与 RV32UM 8 项/32 次均通过；新的频点/计分/来源保护定向测试也通过，详情见 CACHE_LOOKUP_DATA.md。新 PLL 源没有更改 Core/Cache，126 MHz 两组 10 轮编译式短跑分别为 3326116/3329203 周期、2748941/2749614 条退休指令，CRC 通过，报告目录为 build/compiled/20260907-011059-b30ffdd2 与 20260907-011113-60e274c1。短仿真不会被正式验收器当作板测。

性能固件参数：build_coremark.ps1 -Iterations 6000 -ConsoleDelayCycles 2520000 -ClockHz 126000000 -EnableM 1 -Optimization O3 -UnrollLoops -LinkerRelaxation；验证固件另加 -ValidationRun。

对应 run_pds.ps1 采用 -ClockHz 126000000 -UartProfile RemoteLab -Predictor 1 -CacheEnabled 1 -CacheSetBits 6 -ICacheSetBits 8 -BtbIndexBits 8 -EnableM 1 -FastICacheHit 1 -FetchOverlap 1 -FastDCacheRead 1 -FastDCacheWrite 1 -EarlyDRequest 1 -DataOverlap 1 -LoadUseBubble 0 -UartBaud 115200，-FirmwareHex 指向相应新固件。新构建目录由脚本自动生成，不覆盖保留的测量快照。

## 拒绝点与未完成

135 MHz Cache 查找版实现 WNS -0.552 ns，未上板；不拿它的标称频率计算成绩。本次 120 MHz 同源前序候选面积更小，但没有借用 126 MHz 长测冒称那个旧位流已经板测。

126 MHz 只是在当前约束和有限三次长测下验证的候选，不是最大物理频率、多小时稳定性或全部电气要求的证明。SCBV/完整 IO 电气约束、独立 GPIO 输入正例、当前新源 ILA 映射与波形仍缺；三项指标继续联合优化，不缩减为只追求 Fmax。

