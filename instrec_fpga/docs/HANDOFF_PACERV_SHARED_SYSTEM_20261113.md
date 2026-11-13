# PaceRV共享整机集成交接

最新要求：高性能PaceRV＋共享整机存储和外设；只验收100Pro+本地PDS完整构建，远程上板已结束，最后预约已释放。

工作仓库D:/AAAFPGA/ZGTC_RISC_CPU_XSY，XSY分支，基线852f067db4a4a710f5355e3ab311f035ced5b48d。只修改instrec_fpga。结束前更新STATUS→CHANGELOG→本交接，本地commit，不push。PDS同时只能一个流程，不操作cdt_js/cdt_cfg，不改变既有latest位流。

当前wrapper SHA256=4C7FA9F104C33423C76FB3FBBA2DA29F65FDFF0444E50B3E96ABF7EF342B8F9C；生产顶层SHA256=67FB1E361AB497A877A07C0F62EDE47AB142EEB7BD6FD2254CD4BCBE4C7F0C32。八份H3 vendor执行核心逐字节不变。RAM已推断为两个原生DRM，四路共享UART接受保持及优先级已修正。

已验证：run_pacerv_checks三组通过；25项定向、两类1500周期反压、8项取指边界。完整配置固定循环180016 cycles/180008 retired/f2d8888b，原控制核460012/180008/f2d8888b。
最终NPU报告：build/sim/cpu_native_joint_pacerv_h3_imc_timing_pipeline_final/PACERV_NATIVE_REPORT.json，58项输入hash与当前源一致，331 DDR请求/331返回、CRC ab60ce69，四卷积/四池化/GAP/FC1/FC2/概率golden逐位一致，31152091 cycles。
共享DDR Baseline/Modified/Rollback全部通过，996项检查、四客户轮转、迟到返回和原4KiB自检通过。最终全集成回退已恢复21份原始hash及460012周期原CPU行为，live源保持新版本；证据evidence/INTEGRATION_ROLLBACK_RESULTS.json。
生产UART报告uart/after_priority_fix及uart/final_native_ram均通过，4路32字节实际串行输出一致。collector仍选after_priority_fix，输入hash保持一致。
旧CPU入口已迁移更名的frontend_pc调试信号并修复启动事件观察。run_standard_cpu_tb.py实际通过，build/pacerv_shared_system/standard_cpu_entry/RESULT.json。该旧TB显式关闭M/预测器，240009周期，独立于完整配置180016周期。
聚焦Python409 passed/13 skipped，远程辅助13项、时序解析3项通过；RTL checker 81个.v、0 violation。全量外部InstRec资产缺失保留原日志。

唯一活跃PDS：build/pacerv_shared_system/pds/full-20261113-223256-full，父PID53316，exec会话49214；PG2L100H-6IFBG676，202份冻结输入共3223223字节。已完成compile/synthesize/dev_map，已完成综合，正在后续映射/布局布线。映射36453 LUT/39468 FF/1378 Distributed RAM/126 DRM/94 APM，最终路由时序待验。
本轮pnr显式启用-optimize_multi_corner_timing -fix_hold_violation -fix_hold_violation_in_route TRUE，已用本机pnr -help核实。用户时钟125MHz，用户clock pair uncertainty0.150ns，实际路径还出现0.300ns，按真实报告记录。
剩余：等待PDS结束，inspect_pds.py <run> --require-qualified核验十表/Design Summary/位流/冻结hash。若失败，依据实际关键路径针对性修正并另建冻结run。
收集：collect_evidence.py --full-build <run> --npu-run <timing_pipeline_final>；远程参数已经可选，本任务不要传入。核验CPU、标准TB、UART、回退与NPU报告。
补齐物理结果到主技术说明/README/USAGE，按序更新STATUS→CHANGELOG→本交接；make_review_artifacts.py刷新，重开MODIFIED_FILE.sv、DIFF_FILE.patch、VERIFICATION.txt、ROLLBACK.sh。
精确路径stage并审查，ROLLBACK.sh设Git executable位；该.sh是UTF8 BOM PowerShell源码，实测经pwsh ScriptBlock执行，常规入口为ROLLBACK.ps1。本地commit XSY，不push；结束前PDS完全退出。

已结束记录：remote-20261113-213002-full 125MHz十表过，setup+0.113ns，9807LUT/7334FF/610 Distributed RAM/2DRM/4APM，板14零UART，已释放，独立于100Pro+验收。
clock-20261113-210619-full十表过，板12取得15条完整记录/390字节，参考时钟约125MHz；CLOCK_*证据保留。远程工作不再继续。
full-20261113-203016-full过渡快照已停止，无位流，STOP_REASON.json保留。full-20261113-191537-full是旧CB018 wrapper的时序失败版本，不混为当前报告；旧190733远程证据移入evidence/historical_pg200_190733。
环境：PDS D:/PDS_2022.2-SP6.4，授权环境变量有效且不打印内容。native Icarus/vvp可用。NPU使用Ubuntu-22.04的Verilator5.040；旧run_sim依赖H盘MinGW，当前CPU可复现入口为新增native-Icarus脚本。账号/许可证/大数据库不入Git，论文及既有历史实验不动。

本轮新增路径修改：MMIO数据仅由忙状态保持并行采样；activation_store_mux强制寄存命令，24笔混合即时/延迟读写测试通过；dashboard_text增加字形寄存，renderer和TB延迟统一五拍。CPU三组和标准TB、21文件回退已重跑通过；完整NPU31152091周期、331请求返回全部通过。新显示五帧逐像素等价测试运行中，exec83582。213918旧轮最终setup最差-1.262ns、hold最差-0.029ns，已有位流但不合格，原报告保留。

## 最新覆盖：2026-11-13 23:32

用户要求想尽办法使时序合格。223256已完成但setup仍失败：CPU-DDR返回CE -1.414ns、FC系数选择-1.224ns、UI字形-0.292ns；hold/恢复/移除/脉宽均过。当前唯一完整PDS flow为full-20261113-232600-full，runner会话39946，父PID59504；performance模式、seed2、hold修复8轮、预算100分钟，202份冻结输入与Git检出一致。DDR桥增加CHECK_REQUEST拍、IDLE预采样及移除返回数据清零；FC M/shift改同步DRM读取并延迟valid，四组原生DRM18K推断成功；UI分拆通道与字符选择，控制视频统一六拍并指定syn_allow_retiming=0。

最新完整NPU为build/sim/cpu_native_joint_pacerv_h3_imc_timing_registered_ddr_coeff_bram，58输入hash一致，status pass，31152093周期、331DDR请求/返回、CRC ab60ce69。DDR Modified五组过，最大CPU等待56；Baseline/Rollback重跑过，write_pacerv_evidence已刷新。全局原始基线和回退已重跑22文件，原CPU460012/180008/f2d8888b恢复，live不变。相关Python72过1跳；RTL81个0violation。显示新run位于build/pacerv_shared_system/dashboard_equivalence_6clock，runner5576仍在跑5帧baseline与modified，不覆盖旧五拍记录。

collect_evidence已加入共享DDR实际结果及源码hash检查、FC输入hash和22文件文本；需等UI/PDS结束后以最新run和NPU收集。仍需最终时序合格、刷新文档与四件artifact、git stage/commit（不push）。所有旧run保留，远程/Chrome不用。

### 23:50执行状态

PDS full-20261113-232600-full仍在详细布线（迭代20），runner39946/PID59504；综合34757LUT/34363FF/1378DistributedRAM/128.5DRM/94APM。四组FC M/shift原生DRM18K，UI流水属性被ADS识别。旧UI runner5576的modified最后一帧于600秒超时，原始RESULT与文件保留。现已增加1200秒时限及严格基线缓存核验；新UI runner8644，目录build/pacerv_shared_system/dashboard_equivalence_6clock_timing_final，基线源/HEX/五完整帧hash核验通过，当前完成帧相同。collector新增--dashboard-run参数，结束后必须传这个新目录。collect_evidence已检查DDR的三种模式结果及四源码hash；PDS qualification通过retain保留历史。USAGE已同步performance/100分钟时限。

23:56 UI runner8644已结束exit0，五帧10,368,000像素完全相同、2000概率条检查通过，control_latency=6，所有输入hash当前一致。使用--dashboard-run build/pacerv_shared_system/dashboard_equivalence_6clock_timing_final收集。PDS router迭代36继续，39946活跃。

## 最新覆盖：2026-11-14 01:23

用户最新目标允许结合全部布线经历适度降频；继续先验收125MHz。232600已完成但不合格：系统setup -2.437ns、像素-0.138ns，slow hold -0.008ns/fast hold -0.058ns；34595 LUT/34329 FF/128.5 DRM/94 APM。最差路径来自NPU layer经in_valid进入32路activation wd_r的数据零值选择；已将payload选择独立于valid，写使能保持原契约。像素增加选择器一级，整条视频七拍。

当前唯一PDS flow full-20261114-010622-full，runner92986，父68352，normal/seed1/hold12/120分钟预算；202项冻结输入与Git index检出全部一致。最新NPU为build/sim/cpu_native_joint_pacerv_h3_imc_timing_store_payload，58项hash一致，golden逐层全过、31152093周期、331DDR请求返回。显示build/pacerv_shared_system/dashboard_equivalence_7clock_timing_selector_register五帧10368000像素完全相同，2000检查，七拍控制；runner96567已退出0。全局原始基线和回退已刷新为23文件，恢复460012/180008/f2d8888b，live不变。collector新增activation_row_store_dynamic哈希、默认七拍目录，但收集时仍显式传最新目录。

降频准备：prepare_ddr_clock.py在独立副本调用已安装厂商ui.tcl中的PLL/CL/CWL/存储时序计算过程，再用原生ip_generate -disable-syn -i生成；不变的封装/引脚参数沿用原IDF。build/pacerv_shared_system/ddr_clock/20261114-012033-1000.0重生成125MHz的两个顶层RTL逐字节相同（6项仅数值字符串规范化）；20261114-012038-875.0得到109375000Hz、DDR875Mbps、PPLL_FDIV14/DFI9142ps及配套20项参数修改。生产IP未动。若125仍失败，可据实际路径决定是否采用该档，必须同步FDC生成时钟比例、UART分频/相关周期常数、源清单和回退覆盖，再全量验证。尚未宣称降频档已通过布局布线。

已保存旧153MHz含ILA报告证据到evidence/HISTORICAL_MULTICORNER_TIMING.json：multi corner、slow setup+0.053/hold+0.149、fast setup+2.481/hold+0.102ns；该历史PG200点与当前PG100整机分开。用户询问快慢角的原因已按此直接证据回答。

接下来：等待当前run结束并inspect --require-qualified；必要时修复或采用合法降频档。collect_evidence.py --full-build <最终run> --npu-run <timing_store_payload> --dashboard-run <七拍最新目录>，不传远程参数；刷新四件artifact和文档，按精确路径stage并本地commit，不push。当前四件中VERIFICATION仍待最终collector覆盖，其余已按23文件源刷新。新增prepare_ddr_clock.py需随任务提交，原失败probe只在build保留。

## 历史执行状态：2026-11-14 01:57

当前PDS仍为010622，runner92986，父68352/worker14128；详细布线608轮完成，保持修复iter0/1/2分别399/198/192秒，最终报告仍待生成。当前实时可用内存约2–3GB，16GB/24逻辑线程；暂不并行第二个重布线。只读help查询已确认pnr的-number_of_router_thread参数；prepare_pds.py新增--router-threads（默认12并写manifest），014743是仅准备、未启动的seed2/12线程125MHz快照。

compare_original155.py已运行通过，build/pacerv_shared_system/original155_same_wrapper保存原始记录，evidence/ORIGINAL155_SAME_WRAPPER_RESULTS.json合并源码与输出。原八份SV与Original_155250/physical/V0/inputs/rtl逐字节匹配。原核没有H3的i_req_pair_address输出，隔离wrapper去掉该端口并使用原前端约定{address[31:3],1,00}；主线十份输入hash不变。定向1711周期/276退休/25checks/11DDR/1trap，反压各1500，固定循环180016/180008/f2d8888b，三项exit0。H3同一循环周期一致，因此优先处理NPU和显示关键路径，不直接替换生产核心。原155.25MHz属于PG200归档，不能当新PG100整机实测。

用户有关音频的答复事实：当前NPU31152093周期在125MHz为249.216744ms，109.375MHz为284.819136ms（+35.602392ms，+14.29%）。外部PCM1808采样48k由独立27MHz域接收；降频需同步UART_DIV949、空FIFO补样节拍约2279和必要时间常数，并验证连续采样/溢出。109.375仅已生成副本，未启用、未声称布线合格。XSY2原核/固件与852f067的相关八份源在LF规范化后相同，旧音频基线125MHz RV32I，没有该音频整机CoreMark成绩；另一个100H120MHz RV32IM SoC的383.0分只作历史资料。

## 最新覆盖：109.375MHz实际配置与连续音频验证

125MHz的010622轮六阶段结束、exit0，但系统setup -1.438ns/slow hold -0.119ns/fast hold -0.128ns；像素setup +0.751ns。原报告和位流全部保留；其位流尚未获时序资格。生产改用合法875Mbps DDR/109.375MHz用户时钟，三个DDR IP文件、DDR FDC及top配套常数已更新。UART_DIV949、音频补零2279、写超时3670016、PLL等待546875000、DDR等待10937500、M3 quota109375；像素148.5MHz和音频27MHz域不变。

当前唯一重PDS为full-20261114-021145-full，normal/seed2/hold12，202份冻结输入与Git index检出一致。取指FETCH_ADDRESS_BITS=IAW+2（13位物理ROM地址），32位PC和数据地址保留；weight_read_aligner_hardened的17项beats及wdma的16项fifo用syn_ramstyle=registers。八份冻结核心SV保持不变。首次在PnR入口因通用路由线程参数失败；第二次尝试直接载入工程续跑PnR，厂商返回Device Map hasn't been run。两次原日志在attempts目录保留，现用prepare_pds.py --restart从原冻结输入重跑完整配方，runner26725/PDS29272。PG100官方为单线程路由，不再传-number_of_router_thread；此前默认12线程结论已更正。

最新功能证据均已完成：
- build/pacerv_integration/pacerv_checks.json，四组通过；定向1704周期、25项；反压各1500；三个真实指令取指异常case均cause1且PC/mtval准确，无ROM别名；相同固件180016/180008/f2d8888b。初始测试错误地把跨界mtval设为PC，失败日志保留，修正测试预期为故障部分地址0x2000。
- build/sim/cpu_native_joint_pacerv_h3_imc_timing_rom_range_ff_fifos/PACERV_NATIVE_REPORT.json，完整NPU golden逐层精确，31152093周期、331DDR请求/返回、CRC ab60ce69，58份输入hash。
- build/pacerv_shared_system/audio_clock/20261114-022103/RESULT.json，125MHz/109.375MHz各两个132096帧窗口；稳定第二窗真实132096、补零0、溢出0、写超时0、所有样本顺序正确；首窗各补零1帧。实际3.072MHz BCK/48k LRCK、27MHz接收域、生产FIFO/sink，行为DDR固定512周期完成。原旧TB在最后bit采样前提前置SD=1，首次新实验021930保留；只修正生成测试副本，不改生产RTL。
- build/pacerv_shared_system/uart/clock_109375/RESULT.json，四源32字节真实serializer一致、无重复pop。
- 标准CPU入口通过，旧测试显式关闭M/预测，240009周期；八份新H3核心不变。
- evidence/INTEGRATION_ROLLBACK_RESULTS.json已刷新29份原始文件hash，原行为460012/180008/f2d8888b恢复，live新源不变。
- 七拍显示五幅1080p、10368000像素、2000概率条检查全部一致；本轮降频未改变像素域源码。

collect_evidence.py已支持--audio-clock-run及--uart-run并核验对应活源hash；最终收集必须传上述NPU、音频、UART、显示四个目录，以及当前最终full-build。当前VERIFICATION/RESULTS仍是上一轮125MHz记录，待当前PDS结果后刷新。四件artifact中的MODIFIED_FILE已为新wrapper3caa8296…，DIFF覆盖29原始文件；ROLLBACK.sh为PowerShell内容，不能用bash运行。prepare_pds新增--restart会先保存原尝试再从完整冻结配方重跑，单独PnR续跑入口已移除。

用户关于XSY2降频影响的结论：125→109.375降低12.5%，同周期计算延时增加14.29%；NPU当前周期折算249.217→284.819ms（+35.602ms）。原XSY2历史NPU31141255周期约249.130ms，增量还包含10838周期流水开销。相同CPU循环460012/125M=3.680ms，新H3 180016/109.375M=1.646ms，约2.236倍。2.752秒音频窗口及48kHz采样不变；具体模型数值、连续采集分别有以上独立证据，不把单循环或原PG200 CoreMark直接代入新整机。

下一步：验收当前全部十张时序表与实际109.375MHz时钟；通过后最终收集、核对/重开四artifact、按STATUS→CHANGELOG→handoff更新及本地git commit，不push。未合格则只按实际关键路径调整，保留每轮报告。

## 最新执行进度：2026-11-14 02:58

上一轮已本地提交2fac956（258份任务文件，包含源码、实验和历史证据，不push）。当前主线运行输入仍为021145的202份，全部与live和Git检出一致。PDS父29272、详细布线子75172、runner26725；025700仅为备用快照，无运行进程。021145器件映射37,843LUT/46,345FF/1058DistributedRAM/128.5DRM/94APM，详细布局后最差slack=999ps、TNS=0，仅为中间结果。02:57路由迭代8剩42372未布线子网，完整目标104621子网，最终时序尚未生成。

备用：prepare_ddr_clock.py --rate-mbps 812.5得到实际750Mbps、93.75MHz（厂商规则允许DDR3 600–1066.666Mbps，不应沿用早期“至少800Mbps”假设）。原生参数和IP生成均通过，目录build/pacerv_shared_system/ddr_clock/20261114-024634-812.5，live未改。prepare_lower_clock.py已支持109.375/93.75MHz，并可从已有参数化top更新五个命名实例；以该DDR目录/seed3生成build/pacerv_shared_system/pds/full-20261114-025700-full。六份变化含3IP、DDR FDC、top、CPU约束时钟注释；UART814、注入1953、写超时3145728、PLL等待468750000、DDR等待9375000、quota93750。202项冻结hash正确，原109.375主线202项hash保持不变。只在109.375最终未合格时考虑此备选。

inspect_pds.py已加入Requested Frequency核对：系统与像素时钟须匹配INPUTS.json，允许报告舍入误差；Estimated Frequency不能代替Requested Frequency。原3项时序测试加3项时钟测试全过，当前6项。若将来启用93.75，run_audio_clock_check.py默认仍125/109.375，需要改为从实际IDF选择当前频率后重跑；UART报告、29文件回退及checkout审计也要与新的活源匹配。不要直接复用当前109.375的audio/top hash作为93.75证据。

## 最新执行进度：2026-11-14 03:25

021145仍是唯一运行的完整PDS，父29272/子75172/runner26725，CPU时间持续增加。359轮详细布线共778.78秒，全部子网已连通；保持修复iter0/1/2分别413.00/216.94/194.45秒，增量分析各约0.7秒，后续修复尚未结束。此时place_route/instrec_top.prr仍为0字节缓冲文件，不能据此判失败；RESULT.json仍是02:27的失败重启记录，活进程与当前stdout才是运行状态依据。绝不因日志暂时不更新而重启流程。最终report_timing/QUALIFICATION尚未生成。

当前已提交99a063d，collect_evidence.py新增最终元数据：分支、checkout_commit、系统/像素频率与setup/hold不确定性；从选中快照的pacerv_shared_system.fdc核验0.150ns。测试验证器6项全过、collector AST通过；未改任何运行输入。降频常数检查确认CPU软件只输出原始周期，主top的UART/音频/PLL/DDR等待与quota均已配套；diag ACK仍按12500000周期等待，在109.375MHz延长为约114ms，NPU 50000000周期watchdog约457ms，均作为周期预算保留。其他诊断专用top/未例化demo的默认125MHz常数不属于当前完整实例。

继续等待同一runner。结束后inspect --require-qualified；若未合格按具体setup/hold路径决定修复，不能单凭降低时钟处理hold。025700的93.75MHz快照尚未启动，可在setup仍差且hold可修时采用；采用前必须同步live六份文件、Git checkout、音频测试实际频率、UART及29文件回退。当前全部功能测试路径及最终collector参数沿用上面的109.375MHz条目。VERIFICATION/RESULTS还是上一轮125MHz选中结果，必须在最终物理验收后刷新再交付。

## 最终覆盖：021145六阶段结束与音频影响复核

runner26725已返回：完整六阶段均成功、exit0、3789.377秒，202项冻结输入未变，位流已生成；qualified=false。最终report_timing/instrec_top.rtr十张检查表齐全：系统slow setup -1.633ns/TNS -33.413/155失败端点，slow hold -0.127ns/THS -0.529/8失败，fast hold -0.136ns/THS -1.156/28失败；其余检查正裕量，像素slow setup +0.611ns。最终37,599LUT/46,348FF/1,058DistributedRAM/128.5DRM/94APM。内部posthold摘要-1.548ns不是最终报告值。当前没有运行中的PDS构建，备用025700仍未启动。

最差setup实际来自u_weight_loader/racc0，经rdigest_c XOR、比较进入weight_err、weight_ok及tx_line，5级逻辑但约89%的数据路径耗时来自路由；最差hold来自u_npu/u_gap/lane_cnt[2]直接到acc_b_2_20、acc_b_2_21等RAM64 WADDR[2]。下一轮先读对应RTL，按协议拆解校验数据路径并处理GAP存储映射/写地址保持，禁止通过放宽时序或假路径掩盖真实路径。不要猜测本轮仍是CPU分支或之前两级FIFO；最终报告已给出新的关键路径。新改源须进入基线/差分/回退覆盖并重新做相关功能验证，再选择同频或合法较低频率完整实现。

用户本轮询问相对XSY2的语音影响：原125MHz NPU31,141,255周期约249.130ms，新109.375MHz 31,152,093周期约284.819ms，增加35.689ms；固定整数循环3.680096→1.645861ms，快约2.236倍。采样48kHz、窗口132096帧/2.752s及像素域不变，两档连续I2S稳态完整样本一致，固定特征的完整NPU逐层golden一致。约36ms是NPU增量，完整采音至显示延迟还包括Mel和共享DDR等待。docs/AUDIO_FREQUENCY_IMPACT_20261114.md已同步最终物理状态。此轮只更新四份状态/说明文档，无RTL/约束/实验脚本改动；主VERIFICATION仍待最终合格实现后收集，不能作为109.375MHz合格证明。
