# 达标配置的120 MHz原生ILA

## 状态

2026-09-06完成达标RV32IM配置的原生插核及120 MHz PDS时序；累计四次独立完整性能长测、一次验证种子长测，以及链表、矩阵、状态机真实局部窗口。旧27 MHz波形不补算为此版本覆盖。没有改动已达标CPU RTL或CoreMark算法，新增工作没有再次上传GitHub。

## 映射与构建

源实现build/pds/20260906-210034-cd03a56e；插核实现build/ila/20260906-224614-4353eb55。当前源ADF经cdt_ins的ins_list_nets查询，记录在build/ila-probe/target120-1788705742952。查询确认109条候选中的原board/soc/i_rsp_valid不再保留；真实存在的是board/soc/core/fetch_complete，RTL定义为i_rsp_valid && i_rsp_ready，二者不能互称。原nt_clk是27 MHz参考输入；新增采样时钟为PLL输出cpu_clk。

run_ila_pds.ps1新增显式Profile=Target120；默认Legacy27保留旧流程。Target120严格要求M、I8/D2 KiB、BTB256、全部达标快路径、120 MHz及RemoteLab，并用ila_target120_sources.json锁定本轮20份输入版本。源码变化后要重新查询、确认语义与映射，不能只删保护条件继续使用旧网名。原生工具逐通道验证109条连接后插核，不靠网名字符串存在于RTL就宣称连接成功。

cpu_ila_target120.fic.in的0–105及107–108位保持既有定义，106位明确改为fetch_complete。分析器Target120 CSV头必须与该映射逐位相符；旧新版相互误用会拒绝。早发请求、响应缓冲和重叠模式下，MEM load/sent而本拍无D缓存响应的计数只命名为mem_load_sent_without_cache_response_cycles，不能直接叫做存储等待周期。浏览器协议中的legacy指Pango调试传输模式，与本项目的Legacy27分析配置不是一回事。

复现插核：

~~~powershell
& ([System.IO.Path]::Combine('D:/AAAFPGA', 'ZGTC_RISC_CPU', 'cpu', 'scripts', 'run_ila_pds.ps1')) -Profile Target120 -SourceBuild ([System.IO.Path]::Combine('D:/AAAFPGA', 'ZGTC_RISC_CPU', 'cpu', 'build', 'pds', '20260906-210034-cd03a56e'))
~~~

SourceLock完整性保护和相应空对象错误提示是在本次插核实现完成后补强的；它们通过20个前置拒绝测试，并已与本次输入哈希核对。不能将这部分保护描述成已经另跑过一次完整PDS。真实插核及其当前FIC、网表、源manifest、固件、位流和原始时序已由新版分析器独立重读验证。

## 实现产物与代价

| 项目 | 插核版 | 未插核达标版 |
| --- | ---: | ---: |
| CPU时钟配置 | 120 MHz | 120 MHz |
| 布局后LUT | 11212 | 10285 |
| 布局后FF | 6658 | 4808 |
| APM | 4 | 4 |
| DRM36K等效块 | 19.5 | 16 |
| Setup WNS | +0.267 ns | +0.117 ns |
| CoreMark/MHz | 3.0129645923 | 3.0129645923 |
| CoreMark/LUT | 0.03224721290 | 0.03515369481 |

插核增加927 LUT和1850 FF；LUT增幅约9.013%，单位LUT吞吐下降约8.268%。不能拿未插核的LUT数计算插核版资源效率。PDS估计CPU最高频率123.9772 MHz不是实测Fmax；插核WNS较大包含重新布局影响，不能推论加探针必然改善时序。调试域也包含DebugCore_JCLK，原始报告All Constraints Met；SCBV原警告仍未关闭。时钟由PLL和PDS约束绑定，没有独立示波器测频。

位流SHA-256：16AE1E81D6F3B6E2F1BD7A224F090E700C91132DE6E445DE3B09EF3432F52E0C。

FIC SHA-256：3E1CB051DEBF388D92E30702DC87575A4D03627D1C67C69454710D05CEF99582。

固件SHA-256：D603AD2E598DA805EE2BB31AFFCD7430382BF96250E1E84BDEBB478278F53BD7，与未插核性能固件完全一致。

## 实板长测与采集来源

实验箱2/PG2L200H，当前位流每次下载均确认FPGA下载完成且设备唤醒。有效运行r1、r3均为4000次performance种子、1327596086周期、1099619125退休指令、11.0633007167秒，所有CRC正确。两份完整UART均与未插核达标版逐字节一致，SHA-256为3ecf89ee9643e9e6d0da6b9e2bc7ccea3b9d1fa6d04d09093095de3c978997e3。这里只证明这两次未观察到计数扰动，不能证明任何未来触发方式都无干扰；尚未新做插核validation种子长测。

本固件完成后返回启动代码的等待循环，不能直接再发G期望第二轮。r2是在已完成的固件上发送G，未产生新的START，明确不计为一次运行；有效r3先重新烧录。最后一次重烧后的操作被预约结束中止，没有另计测量。预约在23:18自动释放；额外UART页已关闭，用户主浏览器保留登录。

第一次空闲捕获只显示前端运行状态，没有返回数据；查阅已观察到的debugger/status接口确认后端isCapturing=false后，记录失败并刷新页面，随后成功捕获。没有仅凭观察超时重启尚在运行的任务。初次算法抓取过迟落在ee_printf，保留但排除算法覆盖；后续在新G的实际START完整到达后自动触发，取得链表窗口。

浏览器文件下载两次取消，原因未定位。最终CSV取自同一页面“导出”按钮实际生成的CSV Blob，在下载前仅保存其原始字节，未改写、补齐、重排或合成样本；捕获数据来自已捕获状态下的真实JTAG流，不是导入FIC后零值占位。临时Blob引用钩子恢复，浏览器下载设置也已恢复默认。

## 当前有效算法窗口

build/hardware/ila-target120-algorithm-1.csv，SHA-256为73783F35792DD914FE2663136F7D0388544B5E35DDED726BAC0CC4AF638FC845。

1024样本对应8.533333微秒周期槽，首末边沿相距8.525微秒。1023组相邻样本均通过ID→EX的PC/valid传递及EX→MEM valid检查。988次EX fire全部位于core_bench_list；WB为988，局部退休率0.96484375。IF/ID/EX/MEM/WB占用分别1006/1000/994/988/988周期；ID和EX各保持6拍，redirect为6拍，I行填充命令高电平为0拍。

前128点渲染波形在约第41点观察到redirect后各级有效位空缺依次传播；这支持该局部窗口的损失与重定向相关，不能把所有redirect叫作分支预测失败。整个计分区的IPC约0.8283，与此局部0.96484不同；这个短窗口不能代表全算法平均，也不能证明物理极限。

同固件ELF经nm -S -n产生符号表；该ELF重新objcopy并补齐64 KiB生成的HEX与计分固件哈希一致。符号绑定和原始文件哈希见build/hardware/ila-target120-analysis-provenance.json。分析输出及视觉检查后的PNG位于build/hardware/ila-target120-list-analysis。

## 文件与回归

原始UART：ila-target120-performance-r1.uart、-r3.uart及各自-session.json、.result.json。会话记录ila-target120-audit.json保存目标设备、下载终态、发送G、实际串口响应、捕获页面状态、失败尝试和释放状态。所有这些位于build/hardware，不入Git。

ila-target120-idle.csv是空闲等待；ila-target120-algorithm-0.csv只有printf，二者不能用作关键算法证明。分析器需要显式--profile Target120及匹配--manifest，校验实际位流/FIC/网表/ADF/固件/源清单哈希、FIC时钟与采样模式、原始时序及CSV结构。输出hardware_origin_verified_by_analyzer=false是有意的：离线文件校验不自动证明板卡来源，来源依赖上述实际采集记录。

20项PowerShell前置拒绝测试、18项ILA/时序Python测试通过；旧27 MHz的6份真实捕获重新通过现有分析器。修复了负向测试最后一个子进程退出1污染脚本成功退出状态的问题。已接入validate.ps1，但本轮没有再次跑完全部CPU/ISA回归；CPU RTL未改动。

## 后续缺口

独立GPIO输入正例、电气约束/SCBV、算法全路径覆盖、长期稳定性与进一步三指标优化仍不算完成。后续在资源效率至少0.031 CoreMark/LUT的前提下推进执行效率与频率，不将PDS频率估计或有限局部采样叫作物理极限。

## 23:40补测：矩阵、状态机与验证种子

2026-09-06重新申请实验箱2/PG2L200H，通过已登录Chrome 19474完成三次独立下载，每次重烧后发送新的G。性能两次各4000轮，验证一次4000轮，全部完整START至FINISHED、种子/算法CRC、配置字及不少于10秒要求通过。性能UART与未插核性能原始记录逐字节一致，验证UART也与未插核验证原始记录逐字节一致。因此这三次运行没有观察到插核引起的计数变化；不将有限重复外推为长期稳定性证明。已关闭串口、释放设备并关闭本次额外标签页；没有再次上传GitHub。

原始资料统一位于build/hardware：ila-target120-sweep-performance-01、-02和ila-target120-sweep-validation-01的.csv、.uart、-session.json、.result.json；整体来源记录为ila-target120-sweep-audit.json，分析绑定为ila-target120-sweep-provenance.json。CSV仍取自网页真实“导出”动作生成的原始Blob，保留1024点/109通道，不合成样本。

| 窗口 | EX fire函数分布 | WB/1024 | EX保持 | redirect |
| --- | --- | ---: | ---: | ---: |
| performance-01，状态机 | core_state_transition 772；core_bench_state 120 | 892 | 22 | 22 |
| performance-02，矩阵 | matrix_test 878 | 877 | 136 | 2 |
| validation-01，链表/比较 | cmp_complex 573；core_bench_list 349 | 922 | 17 | 17 |

三份CSV各1023对相邻样本均通过传递一致性检查，I行命令高电平及已发送load无原始D-cache响应代理计数均为0。矩阵878次EX fire与877次WB是有限窗口两端的级间差异，并非凭此判定丢指令。局部退休率分别0.87109375、0.8564453125、0.900390625，不能替代整次性能运行的约0.8283 IPC。结合此前的链表窗口，当前Target120映射已取得链表、矩阵、状态机三类关键算法的真实局部证据，但不代表所有算法路径、异常、cache miss均覆盖。

矩阵136个EX有效但未fire的样本按同固件objdump机器码定位：134个对应9个mul地址，另2个对应0x2820处lh。例：0x29b8为mul ra,ra,s5，0x29c0为mul s5,t3,s4。状态机窗口只有22个保持周期且伴随22个redirect；后续优先分析乘法请求/结果交接，其次重定向代价，而非不加区分地只扩大缓存。当前探针未含乘法单元ready/busy，故这些是停顿时所处指令的相关性，不冒称已证明全部因果或精确可消除周期。矩阵预览已视觉检查，位于ila-target120-sweep-analysis-02/matrix-window.png。

验证插核实现build/ila/20260906-232921-1c7885c3来自build/pds/20260906-210119-bcf4ad6d，并使用最终20源输入锁定流程完成全PDS：10778 LUT、6653 FF、4 APM，120 MHz setup WNS +0.267 ns，原始时序All Constraints Met。位流SHA-256为6056E45D96E6847F5E5AD8B6414021B13D06969BBF80D10EF610E0E7B2BB2BDD，FIC为22F8A83927ECCDF71E5076325C11C7B9C73C4EB098212A1C2D0D47BC4A83DA23；不与性能版11212 LUT混用。匹配验证ELF经objcopy和WSL bin_to_hex重建64KiB HEX，完整哈希与07E2DF97开头的原验证固件一致，再生成专用符号表。Windows重建文本因CRLF不匹配的中间文件另行保留，不用换行不同的文件冒充字节一致。

性能插核版仍为3.0129645923 CoreMark/MHz、0.03224721290 CoreMark/LUT，满足用户新增资源效率至少0.031的约束；未插核达标版为0.03515369481。验证种子的吞吐不替代性能成绩，也不使用验证版较少LUT去计算性能版资源效率。

本次自动验收追加资源效率整数不等式门槛，27项性能/ILA/时序Python测试通过；仅修改验收脚本与测试、文档，未修改CPU RTL，没有声称重跑全部CPU/ISA回归。
