# InstRec-FPGA 当前状态（STATUS）

> **2026-11-14 PaceRV共享整机：100Pro+ 109.375 MHz时序收敛中**。完整五级RV32IMC核心与整机音频、NPU、显示、UART、DDR已接通。相同固件固定循环460,012→180,016周期，退休指令均180,008，结果f2d8888b；CPU四组、996项DDR、四路UART、标准CPU入口及29文件独立回退通过。
>
> 当前冻结run为 `full-20261114-021145-full`，PG2L100H-6IFBG676，系统109.375MHz/像素148.5MHz，202份检出输入一致。官方规则生成的875Mbps DDR IP、FDC、UART分频和音频时间常数已同步启用；程序ROM取指物理地址限制为13位，完整PC和数据地址仍32位；两级短权重FIFO改用寄存器映射以处理保持时间路径。完整NPU golden一致，31,152,093周期、331次CPU DDR请求/返回。七拍显示五帧10,368,000像素与原版一致，2000项检查通过。当前normal/seed2/12轮hold修复完整重跑；旧125MHz的010622轮全部阶段完成但时序未合格，原报告保留。
>
> 125MHz及109.375MHz连续I²S仿真各完成两个132,096帧窗口；稳定后的第二窗均全部为真实输入，顺序一致、补零0、FIFO溢出0、写超时0。启动首窗各有1次补零。新频率下NPU周期折算284.819ms，原125MHz折算249.217ms。音频采样48kHz及像素148.5MHz保持独立。
>
> 原155.25MHz核心在隔离副本通过三项集成测试，相同循环仍为180,016周期，生产保持H3。厂商说明PG2L100H采用单线程路由；其不接受通用`-number_of_router_thread`选项，当前配方已删除。单独重启PnR未加载已映射状态，现保留两次失败记录并从同一202份冻结输入完整重跑。16GB主机只运行一项重布线，轻量仿真可并行。
>
> 本轮只验收100Pro+本地完整系统，远程工作已结束；旧正式latest位流不变。说明 `docs/PACERV_SHARED_SYSTEM_20261113.md`；复现 `experiments/pacerv_shared_system/USAGE_zh.md`；恢复 `docs/HANDOFF_PACERV_SHARED_SYSTEM_20261113.md`。
>
> 最新物理进展：021145已综合、映射和详细布局，映射37,843LUT/46,345FF/1,058DistributedRAM/128.5DRM/94APM；布局后初步最差裕量+0.999ns、TNS=0，正在详细布线。PDS父29272、布线子75172、runner26725。另存025700的93.75MHz备用快照，厂商812.5Mbps请求实际生成750Mbps；UART814、补零1953及时间常数配套，202份输入hash正确，尚未运行，生产仍109.375MHz。
>
> 最终更新：021145完整六阶段结束，exit0，202份冻结输入未变，位流已生成；最终时序未合格。系统slow setup -1.633ns（155个失败端点）、slow hold -0.127ns（8个）、fast hold -0.136ns（28个）；像素slow setup +0.611ns。最终布线37,599LUT/46,348FF/1,058DistributedRAM/128.5DRM/94APM。最差setup来自weight_loader的racc0，经rdigest_c与比较进入weight_err/weight_ok；最差hold为GAP lane_cnt[2]直达acc_b的RAM64写地址。下一步按这些实际路径修复，不把降频当作hold修复。备用93.75MHz快照仍未启动，生产109.375MHz未变；当前没有活跃PDS构建。

> **2026-11-13（离线参考量化契约错误修正 —— 板级链路与 golden 逐位一致，先读这节）**
> **根因**：`golden_pipeline.run_mel_pipeline()` 的 `inv_s_in/zp_in` 默认取
> `scripts/outputs/layer_contract.json`（44.1 kHz：zp_in=49、inv_s_in=267723430），
> 而 48 kHz 位流的量化器是 zp_in=47、inv_s_in=236403274（`instrec_top.v:433` 显式覆盖）。
> 因此**所有 48 kHz 的离线 golden 标签都是用偏大 13% 的输入尺度 + zp 49 算出来的**，
> 每一次 board-vs-offline 对比都被这个错误污染。`board_accuracy.offline_top1()` 已改为
> 从同一份 48 kHz layer_contract 取量化参数。
>
> **修正后的等价性（决定性）**：同一段 PCM 下，板级 logits 与 golden 只差 ±1 LSB：
> - 200 Hz 单音（锁窗读回 132096 样本）：board `[-1,9,-24,-16,17,-18,-5,-1]`
>   vs golden `[-2,9,-25,-17,18,-18,-6,0]`，同 top1=4。
> - IRMAS 单簧管片段（锁窗读回真实窗口）：board `[-20,-23,-21,-28,33,23,-47,25]`
>   vs golden `[-20,-22,-20,-27,32,22,-47,25]`，同 top1=4。
> ⇒ mel → standardize → 量化 → NPU 全链路在板上与参考实现一致（±1 LSB 属 requant 截断容差），
> 「板子算错」不再成立。
>
> **剩余差异全部来自模拟回环**：同一片段，用「播放的 wav」算 golden 得
> `[-20,10,-6,-10,21,-5,-26,6]`，用「板子采到的 PCM」算 golden 得 `[-20,-22,-20,-27,32,22,-47,25]`。
> 即 Realtek → PCM1808 这一段改掉了信号：PCM std 6642→5122，dB 谱中位 +15.7 dB，
> z 标准差 1.02σ，feat 平均差 13 LSB。测试台上「板级 ≠ 离线」的观感由这一段造成，与 FPGA 无关。
> 判断模型/FPGA 只能用**板子实际采到的 PCM** 做参考（`scripts/diag_spectrum.py` 就是这么做的）。
>
> **新增工具** `scripts/diag_spectrum.py`：锁窗后一次读回整窗 PCM（264 KB）+ `0x200000` 的 dB 谱
> （331 个 256 B 块，约 31 s），与 golden 逐元素比对。实测板级 dB 与 golden 只差一个**全窗常量**
> （约 +36 LSB ≈ 0.14 dB，源自 259 帧 global max 与 258 帧导出的差异），该常量在 standardize
> 的均值相减里完全抵消，因此不影响特征。
>
> **新发现的 RTL 缺陷（待下次重编修）**：`instrec_top.v:793`
> `dg_rx_sel = rx_byte_valid && !wl_busy && (rx_byte_data != 8'hAA)` 会把**任何值为 0xAA 的字节**
> 从诊断命令通道里丢掉。地址/长度一旦含 0xAA（例如 `0x...AA00`），diag FSM 就少收一个参数字节、
> 后续字节全部错位，通道被 NAK 刷屏且无法自恢复。主机侧已加绕行（`diag_spectrum.read_block`
> 改从更低地址读更宽窗口再切片）；RTL 侧建议把判据改成「仅当 diag 不在 S_IDLE 时才放行 0xAA」。
>
> **注意**：`0x0020_0000` 存的是 **dB 谱（int16 Q8.8，全负）**，不是标准化后的 uint8 特征（它在片内，
>`FEAT_DUMP_ON_M3=0` 时不出 DDR）。此前把它当 feat 槽读低字节得到的"板级特征"是噪声，
>相关结论一律作废。

>
> **追查中的残留缺陷（下次重编一并修）**：`diag_spectrum.py` 反复测同一段稳态单音，
> 窗口**前部 0-75 帧（0～0.65 s）**与 golden 差 2～60 dB，其余 183 帧只差 ≤1.9 dB，且坏帧数量每次不同
> （一次 3 帧、一次 75 帧）。定位到 `mel_engine.v:798`：`win_tick` 时 `win_base <= win_id[0] ? 0x42000 : 0`，
> 而 `audio_sink` 在**同一条边沿**就 `win_id <= win_id + 1`，所以 mel 选中的是「下一窗要写入的那一半」
> （即上上窗 n-1 的数据），而不是刚完成的第 n 窗。mel 用 40 ms 读完这 132096 个样本，同时写侧正在
> 从同一地址覆盖它，写侧一旦突发（FIFO 积压后回灌），被覆盖的前缀就变长——与「坏帧数量随抓取变化」吻合。
> 建议改法：`audio_sink` 额外输出一个「已完成窗口号」`win_done_id`（tick 前的 `win_id`），mel 用它取半区；
> 或最小改动 `win_base <= ~win_id[0] ? PCM_WIN_STRIDE : 0`。修完后用 `diag_spectrum.py` 复核：
> 判据是「去掉全窗常量后 p99.5 ≤ 8 LSB 且坏帧为 0」。

>
> **构建运维（2026-11-13 两次无输出失败后总结，勿再踩）**：`run_pds_full.ps1` 用
> `Start-Process -Wait` 起 `pds_shell`，而 compile 阶段约 3m50s 不向脚本 stdout 写任何东西。
> **后台启动 + 长时间无输出会被回收（两次都在 1.3 / 2.0 分钟被杀，`error_info.txt` 为空、
> `flow.log` 停在 rtl-infer 中途）**；`*>` 重定向到文件同样会让被 Start-Process 继承控制台的
> 子进程直接退出。可用做法：前台调用（compile 单阶段 3m50s 实测 exit 0），或后台启动时套一层
> 每 20 s 打一次心跳的包装脚本（`build/heartbeat_build.ps1`），进程就不会被当成停滞。


> **2026-11-12（最新，先读这节）**：拥塞根问题已解决。方案 A（共享 `beats-1` 减法器）
> 让 multi-seed PnR 从「`Route-0008` 布不通、无位流」变成「`Unrouted 0` + 六阶段全过 + 位流产出」，
> WNS −1.294 → **−0.667 ns**，clk 域已 +33.708 ns 完全收敛。已推送 GitHub（`a797989c`）。
> 详细见 `## 2026-11-12` 一节。方案 B（requant 流水线）实测劣化已回退，勿引用其 latest 指针。
> **2026-11-12（夜）续**：DDR3 读写「混乱」已系统核对——`>>2` 修复早已落地（git `92047409`），
> 控制器/布局模型/读回脚本均统一字节语义，56 个契约测试全绿；修掉了 `diag_dump.py` 的 feat 槽宽
> 缺陷（原只读 16512 裸 B、混着 `0x00` 高字节，导致板级逐级对拍不可信）。契约文档 §5/§7 已由
> 「暂不实施」更正为「已实施」。全量 469 passed / 26 skipped。详见 `## 2026-11-12` 末段。
> **2026-11-12（夜）离线全绿复核**：WSL Ubuntu-24.04 的 iverilog/vvp/verilator 可用（旧记录「无 WSL 仿真」已过时）。
> `sim/run_sim.py all --jobs 4` → **46 pass / 1 fail**；唯一失败 `i2s_capture` 是 STATUS 325-335 已记载的
> 历史未收敛项（L/R 翻转漏检致 2:1 抽取），非本轮回归（本轮零 RTL 改动）。DDR3 契约 6/6 PASS：
> `ddr3_byteaddr`（>>2 后稀疏写=突发读逐字节相等）、`ddr3_m3_share`、`ddr3_subsys`、
> `ddr3_aw_timeout`、`diag_readback`、`diag_longread` ⇒ 契约 §9「离线全绿」条件达成。
> 「恒 top1」三个代码层根因均已在 RTL 修复（standardize shift=36、ZP_IN_CONV1=47/ZP_OUT_FC2=58、
> ddr3 >>2）；golden_ref sine_440_full 的 feat 43..121 非饱和、fc2_logits 八类分化、probs 非坍缩。
> **剩余唯一缺口是板级验收**（FTDI 下载器此前反复丢失）：烧 `202047` 位流 → 自检 → 重复长读 →
> 同窗 PCM/feat/logits 逐级对拍。不基于未确证的「mel 卡 ST_RUN」假设改核心 FSM。
> **2026-11-12（夜）i2s_capture 悬案定性**：全量 sim 唯一失败项用 `--verbose` 抓到精确形态——
> 不是「全零/CRC 失败」，而是 487/512 words 呈 **+1 样本偏移**（偶数 word 正确、奇数 word =
> 期望+1，如 `got 80130013 / exp 80120012`），两轮合计 999；CRC、帧结构、CAPDONE 全 PASS。
> 属样本级对齐（TB 合成源 vs 期望索引），与 STATUS 334 行旧记「2:1 抽取(0x11,0x13…)」表述不同。
> 无板级真实 PCM1808 源时无法判定是 TB 还是 RTL 错，且前人三版相位改动均回滚 ⇒ **守纪律不改 RTL/TB**，
> 记为待板级确证项。该链路是诊断采集（非生产推理链），不阻塞交付。
>
> **2026-11-13（板级验收完成，最新，先读这节）**：FTDI 重插后恢复，烧 `202047` 位流（方案 A）
> 全链路验证：位流 done=1 / crc_err=0；RV32 CPU 自检全过（MMIO/ISA/BENCH acc 匹配）；
> DDR3 自检 `DDROK`；主机诊断读回 4096 B 与自检 pattern 逐位一致（1024 word），6×重复长读 6/6 精确；
> 权重上传 `WOK`（2700 帧 FA0D5236）。**DDR3 读写「混乱」在板上彻底收口**。
>
> **「恒 top1」根因完整定位**：推理链硬件全正常——mel 特征随音频 88% 变化，NPU 分类与 golden
> 参考一致（板子 feat 喂 golden 也得 class7）。真根因在 **i2s 采样链**：读回 PCM std=5.1、
> 符号翻转 7 万次（200 Hz 正弦应 ~1100），采到的是噪声非音频；板子 feat 分布 0..255(mean 128)
> vs 参考 43..121(mean 48.6)。与 i2s 历史悬案（L/R 翻转漏检致 2:1 抽取 / +1 样本偏移）吻合。
> 即 FPGA 的 DDR3/NPU/权重全部正常，唯一卡住识别的是音频进板的 i2s 采样链（PCM1808 回环/接线
> 或 L/R 翻转检测）。详见 `## 2026-11-13` 一节。
>
> **i2s RTL 复检（2026-11-13）**：实际采样模块是 `i2s_slave_rx`（instrec_top.v:330，PCM1808 master，
> BCK=3.072 MHz / LRCK=48 kHz / SD=V16）。逐行复检采样沿（BCK 上升沿）、左移采 MSB、槽位假设
> （24 数据 + 8 零的 32-bit 槽、bit_count==23 完成）均正确，无位错位 bug。结合 PCM std=5.1 的
> 静音/噪声级幅度，**最可能是硬件音频回环（Realtek line-out → PCM1808 line-in）接线断开或悬空**，
> 而非 i2s RTL 缺陷。判定需在板上量 PCM1808 的 SD 引脚（示波器/ILA）或检查音频接线。
>
> **更正（2026-11-13 晚，查历史真实 i2s 数据后）**：`build/i2s_capture/` 留有 10 个之前上板采集的
> `capture.wav`（11-06~11-09，play_mode=none=外部手动播放）。其中 **5 个是有效信号**：`tone6k_check`
> std=20409、`realtek_vol` std=9368、`tone2` std=9317、`route_verify` std=1146、`montage_music` std=1119——
> **证明 PCM1808 + i2s + DDR 存储 + 音频回环当时完全正常，未断线**。其余 5 个是静音/噪声（std<11），
> 是当时「播放音量/路由」问题的历史复现。
>
> 因此「脚本 --play 播放采到噪声（std≈2.2）」的根因在 **PC 端播放链路**，不是硬件断线：
> waveOutSetVolume 的 API 误用已修（60969209，传 device_id 而非 handle），但实测 `waveOutGetVolume`
> 返回 0xFFFFFFFF（MME 层音量本已满），故非根因。剩余疑点是 **WASAPI 端点音量（Windows 混合器里
> Realtek 可能被静音/低音量）或 waveOut device 4「扬声器」输出口 ≠ PCM1808 所接的 line-out**。
> 验证方法：手动在 Windows 播放（确认输出选 Realtek），脚本只采集——若采到信号即坐实脚本播放问题。
>
> **最终定论（2026-11-13 晚）**：用户确认之前是**全局静音**。音量开启后重测：PCM std 2.2 → **18969**
> （满幅度有效音频）；三种音频 top1 完全分化——tone_200→class7、tone_6k→class0、montage→class1。
> 对比静音时三种音频恒 class7（「恒 top1」），现三个不同类别，分类系统彻底恢复。
>
> **结论**：「恒 top1」的唯一根因是 PC 端全局静音，不是 FPGA、不是 i2s RTL、不是硬件接线。
> 整个链路（音频→i2s→DDR3→mel→NPU→分类）从头到尾正常，全部板上验证通过。

> **2026-11-13（第二轮上板验收：权重版本修正 + 数字链等价证明）**：板上原先跑的是 44.1k 旧权重
> （scripts/outputs/weights_image.bin，zp_in=49），而 RTL 是 48k 契约（mel_coo_48k.hex，zp_in=47），
> 两者错配导致分类偏差。重烧 202047 位流后上传 medley_48k/weights_image.bin（WOK CFE5A709）。
>
> **数字链等价性（决定性证据）**：先让板子采集一段 PCM，再把同一段 PCM 喂给离线 golden——
> 板 logits [27,-19,-7,-16,0,-17,4,-7] 与 golden [26,-22,-14,-8,-5,-21,6,2] 同 top1（class0），
> 证明 i2s→DDR3→mel→NPU→权重 的定点实现与参考一致；离线 numpy 与 TorchScript 参考亦 3/3 一致。
>
> **上板准确率（IRMAS val，6 类 × 3 = 18 条，峰值归一化播放）**：board 3/18、同一片段离线 3/18、
> board-vs-offline 一致 6/18。两者同样低 ⇒ 模型对 IRMAS 属域外（自带 MedleyDB 测试 INT8 77.32%），
> 不是 FPGA 缺陷。工具：scripts/board_accuracy.py --per-class N（逐片段 board/offline + JSON）。
>
> 附带修正：board_e2e.py 默认权重镜像改为 medley_48k；工作区忽略 .runtime/、ai_pcb/、pcb-aoi/。

> **2026-11-13（上板准确率复测：工具修正 + 一处待定位差异）**
> 1) 工具修正：板级测试脚本原先写单声道 wav，Realtek 端点拒绝单声道，
>    waveOutOpen 直接失败、板子实际在分类静音（PCM std≈5）。已改为 48 kHz 立体声 +
>    峰值归一化 + 播放失败立即报错；并固定循环单元为一整个 132096 样本窗口，消除窗口相位差。
> 2) 已确证：同一段 PCM 下板卡与离线 golden 一致（稳态 tone：板 [27,-19,-7,-16,0,-17,4,-7]
>    vs golden [26,-22,-14,-8,-5,-21,6,2]，同 top1=class0；numpy 与 TorchScript 参考 3/3 一致）。
> 3) 待定位：音乐类片段上，板卡 UART 遥测稳定输出 "NPU top1=7 last_p=100 c≈32.36M"
>    （100% 置信、恒定），而把板子自己采集的同一窗口 PCM 喂 golden 得到 class1/class4。
>    tone 一致、音乐不一致 ⇒ 两个候选解释尚不能区分：
>    (a) 宿主机读到的 PCM 半区与 mel 实际处理的那个窗口不是同一个（窗口相位差；稳态 tone 对此免疫，
>        音乐则不免疫，且板上导出的 dB 谱整体比离线高约 10 dB、相关系数 0.01 也符合该假设）；
>    (b) mel 的 dB 谱导出/回读在大动态范围下的定点处理有问题。
>    下一步：给诊断加「锁定当前窗口」或 ILA 抓 mel→NPU 的特征边界，把两者分开。暂不作为已收口。

> **2026-11-13（播放工具升级，排除工具误差后）**：新增 scripts/audio_player.py —— waveOut 流式播放
> （60 ms x 4 缓冲、欠载计数、数字增益 -24..0 dB）。板端实测：增益 0/-6/-12/-18/-24 dB 对应
> PCM std 18922/9499/4752/2379/1195（严格等比）、欠载 0；board_accuracy 增加「板端 PCM 电平门控」，
> 电平不达标直接判 INVALID 而非记为模型错误。18/18 条片段全部有效（std 4400-8600）。
> 排除工具误差后：board 5/18（27.8%）vs 同片段离线 3/18，仍不一致。
> **新证据（更像真问题）**：用近似稳态输入（0.75 s 片段循环）时，同一段音频连续两次读取给出不同类别
> （如 class4 → class7），说明板内结果对同一输入不稳定。疑点为窗口交接竞争：mel 在 win_tick 立刻开始
> 读 PCM 窗口，而 audio_sink 的 DDR 写可能尚未排空（page_go 8256 / m0_done 16512 需在 win_tick 时刻核对）。
> 下一步：核对 win_tick 时刻 page_go/m0_done 计数，或用 ILA 观察 mel 首个读命令与 m0 末次写完成的时间关系。

> **2026-11-13（STS 四相遥测解码，抓到 mel 侧症状）**：稳态输入下连续采集 DDR3 STS，解出
> page_go=8255（满 8256）、m0_done=16512（满）、real_frames 在 1024..16512 之间跳变，
> 并出现 **mel_timeout=1、win_miss=1、mel_busy=1** 的采样点。即：
> (a) 音频写侧基本能写满（m0_done 命中 16512）；
> (b) mel 会错过 win_tick 并触发 200 ms 看门狗，说明存在「mel 处理未完 / 停滞 → 丢窗 → 结果滞后」。
> 这与「稳态输入下连续两次读板给出不同类别」一致，是板内不稳定性的直接证据，
> 而非播放工具或 golden 的问题。
> 下一步：读 mel_cycles（窗口处理周期数）判断是吞吐不足还是死锁；若吞吐不足，需评估 259 帧 FFT
> 与 db_norm/standardize 的时间预算；若停滞，用 ILA 抓 mel 状态机与 m2 读握手。

> **2026-11-13（吞吐已排除）**：30 s 稳态播放统计 NPU 完成行 11 次 → 0.367 次/s，理论 1/2.752 s = 0.363 次/s，
> 即 mel 基本能按时完成，**不是吞吐不足**。同段 11 次完成全部 top1=7、last_p 多为 100，
> 说明板内对音乐输入是**确定性**地算成 class7，而非随机抖动（之前 diag 读到的 class4 属偶发/陈旧）。
> 因此剩下的分歧是「板上特征 ≠ golden 特征」：同窗口 dB 谱差约 10 dB、相关 0.01。
> 由于 standardize 是逐样本标准化，常数偏移会被抵消，故不是简单增益问题；需在**同一窗口**上逐元素
> 比对板内特征与 golden（加窗口锁或 ILA 抓 mel→NPU 总线）才能定位是窗口取错还是 mel 定点错误。

> **2026-11-13（决定性现象：板上答案只跟音量走，不跟音色走）**：同一片段在 0 / -12 / -30 dB 三档播放，
> 板卡输出分别是 class1 / class7 / class7，且**钢琴与小提琴两段完全相同的档位给出相同类别**。
> 离线 golden 同样三档都保持各自正确类别（class4 / class7），因为 standardize 是逐样本 z-score，天然电平无关。
> ⇒ 板内特征丢失了音色信息、只保留电平信息，指向 **standardize/归一化环节**（或 dB 谱在大动态范围下饱和），
> 而不是窗口取错（窗口错位不会让不同乐器给出同一答案）。
> 8 类串烧复核：段落切换时板卡输出仅在 class7/4/1 之间摆动，不跟随段落 → 同上。
> 下一步（需重编一次位流）：加 diag 命令把 mel 标准化后的 16512 B 特征 dump 到 DDR，主机读回与 golden
> 逐元素比对，直接定位是均值/方差计算、还是 dB 转换饱和。

> **2026-11-13（测量方法学：三个硬约束已摸清，供后续复用）**
> 1) **UART 快照上限**：115200 下 264 KB 的一窗 PCM 需要约 23 s，而窗口只有 2.752 s，所以
>    「读回整窗 PCM 再喂 golden」永远读到被覆盖的数据 —— 之前所有音乐片段的 board/golden 不一致
>    都不可信（tone 因内容恒定才碰巧一致）。可靠替代：**只读 1 KB（约 0.1 s）并连续两次比对相等**
>    才采信；实测 4/4 稳定。或用 L 命令冻结采样后再读（33 KB 谱可读，264 KB 仍会被 m2 打断）。
> 2) **DDR 谱布局**：0x200000 是 **frame-major**，每帧 64 个 mel 词；用 200 Hz 单音验证——峰值出现在
>    mel 约 5/8 且每 64 词重复一次。
> 3) **COO 表已核对**：src/mel/mel_coo_48k.hex 与 mel_tables_48k.json 的 bin_idx / weight_q15 **逐项相同**
>    （1962 条，权重和 89473），滤波器表本身没有问题。
> 4) 白噪声实验：board 各带摆动可达 35 dB、整体比 golden 低约 24 dB；但同一时刻重测 tone 的电平从
>    18922 掉到 313（端点音量/静音被外部改动），说明**模拟电平会漂移**，任何结论必须先过 PCM 电平门控。
>    已把该门控内建进 board_accuracy（std<400 判 INVALID）。

> 5) **两个操作陷阱（都曾污染结论，务必避免）**：
>    a. 发过 L（冻结采样）后必须发 U，否则采样永久停住，之后所有电平读数都是同一个陈旧值。
>       本次一度出现 tone 电平 18922 → 313，根因就是一次 L 后脚本异常退出、U 未发出。
>    b. Realtek 端点音量被外部改到 14%（pycaw 可查：扬声器 Realtek vol）。现已设为 85%，
>       并在测试前用板端 PCM std 复核（tone 满幅应为 ~19000）。
> 6) **电平正常后的对照结果**：钢琴片段（板端 PCM std 7964）→ board top1=1，golden top1=4；
>    0x200000 的 dB 谱比 golden **低约 32 dB**、形状相关仅 0.12。COO 表已逐项核对一致，
>    故差异在 mel 的功率/log2 定点链路或 bank 寻址，而非滤波器表本身。待重编加 dump 定位。
> 4) 准确率口径：IRMAS val（6 类）离线 3/18——模型对该域本就弱；板卡数字链一致性以第 2 条为准。
>
> **交接中（2026-11-10）：先读 `docs/DEV_SNAPSHOT_HANDOFF_20261110.md`** ——
> 一句话：数值侧全部 0 LSB；板级 top1 对 200 Hz/6 kHz 仍恒定，第一个偏差环节未定位；
> 诊断读回基础设施已完成并离线验证；诊断位流的 DDR3 启动自检 `@0x00300200` 已**离线复现并锁定根因**
> （m3 `rd_ready` 门控错误导致读阶段陈旧末拍被误比较，纯数据比较失败，非超时），修复已合入，待构建验证。
> **2026-11-11 更新：下面的「PCM 静默丢页」结论已被撤销** —— 没有丢页，是 DDR3 地址单位 ×4
> 导致主机读回混叠。先读 `## 2026-11-11` 一节。
> **2026-11-11（夜）更新：降 DRM 84% 实验已证伪** —— 布线瓶颈是逻辑切片拥塞，不是 DRM，
> `lut_ram` 转换已撤销。先读 `## 2026-11-11（夜）` 一节。

## 2026-11-13：板级验收完成——DDR3 读写彻底收口，「恒 top1」根因定位到 i2s 采样链

**背景**：2026-11-12 夜 FTDI 下载器（USB Cable II）在 PnP 里是 `Unknown`（只有 COM5 在线），
板级验收被阻塞。2026-11-13 用户重插后 FTDI A/B 恢复 `OK`（VID_0403&PID_6010，FT2232），
`board_check.py --status-only` 扫描 JTAG 链成功（`cdt_cfg exit 0`，状态寄存器 `0x00180c80`）。

**烧录**：有效位流 `build/pds/20261112-202047-2c1207d6/generate_bitstream/instrec_top.sbit`
（方案 A，顶层 instrec_top，SHA `23b496ee…`）。注意：`build/instrec-latest.sbit` 指向被否决的
方案 B（WNS −0.952），**验收必须用 202047 位流，不能烧 latest 指针**。
烧录结果：`program=True`、状态寄存器 `0x081ffca0`（done=1、crc_err=0）。

**启动 banner（UART 510 B）**：
```
I
RV32 BOOT
RV32 MMIO OK
RV32 ISA OK
RV32 BENCH cycles=460012 inst=180008 acc=0xf2d8888b
DDR WAIT STS 0x00000000
NPU GO
DDR3 SELFTEST...
DDROK
```
即 RV32 CPU 自检（MMIO/ISA/BENCH acc 匹配）+ DDR3 自检 `DDROK`（写 4 KB 地址标签 pattern 到
0x300000 逐字读回全对）。

**DDR3 读写收口证据（主机诊断读回）**：
- 读回 0x300000 的 4096 B，1024 个 word 逐位匹配 `0x5A5A00FF ^ w`（little-endian），
  hex 前 48 B `ff 00 5a 5a fe 00 5a 5a …` 地址标签递减清晰可见。
- 6×4 KB 重复长读，6/6 pattern 精确匹配（无偶发错位/丢帧）。
- 权重上传 691040 B / 2700 帧全 `K` 确认，终帧 `WOK FA0D5236`。

**推理链硬件正常（逐级验证）**：
- mel 特征提取正常：播放 tone_200 vs tone_6k，读回 feat 低字节 88% 不同（前 16 B 完全不同）。
- NPU 分类正确：把板子读回的 feat 喂 `golden_pipeline.npu_forward`，golden 也得 top1=class7
  （probs 100%），与板子 logits 的 top1 一致。

**「恒 top1」根因（i2s 采样链）**：
- 读回 PCM（0x000000，132096×int16）：min=−40 max=13 mean=−1.3 std=5.1，
  符号翻转 70383 次（200 Hz 正弦 @48k 应 ~1100）——采到的是噪声，不是播放的音频。
- 板子 feat 分布 0..255（mean 127.8），golden_ref sine_440 参考是 43..121（mean 48.65）——
  特征被噪声污染、系统性偏向 class7。
- 与 i2s 历史悬案吻合（STATUS 325-335「L/R 翻转漏检致 2:1 抽取」、WSL 仿真定性「+1 样本偏移」）。

**结论**：FPGA 的 DDR3 / NPU / 权重 / mel 全部正常；唯一卡住识别的是音频进板的 i2s 采样链
（PCM1808 回环/接线，或 i2s_rx 的 L/R 翻转检测）。修复方向在 i2s 采样 RTL 或音频接线，
不在 DDR3/NPU（这两条已板上证明正确）。

## 2026-11-12：拥塞根因解决 —— 共享 beats-1 减法器，PnR 收敛并产出位流

**一句话**：把 `activation_row_store_dynamic.v` generate 内 32 份 `beats-8'd1` 提为模块级单份
`wire beats_m1`，`beats[1]` 扇出 206 → 1。这是**纯组合重构，严格位级等价，0 FF / 0 周期 / 0 冒险**。
卡了两轮的「设计布不通」被解决。

**有效交付构建：`build/pds/20261112-202047-2c1207d6`**（六阶段全 OK，位流
`instrec_top.sbit` SHA-256 `23B496EE7FA82DDC2A91B53D40F6F6AE7BA73DF40851F65EF99A313065B95262`）

| 指标 | 上一轮 multi-seed `181201` | **方案 A `202047`（有效）** |
|---|---|---|
| 布线 | `E: Route-0008` 失败，496 轮 / 5396 s，2 条未布 | **`Unrouted 0`**，274 轮 / 975 s |
| 六阶段 / 位流 | 失败 / 无 | **全 OK / 有** |
| WNS (slow) | 无 | **−0.667 ns**（Option A 时代 −1.294） |
| WHS | 无 | +0.030 ns |
| `clk` 域 | — | **+33.708 ns，0 failing endpoints，收敛** |
| `pix_clk` 域 | — | −0.095 ns（10 endpoints，UI 字体 ROM） |
| `ddrphy_sysclk` 域 | — | −0.667 ns（281 endpoints，TNS −42.552；多为 DDR3 IP 内部） |
| DRM | 84% | **130/155 = 84%，DRM18K 92 / DRM36K 84 与改前逐项一致** |
| LUT / FF | — | 33752 / 39390 |

**验证**：`check_rtl` 0 violation；`pytest` 466 passed / 26 skipped；synthesize 阶段
`GTP_DRM18K 92 / GTP_DRM36K 84` 与改前逐项相同（block RAM 未退化）。
`Total nets for routing` 77629 → 77620（−9），印证 32 个减法器合并进了网表。

**方案 B（已否决、已回退）**：`requant_unit.v` 的 S2→S3 64 位组合链切一级流水（+74 FF、
延迟 4→5 拍），并同步 `fc_engine.v` 注释与 `conv_engine.v` 的 `fin_cnt` 22→23。
实测构建 `20261112-215603-990acea9`：布线仍收敛（235 轮 / 1256 s、Unrouted 0、六阶段全过、位流产出），
但 **WNS −0.667 → −0.952 ns、WHS +0.030 → +0.001 ns，明显劣化**。
判据（WNS 改善且布线收敛才保留）不满足，三个文件已 `git checkout` 回退到已推送 HEAD，
SHA-256 与 HEAD 逐项一致。失败日志与位流按惯例保留、未覆盖。

> **注意**：`build/instrec-latest.json` 目前指向被否决的方案 B 构建（WNS −0.952），
> 它是构建脚本自动写的「最近一次构建」指针，**不代表当前有效 RTL**。
> 当前有效交付是 `202047`（方案 A，WNS −0.667）；`build/` 被 .gitignore 忽略，未入库。

**剩余违例的正确方向**：`clk` 域已收敛，剩余 −0.667 全在 `ddrphy_sysclk`（DDR3 IP 时钟域）
与 `pix_clk` −0.095。STATUS 早已标注这些域「用户逻辑改不动、只能靠布局、能跑就行口径可暂放」。
不要再对 NPU 数值核心做打拍类改动（Option A 的 B1/B2/B3 与本次方案 B 均证明：路径只是被挪走，
布线主导的违例不会因加寄存器而消失）。

**git**：分支 `XSY`，已推送 `origin/XSY`（`a797989c`），含此前积压的 68 个提交；
本轮文档回写后需再次提交。未 `push` 之外的红线均遵守（未动 `test_build_tokens.py`、
未并行 `pds_shell`、未做 DRM→distributed 转换）。

## 2026-11-11（夜）：降 DRM 84% 实验结论 —— 布线瓶颈是逻辑切片拥塞，不是 DRM

**一句话**：把激活存储 `activation_row_store_dynamic.v` 的 lane_bank `block_ram`→`lut_ram`（一行属性）
确实把 DRM 从 130(84%) 降到 98(63%)，但**布线反而失败**（`E: Route-0008: Design cannot be routed`，
pnr 3h27m）。根因反转：布线瓶颈是**逻辑切片 CLMA/CLMS 占用率 ~80% 在拥塞悬崖上**，不是 DRM。改已**撤销**。

**证据（旧 00:32 布通 vs 新 19:25 失败，均 bare pnr）**

| 指标 | 旧 00:32（布通） | 新 19:25（失败） |
|---|---|---|
| CLMA 逻辑阵列 | 9327/11675 = 80% | 9796/11675 = 84% |
| CLMS 逻辑切片 | 3970/4975 = 80% | 4206/4975 = 85% |
| Distributed RAM | 940/19900 = 5% | 2988/19900 = 16% |
| DRM | 130/155 = 84% | 98/155 = 64% |

- `lut_ram` 把 64 个 DRM18K 变成 ~2048 个分布式 RAM LUT（940→2988），只把拥塞从 DRM（本就不是瓶颈，
  DRM 有 36% 余量）搬到切片（真瓶颈，80%→85% 推过悬崖）。

**关键事实（`build_full.tcl` 历史注释 + `multiseed_summary.csv`）**

- 设计面积充足：LUT 52% / FF 29%，**不是资源不够，是布线拥塞**。
- bare pnr 单种子在此拥塞度下**非确定**：00:32 布通（iter 981），15:26(post->>2)、19:25 卡死。
- **multi-seed 布置可靠闭布线**（seed1 iter15 即 Unrouted 0），但构建契约测试把 PnR 锁成裸 `pnr`
  （`-gplace_seed`/多种子均被禁）。`-dc_duplication`/`-plc_decongestion` 已试过，更差。

**结论 / 正确方向**

1. **降 DRM 不是布线手段**，不要再做 `block_ram`→`lut_ram` 类转换（FFT 延迟线同理）。
2. 真手段二选一（需用户拍板）：
   - A. RTL 降拥塞 = 三个时序瓶颈流水化（NPU 存储 -0.872 / standardize -0.859 / UI graph -0.381），
     切长组合路径同时降拥塞；
   - B. 放开构建契约、启用 multi-seed / 指定 seed（已知可靠闭布线，但牺牲可复现性）。

**本次改动已撤销**：`activation_row_store_dynamic.v` 回到 HEAD（`block_ram`），git diff 为空。
工作区仍只剩上一线程的 `>>2` 改动（未提交，需先 commit 得到干净基线）。

## 2026-11-11：撤销「PCM 静默丢页」结论 —— DDR3 地址单位是 ×4，25% 是主机读回混叠

> **2026-11-11（续）更正**：本节第 3 条"×4 只是空间浪费、片上流水线读到的正是 audio 写下的数据"
> **作废**。离线核实证明：**单拍稀疏写（audio/feat 导出）与连续突发读（mel/wdma）在 ×4 下不对齐**，
> mel 读丢 3/4 样本、wdma 读被 gap 污染——这是功能缺陷，不是空间浪费。统一契约、故障账本、修复方案
> （`ddr3_ctrl_axi.v` 地址 `>>2`）见 `docs/DDR3_CONTRACT_20261111.md`；生产路径一致性测试已固化
> （`tests/test_ddr3_layout.py` / `test_ddr3_contract_consistency.py` / `test_read_ddr.py`，20 用例）。
> "共用 cmd 地址空间"不能替代"稀疏写 vs 突发读对齐"的逐字节验证。

**结论先行**
1. **没有丢页、没有丢数**。板上 PCM 窗口完整包含 132,096 帧，只是物理步长 128 B、每页 32 B。
2. 根因是 `physical_byte = 4 × cmd_addr`：控制器的 `cmd.addr[27:0]` 被 DDR3 IP 按 32 bit 字地址解释，
   实际落盘是 4 倍。音频写 `page_off = page_no << 5`，所以页 p 落在物理 `128p`；8256 页占物理
   `0 .. 0x101FA0`（1.06 MB），不是文档里的 264 KB。
3. 所有主口（audio 写 / mel 读 / NPU 权重 / diag 读）都用同一套 cmd 地址，**起始地址**互相一致；但
   ×4 只缩放起始地址、不缩放 32 B/拍的突发步长，故稀疏单拍写与连续突发读**物理不对齐**（见上文更正）。
   各区物理区间仍互不重叠（left `0..0x101FA0`、left-b `0x108000..`、right `0x210000..`、weights `0x400000..`）。
4. 之前「每 4 页只有 1 页有音频 / 4964 页等于 page1 / 写地址未错位」全部是**主机读回侧的混叠假象**：
   一次 `R` 命令要 256 B 逻辑数据，实际只覆盖 256 B 物理 = 64 B 逻辑，于是每 4 页只取到 1 页。

**决定性证据（位流 `69041235`，win=62 锁窗）**
- 重叠实验 `build/probe_addr_unit.py`，`read(0)`/`read(32)`/`read(64)` 各 256 B：
  - `p32[0:128] == p0[128:256]` → **128/128 全等**
  - `p64[0:128] == p32[128:256]` → **128/128 全等**
  - 对照 `p32[0:128] vs p0[0:128]` → 6/128
  - 唯一自洽解：`payload[j] = physical[4A + j]`（地址 ×4、拍长仍 32 B）。
- 全窗重建 `build/read_pcm_destride.py`（cmd 步长 64；`payload[0:32]`=页 2k、`payload[128:160]`=页 2k+1）：
  132,096 样本、`holes=0`、**页边界平均跳变 3.63 < 页内平均差分 4.47** ⇒ 页序正确无错位
  （错位会在页边界出现巨跳）。产物 `build/diag/tone200_destride/win0062/pcm.raw`。
- 与旧证据不矛盾：旧 gap 扫描（cmd `0x40800`）在 ×4 下实际读物理 `0x102000`，已越过最后一页
  `0x101FA0` ⇒ 那里本就不该有音频，旧「gap 无音频」恰好**验证**了 ×4 而非否证它。

**对旧结论的处置**
- 「2026-11-10（续 2）」第 3 条、以及 CHANGELOG 同日的「静默丢页 / 单拍写不被 DDR3 IP 可靠提交」
  **作废**，不要再据此改 RTL。`page_cnt=8255`、`done_cnt=16512` 与「零丢失」一致。
- 因此「恒 top1」不是 PCM/DDR 地址问题。

**适用范围（重要）**
- ×4 只影响 **diag 读回通路**（`L`/`R`+addr4B+len2B）。音频**输入链**走的是另一条
  `C` → `R`+seq2B 的**流式抓取**通路（`scripts/i2s_capture.py`），不经 DDR 读回，**不受影响**。
- 真实 I2S 数据早已归档：`data/i2s_capture/montage_music_20261106/{capture.wav,pcm.raw}`
  （768000 B = 8 s @48k，git 跟踪）、`data/i2s_capture/test_tone_full.wav`；另有 10 组
  `build/i2s_capture/*` 留档（`data_line_ok`/`fullcheck`/`realtek_tone`/`realtek_vol`/
  `route_verify`/`tone_1k`/`tone2`/`tone6k_check`/`montage_lead1`/`montage_music`）。
  ⇒ **音频输入链是通的**，这是既定事实，不要再用"链路待查"解释安静数据。
- 本轮测试里重建 PCM 仍是噪声底（`std=4.9`、±55），原因只是那一次播放没有真正送到 ADC
  （`resolve_play_device()` 返回 dev 4，未确认实际路由），**不是链路问题**；要信号直接用上面归档的 fixture。
- 推理链已在仿真对拍通过，不是桩：`reports/golden_ref/{silence_3s,sine_440_full,sine_440_twolevel}/`
  有 conv1..conv4 / pool1..4 / gap / feat / fc1 / fc2_logits / probs 全套 stage 输出，
  `scripts/outputs/golden/sine_440_full_{ref_librosa,ref_torch_logits,ref_torch_probs}.npy` 是三方交叉参照。
  `instrec_top` 里 `mel_feat_rd_addr` 由 `npu_feat_rd_addr` 驱动、`mel_npu_start` 触发 NPU、
  `npu_probs_*`/`npu_top1_u` 直连 `ui_renderer` —— **NPU 是接上的，不是「start/feat 暂置 0」**
  （AGENTS.md 那句是 2026-10-28 的旧描述，已过时）。

**下一步**
1. 固化 ×4 契约：**所有经 diag 读回的板级数据**（PCM/feat/logits）读之前必须按 `physical = 4×cmd`
   换算，否则 `diag_compare.py` 过去的板级对拍结果都是混叠数据、不可信。
2. 用 `data/i2s_capture/montage_music_20261106/pcm.raw` 作为标准输入，跑 `golden_pipeline.py`
   得参考 feat/logits，再与板上 diag 读回（修正 ×4 后）逐级对拍，定位第一个偏差环节。
3. 可选根治：`ddr3_ctrl_axi` 输出 `axi_awaddr/axi_araddr` 前统一 `>>2`，恢复文档的字节语义
   （一次改动、需重建 + 全回归验证）。

## 2026-11-10（续 2）：长读稳定闭环；PCM 窗口 60~75% 页从未被写；烧录位流时序违规

**结论先行（三条互不合并）**
1. **长读随机停帧已解决**：重写读回协议后连续 3 次完整读回同一锁定窗口 264192 B，`holes=0`、三次 sha256 全同、`RESULT: STABLE`。原来的停帧是**传输层**问题（周期遥测插帧 + 主机流水线 + `S_ACK` 期间吞字节），不是 DDR3 读超时。
2. **启动自检 `@0x00300200` 失败已恢复**：本轮位流 `st_fail=0`，此前定位的 m3 `rd_ready` 门控修复（`st_m3_sel` → `!st_done`）在板上生效，全窗读回内容与自检区写入模式一致。两项结论分别有独立证据，不互相替代。
3. **新的硬缺陷（本轮最重要）**：PCM 窗口内**只有约 1/4~2/5 的 32 B 页被真正写过**，其余页是 DDR 上电残留。写路径 RTL 认为成功（`err_cnt` 仅 0~1），因此是**静默丢页**。

**证据（已核实，可复现）**
- `build/diag/tone200b/win0205/pcm.raw`（及 `silence/win0017`、`tone200/win0019`）：页 = 32 B = 16×int16。**每 4 页只有 1 页含真实音频**（页号 0,4,8,12,16,20…），其余 3 页固定为 `[-1,-1,-1,-1,0,0,0,0] ×2`。
- 这 3 类页在 win17 / win19 / win205 之间**逐字节相同**（**4964/8256 页完全等于 page1**），且与从未写过的 stride gap 内容一致 ⇒ 是上电残留，即这些页从未被写。
- `build/check_gap.py`：读 stride gap（0x40800、0x82800，软件永不写入）得到**同一残留模式**；而自检区 0x300000 的 `0x5A5A` 模式读回正确 ⇒ **读路径可用，问题在写**。
- 真实页内容只是 ±3~±7 的 ADC 抖动噪声，**没有 200 Hz 音**；三个采集 `std` 都是 933.8（差异 <0.01%），播放 `build/tone_200.wav` 与静音窗 logits 完全相同 ⇒ **模拟输入当前无信号**（播放侧路由/线缆/patch 待查，与丢页是两个独立问题）。
- 残留页偶发单比特异常（-4097 / 64 / -33 / -17），位置固定，属上电残留位，不是新写的数据。
- **全窗口定量扫描**（`build/win_scan.py`，锁窗 327，读满 264192 B）：真实页 **3112/8256 = 37.7%**，页号 mod 4 直方图 **[2064, 302, 355, 391]** —— `≡0 (mod 4)` 恰好 2064 = 8256/4，是唯一被完整写入的一类；其余 ~1048 页只是残留页上的**单比特翻转**（部分写入痕迹），剩余 ~5144 页完全未写。
- **写入粒度对比**（关键线索）：就位自检用 **len=15（16 拍 × 32 B = 512 B）** 突发，通过；音频写每命令 **len=0（1 拍 = 32 B）**。gap 区（0x40800，软件永不写入）扫描 15/128 页"异常"全是单比特翻转、无真实音频 ⇒ **写地址没有错位**（排除 4× 页号步长假设），问题在**单拍写不被 DDR3 IP 可靠提交**。

**仿真无法复现（说明缺陷是真实 DDR3 IP 特有的）**
- `audio_chain_w4k` 在 `+DLY=4/200/1000/4000/20000` 全档 `real=4096/4096`、`err=0`、`ovf=0`。
- `audio_chain_full`（132096 帧 × 2 窗，315.6 s 墙钟）**PASS**，`real=132095/132096`、`real=132096/132096`。
- 行为模型下 done 必到 ⇒ 100% 写成功。板上丢页只可能来自两个候选，**尚未在板上区分**：
  ① `audio_sink` 的 `page_go` 在写 FSM 忙时被静默丢弃（源码注释已警告该失败模式）；
  ② DDR3 控制器 `S_W` 超时 → `to_abort` **发 done 但丢弃该写命令**（源级静默丢写）。
  判定需要计数器类遥测（`page_go` 计数 / 实际写入页数 / `audio_err_cnt` / `cmd_to_err`），**现有遥测不足以区分**，不做结论。

**位流与时序（必须写明的限制）**
- 板上运行的是 `build/pds/20261110-215916-aa6a43cb/generate_bitstream/instrec_top.sbit`（sha `DA3A9098…`）。
- 该构建六阶段全过但**发布被守卫拒绝**：`Build inputs changed during PDS; refusing publication: ...ddr3_ctrl_axi.v`（退出码 1）。已用 manifest 哈希反证差异**仅为注释**（旧注释版 sha `DE7991CD…` 与 manifest 完全一致），**未绕过守卫**，直接用该 sbit 烧录。
- `report_timing/instrec_top.rtr`：**`Some Constraints Violated`，WNS −1.402 ns**，另有多条 hold 违规（−0.015 / −0.020 / −0.040）。最差路径 `u_npu/u_store1/state[0] → u_npu/u_store1/lane_bank[6].mem`（DRM，12 级逻辑），**与音频写路径无关**；但因此**本夜 NPU 数值结果不得作为结论依据**。
- **带计数器的新位流已产出并发布**：`build/pds/20261111-003237-53a02f27`（`SourcesUnchanged=true`，守卫未拒绝），SHA-256 `69041235…`，已复制为 `build/instrec-latest.sbit`。**WNS −0.872 ns（setup）、WHS +0.116 ns（hold 已无违规）**；LUT 34084/66600 (51%)、DRM 130/155 (84%)。最差路径变为 `u_audio_sink/col_min_mem → u_ui_renderer/graph_s3`（clk→pix_clk 跨域，−0.381 ns），属显示路径，**不再是 NPU store**。
- **烧录阻塞**：`VID_0403` 在 PnP 中计数为 0（连续 30 s 轮询仍为 0），仅 COM5 在线；`cdt_js` 仍在运行但已无设备可握。按纪律不强关、不新起，需物理重插下载器后才能烧 `instrec-latest.sbit`。

**其他已核实事实**
- `addr[15:8] == 0xAA` 的读命令必失败（另一消费者吃掉 0xAA 字节）；`frame_read_wide`（从 addr−256 发 512 B、取 seq==1 载荷）可绕开。
- CPU 固件每窗重写 `NPU_CTRL=0x1`：45 s UART 抓到 `NPU top1=3 last_class=7 last_p=0 c=32362119` 每窗重复 ⇒ **NPU 确实每窗重跑**，"logits 冻结"是**输入恒定**的结果，已被证伪。
- 已 `git restore` 掉 `cpu/fpga/rv32_ddr3_ip_wrapper.sv`、`cpu/rtl/rv32_burst_ddr3.sv` 两个把 AXI 端口方向 / `ddrphy_cpd_lock` 回退成旧 bug 的改动（`git status -- cpu/` 已清空）。

**下一步（按序）**
1. **计数器遥测已实现并提交（`ac953c32`），位流构建中**：`audio_sink` 新增 18 位 `page_cnt_lat` / `done_cnt_lat`（win_tick 锁存），`sys_ctrl` 的 STS 轮转 phase 2 / phase 3 分别输出（满窗应为 `8256` 与 `16512`）。判据：`page_cnt<8256` ⇒ 聚合器从未请求这些页（前端丢帧）；两者都满 ⇒ 命令"完成"但数据未落地（DDR3 IP 单拍写问题），随后改为 4 拍（128 B）突发写入。
2. 同时排查音频模拟输入无信号（播放设备路由、线缆、PCM1808 VINL/VINR）。
3. 位流交付前必须先读 `report_timing/*.rtr` 的 WNS；当前 −1.402 且 hold 违规的位流不可用于数值结论。
4. 待 `FEAT_DUMP_ON_M3=1` 位流后再做 feat 对拍；PCM/logits 的 48k golden 对拍在输入无信号前无意义。

## 2026-11-10（续）：DDR3 自检 `@0x00300200` 根因锁定并修复（离线仿真证据闭环）

- **结论先行**：`0x00300200` 是**数据比较失败**（第 2 条读命令的首拍对不上），**不是写超时、也不是读超时**。证据：`to_err=0`、`cmd_to_err=0`、`dbg_to_state=0`（无任何 AXI 超时），`st_fail=1`、`st_fail_addr=0x300200`。
- **根因（instrec_top.v 的 m3 共享接口）**：`rd_ready[3]` 被 `st_m3_sel(=st_cmd_valid)` 门控。自检读阶段 `done` 在 RLAST 触发，但控制器 fifo 的最后一拍要**晚一拍**才可弹出；此刻 `st_cmd_valid` 已撤，`rd_ready[3]` 跌到 `dg_m3_rd_ready(=0)`，fifo 末拍卡住，随后被当作**下一条读命令的首拍**喂给自检 ⇒ 第 2 条读（0x300200）首拍失配。`cmd_valid` 在 drain-tail 撤是正确的（此时本就不该发新命令），错的是把 `rd_ready` 也一并撤了。
- **修复（1 行）**：`instrec_top.v` 的 `rd_ready` 门控由 `st_m3_sel` 改为 `!st_done`（自检在完成前始终占有 m3 读口）：
  `.rd_ready ({(!st_done) ? st_rd_ready : dg_m3_rd_ready, ...})`。
- **可观测性修复（sys_ctrl.v）**：`ddr_sts_code` 恢复为 AXI 诊断字节 `{cmd_to_err[3:0], to_err, dbg_to_state[2:0]}`（bit2..0 是超时 FSM state：S_AW/S_W/S_DW_*=写相，S_AR/S_R=读相），且 boot 期 `DDR3 STS` 行改打它（此前打的是 `audio_sts_payload`，boot 时全 0，才误判成「板上超时归零」）。数据比较失败时该字节全 0，与「超时」非 0 明确区分。
- **新仿真证据**：`sim/tb_ddr3_m3_share.sv`（复刻 instrec_top 精确 m3 mux：self_test + diag_readback + feat_dump 同挂 m3）跑两档：S0（旧 `st_cmd_valid` 门控）**精确复现** `fail_addr=0x300200, to_err=0`；S1（`!st_done` 门控）**自检全过**。注册为 `run_sim.py` 的 `ddr3_m3_share` 用例。
- **回归**：check_rtl 0 violation；`ctrl_smoke` PASS；`ddr3_m3_share` PASS；pytest 444 passed（唯一失败是锁死旧 STS 字节顺序的契约测试，已同步更新为 `{cmd_to_err,to_err,dbg_to_state}`）。
- **下一步**：FTDI 恢复后构建诊断位流（`FEAT_DUMP_ON_M3=0` + 本修复），一次烧录后走 diag `L/U/S/R` 多组读回同窗 PCM / 特征 / 完整 logits，逐段与 golden 对拍，再决定是否修推理。**注意**：本修复只消除自检失败，不改变 top1 恒定问题（那仍是 mel/m2 读路径待定位）。


## 2026-11-10：mel 状态可观测（零计数器方案布通）；疑点锁定 win_miss 粘滞

- 三次有界构建（含 mel 计数器遥测）均停在 4–6 根未布网络（DRM 95% 局部拥塞），遥测小改动足以触发布局临界。改为**零计数器方案**：`STS` 态 1 = `{agg_freeze[31:3], mel_timeout, mel_win_miss, mel_busy}`（只新增 3 根线），**第 4 次构建 1 h 2 m 布通**（Wns −1.230，LUT 33439/50%，DRM 146/155），位流归档 `releases/instrec-48k-melstat-20261110/`（sha `f7552f2a…`）。
- **代码级定位**：`mel_engine.win_miss` 定义为 **sticky「win_tick during non-IDLE」**（`mel_engine.v:250`）。一旦 mel 卡在 `ST_RUN`（`busy = state != ST_IDLE`，`:294`），此后**每个窗口都记 miss 且 feat 永不更新**，NPU 会一直推理同一份旧特征 —— 与板级「200 Hz 与 6 kHz 的 top1/last_p 逐位相同」完全吻合。mel 正常耗时仅 ~5.09 M 拍（40 ms）远小于 2.752 s 窗口，故卡死不是速度问题，而是 **m2 读路径（DDR3 仲裁/超时）或 win_tick 交接**。
- 已排除：播放设备/音量、I2S 引脚与 CDC、零帧注入门槛、模拟输入（i2s_capture std 20,481）、窗步长（0x84000→0x42000 后 top1 仍恒定）、`fc_*`/NPU 数值（sine440 全层 0 LSB）。
- 板级阻塞：构建完成后 FTDI 再次从 PnP 消失（`FTDI ABSENT`，jtagserver 无）。按纪律不请求拔插，位流与判据已就绪：下载器恢复后烧 `instrec_48k_melstat.sbit`，读态 1 低 3 位——`busy=1` 或 `win_miss=1` 即确证 mel 卡死；随后查 m2 主口（与 m0 并发时的读完成/超时）。
- 回归：pytest 438 passed + 26 skipped、lint 77/0。

## 2026-11-09（续）：全窗口仿真验收 100%；有界 PNR 58 分钟成功出位流；FTDI 链路错误待恢复

- **全窗口验收仿真**（`audio_chain_full`，WIN_FRAMES 132096 × 2 窗，5.5 s 仿真 / 350 s 墙钟）：`WIN1 real=132095 inj=1`、`WIN2 real=132096 inj=0` ⇒ **100% 真实帧、err=0、ovf=0**；`freeze_cyc=107328`（344 M 拍中的 0.03%，即 41 帧周期的总冻结，分散在 8256 页 ≈ 每页 13 拍）。
- **有界 PNR（按用户第 5 条）**：对应提交 `2d6fd26f`（注入修复 + 冻结遥测），上限 90 分钟，**58 分 15 秒完成全部六阶段**；未使用任何 PnR 参数（`-fast_router` 非法 Flow-0075、`-gplace_seed` 被 `test_build_tokens` 禁止，PnR 行保持裸 `pnr`）。逐域时序：`ddrphy_sysclk −0.658 ns（115.5 MHz）`、`pix_clk −0.384`、`rst_clk +2.643`、`clk +32.79` —— **Wns −0.658 为 48k 版本历次最佳**；LUT 33427/50%、DRM 146/155。
- 位流归档 `releases/instrec-48k-injfix-20261109/`（SHA256 `2726f0cd…`）。
- **板级阻塞（再次）**：烧录前 FTDI 从 PnP 消失，设备管理器显示 `USB Serial Converter A/B` 为 `Unknown`，USB 控制器有两个 `Error`（「设备描述符请求失败」「端口重置失败」），仅 COM5（CP2102）在线。`pnputil /scan-devices` 需管理员被拒 ⇒ 软件不可恢复；按纪律不请求拔插，位流与一键验收脚本已就绪。
- 一键上板验收（下载器恢复后）：`python scripts/board_48k_run.py --sbit releases/instrec-48k-injfix-20261109/instrec_48k_injfix.sbit`。判据：①偶数窗 STS 的 `frames` 接近 132096（0x20400）、`err`/`overflow_hi` 为 0；②奇数窗 STS 的 freeze 周期在数千量级；③NPU `top1` 随音乐变化。

## 2026-11-09：19% 真实帧根因锁定并修复——零注入门槛只看 FIFO 空；整机仿真 100%

- **新增整机音频链仿真** `sim/tb_audio_chain.sv`（物理 PCM1808 I2S → `i2s_slave_rx` → `audio_cdc_fifo` → `audio_sink` → 行为 DDR 响应器，`+DLY` 可调 done 延迟），并给小窗口变体 `audio_chain_w4k`（WIN_FRAMES 4096 / 256 页，便于扫参）。`run_sim.Case` 新增 `sim_plusargs` 字段。
- **定位过程（可复现证据）**：2 ms 诊断 `pcm_valid=95 / fifo_rd_valid=95 / ovf=0 / err=0` ⇒ 写侧与 CDC 完全正常（48 kHz）；小窗口基线 `real=2816/4096=69%`、`freeze=3328`（0.03%）⇒ **不是 agg_freeze 卡死，也不是 FIFO 溢出**。
- **根因**：`audio_sink` 的零注入门槛只有 `fifo_empty`。读侧 125 MHz 远快于写侧 48 kHz，**帧间 FIFO 天然为空**，于是几乎每个帧间隙都被判「无音频」而补一个零帧；真实帧到达后叠加，窗口被注入填满。板级 19%、仿真 69% 都是该机制的表现（比例随 FIFO 空窗占比变化）。
- **修复**：注入条件加 `sd_idle_sync` 门槛（仅 PCM1808 watchdog 判定源停止时才注入零帧）。验证：`WIN1 real=4095 inj=1`、`WIN2 real=4096 inj=0` ⇒ **100% 真实帧**。
- 回归：pytest 438 passed + 26 skipped；`mel_credit` / `audio_fifo` / `audio_chain` / `audio_chain_w4k` 全 PASS；lint 77/0。
- 待办：① 按用户要求把「每窗冻结累计周期」编入遥测（当前 STS 为 `{err[6:0], overflow_hi[7:0], frames[16:0]}`，拟按 `win_id[0]` 交替输出 freeze 行）；② 有界 PNR（90 min 上限）出位流后上板验收 `real≈132096`、注入≈0、top1 随输入变化；③ 通过后做同窗 golden 对拍与已知类别音乐识别。

## 2026-11-08：数据链定位到消费侧——overflow 低字节为 256 饱和巧合；加两处 audio_sink 修复；PNR 收敛阻塞

- **板级新证据**：烧录 `releases/instrec-48k-gapfix-20261108/`（sha `40b93d58…`，无 PLL LOCK ERR），播放中周期 STS 读回 `0062C006→0062C008`：真实帧 **25,280/132,096 = 19%**、`win_id` 递增、overflow 低 8 位 = 0。
- **判读纠正**：`overflow_cnt` 的**低 8 位为 0 不能证明无溢出**——若写侧 48 kHz、消费侧 ~9.2 kHz，2.75 s 内约 128k 次溢出，低 8 位恰好回到 0。因此「FIFO 未满」的结论不成立。
- **写侧已排除**：`i2s_capture` 顶层用同一 `i2s_slave_rx`（27 MHz、TIMEOUT 27000）在 4 s 内采到 192,000 帧（48 kHz），证明接收端能产满帧率；`i2s_lrck` 接 `1'b0` 使 `wr_req=pcm_valid`。⇒ 瓶颈在 `audio_sink` 消费侧（`agg_freeze` 长期冻结）。
- **修复①（已提交 `a00be5e7`）**：左右页命令之间插入 `ST_GAP` 一拍（`cmd_valid` 先撤再发），消除「新地址/数据配到退役突发」的风险。板级帧计数**未改善**（仍 25,280）⇒ 不是主因，但属正确的时序加固。
- **修复②（本轮，待上板）**：`agg_freeze_r` 增加 **fail-safe 释放**——右页写超时（`WR_TIMEOUT_CYCLES` ≈ 33 ms）强制解除冻结。页周期仅 333 µs，该上限最多损失 <1% 帧，却能把「写命令卡死 ⇒ 整窗冻结」的损害封顶。
- **遥测（本轮，待上板）**：`DDR3 STS` 重排为 `{audio_err_cnt[7:0], overflow_cnt[15:8], win_frames[15:0]}`——`err_cnt>0` 即写命令卡住（冻结根因确证），溢出高字节判定 FIFO 满丢帧。契约测试已同步，全量 438 passed + 26 skipped。
- **构建阻塞**：48 kHz 顶层默认种子 PNR 在 iteration 394 停（1318 未布，3 h 未收敛）；`-fast_router` 报 Flow-0075（该 PDS 不支持），`-gplace_seed 1` 被 `test_build_tokens` 契约测试**禁止**（PnR 行必须裸 `pnr`）⇒ 不能靠 PnR 参数换布局。seed1 手工实验曾达 85 未布（iteration 616），说明布局质量差异明显但受契约限制。
- 当前板上：`instrec_48k_gapfix`（可用）。**板级识别结果仍不可用**，不宣称 48k 准确率；下一步需在裸 `pnr` 前提下延长构建窗口或做 RTL 拥塞优化，出带 err_cnt 遥测的位流后即可闭环「写卡死 vs 溢出」。

## 2026-11-07（第十二批）：2~5 LSB 根因修复归零；数据链证明音频仅 19% 进窗；FTDI 掉线待恢复

- **2~5 LSB 差异已查清并修复（逐层归零）**：根因是 `npu_top.v` 的两处旧 44.1k 硬编码——`conv_zp_in` 固定 `8'd49`、`fc2` 的 `ZP_OUT(8'd57)`。已参数化为 `ZP_IN_CONV1=47` / `ZP_OUT_FC2=58`（新契约值）；同时把 `npu_probe` 的 RTL 集从 `npu_full_end/*_candidate.v`（未参数化的早期副本）切到**生产 `src/npu/`**。验证：`sine440` **conv1..conv4/pool/gap/fc1/fc2/probs/logits 全部 0 LSB**（此前 conv1 3、conv4 13、logits 5）；`zeros49` 仅 `probs_q16` 差 274（8 个元素，softmax 定点近似，top1 一致，记为待查）。
- **数据链首次给出「真实帧进窗」的定量证据**：新 STS 遥测（`DDR3 STS <8 hex>`：bit31..24 溢出字节 / bit23..8 窗口真实帧数 / 7..0 win_id）读出 **`0262C007`→`0262C008`**：窗口真实帧 **25,280 / 132,096 = 19%**、`win_id` 递增、`sd_idle=0`。即**音频确实进入窗口，但 81% 由 `audio_sink` 空闲零注入填充**——这解释了 top1 恒定（静音主导特征）。
- **播放侧已核实（用户第 1 步）**：`resolve_play_device` 按名称解析（实时命中 Realtek，索引曾从 4→0→4 漂移，硬编码必失效）；端点音量 100%；素材必须立体声（44.1k 单声道在 Realtek 端点静默）。
- 遥测设计：`sys_ctrl` 在 `ST_RUN` 每 ~0.8 s 重发一次 STS（`sts_period_cnt`），播放中可读；`uart_debug` 的 STS 行已扩为 8 位 hex（此前两次「改了没生效」的根因是替换未命中 + 未核对源）。
- 位流 `releases/instrec-48k-diag2-20261107/`（SHA256 `de508328…`，LUT 33428/50%、DRM 146/155，Wns −2.523）。
- **阻塞**：烧录前 FTDI 下载器从 PnP 消失（`FTDI ABSENT`，COM5 正常，`pnputil /scan-devices` 需管理员被拒）。按纪律不请求拔插；板级验证待下载器恢复后用该位流读 `overflow` 字节，即可判定 19% 是「写侧 LRCK 漏检」还是「FIFO 溢出（消费被 m0/m2 竞争拖慢）」。
- 回归：check_rtl 77/0、pytest 438 passed + 26 skipped、`npu_chain` PASS。

## 2026-11-07（续）：诊断位流——`DDR3 STS` 打包音频遥测；板级识别仍待定位

- `sys_ctrl` 的 `ddr_sts_code` 低 3 位由超时 FSM state 改为音频遥测（bit2=sd_idle / bit1=fifo_empty / bit0=fifo_full），契约测试同步；全量回归 438 passed + 26 skipped、lint 77/0。
- 诊断位流（`build/pds/20261107-130050-741c06ed`）板级读回 **`DDR3 STS 02`**：**sd_idle=0（PCM1808 BCK/LRCK 正常）**、fifo_empty=1、fifo_full=0。
- 判读注意：FIFO 深度 16、读侧 125 MHz 远快于写侧 48 kHz，瞬时 `fifo_empty=1` **不足以**证明无真实帧；而 NPU 每窗（2.75 s）完成一次、35 s 内 15 轮，说明 **win_tick 在推进**。因此 top1 恒定（音乐与 1 kHz 满幅测试音完全一致）的剩余解释是**窗口内容恒定（模拟输入静音）**，而非窗口冻结。
- 下一轮定位路径（按成本排序）：① 播放时用 `waveOutGetVolume(4)` 复核 Realtek 端点音量（避免音量被系统重置）；② 把 `win_id`/`overflow_cnt` 打包进 STS 高字节并在**播放中**多次打印（当前 STS 行仅启动后一次）；③ 若确认模拟输入静音，检查 PCM1808 VINL/VINR 与 Realtek 线路输出接线。
- 已完成并入库：48k 契约/镜像、QuantStub 注入、位流、板级 BOOT/DDROK/WOK/推理运行（详见上一节）。

## 2026-11-07：48k 量化模型接入——契约/镜像/位流/板级链路完成；板级 top1 恒定待定位

- 模型侧交付（只读核对，`InstRec/deploy/medley_48k/`）：fp32 test **77.69%** / INT8 **77.32%**（macro-F1 掉 0.95pt，≤2pt 门槛）、`quant_stub.json` s_in=0.0709686279296875/**zp_in=47**、48k 前端参数（sr 48000/fmax 24000/258 帧）、类表对齐、模型 728.56 KB。
- 板级资产生成（本仓）：`gen_weight_image.py --deploy-subdir deploy/medley_48k` → `scripts/outputs/medley_48k/{weights_image.bin(691040 B), layer_contract.json}`；conv1 **zp_in=47**、fc2 zp_out=58、shift 37..53。`golden_pipeline` 新增 `INSTREC_CONTRACT` / `INSTREC_WEIGHTS_IMAGE` 环境变量覆盖，契约与镜像成对切换（旧 44.1k 基线不动）。
- RTL：`instrec_top` 的 mel_engine 注入 **INV_S_IN=236403274 / ZP_IN=47**（bitstream 级参数）；`tb_mel_engine_48k` 同步。仿真：**mel_48k PASS**（48k 表 + 新 QuantStub 逐字节一致）、pytest 438+26skip、lint 77/0。`npu_probe` 用新镜像全链跑通（**RTL 与 golden logits 差 2~5 LSB、top1 一致**，为待查项）。
- 构建：full 58m36s、All Stages OK、LUT 33229(50%)、DRM 146/155、APM 90；时序 **pix_clk +0.059（收敛）**、ddrphy_sysclk −0.915（112.17 MHz）、rst +4.848、clk +32.57。位流归档 `releases/instrec-48k-model-20261107/`（SHA256 `d3ad62dd…`，含 48k 契约与 691040 B 镜像）。
- 板级：烧录 `done=1 CRC0`、`BOOT/MMIO/ISA/BENCH/DDROK`、权重 2700 帧 **`WOK CFE5A709`**、NPU 完成 15+ 轮（32.36M cycles 量级）。**但 `top1=3 / last_p=33` 在音乐与 1 kHz 满幅测试音下完全不变** ⇒ mel 窗口内容恒定。同轮用 `i2s_capture` 位流复核音频链路：48k 立体声测试音采集 **std 9349 / 1 kHz 主峰**（硬件链路正常），44.1k **单声道** montage 播放时采集仅噪声（Realtek 单声道路径问题，已改用立体声素材）。
- 待定位（下一轮）：full 位流下音频帧是否真正进入 `audio_cdc_fifo`/`audio_sink`（怀疑 sd_idle 或 agg_freeze 导致窗口内容不更新）；需要在 UART 增加 audio 诊断行（sd_idle / fifo_empty / overflow / win_id）后重建一次。**当前板级识别结果不可用**，不得宣称 48k 准确率。
- 提交：契约/镜像/参数/工具/位流/证据全部入库。

## 2026-11-06（第十一批）：取消重采样完成——48k 原生前端位流已上板跑通（链路级）

- 按用户分工（量化由模型侧负责）只做板子侧重构：`instrec_top` **删除 147/160 `pcm1808_resampler`**，`i2s_slave_rx` 立体声对直连 `audio_cdc_fifo`（`sd_idle = capture_idle`）；`mel_engine` 改用 48k Mel 表 `mel_coo_48k.hex`（`COO_ROM_WORDS=2027`）；`audio_sink` 空 FIFO 注入节奏 2834→**2604** 拍（48k）。窗口几何不变（259×512=132096 样本=2.752 s@48k）。
- 仿真：mel / mel_credit / **mel_48k**（48k 表 16512 字节 0 失配）/ full_top_ctrl PASS；pytest 438 passed + 26 skipped；check_rtl 77 .v / 0 violation。
- **资源门控**：LUT 33618(50%)、**DRM 150.5→146**（删重采样省 4.5 块，符合预期）、APM 90；48k COO 表被 PDS 正确 `$readmemh`。
- **full 位流**：1h31m40s 六阶段完成、SourcesUnchanged、LUT 33242(50%)、DRM 146/155、APM 90；时序 `ddrphy_sysclk −1.245 ns`（108.17 MHz）、`pix_clk −0.014 ns`、rst_clk +3.805、clk +33.03 —— 与历史可上板量级一致（用户口径「能跑就行」）。位流归档 `releases/instrec-48k-20261106/` SHA256 `9731519e…94b18`。
- **板级**：烧录 `done=1 crc_err=0`；UART 依次 `RV32 BOOT / MMIO OK / ISA OK / BENCH cycles=460012 inst=180008 / DDR WAIT STS 0 / NPU GO / DDR3 SELFTEST… / DDROK / DDR3 STS 00`；权重 2700 帧上传 **`WOK FA0D5236` / `UPLOAD OK`**；随后 **13 轮 NPU 完成**，每轮 32.358–32.362 M cycles（与历史一致）。
- **边界与待办**：①分类值**不可用**——板上仍是 44.1k 旧量化权重与旧 QuantStub 参数（`INV_S_IN=267723430`/`ZP_IN=49`），与新 48k 前端不匹配，本轮只证链路；②`DDR3 STS 00`：self_test 在观测窗内既未 done 也未 fail（`DDROK` 来自 `ddr_init_done`，不受影响），记为待查；③新量化权重与 QuantStub 两参数到位后需**重建位流**（参数是 bitstream 级），权重本身运行时上传、结构不变无需重建。
- 证据：`reports/48k_frontend_board_20261106.json`（位流 SHA/时序/资源/板级行/已知问题）。

## 2026-11-06（第十批）：真实 I2S 采集全链路打通并落库（DATA 线 + 播放设备双重根因）

- DATA 线接好后采集仍近静音，两个根因依次定位：①**Windows 默认播放设备是 `耳机 (NICEHCK HiFi Audio)`（Sound Mapper Playback）**，`winsound` 播放未到 Realtek；②**Realtek 声道音量过低/静音**（用 `waveOutSetVolume(4, 0xFFFFFFFF)` 置满）。改用 `waveOutOpen` 指定设备 4（`扬声器 (Realtek High Definition Audio)`）播放后信号恢复。
- 判定实验：满幅 1 kHz 测试音 → 采集 **主峰 999.8 Hz、SNR 115.9 dB、std 9401** ⇒ I2S 接收链路完全正常（此前 ±50 的 22.9 kHz 底噪是「音乐未到 PCM」的假象）。
- **真实音乐采集**（montage 20–32 s 段，Realtek 满音量）：4 秒 48 kHz 立体声，`std L 1123 / R 1115、max 8008、L/R 相关 1.0000、无削波、重复率 0.3%/0.5%（无 2:1 抽帧）、CRC 0 错、verdict PASS`。走 golden 链（FIR 48k→44.1k 192000→176400 帧 + 44.1k Mel 表）：**feat 64×258、mean 48.9996（=zp_in）、std 15.93、饱和率 0.0** —— 完全符合 shift-36 修复后的预期语义。
- 数据落库 `data/i2s_capture/montage_music_20261106/`（capture.wav / pcm.raw / manifest / check.json）+ 测试音与 `play_to_dev.py` 工具；板级判据链由此具备「真实 I2S → golden 特征」起点。
- 已知细节：采集 L/R 存在约 1 个样本的相位差（`L==R` 率仅 0.11 而相关 1.0000），对 downmix 相当于轻微一阶平均，记录为待评估项；`i2s_slave_rx` 的 2:1 抽帧在本轮板级数据中**未复现**（重复率 <1%），仿真 TB 相位问题属合成源特有。
- 环境提示（后续会话必查）：本机默认播放设备随时可能被切回 NICEHCK；播放必须用 `build/play_to_dev.py <wav> 4 <秒>` 指定 Realtek 并置满音量，否则采集只有底噪。

## 2026-11-06（第九批）：license 打通 → i2s_capture 位流 All Constraints Met → 上板采集；定位到 I2S DATA 线未通

- **license 打通**：客服给的 `pds_windows_c03532573d51_2029-09-04.lic` 属外机；用户按建议用 TAP-Windows 虚拟网卡把 `NetworkAddress=C03532573D51`（PDS 遍历含虚拟适配器的全部网卡 MAC），license checkout 成功。`ip.lic`（FlexLM）不需要；综合用 `synthesize -ads`（Pango 自研），不需要 Synplify Pro/OEM license。
- **构建**：首轮 compile 暴露两处 PDS 严格性错误并修复——`tx_src/tx_len/tx_single/tx_go` 被 TX 引擎块与主 FSM 双驱动（Verilog-4086；统一归主 FSM，S_TXWAIT 单拍自清）；首轮位流 **Wns −8.534**（`rd_fifo→crc_val` 的 32 级并行 CRC 组合链 + 约束加载顺序使 `ddr3_100h.fdc` 异步组因 `clk` 尚未创建被整条忽略）。修复：CRC 改 **串行 1 字节/拍（S_CRC 状态，256 拍）**、约束顺序改为 `top_i2s_capture.fdc`（建 clk）在前 `ddr3_100h.fdc` 在后、删除引用不存在时钟的 `clock_groups_async.fdc`。二次构建 **9 分 25 秒全阶段 OK、All Constraints Met**（ddrphy_sysclk 实际 165.07 MHz，slack +1.942；clk +34.05；rst_clk +5.10），LUT 6462/66600、DRM 0（本顶层无 NPU/Mel RAM）、APM 0。位流 `releases/i2s-capture-20261106/top_i2s_capture.sbit` SHA256 `ef8a187e…42184a`。
- **上板**：安全复用既有 cdt_js 烧录，`program=True done=1 crc_err=0`，UART 收到 `I2SCAP BOOT` + `I2SCAP DDR OK`（DDR3 初始化通过）。
- **真实 I2S 采集结果**：播放 `eight_class_montage.wav`（Realtek 声卡输出接 PCM1808）后采集 4 秒：`CAPSTS state=done words=0x30000 frames=0x0C00 i2s_err=0`；PC 侧导出 **3000 帧 / 768,000 字节 / CRC 0 错 / verdict PASS**（`build/i2s_capture/montage_lead1_20261106_173637/`）。**但数值为 `0xFFFF` 占 99.996%（16 个 0x0000）**：BCK/LRCK 正常（帧计数与 i2s_err 证明两条时钟线通），**I2S DATA 数字线恒高（悬空上拉特征）** ⇒ 当前 J2 的 DATA/V16 线未连接或虚接（引脚约束与曾验证过的 top_pcm1808_probe 完全一致 U20/T20/V16，排除约束错误）。
- 结论：**采集链路（I2S 接收→CDC→DDR3→UART 帧导出→PC 重组）已全程打通并经板级证明**；唯一缺口是模拟/数字音频输入线。DATA 线接通后一条命令即可重采：`python scripts/i2s_capture.py --play-wav <音乐> --lead 1.0`（脚本已加 `--skip-boot`/`--no-capture` 适配板子已在运行/仅导出）。
- 仍未解决（独立问题）：`i2s_slave_rx` 在 27MHz 异步过采样下 LRCK 漏检导致 2:1 抽帧（仿真可见、板级未验证）；本轮采集数据因 DATA 恒高无法判定该缺陷是否在板上复现。

## 2026-11-04（第八批）：license 三文件全部不可用，构建仍阻塞（结论已闭环）

- 用户提供 `D: 0I\Pango\Lisence\pds_windows_c03532573d51_2029-09-04.lic` 后逐项验证（证据 `reports/pds_license_diagnosis_20261104.json`）：
  - 旧 `E:\License\pango
ew_pds_F4A80DA47D72.lic`：Pango package/feature 格式、本机 host，**已过期（2026-11-03）**。
  - 新 `pds_windows_c03532573d51_2029-09-04.lic`：格式正确、有效期 2029-09-04，但 **host_id c03532573d51 属另一台机器**；PDS 原文「specified hostid … mismatchs, system MAC address is 04:D4:C4:16:46:34 …」，本机不可用。
  - 同目录 `ip.lic`：FlexLM `INCREMENT` 格式，PDS 解析器报「keywords "INCREMENT" is not supported」，仅供 Synplify，不能替代 PDS license。
- 本机可用 host_id 由历史构建证明为 **F4A80DA47D72**（旧 license 曾长期使用）。所需：**Pango package/feature 格式、host_id=F4A80DA47D72、含 fabric_shell（及 ads/compiler/configuration 等）** 的 license。
- 环境变量已指向新 license 路径（用户级），换成本机签名版同路径覆盖即生效；`i2s_capture` 构建集五处登记与全部 RTL/TB 已就绪，license 到位后一条命令即可构建→烧录→播放采集。
- 回归未变：check_rtl 77 .v/0、pytest 438 passed + 26 skipped；本轮零新位流、零烧录。

## 2026-11-04（第七批）：I2S 采集再修三处真缺陷；**上板被 license 过期阻塞（2026-11-03 到期）**

- 用户要求「没问题就上板放音乐」。如实结论：**仿真仍有 1 处未收敛 + 上板被 license 阻塞**。
- **本轮新修三处真实缺陷**：①`i2s_capture_ctrl` 的槽位偏移 `beat_wptr[2:0] * 6'd32` 积只有 6 位（7×32=224 截断为 32），槽 2..7 全部回卷覆盖槽 0/1 ⇒ 写回 256 位字只有低 64 位有值（与历史「常量位宽不足」同型，已改 8 位 `bslot_of`，修复后 word0 逐字一致）；②37 位命令捆包仅拼 24 位地址（wr/addr/len 错位）；③wrapper AXI 输入连到悬空裸 wire 而与 ctrl 的 `_a` 族零连线（PDS/Verilator 均静默）。另有 TB 侧两处：BCK 半周期 `#81.38` 实为两倍频、期望数组未记采集起点 `cap_base`。
- **仍未收敛 1 处**：`i2s_slave_rx` 的 L/R 翻转依赖 LRCK 边沿检测，27MHz 异步过采样下漏检一半 ⇒ 采集样本呈 2:1 抽取（0x11,0x13,0x15…）。三版相位改动均引入新错位，已回滚到 HEAD 版本（该版本板级曾验证 PCM1808 非零动态样本）。**板级真实 PCM1808 的 BCK/LRCK 与 TB 合成源不同，实采数据本身可判定是否复现**；PC 侧 `i2s_capture_check.py` 可检测重复对并去重。
- **上板阻塞（硬）**：PDS 报 `Flow-0183 Failed to check license fabric_shell`；许可证 `E:\License\pango\new_pds_F4A80DA47D72.lic` 的 `expire_date {2026-11-03}` **已过期**（今天 11-04），系统无其他 license 文件。⇒ 无法构建新位流；板上现有 0EBF9448（无 NPU 脚本演示）/1497FAF4（含 shift-24 bug）**均不含 I2S 采集导出通路**，不能用于本次采集。license 续期后一键恢复：`powershell -File scripts/run_pds_full.ps1 -BuildSet i2s_capture`（构建集已五处登记：build_sets.json / run_pds_full.ps1 ValidateSet / test_build_tokens SET_NAMES+TOP_MODULES / test_plan_contract_guards SET_NAMES）→ `python scripts/board_check.py --sbit build/instrec-latest.sbit` → `python scripts/i2s_capture.py --play-wav InstRec/data/demo_samples_v2/eight_class_montage.wav --lead 1.0` → `python scripts/i2s_capture_check.py --capture <dir>`。
- 回归：check_rtl 77 .v/0 violation；pytest **438 passed + 26 skipped**；构建集契约 34 passed。零新位流、零烧录。

## 2026-11-04（第六批）：I2S 采集链路开发——数据通路打通，仿真未全通过（上板推迟）

- 用户指令：硬件在线，要求在板上实现 I2S 采集存入工作区（Realtek 声卡播放 → PCM1808），为排除 I2S 输入域偏移提供真实数据。采集点设计在 **FIR 之前**（原始 48k I2S 双声道），攻克「I2S 接收」与「FIR 重采样」分层。
- 已交付：`src/diag/top_i2s_capture.v` + `src/diag/i2s_capture_ctrl.v`（DDR3 写/读 + UART 'C'/'R'/'S' 帧导出，帧格式与 weight_loader 同款 0xAA55+seq+len+CRC16）、`constraints/top_i2s_capture.fdc`、`sim/tb_i2s_capture.sv`（全链行为 DDR3 模型）、PC 侧 `scripts/i2s_capture.py`（采集+播放联动 winsound）/`scripts/i2s_capture_check.py`（健康检查+FIR golden 对接）/17 个离线测试、恢复既有 I2S 接收单测为独立 case `i2s_rx_phy`（A 代理曾覆盖该文件）。
- **本轮修复的四个真实缺陷**：①37 位命令捆包地址字段只拼 24 位（wr/addr/len 整体错位）②wrapper 输入端口全部连到悬空裸 wire、与 ctrl 的 `_a` 信号零连线（PDS/Verilator 均静默，典型「构建通过≠接线正确」）③TB BCK 半周期写成 #81.38（6.144MHz，两倍频）④TB 期望数组从 0 索引未记录采集起点（cap_base）。
- **当前仿真状态（如实）**：采集主链路已从「读回全零」推进到「真实样本经 I2S→CDC→DDR3→UART 回传」（word0/1 与发送值一致、CRC 帧结构正确、S0/S3/S1-CAPDONE/S2/S4 场景 PASS）；**未通过的判据**：frame payload 自 word2 起为零（读回字重复）与「每 2 帧 1 新值」的 pcm_valid 节奏。探针证据：`rd_valid` 为「FIFO 非空期间持续有效」而行为模型每 4 拍推一字，ctrl 每拍消费导致同一 256 位字重复入 exp_buf；`i2s_slave_rx` 的 LRCK 边沿检测在 27MHz 异步过采样下漏检一半（生产板 BCK 亦异步，值得复核）。
- **决定**：不启动构建/上板（带这两处缺陷烧录会浪费唯一板级窗口）；下一步对照已验证的 `mel_engine` m2 读 pacing（FILL_CREDIT/credit 机制）重做导出读节奏，并复核 slave_rx 的 LRCK 边沿余量后，再进「构建→烧录→实采」。
- 回归：check_rtl 77 .v / 0 violation；`i2s_rx_phy` PASS；pytest **438 passed + 26 skipped**（+17 采集工具测试，基线语义不变）。零 PDS/零烧录。

## 2026-11-04（第五批）：等模型期间三线并行——48k 前端真值链/mel 48k 仿真/集成实验顶层；发现模型侧已开工

- **补充收尾：mel_filter coo_rom 深度已参数化**（`COO_ROM_WORDS` parameter，mel_engine 透传，默认 2025 与 44.1k 逐位一致）：mel_48k TB 直接传 2027，run_sim 的 build 拷贝 override 已拆除（补丁层归零纪律）；mel/mel_credit/mel_48k 复跑 PASS。**48k PDS 前置项清单清空**，等模型期间的全部准备项完成。
- 用户指示按 MODEL_TRAINING_SPEC 附录 B 推进不依赖新权重的部分。三子代理并行交付（主线已独立复核 stash 对照与全量回归）：
- **A 48k 前端真值链**：`gen_mel_tables.py` 参数化（--sr/--f-max/--suffix，默认输出与冻结表逐字节一致）；48k 表集 `scripts/outputs/mel_tables_48k.json` + `mel_coo_48k.hex`（1962 entries，bin1..1022）；hann/log2_lut/exp_lut 表级 hash 与 44.1k **相等**（采样率不变量实证，RTL 只需换 COO 表）；`golden_pipeline.py` SR 参数化（帧率断言对表 sr，默认行为不变：44.1k feat 与冻结 golden_ref 逐位一致）；`experiments/mel48k/run_check.py` 自验证：合成 PCM@48k 饱和 0、librosa(48k,fmax24k) 逐 bin Pearson r≥0.999、hex↔json 一致、双跑 hash 复现；报告 `reports/mel48k_truth_chain_20261104.json`。
- **B mel RTL 48k 注入**：`mel_engine.v` 新增 `INV_S_IN/ZP_IN` parameter 并透传至 standardize 例化（**新模型 QuantStub 注入通路补全**，默认值逐位同旧——mel/mel_credit 复跑 PASS 证明零破坏）；新 sim case `mel_48k`：mel_engine 注入 48k COO 表（TB override），48k 合成 PCM 对拍 48k golden **16512 mismatch 0**（frames=259/cycles=5144063）。**已知跟进项**：`mel_filter.v` coo_rom 深度 [0:2024] 按 44.1k 硬编码，容不下 48k 表 2027 行——mel_48k 用 run_sim overrides 在 build 拷贝上扩容绕过，**正式 48k PDS 交付前必须把 coo_rom 深度参数化/扩容**（列入新模型交付后清单首位）。
- **C 三模块集成实验顶层**：`src/integration/top_integration_lab.v`（扁平 MMIO 写口统一 uart_app_boot/ui_scene/logits_snap 三模块 + 假 NPU LCG 结果发生器 + IRAM 执行监视）；`sim/tb_integration_lab.sv` 四场景 50 检查 PASS（APP 加载/场景原子切换/logits 快照闭环/坏帧防御+互不干扰）；run_sim 新增 integration_lab case。**发现三个真实接口问题**（已记录，生产集成时处理）：①logits_snap 寄存器 0x200/0x204 与 ui_scene glyph 子窗地址冲突，生产 MMIO mux 须给独立基址；②epoch 同拍递增约束须写入契约；③ui_scene_top 建议引出 frame_start。
- **重要外部事件：模型负责人已按训练规格开工**——`InstRec/src/features.py` 已改 SR=48000/F_MAX=24000（git M 状态，注释引用规格措辞）。副作用：`test_golden_mel.py` dod1/dod3（golden z vs 训练侧动态参考）因 44.1k golden 域 vs 48k 参考域错配出现 20 failed（delta≈1.113）。处置：加域一致性 guard——参考域与 golden 表域不匹配时显式 skip（注明原因），**不冒充跨域一致也不挂红基线**；基线变为 **421 passed + 26 skipped**（22 个域 guard skip 属预期过渡态，新模型交付+FPGA golden 切 48k 表后自动恢复实测）。
- 验证：check_rtl 75 .v / 0 violation；run_sim mel/mel_credit/mel_48k/ui_scene/uart_app_boot/logits_snap/integration_lab 全 PASS；stash 对照证明 20 failed 与本批改动无关（InstRec 侧外部修改所致）。
- 下一步：等新模型交付（训练规格 §6 七项交付物）；到位后按附录 B：mel_filter coo_rom 深度参数化→48k golden_ref 重生成→NPU 新权重对拍→集成→PDS→三层注入。

## 2026-11-04（第四批）：产出模型重训规格文档，进入「等新模型」阶段

- 用户裁定执行顺序：**先出训练规格交模型负责人重训 → 新模型交付后适配架构 → 分模块逐个仿真 → 全部通过才上板**；此前「修复后直接构建上板」的提议作废。本轮唯一交付为 `docs/MODEL_TRAINING_SPEC_20261104.md`。
- 规格要点：①数据全部现成（Medley-solos-DB cache/group5_cache_v3 在 InstRec/data/，**无需重新采集**）；②前端统一 F1 原生 48k（删 147/160 重采样，Mel 表 fmax 24k 重生成，几何 64×258 不动）；③网络骨架固定 InstrumentCNN 四级 conv-pool+GAP+FC（NPU 算子白名单），通道候选 S0 基线/S1 24-48-96-128/S2 16-32-64-96；④八类与五组均需按 48k 重训（共享前端强制统一采样率；五组 44.1k INT8 契约保留为架构回退开关）；⑤量化交付必须含 QuantStub {scale,zp}（新 zp_in 不再是 49，standardize 参数化适配是交付后第一输入）；⑥验收门槛与交付物七项清单；⑦附录 B 固化交付后 FPGA 侧「契约适配→分模块仿真→全链→PDS→三层注入→真实音乐」逐级流程。
- 事实核实：部署类别表=`InstRec/deploy/class_names.json`（Medley 8 类，idx0=clarinet）；正式八类模型为 Medley 域（runs/best_model.pt）；InstRec 前端参数在 deploy/feature_params.json 与 src/features.py。
- 本轮零仿真/零构建/零板级（分模块仿真按附录 B 须等新模型交付）；XSY 本地 commit 未 push。

## 2026-11-04（第三批·重大修复）：恒 top1 根因修复——standardize 量化移位 24→36，特征恢复分化

- **根因修复已落地并全链验证**：`src/mel/standardize.v` Beat Q 与 `scripts/golden_pipeline.py`（QUANT_IN_FRAC_BITS）的 z(Q4.12)×inv_s_in(Q8.24) 移位从 24 改为 36（12+24）。旧值等效 2^12 增益，uint8 特征 ~50% 饱和（0/255 两值化），这是板上恒 top1 的直接根因；**RTL 与 golden 共享此 bug，故历来位级对拍一致但同吃坏特征**——「golden 位级真值」的可信边界仅覆盖「RTL 实现 golden 数学」，不覆盖「golden 数学实现训练语义」，本次由浮点模型×特征域 2×2 对照补上后半环（`reports/float_vs_quant_domain_diag_20261104.json`）。
- 修复后全链验证：mel/mel_credit PASS（RTL=新 golden 0 失配）、conv1 PASS（hex_conv1 重生成）、全 TB **34/34 PASS**（含本轮新增 ui_scene/uart_app_boot/logits_snap）、pytest **443 passed / 4 skipped**；golden_ref 三 stem 参考按 gen_golden_refs.py 重生成（旧域版本在 git HEAD 可恢复）。
- **IRMAS 八样本 NPU 探针（修复后）**：top1 从全坍缩 0 恢复分化 {4:3, 1:4, 2:1}、RTL=golden 逐位一致、每样本 31,115,245 cycles 不变（`reports/npu_probe_irmas_20261104.json` 已更新）。1/8 准确率属 IRMAS↔Medley 域差异（E4 格 1 float 模型亦 2/8），不构成模型缺陷判据；真实精度须 Medley 验证集（数据缺口仍开）。
- **新知识：修复后特征域上限 177**（Q4.12 极值 z=8 → 8×15.94+49），255 在合法输入域内不可达；旧域「满幅触轨」断言（DoD4 等 3 个共生测试）已改为修复后语义（quantize_int8 极值轨 0/177、列不变性症状消失断言、非排列弱断言）。
- 类别表澄清：E4 判定部署空间 idx 0=clarinet（此前「小号/钢琴」读法均误）；板上恒 top1=6 的类名以部署类别表为准待板上复核。
- 板级含义：板上 1497FAF4 位流含此 bug（其恒 top1 与 RTL 坍缩点不同还叠加板侧输入域偏移）；**修复版需新构建新位流后才有板级意义，本轮零 PDS/零烧录**。五组 INT8 契约（group5_contract）的 inv_s_in 语义与八类同型，其 golden 管线同查点已在评审记录，重生成属 M3 任务。
- 下一步：①修复版唯一资源门控+限时 PNR+板级三层注入对拍（判据=npu_probe 新基线）②Medley 验证集获取（精度评估数据缺口）③logits_snap/uart_app_boot/ui_scene 集成实验顶层 ④五组 golden 同点复查。

## 2026-11-04（第二批）：恒 top1 根因二分完成——模型/特征域（强结论）；logits 快照 RTL；五组 INT8 契约评审转正

- **E2 诊断实验（本轮最重要发现）**：8 个 IRMAS 真实八类样本过 RTL NPU 全链，RTL 与位级 golden **逐层逐位全同**（8×13 层 all_identical），但 top1 全部坍缩到 0（piano），probs 恒 [65535,0,…,0]，仅 piano 样本本身 match。⇒ **恒 top1 根因方向=模型/特征域，非 RTL 数值、非板级搬运**；板上坍缩点 6（guitar_acoustic，此前「小号」为类表误读：trumpet=idx5）≠ RTL 坍缩点 0，说明板侧输入域另有偏移，但**仅修板侧无法恢复正确分类**。证据 `reports/npu_probe_irmas_20261104.json`（8 样本×12 层快照，431.6s 仿真，`sim/experiments/npu_probe/run_irmas.py`）。待区分：量化模型缺陷 vs golden mel 域与训练域失配（下一步浮点模型对照）。
- **E1 logits 快照 RTL**：`src/ctrl/logits_snap.v`（契约 §3 的 RTL 化：16 槽影子寄存器单拍原子锁存、LOGIT_IDX/VAL/META/CTRL 接口、epoch 递增清 valid 不清数据）+ TB 五场景 30 检查 PASS；独立模块未接线生产，集成留下轮。run_sim 新增 logits_snap case（12.0s）。
- **E3 五组 INT8 契约评审：转正提交**。遗留五候选资产（golden_pipeline_group5.py / eval_group5_int8.py / group5_contract.json / group5_weights_image.bin / 校准报告）评审全过：requant RHE/compute_m_shift/zp=98/BN 折叠与八类逐行同型；macro-F1 0.87307→0.86559（Δ-0.0075，门槛 ≤2pt 内）、双跑 byte-identical、来源链 hash 锁定。跟进项：R1 zp 打包 'b'→'B' 解析端同步、R2 无 pytest 冻结测试、R3 agreement 余量 +0.0006。报告 `reports/group5_int8_contract_review_20261104.md`。
- 验证基线：check_rtl 74 .v / 0 violation（+logits_snap）；pytest 443 passed / 4 skipped；零 PDS/JTAG/烧录。
- 下一步（E2 结论后重排）：①**浮点模型对照诊断**（区分量化缺陷 vs 特征域失配，决定重训范围——最高优先）②logits_snap/uart_app_boot/ui_scene 集成实验顶层 ③五组 INT8 R1/R2 跟进（zp 打包统一+pytest 冻结）④存储共享/16/8lane。

## 2026-11-04：按总规划启动并行开发，四工作包首批最小交付完成（M0 数值真源 + M1 双半程）

- 用户指令「按 DUAL_MODE 规划完成开发、注意版本管理、调用子智能体并行」；按 HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104 第 6 节分工并行分派 A/B/C/D 四个子智能体，主线任集成负责人。先修复基线缺口（emergency_demo 漏第 4 处登记致 1 failed），回到 443 passed / 4 skipped。
- **B 线 M0 可定位基线已产出**：`sim/experiments/npu_probe/` 固定 feature→NPU 探针，4 确定性向量（sine440/zeros49/rand/twolevel）×12 层快照，RTL=golden_pipeline=golden_ref 三方逐位一致，每向量 31,115,245 cycles；`reports/npu_probe_baseline_20261104.json` 为未来板上 feature/PCM/I2S 三层注入比对的第一判据真源（比对 fc2_u8/logits_int32/probs_q16，逐层回溯用 conv/pool/gap 快照）。缺口：尚无不同类别真实样本向量。
- **C 线 UART APP 协议 v0 已实现**：`src/boot/uart_app_boot.v`（chunk≤512B/CRC32/seq 严格递增/EXEC 三重校验/ABORT，4KiB IRAM 试写零提交）复用生产 uart_rx/tx；TB 六场景 52 检查 PASS（坏 CRC 重传恢复、seq 跳号、坏 EXEC 拒绝、ABORT 重载、超容量）。独立实验模块，未接线生产顶层。
- **D 线软件 UI 场景 ABI v0 已实现**：`src/ui_scene/` 双 bank 描述符表（32 槽×8 word）+ glyph 序列 RAM + 四拍渲染器（640×360 等比几何）；TB 两场景 921,600 像素与 Python 参考帧逐拍一致，bank 隔离/帧边界原子 commit 验证 PASS。ASCII 去重评估：现状 12 份 DRM18K 复制（format_percent 并行端口），glyph-ID 预格式化可省 6.0 DRM36K 当量（`reports/ui_ascii_dedup_plan_20261104.md`）。
- **A 线前端对照管线已建立**：`experiments/audio_frontend/` F0/F1/F2/F2b 四路线（F1 原生 48k 删重采样、F2 24k/1024FFT 抗混叠 FIR 阻带 81.2dB）；14 输入对照 F1 logits 漂移最小（|Δ|≈1.24、翻转 1/14）但**三路线均不可沿用旧权重，重训是硬前提**；无 Medley-solos-DB 验证集（仅 IRMAS demo 切片缺 2 类）如实记缺口。
- **v0 接口契约文档**：`docs/INTERFACE_CONTRACTS_V0_20261104.md`——UART APP/UI 场景已实现契约固化（含实现偏差澄清），MMIO logits 快照（0x8000_0030–0x8000_003C 锁存握手）、DDR 地址图、模型描述符为 v0 草案待下轮集成冻结。
- 验证基线：check_rtl 73 .v / 0 violation（+4 新文件）；run_sim 新增 ui_scene（14.4s）/uart_app_boot（42.2s）均 PASS；pytest 443 passed / 4 skipped。本轮零 PDS、零 JTAG/串口、零烧录；生产 src 既有文件零改动（src/cpu、src/ui、src/ctrl 未动）；CPU 用户 diff/PCB/obj_dir/deploy/group5 未跟踪资产保持。分支 XSY 本地提交未 push。
- 下一步（按 MASTER_PLAN 顺序）：①MMIO logits 快照 RTL 实现 + rv_cpu_subsys 集成设计 ②uart_app_boot/ui_scene 接入集成实验顶层 ③取得真实八类样本扩充 probe 向量集 ④五组 INT8 契约评审（未跟踪 group5_* 资产转正评审）⑤存储共享/16/8lane 对照启动。

## 2026-11-04：正式开发交接总规划完成

- 用户要求完成规划供交接；新增docs/HANDOFF_DEVELOPMENT_MASTER_PLAN_20261104.md，作为后续架构/任务优先级入口，实时状态仍认本文件。统一双模式、存储优先、性能换资源、软件UI、UART应用启动、音频对照与并行分工。与前规划冲突时认新总规划和软件/存储修订。
- 不强制缩模型，先共享/打包缓存与去重复表；同模型16/8lane对照再决定降并行度，4lane非默认。24k/1024FFT与48k公平比较，16k另测高频精度；CPU最小boot+UART可执行APP、scene软件UI与DDR桥分阶段实现。新增明确首批交付、M0–M7门槛、负责人/文件归属、资源/吞吐预算及2–4周工程量级估计（非承诺）。
- 仿真→唯一新源PDS/十表→feature/PCM/完整串行I2S三层整板对拍→真实音乐/耐久；恒小号根因与正式时序仍FAIL，演示不是推理证据。本轮只写规划，无新训练/RTL/PDS/烧录；硬件在线未知，最后记录FTDI掉线，不沿用旧PID推断。保护CPU用户diff/PCB/obj_dir/未跟踪五组资产及冻结release；本次本地commit交接，不push。

## 2026-11-03：规划修订为存储优化优先、软件UI与UART应用启动

- 用户指出共享NPU缩模型不必然省资源，要求评估F2音频、CPU软件可改UI、应用UART加载启动及DRM外移。已新增docs/SOFTWARE_UI_BOOT_AND_MEMORY_ARCHITECTURE_20261103.md并修订双模式规划入口；本轮仅审计/设计，未改RTL/未训练/未PDS/未烧录。
- 对1497FAF4完整综合逐memory原语统计总数150.5/155，与map一致：Mel32、store0/1共32、conv19.5、显示谱16、文字12、pool/wbuf/wdma各8、CPU6、重采样4.5、波形3、其余1.5。证据reports/drm_storage_audit_20261103.json含报告hash；这些是片上DRM，不是DDR容量。优先小bank碎片/跨层复用/ASCII并行复制/显示页边界，权重/PCM整窗/整层activation已有DDR驻留。
- 不强制缩模型；先24k/1024FFT与48k对照，16k作为高频精度实验，降采样仍需抗混叠、训练前端重核。推荐CPU scene/tile/glyph MMIO原子提交，最小boot ROM+UART应用加载+可执行RAM/DDR桥/取指cache，不能用现有权重loader冒充CPU可执行DDR。DDR预算/总线/ABI先冻结，后并行CPU启动、UI仿真、存储/NPU和音频实验。新范围按2–4周工程量级规划非承诺；当前演示及冻结release保持。

## 2026-11-03：恢复正式开发，硬件适配模型与双模式规划完成

- 用户要求重新规划硬件适配/简化架构，支持八类识别与五类独立活跃度双模式，要求并行调度、仿真优先及板上模拟I2S完成真实推理验收。已生成docs/DUAL_MODE_HARDWARE_MODEL_DEVELOPMENT_PLAN_20261103.md，作为后续实施计划；本轮未启动训练/PDS/烧录，板上演示保持。
- 推荐同位流共享前端/NPU、两模型镜像串行复用，先分别训练轻量模型，再评估共享骨干；首选对照直接48k前端消除48→44.1k重采样，不能盲删抗混叠/Mel或沿用旧权重。模型/前端/INT8精度以独立数据实验定案。
- 规划含P0–P8门槛、A–E并行责任与唯一PDS/JTAG纪律，feature/PCM/串行I2S三层注入、真实DDR逐级对拍与故障分流；正式1497恒小号根因仍未定位、core时序仍FAIL，演示不作为推理证据。初估首个可靠双模式1–2周量级，数据/前端返工预留2–3周以上，不作完成承诺。下一步P0已知向量/可观测性与P1模型实验并行，先锁定数值真源。

## 2026-11-03：CPU＋NPU八类下午版独立源码定版

- 按用户要求冻结下午最后一版真实推理系统，基准0c138d4f（17:23），原始位流1497FAF4；新增releases/pacerv-instrec8-20261103/，后续竞赛技术文档以此目录为唯一源码基准。功能范围固定为PCM1808→44.1k重采样→Mel→真实八类NPU＋RV32I控制＋中文HDMI，不混入后续无NPU曲线演示、五类或Flash扩展。
- 从固定Git提交与原构建清单核对提取，保留56个应用/CPU RTL、所需原厂IP、19份ROM表、C/汇编/linker、权重/量化契约与必要工具；CPU本地化，不依赖包外cpu/。去除未引用模块/旧顶层/开发历史文档与普通注释，保留综合指令/版权/IP原字节；56份RTL执行token不变，固件重新生成2320B/580word与冻结ROM一致。
- 独立PDS compile通过（160秒、exit0、源hash未变），本次只编译，其他阶段未执行且无新位流；原始1497位流随包归档。lint43/0，既有安全/权重pytest24通过；直接针对清理副本的5项安全与8项协议检查通过。175文件SHA256及全部本地构建/IP/ROM依赖校验PASS；VALIDATION/SOURCE_LOCK保留事实。PDS已正常退出，未烧录、未操作cdt。当前板上仍此前0EBF演示，未切换到定版。
- 用户将该版作为功能完成范围供后续写文档；原始core setup -1.071ns与恒top1=6/准确率未测等验证结论未改写。旧报告新增定版入口提示，正文后续据固定源码修订。保护既有CPU用户diff及未跟踪五类资产，本轮不push。

## 2026-11-03 19:50：重插后同版重烧成功，BOOT/DDROK通过，下载器随后掉线

- 用户回复重插后安全复用JS9040/65420烧录同一0EBF9448，program=true、done1/CRC0，7952B串口含RV32 BOOT/MMIO/ISA与DDROK；演示stub输出非真实推理。置信度曲线/去提示保持，未上传权重。
- FTDI在本轮结束检查时再次从PnP消失，故自动overall FAIL，仅下载器在线条件失败，不抹除实际program/启动/DDR成功证据。未重启/终止/新建JS，既有cfg46156保持；不要求为已完成烧录再重插。证据reports/emergency_demo_nohint_repeat_retry_20261103.json及原文hash。保护CPU用户diff/PCB/obj_dir/group5；当前板上去提示演示已启动，后续需要JTAG时再处理连接。

## 2026-11-03 19:45：再次请求烧录，FTDI 缺席，未执行 program

- 用户再次要求重烧同一去提示0EBF9448，位流hash已核对。烧录前PnP无FTDI，自动安全退出，未执行program；JS9040/65420与既有cfg46156保持，未重启或终止服务。独立证据reports/emergency_demo_nohint_repeat_board_20261103.json。
- 已仅请用户重插下载器电脑端USB，保持电源/JTAG/HDMI/音频不动；等待恢复后继续同hash烧录。此次不是烧录成功，不覆盖上次配置成功但UART0B的结果。CPU用户diff/PCB/obj_dir/group5资产保持。

## 2026-11-03 19:31：按用户要求重烧同一去提示版，配置成功但 UART 无数据

- 用户已确认此前0EBF9448提示消失、回放和频谱正常；随后明确要求重新烧录。同一hash位流安全复用JS9040/65420重烧成功，program=true、done1/CRC0，既有cfg46156保持；无新构建/权重上传/服务重启。
- 本次15秒UART为0B，未捕获RV32 BOOT/DDROK，因此自动完整板检FAIL；不能将配置成功当启动或DDR自检通过。已询问本次重烧后画面/KEY1回放状态待答，保留reports/emergency_demo_nohint_reflash_20261103.json及独立原日志/hash，不覆盖首次PASS。下一步按屏幕反馈诊断，不无理由重复烧录。保护CPU用户diff/PCB/obj_dir/group5资产。

## 2026-11-03 18:49：KEY1 提示整行删除，新版 0EBF9448 已烧录且十表时序通过

- 按用户明确要求只删除演示右下角整行“KEY1 重播 / 预设曲线”；置信度ROM数值与此前CE2E2205完全相同，KEY1重播/58秒末帧保持、真实PCM1808/波形/Mel、其余标签保持。lint69/0、五状态全1080p实际RTL回归PASS；显示差异仅y960/x>=1280的20个提示tile，动态类名/数字/百分比glyph一致。
- 新源唯一run20261103-182311-e9fcb396门控正常526.7秒，20880LUT/18148FF/74.5DRM/31APM；同冻结源PNR/十表/位流正常902.4秒，逐文件hash未变。完整十表All Constraints Met，无负项（包括慢角pix setup +0.180ns）；这是演示顶层的新结果，不代表正式推理系统时序通过。位流3791112B，SHA256 0EBF9448533FD958676B376295F1A23D571DD64E881B9C7813C0E036FA12A584。
- 安全复用JS9040/TCP65420烧录PASS，done1/CRC0、RV32 BOOT与DDROK通过，既有cfg46156保持；无权重上传、无NPU推理。串口NPU GO/top1/cycles0是原CPU读演示stub/UI，采集含烧录前旧记录，不作为推理证据。当前板上是去提示0EBF9448，已询问新实屏效果待答，不重复烧录/旧验收。
- 证据reports/emergency_demo_nohint_20261103.json、对应timing/board报告；旧CE2E2205及正式1497FAF4证据均保留。PDS/monitor均正常退出，未操作JS/cfg，未碰CPU用户diff/PCB/obj_dir/group5资产。下一步仅按新实屏反馈处理；正式恒小号、五类与Flash后续任务不以演示替代。

## 2026-11-03 18:19：用户曲线演示 CE2E2205 已烧录，用户确认显示与回放正常

- 唯一run20261103-175125-bc930d4f完成PNR/十表/位流，监控正常退出0、871.6秒，冻结源逐文件hash未变；PDS与monitor均已退出。位流3791112B，SHA256 CE2E2205F4F17C28A5AF2E9E16D8B2ED0DF73F48F8DBE3BD783CF698E2667A88，证据build/emergency-demo-pnr-20261103-180146/result.json与reports/emergency_demo_timeline_20261103.json。
- 完整十表Some Constraints Violated：pix慢角setup -0.005ns/1端点，core慢角setup -0.399ns/34端点，其余setup/hold/recovery/removal/min-pulse通过。仅作为紧急演示候选，不宣称时序收敛或长期稳定；reports/emergency_demo_timing_20261103.json归档全部表/hash。
- 安全复用JS9040/65420烧录成功done1/CRC0、RV32 BOOT/MMIO/ISA与DDROK通过，既有cfg46156保持。无权重上传；当前板上已是无NPU的独立演示CE2E2205，不是正式1497FAF4。串口保留的NPU GO/top1/cycles0是原CPU固件读演示stub/UI寄存器，不代表真实推理；采集开头还含烧录前旧系统记录。烧录/串口hash见reports/emergency_demo_board_20261103.json与timeline报告。
- 用户明确回复“显示与回放正常”，本次真实音频动态显示与KEY1曲线演示实屏验收通过；不重复询问。无需权重/重插/改线。正式位流与资产保留，未触碰CPU用户diff、PCB、obj_dir及group5资产。下一步按实际反馈修复演示，静态时序与原恒小号诊断仍未解决。



## 2026-11-03 17:54：用户时间曲线已冻结，八类演示新源资源门控中

- 用户提供confidence_timeline.json已原字节冻结data/demo/，114窗/1.485–57.985秒；581个10Hz采样点。类别与旧模型不同，演示专用dashboard标签与glyph独立改为钢琴/小提琴/单簧管/长笛/萨克斯/小号/原声吉他/电吉他，正式模型及显示ROM不改。曲线演示标记常显；KEY1从WAV起点计时，第一窗前保持首值、按中心线性插值、末帧保持/再按重播。仍保留真实PCM1808/Mel/波形/HDMI，无NPU/无权重依赖。
- 相关pytest48passed；demo_player和用户曲线581行/全类别/保持/重播实际RTL均PASS，lint69/0。新演示显示五帧RTL验证亦PASS（完整1080p/2000条柱宽检查）。证据reports/emergency_demo_timeline_20261103.json。
- 唯一新源run20261103-175125-bc930d4f于17:51启动compile/synth/dev_map，30分钟硬截止、CPU/日志监控build/emergency-demo-gate-20261103-175124。门控572.1秒正常退出PASS，20886LUT/18148FF/74.5DRM/31APM、SourcesUnchanged；18:02起同冻结源唯一限时120分钟PNR→十表→位流。尚无演示位流/烧录，板上仍1497FAF4；FTDI在线、JS9040/65420可复用。未操作JS/cfg、保护CPU用户diff/PCB/obj_dir/group5资产。

## 2026-11-03 17:44：按用户紧急要求建立无推理演示版，待置信度曲线

- 用户中止恒小号诊断，优先独立演示：八类现界面、真实PCM1808/波形/Mel频谱/HDMI保持，KEY1播放预设置信度，不再推理。XSY新增emergency_demo/top_emergency_demo，正式full顶层不改；移除演示顶层NPU实例、禁止启动，sys_ctrl不等权重，KEY1与DDR自检解除。KEY0仍复位。板上仍1497FAF4，本轮没有烧录。
- 回放10Hz、KEY1消抖/从头播放、完整八项快照后帧边界提交、播完保持/再按重播；最长409.5秒。曲线导入脚本支持八类关键帧插值，详见docs/EMERGENCY_DEMO.md。用户尚未提供变化图，目前ROM全零占位，不能将其当最终演示结果或准确率。
- demo_player实际RTL仿真PASS（零值等待、消抖、三帧/类别、保持、重播），相关pytest47passed，lint67/0。唯一编译run20261103-174125-b3a995ac正常PASS/exit0/110秒，源hash未变；本轮只请求compile，其他stage的FAIL占位是未执行，无综合/映射/PNR/时序/演示位流。首轮173816编译发现生成stub重复驱动，已修复；原失败日志/hash保留。StopAfter compile原脚本不能识别带参数synthesize命令，已修复阶段匹配。证据reports/emergency_demo_framework_20261103.json。
- 当前无PDS/monitor；未触碰cdt_js/cdt_cfg、CPU用户diff、PCB、obj_dir或group5未跟踪资产。下一步收到用户曲线→填入并冻结→唯一新源资源门控→容量允许后限时PNR/完整时序→安全复用既有JS烧录、真实音频频谱及KEY1回放验收。曲线变化后不得复用旧ROM映射。正式恒小号根因尚未定位；演示不作为修复或准确率证明。

## 2026-11-03：新完整系统中文显示用户验收正常，手动复位后重载权重恢复

- 用户确认1497FAF4中文仪表盘、波形/频谱动态都正常，无错位/撕裂/花块反馈，覆盖前条待答显示验收；随后用户按复位。KEY0会清除weight_loader.weight_ok，单纯DDR数据可能残留不能视为权重仍有效，当前尚未Flash自动恢复。
- 复位后只读8秒UART0，随后无需重烧位流，重新上传691040B/2700帧返回WOK FA0D5236，12秒225B/5轮NPU完成及CPU回读恢复、无TIMEOUT。三份原文/hash记入reports/pcm1808_mel_split_full_board_20261103.json/manual_reset_recovery，旧上板证据保留。当前板上仍1497FAF4且权重已恢复；不需用户改线/重插/再次复位。
- 核心时序FAIL与准确率未验收边界不变；后续继续长路径收敛，Flash固化/自动权重加载将解决复位后手动上传需求。无PDS/无下载器服务操作，XSY仅instrec报告/文档更新。

## 2026-11-03 17:17：1497FAF4 完整 PCM1808 系统已烧入，WOK 与连续 CPU/NPU 回读通过

- 用户确认下载器恢复后，FTDI在线，复用JS9040/65420正常program，既有cfg46156保持；done1/CRC0。板上当前为新源完整1497FAF47B83B64A62027C38B6BF94D12112002C250FC5278C3C28AD2FA46ABE，不再是独立诊断。烧录捕获RV32 BOOT/MMIO OK/ISA OK、DDR3 SELFTEST/DDROK；启动时DDR WAIT是自检前瞬时状态，随后DDROK。一次命令相对路径重复前缀导致下载前拒绝，已改正确工作目录后成功；原失败记录保留build/board-pcm1808-mel-split-20261103/invocation_path_error_before_program.json。
- 691040B八类权重2700数据帧上传PASS，WOK FA0D5236。随后30秒450B串口记录包含10轮NPU完成/真实CPU读取ACK再排队，cycles32358425–32362149，全部top1=6，无TIMEOUT。last_class7/last_p0是末类寄存，不是top1置信度。生产启动受完整Mel窗门控；本整机位流未另测采样率/输入幅值，不能把既有独立诊断采样率或相同分类输出当本次准确率证明。证据reports/pcm1808_mel_split_full_board_20261103.json，串口/上传原文和hash均保留。
- 已询问用户当前中文HDMI仪表盘、波形/频谱动态与花块/撕裂情况，后来已确认都正常（见顶部复位恢复记录），不重复旧fallback验收。PCM1808接线保持；未恢复任何旧输出BCK/LRCK位流。没有Flash固化操作。
- 当前内部十表仍仅核心慢角setup FAIL -1.071ns/338端点；上板跑通不等于时序收敛或长期稳定。下一步修复npu_m1_bridge完成控制到weight_read_aligner CE及FC1 requant控制长路径，相关无reset/全层golden验证后新源唯一资源门控与限时PNR；不能复用本次map称修复。PDS/monitor均已退出，工作维持XSY，保护CPU用户diff/PCB/obj_dir/group5资产。五类双头和Flash后续任务保留。

## 2026-11-03 17:04：PCM1808 完整整机位流生成，最终时序仍 FAIL；下载器缺席未烧录

- XSY 唯一 run20261103-152639-fb2ffc99 已正常完成 PNR→report_timing→gen_bit_stream；监控 normal/exit0、4614.5秒，PDS/monitor 均退出。Mel 宏放置/详细布线成功，完整位流3791112B、SHA256 1497FAF47B83B64A62027C38B6BF94D12112002C250FC5278C3C28AD2FA46ABE。103项冻结输入逐文件hash未变；证据 build/pcm1808-mel-split-pnr-20261103-154653/result.json。不是旧映射或诊断位流。
- 最终十表完整，Some Constraints Violated：唯一负项为核心ddrphy_sysclk慢角setup -1.071ns/TNS -88.874ns/338端点；pix setup +0.041ns，全部hold/recovery/removal/min-pulse无负项。最差路径reads_left→weight_read_aligner状态CE，其次FC1 rq_cnt→requant APM (-0.953ns)。reports/pcm1808_mel_split_timing_20261103.json存完整表与报告hash；不把PNR成功当时序收敛。
- 复用JS9040/65420的烧录前检查报告FTDI ABSENT，安全退出，未执行program；cfg46156保持，不新建/重启/终止JS。已仅请用户重插下载器电脑端USB，保持板电源/JTAG/PCM1808/HDMI；等回复后重新核验并烧入本次输入方向位流，确认done/CRC/BOOT/DDROK→691040B权重WOK FA0D5236→真实音频连续NPU/CPU回读与中文HDMI。报告pcm1808_mel_split_board_20261103.json为FAIL，不是烧录成功。
- 用户回复已重插后第二次检查仍FTDI ABSENT，独立Get-PnpDevice -PresentOnly仅见COM5；FTDI仅历史Unknown记录。再次未执行program，证据reports/pcm1808_mel_split_board_retry_20261103.json；已请确认是独立下载器USB并改用电脑另一直接USB口，保持JTAG/电源/音频不动。不绕过在线检查、不操作既有JS/cfg。
- 板卡最近只读done0/UART0，当前没有新整机板测结论或准确率结论。旧输出BCK/LRCK位流禁止在PCM1808接着时恢复。更新PCM1808说明中的27MHz实际域；保护CPU用户diff、PCB、obj_dir、未跟踪group5资产。下一步除恢复下载外仍需修复核心长路径、新源单路构建/最终时序，Flash和五类工作不混入本次位流。

## 2026-11-03 16:26：Mel split 宏放置通过，详细布线持续收敛；板卡当前 done=0

- 唯一PNR run20261103-152639-fb2ffc99已通过前轮失败的RAM宏放置；详细放置完成，工具放置估计slack +0.500ns/TNS0（非最终STA）。详细布线第71轮未布通5302，较初始65872持续下降，CPU持续推进；硬截止仍17:46:55，不启动第二条PDS。实际监控目录为build/pcm1808-mel-split-pnr-20261103-154653，已修正文档/报告中的154655误记。
- 15:56只读复用JS9040/65420：FTDI/COM5在线、既有cfg46156保持，status0x00180c80/done0/CRC0，UART10秒0字节；没有烧录，不能宣称旧2856BB4D诊断当前仍运行。证据build/pcm1808_probe/status_before_full_split.json。新位流完成后需安全重烧，再确认BOOT/DDR/WOK与真实音频连续推理/HDMI。
- 当前仍无新完整位流/最终十表/整机板测结论。源冻结，CPU用户diff、PCB、obj_dir与group5资产保持不动；继续当前PNR直到完成或截止并归档。

## 2026-11-03 15:47：Mel split 整机资源门控通过，唯一新映射 PNR 中

- run20261103-152639-fb2ffc99 compile/synthesize/dev_map全PASS，SourcesUnchanged=true，正常退出；33967LUT/35466FF/150.5of155DRM/92APM。Mel主bank实推8DRM36+尾1DRM18；整机净省4.5DRM（工具对其他RAM重新分配），不拿局部7.5节省代替整机结果。完整map7623145B，hash见reports/pcm1808_validation_20261103.json；门控证据build/pcm1808-mel-split-gate-20261103-152638。
- 核验源hash未变及无其他PDS后，15:46:55从新库启动唯一PNR→十表→位流，17:46:55硬截止，15秒CPU/RSS/阶段监控存build/pcm1808-mel-split-pnr-20261103-154653。manifest中StopAfter后的FAIL占位是未执行，不能当本轮PNR结论。结束前读取实际stage日志/最终十表，保留所有失败证据。
- 修复与全量回归已push XSY/782e880e；生产ROM A/B连续native golden/CPU回读ACK回归证据005bacf5已push。板上仍输入诊断2856BB4D，最近COM5只读10秒0字节，烧录前需只读核验当前状态；未改既有JS/cfg。当前无新完整位流、不声明整机完成。

## 2026-11-03 15:27：27MHz 整机宏放置失败，Mel 存储边界拆分回归通过，新源门控中

- 上轮 PNR 于 15:18 正常报 Place-0006：u_mel_engine/spec_bank_0/gopdrm_36k cannot be placed，无路由/最终十表/位流/烧录。失败日志与 hash 保留 build/pcm1808-27m-pnr-20261103-151232/result.json；更正旧条目的 archive 尾号151234为151232。板上仍2856BB4D输入诊断，PCM1808接线保持。
- 定位原16576x16 Mel bank被向上分配为32768深度、16块DRM36。生产bank拆为16384x16与192x16，同步读保持一拍，保留三writer优先级及读写同址行为；是否节省DRM以新完整映射为准。新源逐拍miter212480比较/两轮无reset PASS，真实Mel整窗16512bytes/0mismatch PASS，NPU交接16512bytes PASS；历史20261101报告保持，新增20261103报告独立记录。
- 新冻结源唯一门控run20261103-152639-fb2ffc99于15:26:39启动，compile/synthesize/dev_map，30分钟硬截止、15秒CPU/日志监控。不复用旧map；新资源结果后再决定限时PNR，成功后核验十表、安全复用JS烧录与WOK/真实音频联合验收。本次split后全量pytest436passed/4skipped（127.70s）、lint65/0；生产ROM/真实native A/B两轮无reset全部层golden及CPU回读ACK PASS（reports/cpu_native_pcm27_melsplit_20261103.json）。
- 仅XSY/instrec_fpga改动，CPU用户diff、PCB、obj_dir和group5未跟踪资产保留，cdt_js/cdt_cfg未操作。

## 2026-11-03 15:13：27MHz 完整映射库恢复成功，唯一新源 PNR 已启动

- 同源 dev_map 恢复于 15:12:05 正常完成，PDS exit0、Executing dev_map successfully；完整 map 7890600B、SHA256 762c19fc9596a8d3d7bae455fa1ac445922ee94f8430988cf007827d42dcd6e8，资源仍 35743 LUT/35504 FF/155 DRM/92 APM。临时 map-only wrapper 因复用末尾“必须有位流”检查而 exit1，此为 wrapper 条件不匹配，非工具映射失败；该轮从设计上没有 PNR/位流。原超时不完整 map 证据保留。
- 核验全部源 hash 未变、无残留 PDS，15:12:34 从本次新完整 map 启动唯一 PNR→十表→位流流程，17:12:34 硬截止；15秒记录 CPU/RSS/路由日志，存 build/pcm1808-27m-pnr-20261103-151234。不得拿同目录旧门控 FAIL 占位当已执行 PNR 失败，最终以此次 stage 日志、十表及新位流 hash 为准。
- 当前没有新完整位流，板上仍 PCM1808 2856BB4D 诊断；烧录、权重 WOK、真实音频 NPU/CPU 回读、HDMI 联合验收仍待后续，不声明整机完成。详见 reports/pcm1808_validation_20261103.json。

## 2026-11-03 15:09：27MHz 整机资源报告通过，门控截止打断映射库保存，正在仅恢复 dev_map

- XSY/fc675565 新源 run20261103-144754-6578ad23 compile/synthesize 已完成；dev_map 资源报告为 35743 LUT、35504 FF、155/155 DRM、92 APM，容量未超限但 DRM 已满。dev_map 于保存数据库期间触及 20 分钟截止并安全停止，不能将资源报告当作可恢复的完整映射库，更不能称 PNR/时序/位流通过。
- 不完整 map 2396160B、SHA256 acfd6a5a5ab7bcbeadabb94e54551700e08ee82475215e477925d55f62be4d99 已另存 .adf.deadline-incomplete；原门控 result.json 保留 build/pcm1808-27m-gate-20261103-144753。完整 synth 9089353B、SHA256 fd94803ba8e051c8c4ef8dc229c5cb9888588c337a6861163652ed19199962c4 保留。
- 核验冻结源逐文件 hash 全部一致、无 PDS 残留后，15:08:49 使用独立 driver、同一完整综合库只恢复 dev_map；20 分钟新截止，监控存 build/pcm1808-27m-map-recovery-20261103-150848。不执行并发 PDS，不修改源、不复用旧源库。映射完整保存后才进入最长 120 分钟受控 PNR，并检查十表，再决定板级烧录。
- 当前板上仍 2856BB4D 真实 PCM1808 采集诊断；没有新完整位流/烧录。cdt_js/cdt_cfg 未操作，接线无需改动。保护 CPU 用户 diff 与其他未跟踪资产。

## 2026-11-03 14:48：按用户要求回到 XSY，完整系统改用已实测 27MHz 音频域

- 用户明确要求继续完整系统并放在 XSY，XSY2 暂不用。已切换 XSY，将 XSY2 的 9d2940f9..8f902aec 五个仅 instrec_fpga 提交 fast-forward 合入，并推送 origin/XSY；上游改为 origin/XSY。未修改/暂存 CPU 两项用户 diff、PCB、obj_dir 或另一组未跟踪 group5 资产；不再向 XSY2 续交。
- 完整 instrec_top 的外部主机 I2S 接收/FIR/CDC 写域由 216MHz 改为板载 27MHz，使用同一已实测算法；288 拍计算小于每输入帧 562.5 拍预算。移除该顶层不再需要的 audio PLL 实例，保留可复用历史模块/IP；本域复位异步置位、两级同步释放，sys_ctrl readiness 接同步释放完成，1ms watchdog 对应 27000 拍。原模型 44.1kHz、147/160、系数数值与 NPU 结构不改。FDC 去除不存在 PLL 的 generated clock，异步组改用实际 clk，仍在 DDR clocks 创建后加载。
- 新源唯一资源门控 build/pds/20261103-144754-6578ad23 于 14:47:54 启动，止于 dev_map，20 分钟截止；当前 compile 中、有 CPU 推进。现有 wrapper 的“最新目录”采样被 pytest -DryRun 目录干扰，实际 run 以本条和 wrapper.log 为准，不以 144823-2f39978d 当真实构建。源 hash 及最终门控结果须补录，尚无本轮映射/时序/完整位流。
- 27MHz 实际串行/FIR/CDC golden 回归 PASS（33s），audio_fifo、rv_top_ctrl PASS；lint 65/0。全量首次 435 passed/4 skipped/1 failed，唯一失败是旧 plan-contract 的构建集清单漏 pcm1808_diag，已补清单、相关 9 tests PASS；不是 RTL 功能失败。不宣称初次全量全绿。
- 板上仍 2856BB4D 真实音频诊断，J2 实际音源已经通过，保留接线、不重刷旧输出方向位流。门控通过后在新库执行受控 PNR→完整十表→安全复用 JS 烧录→权重 WOK→真实音频联合回读/HDMI 验收；不得拿旧库充作新源结果。

## 2026-11-03 14:43：真实 PCM1808 音频采集与 FIR 重采样板测通过

- 用户补供电后仍无完整帧，随后发现误接紫卡 J3，改接 J2 后无需复位/重烧即恢复。当前板上仍为 2856BB4D 输入方向诊断位流。
- 连续 10 个一秒串口快照：输入 48000/48001 对，输出 44100/44101 对，非零样本 47142–47992 对，左声道正负幅度和滤波后左右样本持续变化，全部 G=00（idle=0、overrun=0）。实际外部音频→I2S→生产 FIR 板测通过；不是 DDR/Mel/NPU 联合或识别准确率验收。原始 ASCII、SHA256 与解析数据纳入 reports/pcm1808_probe_validation_20261103.json。
- 为定位零计数曾启动带独立引脚边沿计数的小型候选 build/pds/20261103-144005-65daa515，正常结束并生成位流，但接线修正已解决问题，未烧录。候选源保存在 build/pcm1808_probe/edge_candidate.v，主线恢复已验证诊断 RTL；不将候选位流冒充当前板上版本。PDS/monitor 均正常退出。
- 保持 J2 接线和 PCM1808 供电，下一步继续完整系统路由/资源优化与联合验收；不恢复旧 BCK/LRCK 输出位流，不重复要求重插或接线。

## 2026-11-03 13:50：PCM1808 独立真实采集诊断已烧入，等外部音频接线

- 优化完整系统 PNR 已于 13:42 按 50 分钟截止结束：第 132 轮仍有 4737 条未布通网络，无最终 STA/新完整位流；证据及 hash 保留 build/pcm1808-pnr-20261103-125201/result.json，reports/pcm1808_validation_20261103.json 已更新。不要把下述小型诊断当整机完成。
- 为先打通实际音源，新增 pcm1808_diag 构建集/top_pcm1808_probe：直接 27MHz、生产 I2S 从接收＋完整 147/160 FIR＋UART/LED，不含 DDR/NPU/HDMI。F 字段观察实际滤波样本，避免未使用导致 FIR 被综合裁掉。唯一标准全流程 run20261103-134537-c263d9e2 全六阶段 PASS、SourcesUnchanged=true；最终 701 LUT/742 FF/2 APM，十表全部 PASS（setup +29.430ns、hold +0.158ns）。异步输入/输出 IO 存在未约束告警，不代表外部接口认证。
- 位流 SHA256 2856BB4D19390773462EF6830504A772750693D20355411EF0A2C2AB950F1CBE，13:49 复用 JS9040/65420 成功烧入，done=1/CRC=0；原有 cfg46156 未操作，JS 实例保持单一。串口连续收到 A=50434D38；B/C/D=0、G=01，符合未接外部时钟状态，尚无真实音频验收。已通知用户可以接 J2 BCK11/LRCK12/DATA20/GND，MCK/VDD33 不接；诊断期间 HDMI 无输出，不能反复当显示故障回退。
- 27MHz 与原 216MHz 两套实际串行/FIR/CDC 回归均 PASS：两轮无 reset、4096 对输入/3762 对整数 golden 输出，含断钟/LRCK 卡死恢复。构建集及烧录安全 pytest 41 passed，lint 65/0；本轮未重跑全量 pytest，先前完整 436 passed/4 skipped 的范围见旧记录。
- 报告 pcm1808_probe_validation_20261103.json / pcm1808_probe_timing_20261103.json / pcm1808_probe_board_20261103.json；两个早期诊断试验失败保留、不用于烧录。PDS/monitor 已正常退出。下一步用户接线播放后只读串口核实约 48000→44100 对/秒、非零率、正负范围和滤波样本，再集成完整系统；不以采样计数宣称识别准确。当前板上为输入方向诊断，禁止在 PCM1808 时钟接着时恢复旧输出方向位流。五类与 Flash 保留待续。

## 2026-11-03 12:52：PCM1808 精简完整资源门控通过，唯一新映射限时 PNR 中

- run20261103-123749-eb5117d4 的 compile/synthesize/dev_map 全 PASS、SourcesUnchanged=true，正常退出。完整资源 35931 LUT、35508 FF、155/155 DRM、92 APM；较首轮少 3818 LUT/4068 FF，但自动 RAM 分配后 DRM 全满，不能宣称剩余容量增加。历史成功合并至一块 DRM18K，系数 ROM 三块 DRM36K。映射 ADF SHA256 dbee9ac6d2f55228bbb48b02528d410c5df7bd77c2a932bfe1fdcb3ed4c053c6，门控证据 build/pcm1808-gate-20261103-123746/result.json。
- 新源实际串行/FIR/CDC 联合 RTL PASS；全量 pytest 436 passed/4 skipped，烧录安全 16 passed、lint 64/0。改动已提交 9313dba8 并推送当前已有工作分支 XSY2；CPU 用户 diff、PCB、obj_dir 和另一路 group5 未跟踪资产未提交。
- 核验源 hash 未变、无 PDS 残留后，12:52:02 从本次新映射库启动唯一 PNR→十表→位流流程；13:42:02 硬截止，15 秒监控 CPU/日志，存 build/pcm1808-pnr-20261103-125201。不是复用首轮旧映射。当前没有新位流/新烧录；旧板上 BCK/LRCK 仍须断开，既有 JS9040/cfg46156 不动。

## 2026-11-03 12:38：PCM1808 首轮布线超时无位流；精简源联合 RTL 通过，重新资源门控

- 首轮 run20261103-112431-bd9f445f 的 PNR 于 12:32:58 按 50 分钟截止安全结束。放置估计 WNS -2.008ns（不是最终 STA），详细布线第 16 轮仍有 40256 未布通网络；没有最终 PNR 库、十表时序或新位流，未烧录。监控/失败 hash 已保存至 build/pcm1808-pnr-20261103-114253/result.json 并纳入 reports/pcm1808_validation_20261103.json；放置 ADF SHA256 a421a6951559319294a509970068c3563ace888af0021551a6a024fdae643d60。
- 精简 FIR 保持原 14112 项系数逐值不变，以 7104 项基表＋73 相中心抽头微校正重建；历史改为两路 128x16 同步 block_ram 模板，使用有效历史计数补零，不清 RAM。实际串行→FIR→CDC 两轮无 reset 的 4096 对输入/3762 对 golden 输出再次 PASS，含断钟/LRCK 卡死恢复；pytest 3 passed，lint 64/0。系数数值 hash 仍 f8ee7f0f05b9a726fb0345922ddf3dd4247fa2b33146f2151913e127461c8033。
- 12:37:46 启动唯一新源资源门控 run20261103-123749-eb5117d4，止于 dev_map，20 分钟截止、15 秒 CPU/日志监控。不能拿首轮映射资源充作本次优化结果；读到新完整资源后再决定受控 PNR。
- 用户已重插下载器；只读确认 FTDI 恢复，既有 JS9040/cfg46156/65420 未改动。板上仍旧输出方向位流，**BCK/LRCK 继续断开，等待新输入方向位流确认烧录成功**。没有真实音频验收，不重复要求重插。

## 2026-11-03 11:43：PCM1808 联合仿真及整机资源门控通过，唯一新源限时 PNR 中

- 用户实际音源为自带晶振的 PCM1808，固定 I2S master / 48kHz / BCK64FS / 24bit。已将完整系统 U20/BCK 与 T20/LRCK 从输出改为输入，新增两级同步从接收、147/160 的 96tap/147phase 双声道定点 FIR，输出保持既有模型 44.1kHz 契约；不接 MCK。MES-FMC-LPC-IO 紫卡接线见 docs/PCM1808_AUDIO_INPUT.md。**旧板上位流仍输出 BCK/LRCK，新版确认烧入前保持这两根线断开，已告知用户。**
- 实际串行引脚→接收→FIR→异步 FIFO 两轮无 reset 联合 RTL PASS：4096 对输入、3762 对输出逐项整数 golden 一致，含 24bit 低位丢弃、正负满量程、随机立体声、LRCK 卡死及断钟恢复。修复 watchdog 超时后持续清除对齐状态导致无法恢复的问题。原 I2S/CDC 回归 PASS；新增 pytest 3 passed，已有全量 433 passed/4 skipped，lint 64/0。频响通带最大误差 0.00315dB，22.05–24kHz 最差 -69.20dB；独立报告 reports/pcm1808_filter_20261103.json、pcm1808_validation_20261103.json。
- 唯一新源 PDS run20261103-112431-bd9f445f：compile/synthesize/dev_map 全 PASS，SourcesUnchanged=true，正常退出；39749 LUT、39576 FF、154.5/155 DRM、92 APM，容量通过但 DRM 仅剩 0.5。常量 case 系数 ROM 实际推断 6 DRM，不能宣称零 DRM；历史为寄存器。映射 ADF SHA256 c22b303376f93ccdf699c98d65e5a633adaf16caaac301f0d600302c0481cba7，门控监控与 hash 存 build/pcm1808-gate-20261103-112430。
- 确认全部源 hash 未变、没有其他 PDS 后，11:42:54 从本轮新映射库启动唯一 PNR→十表时序→位流流程；硬截止 12:32:54，15 秒 CPU/RSS/阶段日志监控及结果存 build/pcm1808-pnr-20261103-114253。RTL/约束冻结，不复用旧源数据库；当前尚无新位流/时序结论。
- 当前没有新位流、没有新烧录或外部音频准确率结论；保留 2673246E 完整显示基线及 602AB321 fallback。未触碰 cdt_js/cdt_cfg、CPU 用户 diff、PCB 或 obj_dir。五类迁移和 Flash 工作保留，当前优先完成实际 PCM1808 音频接口。

## 2026-11-03 00:10：Flash 固化工具流程打通，第一版烧写镜像已产出（文件层）

- 完成 PDS 位流→SPI Flash 固化的全工具链研究并**实际离线转换**出第一版可烧写镜像 `build/flash_boot/instrec_top_w25q128q.sfc`（3,791,112 B，SHA256 `2673246E…`）。手册 `docs/FLASH_PROGRAM_FLOW_20261103.md`、结构化记录 `reports/flash_program_flow_20261103.json`。
- **格式转换结论**：流程要求 .sbit→.sfc（`cfg_gen_sfc`，cdt_cfg `-file` 批处理可完全离线运行，已实测）；但 X1 模式（opcode 0x0B、`W25Q128Q`）下输出与源 sbit **逐字节相同**——.sbit 即 Flash 线性镜像，仅 X2/X4/X8/偏移/附加数据时才有差异（偏移试验 0x1000→头部 4096×FF 实证）。坑：`-device_name` 必须用 cfl 确切名 `W25Q128Q`（填 `W25Q128` 被拒）。
- **烧写通路**：JTAG 间接烧写（原厂《下载与固化》同路径）：`cfg_jtag_flash_scan_device→readback(备份)→assign_file→erase→program→verify`，复用 cdt_js:65420。MSPI 启动已由原理图实证（`001,MSPI` 标注+R14 上拉 M0），CFG_CLK=H13，Logos2 主 SPI 有 FCS_N/FCS2_N 双片选对应 U15/U9。
- **GTP_CFGCLK 用户模式评估更新**：原语仅 CLKIN/CE_N（时钟通路）；PG2L100H ini 默认 `persist_pin="Release For USER"`——配置复用 IO 用户态释放，用户模式读 Flash 可行性上调，仍需探针实证；最小 JEDEC 读回探针设计已写入手册 §8.3。
- 本轮**零 JTAG/零板级/零 GUI/未改 RTL 约束脚本**；烧录安全回归 16 passed。工作区存在先前遗留改动（cpu/fpga、cpu/rtl 两个 .sv、golden_pipeline_group5.py 未跟踪等），非本轮产生，未代为处置。
- 下一步（上板，按序）：①复用 cdt_js 扫外挂 Flash 读 JEDEC（确认实装型号+哪颗是 FCS_N）→ ②两颗全量 readback 备份 → ③擦写 instrec_top_w25q128q.sfc → verify → ④断电冷启动验收（done=1/crc=0 + COM5 启动横幅 + HDMI 仪表盘）；失败回退 JTAG 直载（jtag_program_latest.tcl 永远可用）。

## 2026-11-02：Flash固化与五类主奏识别双任务交接文档

- 按用户要求新增docs/HANDOFF_FLASH_AND_GROUP5_20261102.md，集中记录两项目标、已有资产与证据、CPU现状/目标分工、实施顺序、风险及验收条件，作为接手入口；实时状态仍以本文最新记录为准。
- Flash仍为可行性评估完成、未实施；五类仍为float资产/复用评估完成、待训练split校准与双头INT8契约/独立留出评估。主导组为主＋五组独立活跃度的语义保持，保留八类2673246E已验收显示基线及其时序FAIL边界。
- 本轮仅文档整理，无RTL/约束/脚本修改，无PDS、烧录或Flash操作；不重复运行已有功能回归。后续分别验证启动通路与模型数值，再集成脱机冷启动，详细下一步见交接文档。

## 2026-11-02 23:10：位流/权重Flash固化任务难度评估

- 用户提出增加位流与权重固化并评估难度。本轮仅评估，无Flash扫描/擦写/新RTL/PDS/板级操作，不改变当前2673246E运行配置与五类迁移方向。
- 已视觉核对100Pro核心原理图p3：U15/SPI0、U9/SPI1两颗标称128Mbit(各16MiB)，共用SPI_CLK至专用CFG_CLK H13；实际焊接/JEDEC待核。现有3.79MB位流与0.69MB权重容量不是主要障碍，先不增加器件。
- 历史CPU软SPI的H13普通IO限制不可照搬占位约束。PDS确有GTP_CFGCLK原语与Logos2映射，是用户模式读Flash候选，尚无PG100映射/实板读回结论。位流固化低中难，权重自动加载中高难；条件估计0.5-1工作日及额外1-3工作日，不承诺当天。
- docs/FLASH_BOOT_FEASIBILITY_20261102.md与reports/flash_boot_feasibility_20261102.json记录方案/原理图及库文件hash。建议先持久位流，再验证用户Flash读，有限缓冲至DDR＋CRC/模型契约核验＋weight_ok门控，保留UART恢复；CPU固件已在位流中，CPU监督、硬件搬运，不复制整份权重到片内RAM。不在评估阶段扩展在线A/B更新。

## 2026-11-02：PaceRV应用部分中文竞赛报告v0.1（文档工作）

- 新增docs/competition/application-report/APPLICATION_REPORT.md，依据用户Word模板与DYH提交4ef1ea1b的CPU_REPORT，按完整五部分起草应用正文，附四个Mermaid图、实际RTL界面截图及证据索引；SOURCES.json保存模板hash与远程来源身份。报告事实截点为本日22:55记录。
- 八类已有实现与五组双头/CPU后处理目标明确分开；保留外部音源未接、诊断位流时序FAIL、NPU249.1ms超200ms预算、新分拍源153.5DRM且未PNR等边界，不引用CPU历史CoreMark作为应用成绩。
- 文档检查通过：章节、主要篇幅、图链/证据路径、461445120 MAC与周期/资源值复核；本轮未修改RTL/约束/脚本，未启动PDS或板级操作。后续以真实音源、五组量化与新完整时序结果修订。开发下一步仍按22:55及后续实现状态推进。

## 2026-11-02 22:55：八类三项分拍资源门控完成，DRM余量仅1.5；五类评估已提交

- run224004-e25e4ce6 compile/synthesize/dev_map全PASS，22:53:40正常退出，SourcesUnchanged=true；33640LUT/35394FF/153.5DRM(155容量)/90APM。报告replay_pipeline_resource_gate_20261102.json包含数据库/源/日志/监控hash；PDS与monitor退出，临时防休眠释放。
- 仅按门控止于dev_map，未启动PNR/未做新时序/无新位流；manifest将未执行后续阶段写FAIL是脚本既有表示，不能误报为已尝试布线失败。用户现阶段优先五类复用评估，因此本轮不延伸八类PNR；当前八类2673246E实屏正常版本保持。
- 五类评估fb641ad4已push，完整训练cache只读确认44091x64x130、35185训练/8906验证、labels/dominance/mask齐全；可以直接准备新量化校准，无需用户重给资产。五类需显式缩减缓存/串行双头，不能凭时间维减半假设DRM必然降低。下一步训练split校准、BN折叠/双头INT8契约和独立留出集评估；保留八类基线与全部证据。

## 2026-11-02 22:50：用户恢复五类迁移，确认“主导组为主＋五组活跃度”；复用与CPU评估完成

- 用户认为八类阶段基本可用，要求开始五类迁移并先评估复用与CPU作用；已明确五类主导组为主，同时显示五组活跃度。不再维持“迁移暂缓”的任务设定。保留八类2673246E已验收中文显示基线，不在本轮评估中改生产数据通路。
- docs/GROUP5_REUSE_AND_CPU_ASSESSMENT_20261102.md给出逐模块复用、CPU现状/限制、新分工与实施顺序；GROUP5_MIGRATION已标记恢复。冻结float资产全部hash重核，严格重载后5参考样本的双head logits逐值完全一致；不是量化或精度新验收。报告group5_reuse_assessment_20261102.json。
- 卷积核/通道与旧NPU相同，64x130窗口使理论卷积MAC为旧50.2%；GAP4x8/32。双独立FC头可串行复用硬件；纯INT8权重716976B（不含bias/量化/对齐），比旧纯权重增加33024B。前端FFT/Mel核心复用，但66150样本、130帧/统计域、输入量化与replay/GAP/FC调度必须重做契约。主导head不得用activity argmax替代，无活跃时不强选。
- CPU生产实例实际RV32I（ENABLE_M=0），8KiB ROM/8KiB RAM；默认NPU_ENABLE=0，CPU真实请求/ACK并请求下一轮，RTL守卫Mel/DDR安全条件。当前只回读最后概率事件与top1并串口报告，UI直接由NPU驱动，尚无完整向量/业务后处理；作为控制核合理但职责偏薄。建议NPU算卷积与双FC，CPU读取同帧10logits，定点sigmoid/softmax/mask/归一/主导决策/可选平滑/超时有限重试并原子提交UI。需扩MMIO完整快照，不能只改固件。
- 当前唯一八类三项分拍资源门控run224004-e25e4ce6仍在synth保存数据库，CPU有推进、compile已PASS；23:10审查不变，未启PNR/未烧录。保留八类门控结果作为基线；五类后续先新量化契约与留出精度评估，不复用旧8类量化参数或以理论MAC承诺完成时刻。

## 2026-11-02 22:41：三项分拍修复新源唯一资源门控启动

- 冻结3ea8f787，run build/pds/20261102-224004-e25e4ce6于22:40:04启动，StopAfter=dev_map；exec12001、monitor76991、父33492及同run编译子进程，不是并发工程。15秒CPU/RSS/阶段/日志监控及临时防休眠，23:10截止审查；不修改冻结RTL。当前编译中，无资源/时序结论，无新位流。
- 读取完整映射容量后再决定受控PNR；已有2673246E板上中文UI已验收，保持运行，不重复烧录。既有cdt不动。

## 2026-11-02 22:39：NPU重放到卷积输入分拍，真实CPU/native两轮golden通过

- npu_top在两路activation store的字节lane选择后寄存8bit payload与valid，再进入conv输入RAM，切断长距离RAM/mux/RAM路由链；两接收端原本固定ready=1，吞吐仍每拍1字节。payload无reset，valid在复位及对应layer start清空。store本体/DDR契约/八类算术不变。
- 生产ROM+frame-major真实布局、native DDR模型、不同A/B全16512特征字节改变、无reset两轮：所有conv/pool/GAP/FC/logits/probs中间结果逐值golden PASS，CPU两次请求/ACK闭环且第三次请求排队。每轮实际31141255cycles（较原31141202增加53拍），CPU报告31141254；run_repeat改为从日志提取实测周期数，新增--report保存独立证据，避免硬编码旧周期或覆盖历史报告。reports/cpu_native_store_replay_pipeline_20261102.json含完整源hash。
- npu_completion/full_top_ctrl实际RTL PASS；pytest433passed/4skipped，lint61/0，reports/store_replay_pipeline_validation_20261102.json保存hash。当前修复源尚未PDS/无新位流，不能宣称负裕量已消除。
- 当前板上仍2673246E中文完整诊断版，用户实屏已确认正常稳定；不重复烧录，602AB321 fallback保留。下一步对包含glyph/self_test/store三项分拍的新源建唯一完整资源门控，容量允许后受控PNR核验十表。既有cdt未动，未接外部音源，不宣称识别准确率。

## 2026-11-02 22:28：用户确认新版中文仪表盘正常且稳定

- 用户同时补回三项反馈：已重插下载器；此前602AB321显示保底彩条及KEY1 UI均正常；当前2673246E完整系统中文仪表盘正常且稳定。两份对应板级报告已记录实屏PASS，反馈不再待到；无需再次要求重插或重复询问。
- 结合此前CPU/MMIO/ISA/DDR自检、WOK及六轮NPU/CPU回读，完整系统具备已观察到的基本运行与中文显示闭环。视觉确认不消除该诊断位流的setup/hold负裕量，也不等同长时稳定性或识别准确率验收；外部音源仍未接。
- 当前板上保留2673246E，不重复烧录或恢复旧演示；602AB321 fallback继续归档。71f8810f文字glyph与7d097105自检分拍均尚未PDS，继续store/conv路径修复及新源资源/时序门控。无PDS运行，既有cdt不动。

## 2026-11-02 22:14：DDR自检长路径分拍，三项RTL与全量Python回归通过

- self_test在FIFO读数据后新增256bit无reset payload寄存及valid，比较/状态独立下一拍；读完成abort witness同步增加一拍，原始done仅在ST_RDATA采集，避免上次写完成残留误报读abort。外部端口/4KB模式/命令保持/读流吞吐不变；结果内部晚一拍，最后beat优先于abort契约保持。Python cycle model与源优先级断言同步调整。
- self_test实际RTL扩为12项检查：完整128beat、写/读abort、无reset恢复、最终beat最高bit翻转失败及正确命令地址、sticky结果和再次无reset恢复；最终PASS。修正测试响应器在done周期重复grant旧held命令及restart采样时机；中间失败摘要保留，不掩盖首次尝试失败。ddr3_subsys与ddr3_aw_timeout实际RTL均PASS，23项模型/契约PASS；全pytest433passed/4skipped，lint61/0。
- reports/self_test_read_pipeline_validation_20261102.json包含RTL/TB/模型与原始日志hash。尚未PDS/无新位流，不能宣称core负裕量已消除。当前板上仍2673246E诊断完整系统，新中文UI实屏反馈待用户；没有重复烧录/要求重插，既有cdt未动，无PDS运行。
- 下一步处理NPU store到conv RAM路由长路径，再对包含文字glyph与self_test分拍的新源建立唯一完整资源门控并受控PNR；保留602AB321 fallback及所有失败时序证据。未接外部音源，不宣称准确率。

## 2026-11-02 22:02：新版完整系统已烧录，启动/DDR/WOK/六轮推理PASS；时序仍FAIL

- run211104的PNR/report/bitstream均正常结束，21:55:03生成2673246ECAC0ECB3E00721C53EFD6B941CC0E8CA44022064AE36C21941D89318；PDS/monitor零残留，临时防休眠已释放。报告ui_dashboard_full_build_20261102.json保存位流/完整时序/源清单/阶段日志/监控hash。
- 完整十表时序FAIL：slow pix setup -2.708ns/32端点，core setup -1.267ns/1393端点；slow/fast core hold -0.011/-0.009ns各1端点。仅诊断候选，不是稳定交付。具体路径为tiles RAM经百分比格式化到font RAM、DDR FIFO读经256-bit self_test比较到状态、NPU store到conv RAM写入；后两项待修复。
- 安全复用JS9040/cfg46156烧录该完整新UI候选，program成功/done1/CRC0，实收RV32 BOOT/MMIO OK/ISA OK/DDROK；691040B权重2700帧上传返回WOK FA0D5236、UPLOAD OK。随后12秒6次NPU完成/CPU回读，每轮约3236万cycles。reports/board_dashboard_20261102_2155.json含唯一raw/TCL/UART/上传日志hash。启动捕获含烧录前UIDEMO残留，不能将其当新设计输出；上述启动token与上传后NPU行均来自新完整设计。
- 当前板上为2673246E完整系统，已询问新版中文dashboard是否稳定，用户屏幕反馈待到；此前602AB321显示fallback完整保留，不覆盖。外部音源未接，不宣称识别准确率。
- 已推广预先验证的文字时序修复：八路百分比先并行寄存为glyph包，再由tile选择，移除tile读后十进制算术，视频仍四拍。dashboard_ui实际RTL重跑PASS23.1s，五状态全帧与原始输出逐字节/hash一致；lint61/0，报告dashboard_digits_timing_fix_20261102.json。此修改尚未PDS，当前烧录位流不包含它，不能声称像素负裕量已消除。
- 下一步先收实屏反馈，异常时恢复602AB321；继续修复self_test比较与store/conv路径，跑相关回归。新RTL须新建唯一完整资源门控，再限时PNR读取全部时序；旧映射库不得冒充新源。当前无PDS运行，既有cdt均未动。

## 2026-11-02 21:34：FTDI恢复，显示保底已重新烧录；新版PNR详细布线

- 21:30系统已枚举FTDI A/B与COM16/17，COM5亦正常；安全复用JS9040/cfg46156读取状态done0/CRC0，确认重新上电后未配置，报告board_online_status_20261102_2130.json。无需继续要求下载器重插。
- 21:33已烧此前用户验收的602AB321显示保底（hash再次核对），program成功/done1/CRC0、COM5实收38129字节UIDEMO；raw/TCL/日志单独保存在build/board-fallback-20261102-2133，报告board_fallback_20261102_2133.json含hash。用户当前彩条/KEY1 UI反馈待到；这不是新版dashboard，也不是完整AI系统。既有cdt实例保持，下载器烧后仍在线。
- 新版run211104 PNR已进入详细布线，placement估算WNS -1.387ns/TNS -28.950ns（非最终报告），全局布线21:34到0后详细布线起始1857未布通。继续同源单路、22:10截止审查，无新位流/最终时序，不以placement估算作为验收。

## 2026-11-02 21:27：新版完整资源门控PASS，唯一PNR限时进行

- run211104-aedccc03 compile/synthesize/dev_map全PASS，21:23:57正常退出，SourcesUnchanged=true；完整映射33462LUT/35118FF/147.5DRM(155容量)/90APM。新font_bits4个DRM36K、tiles2个DRM36K，HDMI27路输出全部实测OFF打包。reports/ui_dashboard_resource_gate_20261102.json含原始map数据库/日志/源hash；容量PASS不等于可布性或时序PASS。
- 21:25:09复用同映射库启动唯一PNR（stage-20261102-212509-a0cc741c）；使用plain pnr，无种子覆盖。当前全局布局进行中，15秒监控阶段/CPU/RSS/日志，临时防休眠；22:10截止审查，不无限等待。无新位流/最终时序；FTDI缺失重插回复仍待，COM5存在，cdt未动。

## 2026-11-02 21:16：用户恢复板子上线，完整新版资源门控进行中；FTDI待恢复

- 用户明确授权开始烧录调试，离线阶段限制解除。COM5已出现且可读，6秒只读捕获0字节；FTDI PnP仍缺失，已请用户仅重插下载器电脑端USB，尚未收到回复。既有cdt_js9040端口正常/cdt_cfg46156保留，未终止、重启或新建JTAG服务；尚未烧录新位流。
- 新UI源7d143626首次资源门控run210140-5c55ca93在PDS预解析子进程退出清理挂起：CPU4.53s长期不变、无compile目录；等待链/栈为Tcl_Exit/onexit/Thrd_join等待处于LdrShutdownThread的工作线程。21:10保存日志/清单/hash后只结束该run的两个PDS进程；无编译/无位流。未将外部DLL加载或许可证即将到期提示推断为根因。
- 修复run_pds_full的StopAfter：exit仅在正式执行阶段存在open_project命令时执行，预解析跳过退出；同样保护run_pds_stage末尾exit，避免后续PNR预解析重现。实际生成TCL分别在预解析/执行命令环境验证继续扫描与正确止于dev_map；tests/test_build_tokens.py共25passed，stage PowerShell5.1解析PASS。证据reports/pds_preparser_exit_fix_20261102.json。
- 唯一新run build/pds/20261102-211104-aedccc03于21:11启动，仅compile/synthesize/dev_map。compile21:13:31 PASS，目前综合tech-mapping2；15秒监控阶段/CPU/RSS/日志，临时防休眠随进程退出释放，截止21:41审查。源码清单冻结，不并发PDS。读取完整容量/字体与图块DRM推断后才决定PNR；当前无新资源结论、无新位流。
- 继续原八类模型；新UI实际仿真PNG已通过，不等于时序或板测通过。旧HDMI fallback/两轮PNR失败证据保留；外部I2S音源尚未接，不能宣称识别准确率。

## 2026-11-02 20:07：中文仪表盘改版已实现并通过实际RTL全帧仿真

- 按用户要求仅做离线UI优化：左上“输入波形”解释声音振幅/时间，左下独立Mel频谱说明时间/高低频带/能量色阶，右侧最近完整识别结果及带中文类别名、数字百分比的八条置信度；深色卡片/青色高亮，原八类单标签模型不变。设计及重建说明见docs/UI_DASHBOARD.md。
- 新dashboard_renderer/dashboard_text接入instrec_top；保留完整特征页/概率快照的帧边界提交。bars_data增加frame_ready，首次完整结果前显示“等待识别”及--%，不把复位类别0冒充识别结果。视频RGB/DE/HS/VS统一四拍；字图及图块为同步ROM、无payload reset。旧显示演示分支/已确认位流保持。
- 实际RTL生成1920x1080等待/正常/0%/100%/越界五帧，共10368000有效像素；每帧计数、同步四拍、波形缩放、64x258频谱方向与完整范围、RAM边界、卡片边界、2000个条形内部像素PASS；100与255输入完整帧逐字节相同。五项RTL回归dashboard_ui/dynamic_ui/text_pipeline/ui_render/full_top_ctrl全部PASS；dynamic_ui含首次ready/帧中稳定检查。lint61文件0违规，pytest432passed/4skipped。
- reports/ui_dashboard_ready_20261102.png及waiting/full_scale/zero/clamped均来自实际RTL的PPM，已视觉检查等待/正常/满量程；示例波形/频谱/概率为合成夹具，显示“仿真演示”，不是实采或准确率证据。报告ui_dashboard_validation_20261102.json含RTL/ROM/PNG及仿真日志SHA256。gen_dashboard_assets.py重生成逐字节相同；冻结字图纳管，无需字体即可仿真，scripts/render_dashboard.py可一键重建实际预览。
- 本轮未启动PDS/未烧录/无新位流；新UI资源推断与最终时序尚未验证，不能用仿真PASS宣称动态花屏板测已修复。板子按用户要求暂不上线，无外部音源。前两轮PNR失败证据保留，cdt/下载器未操作。
- 下一步：板子可用前继续离线开发；重新进入硬件阶段时，先对这版新源做唯一PDS资源门控（旧133.5DRM映射不能复用），容量允许后受控PNR并核验完整时序，再进行实际动态显示及外部I2S验收。原有core-only生成脚本已有LED区域旧锚点失配，本轮未改它或重生成历史top。

## 2026-11-02 19:50：用户转向仿真优化UI；板子暂时断电/拔线，不上板

- seed1在约2717 CPU秒仍剩3638连接，默认布局约2715秒时剩916；未见可布性改善，19:40提前保存完整布局/TCL/日志/hash后结束，报告dynamic_ui_seed1_stop_20261102_1940.json。两轮均无新位流/最终时序。PDS与监控零残留，防休眠请求释放，既有cdt未动。
- 用户确认当前断电或拔线，暂不能上板；当前USB缺失符合连接状态，不再要求重插。新任务：基于实际RTL仿真重做显示布局、中文说明、频谱位置、八类置信度标签与输入波形解释；本阶段不启动PDS、不烧录。保持原八类单标签模型。
- 设计：左侧上下独立波形/频谱卡片，右侧结果及带乐器名/百分比的八类条形图；中文标题、时间/振幅/Mel频带/能量含义、空态与仿真演示标识。以实际RTL全帧导出PNG验收，不能用软件示意图冒充硬件渲染。

## 2026-11-02 18:58：显示修复候选首轮PNR未完成，已按截止保存并结束；准备单种子替代布局

- bca1fce8源的完整资源门控PASS（33447LUT/35106FF/133.5DRM/90APM、27路HDMI OFF），功能回归通过；但run171830-91e7a308首轮默认PNR到18:55仍有未布通连接，停止前最后采样1163轮/275条。布局估算+0.541ns不是最终时序PASS，本轮无位流、无最终时序。18:35仅补回监控19m22s暂停窗口后未再延长。
- 已归档完整place_route、原始stage日志、源清单、监控和hash至该run/bounded-stop-20261102-1855；报告dynamic_ui_pnr_bounded_stop_20261102_1855.json。PDS零残留、monitor正常退出、临时防休眠请求释放，cdt_js9040/cdt_cfg46156未动。
- 为避免同默认布局重复陷入局部拥塞，run_pds_stage新增可选PlacementSeed，仅From=pnr可用；默认行为不变。PowerShell解析PASS，构建令牌测试24passed。18:58:14同源同映射数据库单路seed1 PNR已启动（stage-20261102-185814-d54f1838，子进程明确-gplace_seed 1）；19:03全局布局checksum D9A3386988729C3A与默认D92E2C18BEEFAC1E不同，确认替代布局生效；19:07布局估算+0.687ns/TNS0，19:09进入74138网布线、19:11全局布线完成，19:31详细布线80轮剩5951条/CPU2218s（非最终时序PASS；新种子可布性改善尚未证明）。源清单再次hash零变化，证据dynamic_ui_seed1_progress_20261102_1932.json。不改生产RTL、不重综合；新一轮独立限时审查20:00，前次完整证据不覆盖；15秒监控含临时防休眠请求。
- 最后成功烧录CDE1D2F6诊断版：16:55-16:58的CPU/DDR/WOK与6次推理完成有证据，用户UI可见但动态花屏FAIL。19:09只读实时复核时COM5不存在，串口枚举与VID10C4/0403现存设备均空；当前运行状态无法实时确认，不能沿用历史记录称此刻仍连续推理。报告board_readonly_cde_20261102_1909.json。未操作USB/驱动或cdt；尚无外部音源。

## 2026-11-02 17:33：完整UI可见但动态内容花屏；修复布局/换页/快照与dB转换分拍，回归通过

- 用户重插FTDI USB后，CDE1D2F6诊断位流成功program/done1/CRC0，实收RV32 BOOT/MMIO/ISA/DDROK；权重2700帧、WOK FA0D5236成功，12秒6次NPU完成/CPU回读。用户确认有UI，但频谱/置信度出现错位、撕裂、花块或条纹，属于显示内容验收FAIL，不再是无信号。报告full_cde_diagnostic_board_20261102_1655.json含唯一raw archive/hash。此版时序仍FAIL，未接音源，不宣称准确率。
- 下载器随后再次从PnP消失（CM_PROB_PHANTOM），17:07恢复演示尝试在烧录前被阻止；板上目前仍CDE1D2F6，不是显示保底。既有cdt_js9040/cdt_cfg46156保持，未终止/重启。无需现在反复重插，下一次烧录前再处理。
- run165021-256e7b77单路compile/synthesize/dev_map成功，SourcesUnchanged=true，32156LUT/35073FF/133.5DRM/90APM；label256x6已推断DRM18K。按门控止于映射，无PNR/无位流；新增显示修复后不能复用此旧源数据库。报告label_resource_gate_20261102.json。
- 已修复实际UI接线问题：frame-major特征复制时转为64x258行布局；频谱首次完整页前屏蔽，经toggle同步后只在vsync换页；概率流收齐8类后以held bundle/request-ack传递，类别与8路概率同帧提交，拒绝部分流、百分比钳位。bars采用两拍坐标+一拍绘制，spectrum直接原坐标、地址/RAM/色彩三拍，valid同延迟，均与waveform三拍对齐。HDMI27个数据/同步输出增加PAP_IO_REGISTER约束，实际打包与物理采样仍待PDS/板测。
- 路径详细预算显示RAM/dB转换自身仍长，因此db_norm再分RAM读/差值/乘法/舍入写四拍，统计沿用上拍寄存累加；payload无reset，FSM保证初始化后才使用。Mel5144053cycles、16512特征golden0差异，实际125MHz约41.2ms，低于150ms需求。
- dynamic_ui新RTL测试PASS：两窗口33024页字节/转置/读口stall/帧边界换页/初始化屏蔽，概率完整快照/部分流拒绝/饱和/复位及帧中稳定；16000坐标逐像素RGB/on三拍对齐PASS。mel/mel_credit/db_norm_stats/text_pipeline/ui_render/full_top_ctrl另6项PASS；pytest432passed/4skipped，lint59/0。证据dynamic_ui_fix_validation_20261102.json。新源尚无PDS时序/新位流。
- 源bca1fce8资源门控run20261102-171830-91e7a308于17:32:30正常完成compile/synthesize/dev_map，SourcesUnchanged=true；33447LUT/35106FF/133.5DRM/90APM，容量可用。27路HDMI输出全部实测打包OFF（含复制的共享颜色寄存器），label256x6仍推断DRM18K。报告dynamic_ui_resource_gate_20261102.json保留mapADF/日志/hash；门控阶段无PNR/无位流。17:33:48已复用当前数据库启动单路PNR（stage-20261102-173348-e829e027）；17:41布局估算最差+0.541ns/TNS0，17:43进入74324网布线，17:46全局布线0未布线后进入详细布线；18:35审查详细布线迭代414剩727条、CPU2789s持续推进（非最终时序PASS）；监控18:09:24至18:28:47断档19m22s，疑似系统暂停而非PDS持续计算。仅补回该暂停窗口至18:55再次截止审查，报告dynamic_ui_pnr_deadline_review_20261102_1835.json；临时防休眠请求随PDS退出释放，不改永久电源设置，继续15秒CPU/日志监控；源码冻结。显示恢复与整机动态验收未完成；真实音源仍未接。

## 2026-11-02 16:50：完整修正版时序未过，已针对剩余两条路径修复并完成功能回归

- run20261102-155516-512e7322六阶段正常结束，SourcesUnchanged=true，位流CDE1D2F660CA0A44D3BF212D5EF0DC8DA0B40B19F12C1CDDA3E4390A17A2B4F9；post-PNR32074LUT/35059FF/133DRM/90APM。完整10表报告FAIL：slow core setup -2.933ns/6584端点，pix setup -0.456ns/6端点；其他检查均PASS，音频与recovery旧违例消除。未烧此版，板上保留用户确认正常的602AB321彩条/UI。报告full_corrected_build_20261102.json、full_timing_corrected_20261102.json；PDS/monitor均正常退出。
- 精确失败路径为spec_bank_0输出到db_norm.sum_db、top1_s0到text_disp.char_code_r。db_norm改在RD与末尾flush累加上拍寄存dB，避免RAM/dB转换/48位加法串联，统计脉冲及周期数不变。文字REGISTER_CHAR路径改同步label ROM读及独立百分比寄存，三拍/legacy两拍不变。尚未有这两项修改的PDS结论。
- 新db_norm_stats六组不同窗口无reset：零、正负极值、斜坡、末值最大与丢弃头帧最大，保留区12写/有符号sum/square-sum/末尾flush逐项PASS；mel16512特征golden、mel_credit、text_pipeline全部PASS。lint59文件0违规，pytest432passed/4skipped。证据timing_path_fix_validation_20261102.json。
- 构建脚本WNS/WHS修正为slow corner所有clock行最小值，避免首行音频+0.867掩盖core -2.933；实际完整负例/显示正例验证PASS。完整验收仍以summarize_timing十表为准。HDMI管脚属性对照无差异，但外部接收器时序未证明，见hdmi_full_vs_display_review_20261102.json。
- 下一步提交后只启单路compile/synthesize/dev_map门控，核验同步label ROM推断和完整资源，再受控PNR；不以功能仿真代替时序闭合。真实音源仍未接。

## 2026-11-02 16:25：完整诊断版显示失败，已恢复显示保底；修正版详细布线中

- 用户要求重烧489EF753完整诊断位流，program/done1/CRC0及RV32 BOOT/MMIO/ISA/DDROK实收通过；但权重重载第814帧无ACK失败，后续8秒UART无输出，用户明确确认默认HDMI无信号。完整系统显示验收FAIL，不能沿用早先WOK/6轮完成证明当前运行正常。报告full_system_reflash_20261102_1614.json与build/pds/20261102-140426-6c67b772/board_reflash_20261102_1614保留证据。根因未确定，旧位流已有负时序。
- 已恢复曾获用户确认的602AB321显示保底，program/done1/CRC0、49868字节UIDEMO实收通过；原始UART/TCL/log独立冻结build/board_display_fallback_20261102_1620，hash在display_fallback_restore_20261102_1620.json。用户已确认本次恢复后彩条和UI均正常；板上当前为固定演示数据，非完整AI系统。
- 修正版run20261102-155516-512e7322仍是唯一PDS flow，16:24全局布线第78轮至0未布线网后进入详细布线，日志/CPU有进展。完整时序/位流尚未产出；17:10截止审查不变。未修改构建冻结生产源码，未终止/重启既有cdt。
- 更正文档：八类权重镜像实际691040字节，2700帧是末帧含填充的传输帧数，不能将2700x256当实际文件长度。保留早先成功与此次失败两份证据。

## 2026-11-02 16:13：最终完整候选进入PNR，音频接口核对完成

- 源提交bd295a96，run20261102-155516-512e7322，15:55启动完整compile/synthesize/dev_map/pnr/report/bitstream流；compile/synthesize/dev_map均已完成，映射32206LUT/35057FF/133DRM/90APM；约16:10进入PNR，16:13已完成全局布局，正在post-global placement。唯一PDS flow，父子进程属于同一工程；full-monitor.jsonl每15秒记录阶段日志/CPU/RSS，17:10为完整流截止审查，不能无限等待。尚无本轮位流或时序结论。
- 新增scripts/summarize_timing.py覆盖slow/fast共10种summary，实际旧完整负裕量、已验收显示正裕量与伪全绿截断报告三项验证PASS；不完整报告禁止PASS。旧完整报告结构化归档full_timing_diagnostic_20261102.json。
- 生产framer两处边界修复后，mel/mel_credit/framer_repeat三项PASS；后一项带间歇out_ready并检查两个不同PCM窗口的1060864样本。native CPU A/B报告独立归档为cpu_native_timing_resume_20261102.json，原先full-continuous报告保留，避免覆盖旧证据。
- 已核对100Pro核心原理图p6、底板p9/p5并渲染检查：U20/T20/V16分别扩展网FMC_LPC_LA07_N/LA07_P/LA03_P，当前16bit紧凑Philips主机I2S44.1kHz；不是底板现成模拟音频口。MS7200 HDMI RX另有I2S，但本设计未接入其从机时钟采集，不能直接当已支持音源。docs/AUDIO_BOARD_ACCEPTANCE.md与reports/audio_pin_review_20261102.json记录协议/引脚/PDFhash。真实音源仍未接。
- 维持用户已选原八类版本，GROUP5_MIGRATION已标注暂缓。下一步等待本轮映射容量与完整setup/hold/recovery报告，再按证据决定候选烧录；保留HDMI fallback及当前489EF753诊断版WOK/CPU循环证据。

## 2026-11-02 15:53：资源门控完成；补齐连续窗口原有缺陷，准备最终候选重建

- run20261102-153838-0eeebb9d compile/synthesize/dev_map全PASS，结束时SourcesUnchanged=true；32236LUT/35057FF/133DRM/90APM，head/tail各1Kx16确认为GTP_DRM18K_E1，比上一完整候选减少1012LUT、增加1DRM。监控记录阶段/CPU/RSS/日志；该run按设计止于映射，无PNR、无位流，禁止当完整时序通过。报告reports/timing_resource_gate_20261102.json。
- 新framer_repeat反例明确复现ff3548bd原始基线帧尾win_valid粘住；仅清空valid后继续复现第二窗口frame_base未重置。生产现已两处修复：idle清空有效流水，win_start时环形读基址归零；DSP payload无需复位，valid/control清空。隔离候选对两组不同PCM共1060864个Hann/reflect样本逐值PASS，额外out_ready间歇stall版本PASS；原始反例/单修复源/组合修复源与hash保留，见framer_repeat_validation报告。
- 先前21项RTL suite + 新requant_reset PASS；真实生产ROM/真实frame-major/native DDR不同A/B两轮无reset各31141202cycles、全部中间层与结果golden exact，报告timing_resume_validation_20261102.json。合入边界修复后mel/mel_credit/framer_repeat三项全PASS，真实Mel16512特征0差异；lint59文件0违规。
- 下一步只用包含边界修复的新源码新建单PDS完整流；旧映射数据库不复用为修复版。完整候选时序仍未验收，板上仍489EF753诊断版，已WOK且6轮CPU回读；未接音源，不宣称真实音频识别准确。

## 2026-11-02：用户决定维持原八类版本，继续时序与完整板级闭环（当前有效目标）

- 用户明确“维持原来的吧，继续工作”：恢复八类单标签识别交付，暂缓五组活跃度迁移；五组float资产保留，旧目标纠正条目仅作历史。巡检已同步更新，不再等待模型方向选择。
- 板上489EF753诊断候选完成691040B/2700帧权重上传和DDR读回，真实回复WOK FA0D5236、UPLOAD OK。随后12秒UART捕获6次NPU完成/CPU回读，约3236万cycles/轮；报告reports/board_weights_resume_20261102.json含image/日志/捕获hash。未接外部音频，不能以悬空/静态输入完成代替真实音频识别准确率验收。
- 时序修复候选：standardize将RAM读后减法/乘法/舍入/量化分为6拍，保持全部定点舍入；framer head/tail改同步读并推迟一拍ring写元数据，移除异步大mux；audio FIFO注册next-pointer full，移除Gray比较到WEA路径；full文字内部寄存char/font地址前级，替换原坐标延迟，整体三拍不变，显示fallback默认路径不变。
- framer/requant仅移除DSP payload复位，valid/control保持异步清空，针对此前DSP recovery高扇出路径；requant独立1000输入/27次中途异步复位黄金算术PASS。FIFO容量/丢弃/计数饱和/回绕/并行双时钟/复位PASS，文字8类/6种百分比/区域逐像素延迟对拍PASS，修改后Mel16512特征0差异PASS。pytest432 passed/4 skipped；全RTL回归正在运行，尚未有本次候选完整PDS时序结果或新位流。
- 下一步完整回归后单PDS容量门控，核验head/tail DRM推断和资源，再受控PNR读取全部setup/hold/recovery；保留旧诊断位流与失败证据，严禁以功能PASS代替时序闭合。外部音频源仍未接。

## 2026-11-02：用户纠正目标，切换五组多标签活跃度（最高优先级）

- 用户明确要弦乐、铜管、木管、键盘、打击的活跃度；旧8类具体乐器softmax不是目标。此前模型选择有误，停止旧模型权重上传（尚未上传），旧golden PASS只保留为历史硬件证据，不作为目标任务验收。
- 已核对兄弟InstRec工程网页端与真实训练checkpoint：group5_v3/best_model.pth，epoch22，DualHeadInstrumentCNN；SHA256 5ada8db602427af8b5c7ba01aa581f5852ebf2b884d94932c821fe44cf22b636。训练顺序strings/woodwinds/brass/percussion/keys；五个独立sigmoid可同时活跃，主导度另有独立head，禁止混淆。
- 正确输入44100Hz/66150样本/64x130 Mel，当前64x258、GAP64和8类softmax契约需整体迁移。已冻结正确float权重、模型源、配置、真实留出特征和双head参考输出到models/group5_v3_float_20261102；独立从冻结NPZ重载，资产hash与双head logits逐值完全一致PASS。尚无新INT8契约或五组RTL推理PASS。迁移清单见docs/GROUP5_MIGRATION.md。
- full run20261102-140426-6c67b772已完成PNR/位流，33248LUT/34986FF/132DRM/90APM；SHA256 489EF753C45A2F10315230B95E3AC004B17BDC6D503A468279BFCD9E26F2E5EF。Some Constraints Violated：slow core setup -2.811ns、pix -0.881ns、audio -0.413ns，另有recovery负裕量；仅诊断候选。
- 已烧录该完整候选，done1/CRC0，真实RV32 BOOT/MMIO OK/ISA OK/DDR3 SELFTEST/DDROK均实收；报告reports/full_system_board_20261102.json。原始UART/TCL/log已冻结至该run的board_boot_20261102，hash在full_system_integration报告。板上没有正确五组模型，不宣称识别成功。PDS已退出，既有cdt未终止或重启。
- HDMI固定数据保底已由用户实屏确认，codex/display-demo保留；用户尚未接音频源。下一步先正确checkpoint的BN折叠/INT8校准与新golden，再130帧特征/空间尺寸/GAP/五路sigmoid/CPU/UI联动迁移，同时处理完整系统时序；不得继续旧模型上板部署。

## 2026-11-02 14:13：回归完整系统，RV接入音频与HDMI全拓扑

- 用户确认显示参考图与实屏完全一致，保留codex/display-demo作为可回退演示；按要求恢复完整项目。用户另确认尚未接外部音频源，真实音频板级验收目前缺输入硬件。
- full/instrec_top接入真实RV32I子系统、MMIO安全窗口请求/结果回读、三路共享UART握手保护，保留外部I2S与Mel/NPU/实时UI链；新增G25物理HDMI复位并迁入已上板通过的下降沿输出。audio_sink在sys_run前屏蔽样本，避免启动自检被m0写入干扰。
- 生产固件在每次结果ACK后请求下一Mel窗口，ROM2320B；真实CPU C1-C10 PASS。full_top_ctrl直接抽取本次完整顶层逻辑，17项PASS；I2S外部波形16字/idle/复位PASS；RTL59文件0违规。完整pytest432 passed/4 skipped，构建清单测试已适配full所需共享CPU源和.sv文件。
- 当前生产ROM + frame-major真实Mel布局 + native DDR/NPU不同A/B两轮无reset golden全链PASS；每轮31141202cycles，16512个输入字节全部改变，2次完成/ACK后第3次请求保持待发。证据reports/cpu_native_continuous_validation_20261102.json；不等价真实PHY/音频/板级。
- 唯一PDS run build/pds/20261102-140426-6c67b772，full资源门控只到dev_map；compile2m19s成功，综合资源33253LUT/34997FF/132DRM/90APM，映射完成为33248LUT/34986FF/132DRM/90APM、SourcesUnchanged=true；14:19复用数据库开始单路PNR，14:24已完成全局布局，15:04截止审查。整套RTL仿真19/19 PASS。尚无完整新位流，板上仍为已验收602AB321显示候选。
- 下一步读完整dev_map资源，容量可用则复用数据库单路PNR并监控进展/时序；完整候选出来后板级启动、权重WOK与推理回读。保留所有失败记录，不操作或重启既有cdt进程。

## 2026-11-02 14:00：用户确认彩条与UI均正常，导出实际RTL参考帧

- 用户反馈下降沿输出602AB321候选“都正常”，默认彩条与按住KEY1的UI均可见；本次板级可视验收PASS。该结论不替代外部电气时序或长时稳定性验证。
- 用户询问左上蓝块：实际RTL全帧导出ui_frame PASS，2073600像素；参考图reports/ui_demo_expected_20261102.png。蓝块是(80,80)起512x256固定演示频谱，深蓝/蓝/青三条带覆盖部分顶部绿色包络，属于当前布局。右侧Piano 72%与紫色最长概率条一致。
- 当前显示专用位流仍为固定演示数据，尚未接真实I2S/识别结果；保持当前板上版本，不因解释UI再次烧录。完整RV+AI+I2S+HDMI集成仍开放。

## 2026-11-02 13:52：下降沿HDMI输出候选已烧录，待UI实测

- 用户进一步明确：9F0181AD彩条可见，按住KEY1后显示器明确提示无信号；原厂1080p60可见。UI路径尚未修复，不宣称仅内容异常。
- 全帧ui_raster逐拍HS/VS/DE对拍两帧PASS；物理输出边沿候选源f4757301，run20261102-134737-7cc2b17b六阶段成功，完整All Constraints Met，slow setup+0.544ns/hold+0.346ns，1030LUT/952FF/1DRM。
- 位流602AB321075B25F0F9931C99CC7369AB1223E3A27A0177953F20F2DDFE60A17C已program成功、done1/CRC0，UART 64025字节，末帧G07/H81；默认彩条、按住KEY1切UI。外部采样相位是假设，尚待用户反馈，不能据内部时序称物理MS7210输入时序已证明。
- reports/hdmi_halfcycle_board_20261102.json保存本次摘要，原始UART/TCL/日志在显示工作树build/board_hdmi_halfcycle_20261102。PDS已全部退出，cdt_js9040/原cdt_cfg46156未终止重启。
- 若仍UI丢信号，下一步用已通过的原始同步时序仅切RGB，继续隔离UI控制与像素路径，不再重复原厂或同版本烧录。

## 2026-11-02 13:47：彩条可见，切UI异常；全帧逻辑对拍通过

- 用户确认9F0181AD同一位流默认彩条有画面，按住KEY1切UI后异常或无信号。板卡/PHY配置与原始视频模式可工作；UI显示仍FAIL，具体黑屏/丢信号细节待用户反馈。
- 新ui_raster用真实sync_vg 1080p60驱动ui_renderer，逐拍检查HS/VS/DE相对输入四拍延迟，两整帧4950010周期/4147200有效像素全部PASS；未复现逻辑同步丢失，不能猜称已修复。
- 显示分支将hdmi_tx_if物理RGB/DE/HS/VS输出寄存从上升沿改下降沿，转发时钟不变，作为外部MS7210采样裕量候选；内部原约束未包含外部接收器setup/hold，内部All Constraints Met不能替代板间时序。此次改动是待实测假设，不是已证实根因。
- 保留彩条/KEY1选择以在同一候选比较两路。RTL59文件0违规，下一步单PDS构建读取半周期路径报告后烧录；旧版与失败证据不覆盖。

## 2026-11-02 13:34：HDMI二分诊断位流已烧录，待彩条/KEY1画面结果

- 用户确认原厂画面输入为1920x1080 60Hz，与自研目标相同；现阶段已有原厂板级显示PASS，自研20B31B08无信号FAIL，未确定软件根因。
- 显示分支源81191c71，run20261102-132721-a565919a六阶段成功，SourcesUnchanged=true，完整报告All Constraints Met，slow setup+0.406ns/hold+0.338ns；1031LUT/952FF/1DRM/0APM。位流SHA2569F0181AD711D49541C8BE69C4531655754483476F9B57A1B64D3E4311DB475F2。
- 已烧录该诊断候选，program成功/done1/CRC0，27300字节、300帧UIDEMO，末帧G07/H81，确认默认选择原始sync_vg+彩条。按住KEY1下一帧切UI，松开回彩条；选择经双拍同步并在帧边界锁存。
- 当前板上是9F0181AD诊断版，不再是原厂位流；尚待用户确认默认彩条和按住KEY1的UI各自结果。若两者都无信号，重点转新HDMI封装/配置/物理输出；若彩条正常且UI异常，重点查UI输出同步。不得将UART/H81代替实际画面证明。
- 报告reports/hdmi_bisect_board_20261102.json；原始日志/UART/TCL在显示工作树build/board_hdmi_bisect_20261102。未终止或重启cdt进程，PDS已退出。

## 2026-11-02 13:27：原厂 HDMI 已由用户确认有画面，定位自研显示链路

- 用户明确报告重烧UI仍无信号；再次烧原厂5D1FE82E...1D7A5C6，program成功/done1/CRC0，用户随即确认“原厂例程有画面”。这确认同板J9/线缆/显示器链路可工作，修复UI候选20B31B08实际显示FAIL，不能宣称G25修复已解决。
- 按字节核对：PLL .v/.idf相同，ms7210/iic_dri/sync_vg相同，ms72xx仅去除重复wire；视频与I2C引脚/驱动属性相同。尚未确定软件根因，不再据内部G07/计数宣称显示成功。
- 显示分支增加可切换诊断：默认原始sync_vg同步信号+彩条绕过UI，按住KEY1在下一帧切到UI，松开回彩条；H.bit7=1表示原始彩条。仅用于二分UI/封装路径，尚待PDS和板测。板上当前保留已确认出图的原厂例程。

## 2026-11-02 13:18：按用户要求重新烧录显示候选

- 用户说明HDMI此前已测试，要求重新烧录。再次下载20B31B08...605854BE显示专用位流；复用cdt_js9040，原cdt_cfg46156保持，临时配置客户端正常退出。
- program明确成功，JTAG0x081ffca0、done1、CRC0，捕获67876字节/744帧UIDEMO，最终G=7。仍等待本次重烧后的实际屏幕反馈，不以用户对硬件的判断代替当前画面验收。
- 报告reports/ui_reflash_20261102_1318.json；原始UART/TCL/日志在显示工作树build/board_ui_reflash_20261102_1318。未运行PDS，未换入RV或I2S位流。

## 2026-11-02 12:51：外部 I2S 波形补测复现并修复一位采样偏移

- 新增i2s_capture Verilator入口：真实i2s_clk_gen接i2s_rx，测试源只观察物理BCK下降沿输出Philips I2S 16bit紧凑帧，不使用接收器内部phase驱动数据。旧RTL明确FAIL：左声道发送0x1235却收到0x091A，证据build/sim/i2s_capture/before_fix.log保留。
- 根因是发生器同时寄存tick与新phase；接收器消费tick时看到的是边沿后的phase，却按边沿前even phase判断上升沿。改为odd phase采样，MSB通道标签由phase2改3、LSB完成由phase0改1。
- 修复后左右交替16个字逐值匹配，包括正负/零/全1/交替位；静态SD idle置位、活动清除、帧中复位与重新接收全部PASS。RTL59文件0 violation，完整pytest432 passed/4 skipped；结构化证据reports/i2s_capture_validation_20261102.json。
- 本次未运行PDS、未烧录、未操作cdt；板上仍为显示分支20B31B08候选，等待用户屏幕反馈。此结论仅证明16bit紧凑Philips帧RTL功能，不能称真实麦克风/音频板级通过；top_rv_core的SD仍接0，外部I2S引脚整合尚待完成。
- 下一步保持显示候选供验收，同时继续RV外部音频接线与完整位流时序、UART修复版权重WOK验证；不要把当前I2S修复已包含在旧位流中。

## 2026-11-02 12:44：显示专用修复位流已完成并烧录，待屏幕验收

- codex/display-demo（源提交8d5382a2）补接底板G25物理HDMI复位，固定piano演示柱与文本一致，烧录脚本缺失program成功证据时不再误报PASS。RTL59文件0 violation，烧录契约/安全39项PASS。
- PDS run 20261102-124002-c2bc537c 六阶段成功、SourcesUnchanged=true；完整slow/fast报告All Constraints Met，slow setup+1.191ns、hold+0.338ns；1035LUT/948FF/1DRM/0APM。cfg与pix之间仅有复位/准静态双拍同步路径，显示分支补了对应CDC时钟分组，域内时序仍检查；原始负裕量首候选与报告保留。
- 位流SHA256 20B31B08C7D56982E580A709A26A9E965780437A4BDB79BF6DB04093605854BE。已复用cdt_js9040烧入，program明确成功、done1/CRC0、27300字节UIDEMO，G最终07；未终止/重启原cdt_cfg46156。PDS已全部退出。
- 现在板上是这个修复UI候选（不再是原厂对照版）。**用户尚未确认最新候选屏幕画面，显示未验收**；旧UI位流在底板J9无信号为明确失败证据。原厂对照版成功烧录后未收到屏幕反馈，因此不作硬件链路通过结论。
- 报告reports/display_demo_build_20261102.json、ui_reset_board_20261102.json；原始UART/TCL/日志在显示工作树build/board_ui_reset_20261102。当前只演示固定数据，无真实音频或推理。完整项目今日交付仍低置信度，待显示验收后回到RV串口权重WOK、真实I2S和HDMI整合。

## 2026-11-02 12:38：显示保底分支与 HDMI 无信号实测

- 用户要求评估今日交付并优先准备显示演示。完整 RV+AI+真实 I2S+HDMI 今日完成置信度低：当前 top_rv_core 无 HDMI，i2s_sd 接常0；独立 instrec_top 有外部接口但尚未与 RV 合并，不能称完整系统已交付。
- 已建 codex/display-demo 分支与隔离工作树 build/ui-wt。既有 UI 位流 D1EF2594...CE9B1A9 烧录 done1/CRC0，339帧 UIDEMO、G07及像素计数递增；用户明确确认底板 J9/HDMI OUT 仍无信号，显示验收 FAIL。内部计数/I2C init_over 不等价显示器有图。
- 核对 BASE 原理图：J8=HDMI_IN/MS7200，J9=HDMI_OUT/MS7210；T24=HD_TX_PCLK，K22/K23=HSP_SCL/SDA，G25=RSTN_OUT。例程虽位于 FMC 目录，HDMI 使用底板接口，不能据目录认定接错扩展卡。
- 原厂同器件 HDMI 位流 SHA256 5D1FE82ECD2F2D9A2C85BAFC4A3BBC34D99F19668BA432EBED55A4F811D7A5C6 已烧入，program明确成功/done1/CRC0；等待用户可视反馈。初次中文路径指定失败的日志保留，随后复制ASCII路径成功；不得用旧done状态证明program成功。
- 独立显示候选补接原厂G25物理复位，并使72%柱与piano文本一致；尚未PDS/板级验证。构建将优先于RV，禁止并发PDS。
- RV run build/pds/20261102-121546-d902b356 已compile/synthesize/dev_map并进入PNR，布局CPU持续推进；为优先显示交付而受控停止父37344/子32688，非工具失败，**无新位流、无时序结论**。日志哈希与进程证据在priority-stop-evidence.json/priority-stop-processes.json。未终止或重启cdt_js9040/cdt_cfg46156。

## 2026-11-02 12:14：RV 板级启动已确认；UART RX 首帧阻塞已定位修复

- 用户已明确要求烧录调试。诊断下载既有 `20261102-003406-7af1bf17` 位流（SHA256 `605C234F...B488CFB`），复用 `cdt_js` PID9040；配置客户端正常退出，原 `cdt_cfg` PID46156 未终止/重启。JTAG `0x081ffca0`、done=1、crc_err=0，COM5 捕获 136 bytes，包含 `RV32 BOOT`、`RV32 MMIO OK`、`DDR OK STS 0x00000040`、`NPU GO`；部分字节损坏，不能宣称 UART 或推理全链通过。
- 权重上传实测首帧 seq0 无 ACK（2 次重试后失败），尚无板级 WOK 或 NPU 结果。原始日志/UART/TCL 已保存在 `build/board_rv_20261102_1208/`，结构化烧录证据为 `reports/rv_board_smoke_20261102.json`；该 JSON PASS 只代表烧录与 BOOT token。
- 明确 RTL 根因：`uart_rx` 原先在 1.5bit 检查 START，再等 1bit 才采 bit0，采样整体晚一位。修复为 `(BAUD_DIV+1)/2`（默认543周期）检查 START，随后每1085周期采样。旧 RTL 串行回归首字节 AA 收成20而 FAIL；修复后264字节、全字节值/连续帧/坏停止位/毛刺/复位恢复 PASS。
- 新增物理串行模式 `weight_loader_serial`：真实 uart_rx 接真实 loader，4x256B、32拍读回、`KKKKWOK 42851062`、CRC NAK、复位恢复10项全部 PASS；原直接字节注入 `weight_loader` 仍10项 PASS。板级问题尚需修复位流重烧验证。
- RTL59文件0 violation，UART/烧录/构建定向pytest57 passed。下一步单实例构建当前 UART RX 修复和已有 db_norm 流水候选，受控监控布线与slow/fast timing，再回板重试权重。
- 更正历史阻塞表述：板卡技能与 `run_pds_full.ps1` 明确将 `SCBV has not been set` 列为原厂缺省PCB参数的正常提示，**不是禁止下载的错误**；仍需如实记录时序负裕量，不能以板上启动代替时序达标。reset-mid-read 同RID迟到响应风险继续开放。

## 2026-11-02：未覆盖 NPU activation/full-end 补测通过

- `python sim/experiments/npu_activation/run.py`：conv1、pool1、DDR activation replay、conv2 全部逐值匹配 golden；conv1 792576 outputs，最终 cycles `12242761`。
- `python sim/experiments/npu_full_end/run.py`：四层卷积与 DDR activation replay、GAP/FC/softmax 全链逐值匹配 golden；`full npu_top` PASS，cycles `30757679`。
- 日志保留于 `build/sim/npu_activation/run.log` 与 `build/sim/npu_full_end/run.log`。本轮未修改生产 RTL，未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器；板级仍 `NOT_RUN`。
- 最新完整位流候选仍因 `ddrphy_sysclk` slow/fast 时序负裕量及 `SCBV has not been set` 警告禁止上板；reset-mid-read 同 `axi_rid` 迟到响应风险继续开放。

## 2026-11-02：收尾核对与 RV 轻量集成确认

- 按 `HANDOFF_SNAPSHOT_20261101.md` 复核当前主线：`top_rv_core` 已真实例化 `rv32_cpu_subsys`，CPU 通过 MMIO 发起 NPU 请求、读取 DDR/NPU 状态与结果，并复用共享 UART；`rv_core` 构建集包含 CPU RTL 与 `src/cpu/prog.hex`。
- 并行审查确认无需新增 RTL 改动：`python sim/run_sim.py rv_cpu --verbose` C1-C9 全部 PASS；`python sim/run_sim.py rv_top_ctrl --verbose` 17 项 PASS；`python scripts/check_rtl.py` 检查 59 个 `.v`、0 violation；构建护栏定向 pytest 45 passed。
- 最新候选 `build/pds/20261102-003406-7af1bf17/generate_bitstream/top_rv_core.sbit` 已完成布线并可复核（SHA256 `605C234FA2B14BB174C304B0B99FB7E5E7768643F999A97BEC70FA328B488CFB`），但 `ddrphy_sysclk` slow WNS `-4.462 ns`、fast WNS `-0.793 ns`，报告为 `Some Constraints Violated`，且有 `SCBV has not been set` 警告；不作为板级候选，板级仍 `NOT_RUN`。
- 本轮未启动新的 PDS、未操作 `cdt_js`/`cdt_cfg`/下载器。用户已有的 `cpu/`、PCB、PDF 和 `obj_dir` 工作区改动保持原样。

## 2026-11-02：控制冒烟与真实 RV CPU 回归通过

- `python sim/run_sim.py ctrl_smoke --verbose`：6 项 PASS，覆盖 BOOT、DDR3 SELFTEST、DDROK、STS=00、RUN 及控制状态收敛。
- `python sim/run_sim.py rv_cpu --verbose`：C1-C9 全部 PASS，覆盖 RV32 BOOT/MMIO/ISA/mcycle、NPU 触发、DDR 状态、ACK 与结果快照；UART 观测 `NPU top1=5 last_class=3 last_p=87 c=12345`。
- 以上为 RTL/模型仿真证据，不等价于真实 DDR PHY、音频输入或板级 RV+NPU 证明；板级仍 `NOT_RUN`。本轮未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器。
- 追加定向回归：`tests/test_golden_mel.py tests/test_conv1_debug_vectors.py tests/test_contract_stream.py` 为 44 passed；`tests/test_golden_refs.py tests/test_mel_tables.py tests/test_plan_contract_guards.py` 为 54 passed。覆盖 Mel/conv1 golden、frame-major contract、表完整性和计划护栏。
- 本轮完整 `python -m pytest -q`：**432 passed / 4 skipped**；追加 `tests/test_npu_stream_model.py tests/test_wdma_param_pipeline.py tests/test_board_e2e_order.py`：**34 passed**。均为离线模型/编排验证，不等价 PDS 或板级通过。
- `tests/test_board_flash_safety.py tests/test_uart_debug_handshake.py`：**21 passed**，验证复用既有 `cdt_js`、禁止重复实例/强杀及 UART 握手保护；本轮未执行烧录。

## 2026-11-02：UART line buffer 与 NPU completion 补测通过

- `python sim/run_sim.py uart_linebuf --verbose`：PASS，覆盖满 128 字节/无换行、短行/空行、blocked-write 丢弃、TX backpressure 及 busy/ready 恢复。
- `python sim/run_sim.py npu_completion --verbose`：PASS，覆盖两次真实 softmax completion、busy 清除和重新启动。
- 本轮未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器；板级仍 NOT_RUN。

## 2026-11-02：UI 与特征页模型补测通过

- `python sim/run_sim.py ui_render --verbose`：3 项 PASS，64 个 active pixels、层优先级和 RGB/DE 四拍对齐均 0 mismatch。
- `python -m pytest -q tests/test_feat_page_model.py tests/test_spectrum_overlay_model.py`：19 passed，覆盖特征页翻页、尾拍和谱图 overlay 模型；`run_sim.py` 无 `feat_page` 入口，未将该入口提示视为测试失败。
- 本轮未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器；板级仍 NOT_RUN。

## 2026-11-02：权重加载与 AW timeout 补测通过

- `python sim/run_sim.py weight_loader --verbose`：10 项 PASS，覆盖 4 个 256B chunk、32 拍读回 digest、完整 `WOK`、CRC 拒绝/NAK 与复位后重新接受。
- `python sim/run_sim.py ddr3_aw_timeout --verbose`：6/6 场景 PASS，覆盖正常负载、S_AW 超时、m3 单独加载、16 命令、m0 饱和配额及板级 STS 归因复现。
- 本轮未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器；板级仍 NOT_RUN。

## 2026-11-02：RV 控制与 self-test 补测通过

- `python sim/run_sim.py rv_top_ctrl --verbose`：17 项 PASS，覆盖物理 UART 解码、三生产者请求一次性消费、CPU 请求排队、安全 Mel 窗、权重上传/忙/DDR 失败/native fault 门控及 CPU-only 单次启动。
- `python sim/run_sim.py self_test --verbose`：8 项 PASS，覆盖 4KB 写读回、16 条命令保持、写/读 abort 失败地址，以及 abort 后重新运行恢复。
- 本轮未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器；板级仍 NOT_RUN。

## 2026-11-02：DDR3/NPU 共享路径补测通过

- `python sim/run_sim.py ddr3_subsys --verbose`：15/15 场景 PASS，覆盖 self-test、四主争用、读命令保持、AW/W/AR/DW watchdog、abort recovery；watchdog blind spot 场景仍按预期复现并记录，不宣称已修复。
- `python sim/run_sim.py npu_chain --verbose`：GAP 256、FC1 128、FC2 8、softmax 8 项均 0 mismatch，top1=0。
- 两项补测均未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器；板级仍 NOT_RUN。

## 2026-11-02：db_norm 平方位宽显式化；reset-mid-read 风险复现确认

- `src/mel/db_norm.v` 将平方路径改为显式符号扩展到 32 位、64 位乘积后取低 32 位，再进入原有 48 位累加器；保持端口、状态机和数值语义不变，避免综合器依赖隐式乘法表达式宽度。
- 修复后 `python scripts/check_rtl.py` 为 **59 个 `.v` / 0 violation**；`tests/test_ddr3_ctrl_model.py tests/test_plan_contract_guards.py` 为 **35 passed**；`python sim/run_sim.py mel_credit --verbose` 为 **16512 特征、0 mismatch、PASS**。
- 定向复现 reset-mid-read：读事务进入 `S_R` 后复位控制器、释放复位并发起同主口新读，注入旧 `0xDEADBEEF/RLAST`，模型观察到 `read_cmpl=True` 且旧数据进入 `r_beats`。这确认现有 `S_R_DRAIN` 只覆盖 watchdog 超时，不覆盖外部复位；由于 `axi_rid` 仅为 master ID，当前接口无法安全区分旧/新事务，继续保留为开放 IP/PHY 契约风险。
- 本轮未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器。下一步在无 PDS 时继续低风险回归；若重新布线，先确认单实例并读取 slow/fast timing，不能把本次位宽修复当作时序闭合证据。

## 2026-11-02：db_norm 候选回归通过；新 PDS 布线停滞并安全结束

- 生产 `src/mel/db_norm.v` 当前候选保留原端口和同步 RAM 节拍，在平方累加前加入寄存/末项 flush；小几何边界对拍、真实 `mel_credit` 16,512 字节 golden、CPU/native frame-major 联合均通过。候选仍需关注 PDS 对乘法表达式位宽的推断，未宣称板级验证。
- 并行定向验证通过：`python -m pytest tests/test_ddr3_ctrl_model.py tests/test_ddr3_arbiter_model.py tests/test_sys_ctrl_ddr_result_latch.py -q` 为 **49 passed**；`python sim/run_sim.py uart_linebuf --verbose` 和 `python sim/run_sim.py npu_completion --verbose` 均 PASS。全量基线仍 **432 passed / 4 skipped**，RTL 检查 59 个 `.v`、0 violation。
- 唯一 PDS `build/pds/20261102-013400-e8658663` 已完成 compile/synthesize/dev_map 并进入 detail routing；未布网络从 60995 降至约 717，随后在 iteration 500--560 间约 950--1026 长时间振荡，未出现 `placed and routed successfully`，也没有 `report_timing/` 或 `generate_bitstream/*.sbit`。按止损规则仅结束该 run 的 PDS 父子进程，**无位流、无 timing 结论**。
- 停止前已保存 `stall-processes-20261102-024125.txt`、`stall-manifest-20261102-024125.txt`、`stall-log-sha256-20261102-024125.txt`；最终 `place_route/run.log` SHA256 为 `44569FD964C92F35C4E2BA15C6DA672E9A3BAEB6D73EB66E3AAEA9D01B06A6BB`。未操作 `cdt_js`/`cdt_cfg`/下载器；`cdt_js` PID 9040 仍在。
- 板级仍 **NOT_RUN**。reset-mid-read 后同 `axi_rid` 的迟到 `RVALID/RLAST` 误收风险仍开放，不能把 Python/Verilator PASS 写成物理 DDR PHY 或完整顶层复位证明。下一步应先处理 db_norm 关键路径和 PDS 布局候选，再单实例重跑并读取 slow/fast timing。
- 本次心跳重新执行全量 `python -m pytest -q`：**432 passed / 4 skipped**，仅 2 条既有 PyTorch FutureWarning；未启动 PDS，未操作下载器或 JTAG 服务。
- 本次继续补跑 Verilator：`rv_top_ctrl` PASS（CPU 请求排队、安全 Mel 窗、DDR/NPU/故障门控）；`mel_credit` PASS（132096 命令、16512 特征、0 mismatch）；`ui_render` PASS（64 active pixels、层优先级和 RGB/DE 对齐 0 mismatch）。
- 继续补跑 `ddr3_subsys`：15/15 场景 PASS，覆盖 self-test、四主仲裁、读命令保持、各状态 watchdog 与 abort recovery；测试同时明确复现并记录 watchdog blind spot。`ctrl_smoke` 和 `npu_chain` 也 PASS，NPU GAP/FC1/FC2/softmax 均 0 mismatch。
- 继续补跑 `self_test`、`weight_loader`、`ddr3_aw_timeout`：分别 8、10、6 项检查全部 PASS，覆盖 self-test 中止/恢复、权重 CRC 与写回读 digest、m0 饱和下 m3 AW 超时归因；watchdog blind spot 与 reset-mid-read 风险仍按已知限制保留。
- 继续补跑 `rv_cpu`、`conv1`、`mel`：RV32 CPU 9/9 检查 PASS；conv1 输出 792576 项、mel 特征 16512 项均与 golden 逐值一致（0 mismatch）。
- 本次心跳重新执行 `python scripts/check_rtl.py`：59 个 Verilog 文件、0 violation；无 PDS/JTAG/下载器操作。
- 烧录安全回归 `tests/test_board_flash_safety.py tests/test_uart_debug_handshake.py`：21 passed；未连接或操作下载器。

## 2026-11-02：修复版 PDS 完成布线并产出候选位流，时序未闭合

### 心跳补充（2026-11-02）

- 重新执行 `sim/experiments/cpu_native_joint/run.py --frame-major --run-label heartbeat-20261102-uncovered`：真实 RV 固件 MMIO 启动、conv1 792576 项、四层 conv+DDR activation replay、完整 native NPU golden 均逐值通过；31,141,202 cycles，UART `top1=0,last_class=7,last_p=0`，CPU ACK 正确。日志保留在 `build/sim/cpu_native_joint_heartbeat-20261102-uncovered/run.log`。
- `python sim/run_sim.py mel_credit` 通过（16,512 个特征逐字节 golden 对拍）；`python scripts/check_rtl.py` 通过，59 个 `.v`、0 violation。未启动 PDS，未操作 `cdt_js`、`cdt_cfg` 或下载器。
- 时序复核确认最差路径为 `spec_bank_7` DRM → `u_db_norm` dB 转换/平方 → `sum_db_sq`，slow WNS -4.462 ns、fast WNS -0.793 ns；当前生产 RTL 尚未修改。正在隔离评估平方寄存与末项 flush，语义通过后才决定是否进行下一轮单实例 PDS。
- 隔离候选 `build/experiments/db_norm_pipeline/db_norm_pipelined.v` 已完成 Verilator 小几何同步 RAM TB：`N_MELS=2, SPEC_FRAME_COUNT=3, OUT_FRAME_COUNT=2`，覆盖首帧丢弃、写地址/数值及末项 flush；结果 `sum_db=-1513, sum_db_sq=1190489`，`RESULT: PASS`。候选未进入生产 RTL，尚未做候选全链 PDS或板测。
- 同一候选替换到真实 `mel_credit` 仿真入口后，全链 16,512-byte feature golden 对拍通过（`mel_credit_dbnorm_candidate`，25.6 s）。这证明当前候选在生产几何和标准化交接下语义一致，但仍不等价于 PDS 时序或板级验证。

- 当前唯一 PDS run `build/pds/20261102-003406-7af1bf17` 已完成 compile/synthesize/dev_map/PNR/report_timing/gen_bit_stream；detail routing 在迭代149达到最终 `Unrouted nets 0`，并确认 `top_rv_core` placed and routed successfully。全流程已退出，未操作 `cdt_js`、`cdt_cfg` 或下载器。
- 候选位流 `generate_bitstream/top_rv_core.sbit` 大小 3,791,112 bytes，SHA256 `605C234FA2B14BB174C304B0B99FB7E5E7768643F999A97BEC70FA328B488CFB`。源清单 SHA256 `491168B89E5348B12B6889045B3860C7870FDF7E95F55D0BCF3BEEAEF6BDFFA6`，run.log SHA256 `E7B0FB73CE8D7A81CF690A73DBC1DC600310D92B0989D07B50AA5CB14FCDE66E`。
- 资源约为 LUT 32063/66600、FF 33300/133200、DRM 120.5/155、APM 90/240。detail routing 从 62810 收敛至0，但这不等于时序闭合。
- `report_timing/top_rv_core.rtr`：slow `ddrphy_sysclk` WNS -4.462 ns、TNS -4036.195 ns、6015 个 setup endpoint 失败；fast WNS -0.793 ns、96 个失败；其余列出时钟 setup/hold 为正。报告结论为 `Some Constraints Violated`。
- bitstream 日志有 `Bitstream-2001: SCBV has not been set` 警告；因此候选位流不得直接上板。
- 并行只读验证新增全部通过：DDR 控制器模型 26 passed；DDR/自检/契约组 49 passed；板级烧录安全/串口握手 43 passed；权重/NPU/Mel/特征页 78 passed（2 条 torch FutureWarning，无失败）。
- loader/native 读超时 fail-closed/reset、owner early-done/CRC/复位恢复路径均通过，证据位于 `build/sim/loader_native_read_timeout/` 与 `build/sim/loader_owner/`。reset-mid-read 后同 `axi_rid` 的旧 `RVALID/RLAST` 误收仍是开放风险，未加入猜测性丢弃逻辑。
- 板级仍 NOT_RUN；后续优先处理 DDR PHY 时序/SCBV 配置，再另行生成可上板候选。reset-mid-read 后同 `axi_rid` 的旧响应风险仍开放。
- 本次心跳重新执行 `python -m pytest -q`：**432 passed / 4 skipped**，仅 2 条 PyTorch FutureWarning；未启动 PDS、未操作下载器。

## 2026-11-02：DDR 修复版资源门禁完成，未进入布线

- 修复后的 `ddr3_ctrl_axi` 超时迟到响应隔离与 `instrec_top` 初始化门控已通过受控 `rv_core` PDS compile/synthesize/dev_map；本轮 run 为 `build/pds/20261102-001943-d6bfe5cb`，源清单已固定，PDS 正常退出 0。
- dev_map 资源：LUT **32063/66600 (48%)**、FF **33300/133200 (25%)**、DRM **120.5/155 (78%)**、APM **90/240 (38%)**；无 PNR、report_timing 或新位流，不能把旧 `ED7138…` 候选位流归因于本次修复。
- 全量回归 **432 passed / 4 skipped**，RTL 词法检查 **59 文件 / 0 violation**。真实 frame-major CPU+native NPU 联合和无复位 A/B 双帧连续推理均 PASS，各 31,141,202 cycles，证据在 `build/sim/cpu_native_joint_heartbeat-20261102-{native-check,repeat-ab}/`。
- 仍开放：reset-mid-read 后同 `axi_rid` 的旧 `RVALID/RLAST` 无法从当前接口可靠区分；模型可复现误收，未加入猜测性丢弃逻辑。板级仍 NOT_RUN，下载器与 `cdt_js/cdt_cfg` 未操作。
- 下一步：若确需新位流，必须另行启动单实例 PNR 并设置明确布线止损；板测前先取得修复版完整位流和时序证据。

## 2026-11-02：DDR 读超时迟到响应已隔离

- `src/ddr3/ddr3_ctrl_axi.v` 新增 `S_R_DRAIN`：读 watchdog 超时后禁止新事务，丢弃迟到 `RVALID` 数据，收到 `RVALID && RLAST` 后才恢复仲裁；普通写/地址阶段超时语义保持不变。
- 周期模型与回归同步更新，新增 timeout → late `RLAST` → queued read 以及 init gate 场景，验证迟到数据不进入 FIFO、不会误完成下一笔读；DDR/仲裁/自检定向 48 项通过，全量 Python 回归 **432 passed / 4 skipped**，RTL 词法检查 59 文件 0 violation。
- 该修复尚未重新综合、布线或上板；当前候选位流仍对应修复前 RTL，不能宣称硬件已验证。若 DDR 永久不返回 `RLAST`，控制器会保持隔离并需外部复位恢复。

## 2026-11-02：复位后 DDR 初始化门控缓解

- `instrec_top` 现在仅在 `ddr_init_done=1` 时向 `ddr3_ctrl_axi` 放行四路 command valid，并将送入控制器的 `axi_rvalid` 置为 `ddr_init_done && axi_rvalid`。契约测试覆盖初始化前 stale R 屏蔽及初始化后正常 R 放行（9 passed，RTL 59 文件 0 violation）。
- 该门控依赖 DDR IP 在 `ddr_init_done` 置高前清空/不再返回复位前事务；它不能防止初始化完成后仍迟到的旧 R 响应，也尚未重新综合、布线或上板验证。
- 新增静态复位边界风险：顶层 `rst_n` 会同步复位 `ddr3_ctrl_axi` 与 DDR3 IP，但源码未证明 IP 已清空已接受事务，wrapper 也未屏蔽复位释放后的旧 `RVALID`。因此“读事务中复位 → 旧响应跨释放 → 新读”仍未验证，暂不宣称完整 reset recovery；需模型 directed case 和后续硬件/PHY证据。
- directed 模型已复现该风险：在 `S_R` 中复位并释放后注入旧 `RVALID/RLAST`，控制器会把 `0xDEADBEEF` 当作新读首拍并完成。当前将其作为开放问题保留，不加入未经 DDR IP idle/清空证据支持的固定等待逻辑。

## 2026-11-01 23:43：frame-major CPU+NPU 候选已完成布线并生成位流

- 冻结快照 `build/npu_production_candidate/frame-major-20261101-230923` 的完整 flow `build/resource_gate/native-20261101-230932-136199` 已完成 compile/synthesize/dev_map/PNR/report_timing/gen_bit_stream；PDS 父进程32412于23:09:47启动，PNR子进程33836于23:21:27启动。详细布线第105轮未布网络0，日志确认 `Design 'top_rv_core' has been placed and routed successfully`。
- 映射资源 LUT 32075/66600、FF 33300/133200、DRM 120.5/155、APM 90/240；最终路由逻辑 LUT 31968、FF 33300、DRM 120.5、APM 90。DRM占78%，余量有限。
- 位流 `build/resource_gate/native-20261101-230932-136199/generate_bitstream/top_rv_core.sbit`，3,791,112 bytes，SHA256 `ED713818EFE9E5A616437D302A994B69984F66FCE9E8D43A8EE2AA8BF8509163`。不得覆盖既有release；此为新候选，尚未板测。
- 时序不是全约束达标：slow-corner `ddrphy_sysclk` 125MHz estimated 75.6029MHz，WNS -5.227ns、TNS -8567.538ns、10261/112147 setup endpoints failing；`clk_nco` WNS +2.220ns、`rst_clk` +3.954ns，所有列出的hold WHS为正。主要负裕量路径位于DDR PHY sysclk域，路由成功不能表述为时序收敛。
- 快角复核同样未闭合：`ddrphy_sysclk` WNS -1.305ns，96 个 setup endpoint 失败；激活行缓存 reset 回归只覆盖模型主动取消未完成 DDR 事务，迟到上游 R 和完整顶层物理复位恢复仍未验证。
- 报告在该run的 `report_timing/top_rv_core.rtr`，详细布线和完整日志在该run目录；进程退出与manifest/日志hash已于23:49复核。下一步是处理负时序并在合适窗口执行板级 smoke；当前板级仍NOT_RUN，不操作下载器。

## 2026-11-01 23:49：最新 PDS 产物与自动化状态复核

- 复核确认 `native-20261101-230932-136199` 的 detail routing iteration 105 未布0，`placed and routed successfully`；PDS flow、timing报告和 `.sbit` 均存在，当前 `pds_shell.exe` 进程数为0。
- SHA256：`gate-manifest.json` `C2F3F1F4C5DCCBD55FDDE54A6A970F78C032C0D6E8E44EB5CD67A6E853C3581E`；`run.log` `69F3EFDAA5047F261FFE859FF2003F40096673EBAF5B973285D67767581481E`；`top_rv_core.rtr` `C1C1D8B19EA696E0968563A313621A03F97E51D1027397448DFBD3628B825853`；位流 hash 见上。
- 自动化提到的 `native-20261101-224112-909881` 已过时；它只完成 dev_map。后续以本文件顶部的 `native-20261101-230932-136199` 为唯一最新完整 flow。23:15/23:11条目中的“当前 synthesize/尚无位流”已标为历史状态。
- 主线 frame-major CPU/native 联合仿真已用独立 run-label PASS：`build/sim/cpu_native_joint_heartbeat-frame-major-20261101-1548/run.log`；真实RV固件MMIO启动、conv/pool/GAP/FC/softmax全层golden exact，31,141,202 cycles，UART `top1=0,last_class=7,last_p=0`，ACK正确。仍未覆盖物理DDR PHY、真实音频/Mel、完整top reset和异常事务恢复。板级仍NOT_RUN，下载器及 `cdt_js`/`cdt_cfg` 未操作。

## 2026-11-01 23:15：UI特征拷贝占口恢复与末尾重复写已修复（历史记录）

- `feat_copy_engine`改为区分当前获准读请求与上一拍pending同步RAM响应：本拍NPU抢占时仍消费属于copy的旧响应，恢复时不会误收NPU数据；末尾最后字节只写一次，随后翻页，idle/tail地址夹到0。
- 旧反例addr9应66却170且多写16513次；生产修复后连续/7拍抢占/随机暂停/末尾暂停四场景均0 mismatch，每轮严格0..16511各写一次，最后写完才flip。定向Python19 passed（0.36s），词法59.v零违规。证据`reports/mel_npu_interface_audit_20261101.json`，旧失败日志保留。
- 独立审查量化与同步读延迟正确。正常3s窗口节奏下Mel后idle约2.95488s，大于实测NPU0.24913s；异常长时停顿跨下一窗时，单feature bank仍无硬件锁页，不宣称该错误恢复支持。
- UI修复不在当时rv_core冻结源列表；“当前synthesize/尚未进入PNR”是该时间点记录，已被顶部23:43的`native-20261101-230932-136199`完整flow结果取代。

## 2026-11-01 23:11：Mel布局修复验证通过，正确冻结版本已重新构建（历史记录）

- `npu_top`新增显式`FEATURE_FRAME_MAJOR`读口模式，使用已有time/mel计数器拼接地址；三个生产top均设1。默认0只保留独立mel-major模型兼容，不增加除法电路；Mel内部+64偏移保持唯一。
- 抽取实际NPU replay/Mel同步bank切片：旧直连16446/16512字节错，修复后0错、全地址双射，含8252个>=128字节。进一步使用frame-major RAM完成真实CPU/完整native NPU联合：全部各层golden exact，31141202cycles，UART/MMIO/ACK正确。uint8[0,255]/zp49契约核验正确。报告`reports/mel_feature_handoff_validation_20261101.json`；不等同完整音频/Mel计算或板级验证。
- 修复后全量Python **429 passed / 4 skipped**（83.22s），59.v词法0 violation。续跑脚本增加真实ADF门槛、ADF备份与独立driver工程名；PS5.1解析与缺ADF提前拒绝PASS，完整成功续跑尚未验证，当前构建不用续跑。
- 新完整flow `build/resource_gate/native-20261101-230932-136199`于23:09:47启动；该时间点仍在前置阶段。最终结果以顶部23:43记录为准：已完成PNR/timing/bit并生成候选位流。
- 并行发现UI copy在NPU占口后恢复会误收一拍，且末尾多写一次；仅影响UI路径，`feat_copy_engine`独立修复/边界回归中，不在当前rv_core源集合。无新版位流/时序/上板结论，下载器未操作。

## 2026-11-01 23:07：发现真实Mel/NPU布局错接，先修复再构建

- Mel标准化和导出接口是frame-major（frame*64+mel），NPU按mel-major（mel*258+time）扫描；三个top原直接相连。已确认`mel_engine`的+64只是内部guard偏移，不做转置：NPU第二字节期望(mel0,time1)，旧地址1实际取(mel1,time0)，应取64。此前使用mel-major行为RAM的完整NPU/CPU联合不覆盖此真实前端错接。
- 正在利用现有feat_row/feat_col增加明确frame-major读模式，三个生产top启用，并补旧版失败/修复PASS、全部16512地址及完整native golden验证；不添加除法电路。独立审查量化符号/同步读延迟/安全窗。
- 旧mapped gate的ADF在续跑参数探测误触compile时被PDS清理，不能再复用；资源PASS报告仍完整。新隔离单flow`native-20261101-230237-445245`于23:03:25启动，但因上述真实功能bug，核验后结束其synthesize子42004（当时compile已退出，不操作旧PID6588），父33872自然退出。无PNR、无位流，日志/manifest保留。
- 待前端契约修复验证通过后重新冻结并单实例构建；PNR实际进入后45分钟上限仍有效。未操作下载器/cdt。

## 2026-11-01 22:59：完整映射通过，CPU双轮与生产reset补测通过

- 唯一完整gate正常exit0，compile/synthesize/dev_map全部PASS；最终映射**32076 LUT / 33300 FF / 120.5 DRM / 90 APM**。归档`reports/npu_narrow_full_gate_20261101/`含manifest、snr、dmr和日志hash；资源容量阻塞已解除，但尚无新版位流/时序。
- 首次复用映射续跑暴露PDS入口问题：`-file`先初始化默认工程，后续open_project不能正确恢复阶段；`-project -run pnr`则从compile起重跑。失败日志及工程备份保留，精确停止误启动compile，不触碰JTAG；正在改用显式加载原工程+仅执行PNR的入口。**PNR尚未实际开始，45分钟计时尚未开始**。
- 生产RTL的CPU驱动A/B两轮无复位联合PASS：全部16512输入字节改变，各31141202周期，完整各层golden、两次安全窗启动/MMIO/UART/ACK正确，requests=launches=acks=2。使用隔离重复启动固件候选（仅首次ACK后再发一次CTRL[0]），生产ROM仍为单次启动，未改冻结源。证据`reports/cpu_native_joint_repeat_ab_validation_20261101.json`。
- 直接使用生产行缓存SHA05321eb0的八状态中途reset回归PASS：重新配置/写入/逐字节回放、行数及DDR命令数、无旧credit复用均通过。`reports/activation_narrow_reset_validation_20261101.json`保留候选及生产独立日志hash；模型协同取消未完成DDR响应，不覆盖未取消事务迟到R或完整top/板级reset。
- 下载器与cdt进程未操作；继续修复续跑入口并限时观察布线。

## 2026-11-01 22:52：生产 CPU+narrow NPU 联合通过；全量回归完成

- 新ROM与narrow行缓存同时在生产路径联合仿真PASS：真实CPU启动、CTRL请求等待模拟Mel安全窗、完整native各层golden exact、结果MMIO/UART、CTRL[1] ACK；31141202观测周期。27项输入SHA256复核与当前文件一致，证据`reports/cpu_native_joint_narrow_validation_20261101.json`。DDR PHY、完整音频/Mel前端及真实UART电气不在此仿真范围。
- Python全量回归完成：**429 passed / 4 skipped**，102.03s。新增独立run-label避免联合仿真覆盖历史日志。
- 唯一gate `native-20261101-224112-909881`技术综合表为**LUT 32077/66600、FF 33311/133200、DRM 120.5/155、APM 90/240**，已低于资源上限；22:50仍保存综合数据库，尚未最终dev_map，不当成布线成功。
- map正常完成并核验manifest后才串行复用映射进入受控PNR：总上限45分钟；detail route至少观察15分钟，连续20轮未布数无明显下降则留证止损，仅结束本run的PNR子进程。下载器与cdt进程保持不动。
- 并行补CPU驱动连续两次无复位推理；已有双轮native A/B通过，但不能替代CPU连续两次联合验证。当前仍无新版RV位流/时序/板级证据。

## 2026-11-01 22:42：RAM推断修复已推广；新完整拓扑gate运行

- 原完整gate容量超限，22:31核验进程/保存报告与manifest后仅结束其synthesize子进程36212，父43724自然退出；无dev_map结果、无位流。原版isolated probe也在22:38截止后保留日志止损，未完成，不当成通过。
- narrow isolated probe已完整compile/synthesize/dev_map通过：含观测wrapper共**794 LUT / 343 FF / 16 DRM / 0 APM**，用时39秒。32个lane_bank均识别为GTP_DRM18K_E1，真实修复RAM推断；纳管结果见`reports/activation_store_narrow_20261101/`。
- 新冻结`build/npu_production_candidate/narrow-20261101-223829`直接复制当时生产，仅替换行缓存；三top结构展开、三geometry逐拍miter、完整native A/B无复位两轮golden均PASS（各31141202cycles）。已逐字节推广唯一RTL差异`activation_row_store_dynamic.v`到生产，59.v词法0 violation；证据`reports/npu_narrow_snapshot_validation_20261101.json`。
- 唯一PDS现为`build/resource_gate/native-20261101-224112-909881`（22:41:58启动，compile→synthesize→dev_map），45 RTL、2约束、89个冻结IP文件及ROM/TCL/manifest launch核验通过。尚无完整资源结果，未启动PNR；isolated结果不能当作完整拓扑已可实现。
- 即时R/忙期start补测通过：三geometry共10816即时响应、9次忙期start不破坏配置/数值、IDLE异常R置sticky、reset清错后等待credit；中途事务reset和自动retry仍未验证。继续等待新完整资源，达标后才受控布线，不操作下载器。

## 2026-11-01 22:24：完整拓扑综合超容量；禁止进入 PNR

- exact combined gate `build/resource_gate/native-20261101-215404-522126` 已完成技术综合，资源表为 LUT **115473/66600 (173.38%)**、FF **133439/133200 (100.18%)**、DRM **88.5/155**、APM **92/240**。当前仍保存综合数据库，尚无最终 dev_map 结果；无位流，不能进入布线。
- 综合层级表`top_rv_core.snr`已确认两个`activation_row_store_dynamic`未映射RAM：u_store0=42441 LUT/50140 FF/0 DRM，u_store1=42445 LUT/50140 FF/0 DRM；合计84886 LUT/100280 FF。不能把综合成功解释为可实现，修复候选仍需隔离映射及新全拓扑gate证明。
- 已准备窄位/单写口候选，三种真实尺寸逐拍miter与逐字节重排均PASS（198144/98304/49152B）；当前gate完全退出后才串行运行original/narrow单模块映射probe，不并发PDS。证据与命令见 `reports/activation_store_resource_review_20261101.md`。
- 真实RV CPU+完整native NPU联合仿真也已PASS：CPU执行ROM、CTRL请求等待Mel安全窗、各层golden比较、结果MMIO/UART及固件ACK。DDR PHY、真实音频采集和完整Mel计算仍为模型边界；见 `sim/experiments/cpu_native_joint/README.md`。
- 新增A/B不同输入连续无复位native回归PASS：B=255-A，16512个feature字节全部改变，分别重算golden，两轮各31141202周期，conv/pool/GAP/FC/softmax全部逐值一致。见`reports/activation_repeated_boundary_review_20261101.md`；尚未证明异常事务后无需reset的恢复。
- 发现并修复UART语义：旧固件的`t`为最后概率lane，不是top1；生产固件分别输出STATUS硬件top1和last_class/last_p。独立CPU注入top1=5/last_class=3及完整native联合均PASS；生产ROM两次`--no-m`重建与联合仿真ROM逐字节相同，SHA256 `24d0b7fd4cb3e37f08cdfe4e3ab361321ba43f21ea6ec5367c3b2703b2dec294`（2316 padded bytes/579 words）。冻结gate源不变，不包含此ROM更新。
- GitHub已同步`34fa09b`；下载器与`cdt_js/cdt_cfg`未操作。下一步先解决容量超限，再做新完整拓扑gate；未获得新版RV位流、时序或板级RV证据。

## 2026-11-01 21:57：RV+NPU 候选已推广主线；最终冻结两轮与 loader/native 争用通过

- 最终冻结 `build/npu_production_candidate/20261101-215059`：18 项冻结 DUT/model 输入，完整 native+M1 owner 连续两轮不复位均 PASS；每轮 31,141,202 cycles，全 conv/pool/GAP/FC/softmax 逐值 golden exact。相比不含 owner 的31,115,245增加25,957周期；125MHz下约249.13ms，未达到旧200ms目标。
- 同一冻结版本 CPU/ROM C1–C9 PASS；固件隔离重建与 ROM 字节一致。真实 RV32I 软核执行 MMIO 启动、状态/结果读取与清除，M扩展在此集成关闭；该CPU测试注入NPU返回，不等同完整CPU+音频+NPU联合实测。
- 三个顶层 top_rv_core / top_core_only / instrec_top 结构展开 PASS（外围vendor wrapper stub）；59个候选.v词法0 violation。16个已核验文件已推广到生产 src：六compute、arbiter、六新增native/activation模块、三top；diag和仿真端口同步适配。生产真实源路径完整两轮也已 PASS（各31,141,202 cycles）；conv1–4全部输出0 mismatch、GAP/FC/softmax、两次完成、CPU C1–C9、顶层控制17项断言均PASS。
- 真实 weight_loader+owner+生产 ddr3_ctrl_axi+full AXI model：4×256B上传、0x100000基址、32拍读回、完整WOK摘要、CRC拒绝、AW超时、读超时、复位恢复 PASS。owner延迟loader done到数据排空并等待registered native done，消除提前done死锁与超时误ACK；错误后需reset，未实现UART NAK恢复。
- 四主口真实controller争用/超时隔离 PASS：m0/m1/m2/m3同时pending，完成计数4/4/3/4，PCM/Mel/权重/激活/自检payload与地址隔离正确；不是完整NPU推理与所有master持续竞争测试。异常UART长度/全镜像长度验证仍未覆盖。
- 已启动唯一 exact combined topology 资源gate `build/resource_gate/native-20261101-215404-522126`，严格止于dev_map；45项真实rv_core RTL、2约束与完整IP冻结并校验hash，compile已完成（6m43s、peak502MB、0条E），现进入synthesize；尚无最终资源。215359 gate仅准备未启动。当前仍无新版RV位流/PDS时序/板级RV证据；不操作下载器或cdt进程。
- 推广后Python 429 passed / 4 skipped（119.36s），主线59个.v词法0 violation；仅npu_top过时注释及WDMA尾空格随后清理，16文件无功能token差异，双SHA证据见reports/npu_production_promotion_20261101.json。
- 后续：提交并同步GitHub；读取本轮真实资源，若可实现再启动单实例受控PNR并监控收敛，不能用旧WDMA-only gate估计完整新拓扑资源。

## 2026-11-01 21:45：冻结顶层候选结构通过；重复推理与 loader 提前完成问题修复中

- hardened 权重读对齐器定向通过（16-byte 偏移、17 物理 beat 拆包、边界拒绝、背压、early-done/abort）；完整 native 单轮仍为 31,115,245 cycles 全层 golden exact。
- 两轮不复位回归暴露真实缺陷：第二轮 FC2 第 0 项 got29/expected202；FC2 在 FC1 阶段预装输入后，旧参数计数可使其提前进入 MAC，并误收共享权重。仅加权重门控仍失败（got6/expected202）；最终增加 FC 完成时清参数计数，两轮不复位均 PASS（各 31,115,245 cycles，全层 golden/输出计数一致）。独立延迟参数短测原版 FAIL、修复 PASS；中途 abort/restart 未宣称支持。
- `build/npu_production_candidate/` 已生成生产命名的隔离 snapshot：补齐 activation/aligner/bridge/事务 owner、loader 0x100000 基址与 fault 传播。top_rv_core 和 instrec_top 的 Verilator 结构展开通过（audio/DDR/HDMI 外围使用 stub），不能等同真实 IP 或 PDS 通过。
- M1 owner 初版定向回归通过，但进一步审查发现真实 loader 在 native done 时提前撤 rd_ready，可能导致剩余 FIFO 永不排空；修正后延迟 loader-facing done 到读数据交付完毕，真实 loader+owner 已通过 10 checks（4×256B、32拍读回、完整 WOK 42851062、CRC拒绝、复位恢复）。真实控制器 timeout 回归及最终冻结继续；旧 snapshot 不可作为最终构建输入。
- 本轮复验 Python 429 passed / 4 skipped（99.16 s）、RTL 53 个 .v / 0 violation；uart_linebuf、rv_top_ctrl 均 PASS。UART 128 字节边界实际通过：旧记录仅按 7-bit ram_len 推断失败不成立，其 0 编码经 7-bit 减一比较终止于127，暂不做无反例改动。
- 下一步：双轮修复与 owner 回归通过后重新冻结，使用冻结 DUT 源完整 native 两轮并含 owner；随后才对 exact combined topology 做单实例 dev_map。当前无 PDS 在运行、无新版 RV 位流；下载器与 cdt 进程未操作。

## 2026-11-01 21:30：RV PDS 已止损；两项资源 gate 完成，继续整合审查

- 唯一 RV 构建 `build/pds/20261101-130420-0ed52a5d` 在观察截止后仍无收敛：iteration 370，未布 7156；62 项 source manifest SHA256 全部一致，无 `.sbit`、时序报告或可发布位流。
- 已仅结束该 run 的 PDS 子进程，随后确认 PDS 进程归零；未触碰 `cdt_js` PID 9040、`cdt_cfg` PID 46156 或下载器。失败/中断日志仍保留在原 run 目录。
- 已串行启动 `build/resource_gate/20261101-202028-476220` 的 corrected-scalar gate，严格止于 `dev_map`；当前仍在 PDS compile/synthesis，未启动 wide、PNR 或新位流构建。完成后再读取 LUT/FF/DRM 与 gate 日志。
- scalar gate 已完成：LUT 40,206/66,600（61%）、FF 53,718/133,200（41%）、DRM 80.5/155（52%）、APM 90/240（38%）；未进入 PNR。该变体没有降低 DRM，LUT 高于当前约 35,840 基线。已串行启动 wide gate `build/resource_gate/20261101-202029-216909`，当前在 compile。
- wide gate 已完成：LUT 29,409/66,600（45%）、FF 33,211/133,200（25%）、DRM 88.5/155（58%）、APM 90/240（38%）；同样未进入 PNR。wide 显著降低 LUT/FF，但增加 DRM，不能据此宣称能解决当前布线停滞；两个 gate 均无位流。
- 验证更新：完整 native NPU 自然推理 PASS（31,115,245 cycles，全层 golden exact，证据 `build/sim/npu_full_native/run.log`）；抽象 DDR 全链 PASS（30,757,679 cycles）；全量 Python `429 passed, 4 skipped`，`check_rtl.py` 为 53 个 `.v`、0 violation。
- 生产 WDMA 的 0 基址/16-byte 未对齐契约仍未合入；native PASS 使用实验 `weight_read_aligner`，不能外推为生产 RTL、PDS、PHY/CDC 或上板 PASS。下一步完成生产接口修复及全链候选整合审查，再决定是否重新布线。
- 资源判断纠正：没有证据表明 DRM 是本轮路由停滞根因。wide 相对 corrected-scalar 减少 10,797 LUT / 20,507 FF，代价是增加 8 DRM；DRM 仍低于容量，不能据 DRM 增长否定该优化。资源优势不等同路由/时序通过。

## 2026-11-01 20:34：完整native控制器NPU自然推理通过；布线截止20:43

- `sim/experiments/npu_full_native/run.py` 实际PASS，自然done=31115245周期：conv1..4、pool1..4、GAP256、FC1 128、FC2首8语义logits/16输出握手、softmax8全部golden及最终计数一致。
- 真实生产ddr3_ctrl_axi + 候选arbiter/bridge/read aligner + full8MiB行为AXI模型；无protocol_error/timeout/addr_err。最终权重first0x1003a0/last0x1a8900/min0x100200/max0x1a8b40，Amax0x4307e0/Bmax0x457fe0。
- 仅独立实验候选，生产WDMA基址/未对齐读取仍待采用适配，未证明PHY/CDC/PDS/上板或CPU协同完整推理。
- 用户要求布线别无限等待：20:27 iteration358未布7226，观察截止20:43；20:34 iteration363未布7201，仍震荡。截止若无显著下降，保留日志/manifest并核验PID后结束此无位流PDS，串行scalar/wide资源gate。绝不触碰cdt_js/cdt_cfg或下载器。心跳已改每5分钟。

## 2026-11-01 20:24：完整abstract NPU通过，native四层通过，资源gate已准备

- `sim/experiments/npu_full_end/run.py` 完整自然推理PASS：conv1..4、pool1..4、GAP256、FC1 128、FC2 8真实+8padding、softmax8全部golden及计数一致，30757679周期。修复FC参数跨输入加载并行采集/饱和计数、完成判断及消费者控制wbuf重装；仅独立候选，abstract DDR。
- `sim/experiments/npu_pingpong_native/run.py` 真实controller四层两次PASS，31106081周期；完整8MiB地址索引避免原模型2MiB alias。新增实验weight_read_aligner将WDMA零基址/16B偏移重定位0x100000并32B对齐拼接。生产WDMA仍有此地址契约缺陷，未合入修复。最终权重命令min0x100200/max0x1a0180，Amax0x4307e0/Bmax0x457fe0。
- native全链后半段继续合并验证；native四层PASS不能扩展为FC/softmax或生产/上板PASS。
- 资源gate脚本 `sim/experiments/wdma_parameter_ram/prepare_resource_gate.py` 已准备corrected-scalar/wide公平对比冻结工程，严格止于dev_map且启动拒绝并发PDS，尚未运行/未证明资源下降。核心时钟来自DDR IP125MHz，单改FDC不改变实际频率，不能当作快速降频方案。
- 当前唯一PDS iteration355未布7182，仍无时序/位流；未操作下载器。候选全部隔离在实验目录。

## 2026-11-01 19:54：真实 DDR 控制器联合验证通过，四层 native 接入继续

- `sim/experiments/npu_lifecycle/run_ddr3.py` 现场PASS：真实生产 `ddr3_ctrl_axi` + 候选激活区arbiter + AXI模型 + 修复bridge，16-beat权重读取、4组激活写后读回、addr_err=0、cmd_to_err超时失败路径均通过。
- 修复写缓存契约：act_wr_ready在ACT_DATA表示本地单拍缓存接收，后续才提交native命令；不表示DDR提交成功。联合TB原来过早撤command valid、未跨采样边沿，也已修正。此前“必然死锁”表述过强：已主动提供valid的客户端可推进缓存，但ready语义与harness均需修正。
- bridge70事务回归复验通过，继续补缓存接收后写abort；四层pingpong接真实controller新case正在并行开发，尚未证明完整native NPU链或最终FC/softmax。
- 唯一PDS iteration334未布7246，仍无时序/新位流。下载器未被操作，不并发PDS或JTAG。

## 2026-11-01 18:54：原生 DDR 联合测试发现激活写握手卡点

- 新增 `sim/experiments/npu_lifecycle/tb_npu_ddr3_lifecycle.sv` 与 `run_ddr3.py`，首次把 `ddr3_ctrl_axi`、DDR3 AXI model 和 bridge 放入同一测试平台。16-beat 权重读取已完成，但激活写入阶段出现 `act_wr_valid` 持续、bridge/controller 空闲的握手卡死；这是联合 harness 尚未闭环的失败证据，不能宣称 native DDR 集成通过，生产 RTL 未修改。
- 抽象 bridge 70 事务回归仍 PASS；继续修复 activation write ready/valid 时序并补 watchdog/abort 场景。PDS 唯一路由已到 iteration283，未布6813，仍无 `.sbit` 或时序报告。

## 2026-11-01 18:31：四层 ping-pong 激活回放通过，下载器已重新枚举

- `sim/experiments/npu_pingpong/` 持久化四层候选：conv1..conv4 全部输出及 pool1..pool3 激活回放逐字节 golden 一致，`build/sim/npu_pingpong/run.log`，30750042周期。双store A=0x00400000（pool1/pool3复用）、B=0x00440000（pool2），使用抽象DDR命令；不等同原生37-bit控制器、综合或上板。
- 下载器物理重插后只读枚举成功：FTDI USB Composite、Converter A/B、COM3/COM4，CP2102 COM5 均为OK；`cdt_js` PID9040、`cdt_cfg` PID46156保持，未重启/终止/烧录。
- 唯一PDS仍在运行至iteration252，未布6619，未生成timing或sbit；继续自然收敛，不能宣称布通。GitHub上一版本 `958a84d`，本轮pingpong证据提交后再推送。

## 2026-11-01 18:23：重复推理反例修复与 native bridge 增强通过

- `sim/experiments/npu_lifecycle/` 三项真实RTL测试通过：GAP原版late-arm两帧只产256结果，early-arm+priority restart候选512结果逐值一致；真实pool两帧及accepted-last sticky完成保持；新A/B激活区17项边界/owner/len地址错误标志验证。arbiter只置addr_err，不拦截非法grant，未宣称地址保护。
- `sim/experiments/npu_m1_bridge/run.py` 持久runner实际PASS：70正常事务（480权重beat、20激活写/20读），early-done16/same14/delayed20；额外不完整读abort显式失败，FAULT静默到复位。旧bridge early-done在905ns截断读的反例已保留，见 `reports/npu_m1_bridge_validation_20261101.md`。
- bridge现按valid&&ready计数读beat，native done后撤请求但保留owner到读完；新增m1_abort/transaction_failed，仍需真实控制器cmd_to_err接线与联合仿真，不将独立模型等同实际DDR通过。
- 已推送 `7c19441`：前两层真实激活链基线持久runner含每读命令credit断言并现场通过12242761周期。继续扩conv3/4双store/mux，同时补bridge+真实controller联合验证。主线与唯一PDS输入继续冻结。

## 2026-11-01 18:17：真实前两层 DDR 激活链候选通过

- 修复store行切换与顶层计数错一拍的信用漏洞：CREDIT曾使用上一行号提前回放未来行，覆盖conv仍读取的bank。改用动态store直接输出replay_row后通过。
- `build/sim/npu_activation_dynamic/run.log` 实际运行：conv1 792576项、conv2 396288项完整golden逐值一致，pool1写出及canonical回读逐字节一致，共12242761周期。使用宽口WDMA与抽象DDR模型；BASE=0x00400000。持久化成功基线与扩展conv3/4继续，尚非原生DDR/完整NPU/板级通过。
- 宽口WDMA完整conv1也通过：`build/sim/npu_conv1_wide/run.log`，792576项、859229周期；尚无综合资源收益实测。
- native bridge首轮70事务模型覆盖不足：真实controller的done可能早于读FIFO排空。代理正补early-done反例和读beat计数保留owner，同时审查watchdog abort显式失败，首版不得视为原生接入已通过。
- 独立激活地址候选A=0x00400000..0x0043ffff、B=0x00440000..0x0045ffff，与原五区不重叠；候选arbiter白名单与长度/越界测试正在补齐，主线尚未改。
- PDS iteration247未布6653，仍无位流；只读板卡诊断 `build/board_diag_20261101_1813.json` FTDI未枚举，PnP仅COM5 CP2102在线，既有JTAG进程/端口保持。未终止或重启设备服务。GitHub已推送 `01ca299`。

## 2026-11-01 18:09 心跳：激活缓存真实尺寸通过，conv2 回放失配修复中

- 动态共享行缓存候选 `sim/experiments/activation_store/` 三层真实尺寸 RTL 逐字节回读 PASS：198144/98304/49152B，分别6208/3072/1536次写和读。尚未综合、尚未证明原生 DDR 端到端。
- 修复版 WDMA 宽口参数 RAM 持久 runner `python sim/experiments/wdma_parameter_ram/run.py` 六层各350000周期逐拍差分 PASS；日志 `build/sim/wdma_parameter_ram_experiment/run.log`。未综合，不宣称资源收益；完整conv1宽口复测继续。
- 真实 conv1→pool1→DDR→conv2 首轮在 conv2 index24808（row2/group0/col2/lane8）失配 got17/exp28；证据 `build/sim/npu_activation/run.log`。代理继续对照canonical回放逐字节定位，不能宣称完整NPU通过。
- 原生 m1 bridge 候选70事务独立模型通过（480权重读beat、20激活写+20读），将持久化并接顶层；激活DDR候选地址与spectrum重叠也已发现，正在按内存图选择合法双区与白名单。
- 唯一 PDS run `20261101-130420-0ed52a5d` iteration244，未布网络6643，仍无新位流；62项manifest哈希全部一致。原JTAG进程保持，未另起PDS、未烧录。当前布线不含上述候选修复。
- GitHub已同步至 `3d71932`。本轮补充持久实验、纠正交接文档的历史“全链”措辞；下一步继续修conv2、接native bridge、验证二次推理。

## 2026-11-01 18:04 心跳：真实集成 conv1 候选完整对拍通过，层间 DDR 修复继续

- **正式行信用端口候选完整 conv1 PASS**：`build/sim/npu_conv1_step9/run.log`，792576 个输出逐字节与 golden 一致，859229 周期；当前 feat 重新计算 golden 也一致。候选包含参数 beat/通道索引、WDMA 握手、半 beat 末 tap、wbuf 预读/装载屏蔽和特征行信用修复，尚未合入主线或当前 PDS。
- **背压候选通过**：独立 conv 输出 FIFO 随机背压对拍 792576 项 mismatch0；pool 奇数宽度长背压 128 项通过；pool→激活缓存→DDR→规范顺序重放 128B 逐值一致（4 写4读，DDR write ready 每101拍只开放5拍）。持久资产 `sim/experiments/activation_pipeline/`；真实前两层集成继续，不能扩展为完整 NPU PASS。
- **真实小几何联合链通过**：`sim/experiments/activation_pipeline/run_conv_pool_store.py`，非零3x3权重、通道bias、整数requant的独立数学golden，384个conv值+96个pool/DDR重放值一致，4写4读且长DDR写暂停；不是只用驱动器模拟conv输出。
- **wbuf 反例补齐**：持久化 `sim/experiments/wbuf_replay/`，旧 step4 在装载阶段 stale valid 反例失败，新 step8 10797 次握手通过。旧的 10797 次 PASS 没有覆盖此边界，已在报告纠正。
- **唯一 RV PDS**：`build/pds/20261101-130420-0ed52a5d` 到 iteration240，未布网络6538，仍无时序报告/新位流。继续运行，不并发另一 PDS；当前冻结 run 不含 NPU 候选修复。GitHub 最新已同步700d7fa，后续实验将继续提交。

### 之前的定位记录（保留失败证据，以下 mismatch 已被上面的 conv1 候选覆盖）

- `build/sim/wdma_wide_diff/run.log`：原版与宽口候选在 layer 0..5 各 350000 周期逐拍比较通过；覆盖 `rd_cmd`、权重/参数流、`grp_start`、`busy`、`done` 及随机响应间隙/背压。该结果只证明候选与原版等价，不证明原版功能正确，也未证明资源下降。
- `build/npu_full/wdma_step3.v` 候选已修复 bias/M 每个 DDR beat 的索引步长（+8）、shift 索引步长（+32）及 `grp_mod * 16` 通道偏移；诊断确认参数 index 0 的 bias=-287、M=1762673006、shift=41 与合同一致。但完整 conv1 首点仍失败：`got=7 exp=4 cycle=535`，因此整链仍不正确。候选仅在 build 目录，主线 RTL 与冻结 PDS manifest 未修改；继续定位权重/激活选择或 MAC/量化数据通路。
- 唯一 PDS run `build/pds/20261101-130420-0ed52a5d` 继续 detail route；iteration 220 未布网络 6756。最近 30 轮（191–220）未布网络 6572–6926、均值约 6772，呈高位震荡；仍无 `report_timing`、`.sbit` 或 RV 板级证据。父子 `pds_shell.exe` PID 36628/40640 属于同一 run，不得终止或另起 PDS。
- 当前已验证：RV CPU C1-C9、RV 控制/MMIO、Mel/Mel credit、conv1 独立 golden、NPU 组件链、DDR3 子系统/AW timeout、UART line buffer、UI render/overlay、WDMA 原版/候选逐拍等价。未验证/有问题：CPU→NPU 真实数值端到端、完整 NPU 自然逐层通过、当前 RV 位流及板级 RV/权重上传。
- 后续 step4 候选修复 `wbuf` 同步读地址推进：原版实际 MAC tap 序列为 0,0,1..7，重复首项遗漏末项。候选首点已为 `got=4 exp=4`，前 272 项通过；下一失败是 index272（row0/group0/col17/lane0）`got=17 exp=0 cycle=824`。日志 `build/sim/npu_full_step4/run.log`；正在检查无背压 feature replay 对三行 ring 的覆盖。独立代理补做 wbuf 随机背压/重载验证，以及共享 conv 核层间缓存容量审查。
- 本次重新运行 `python scripts/check_rtl.py`：53 个文件、0 violation；`python -m pytest -q`：429 passed / 4 skipped（88.36 s）。最新状态提交 `58d8ebb` 已同步 `origin/XSY`。
- step5 feature 行信用候选后，conv1 group0 整行 4128 个输出已通过，首次失败推进到 group1 首项：index4128 `got=0 exp=51 cycle=4926`；正在对照换组参数 shadow/active bank 与同步 RAM 预热。wbuf 候选独立 10797 次握手验证通过，详见 `reports/wbuf_candidate_validation_20261101.md`（含修复 diff 和 SHA256）。
- 层间结构审查确认另有三项独立阻塞：下一层三行 bank 被整帧 pool 输出覆盖、下一层 start 清 row_done、pool 的 row/group/col/lane 顺序与 conv ingress 不同。片上全帧缓存余量不足；正在 build 目录开发 DDR 激活缓存/受信用重放协议候选，详见 `reports/npu_interlayer_storage_review_20261101.md`。当前 PDS 即使布通也不含这些修复，不能当作真实完整 NPU 推理已验证。
- WDMA 随机背压原候选已在 layer0/group0/tap1 复现失败；修复候选用当前 FIFO 指针组合派生 `w_valid/w_data`、仅真实握手推进，4943 个真实 tap（conv1/2/4/fc2、长 stall、随机 ready、半 beat）通过。接入 conv1 step7 后 group1 cache 已匹配镜像，但首输出仍 `index4128 got=72 exp=51`，继续定位换组 MAC 窗口对齐，未改主线。
- 激活缓存协议候选已持久化到 `sim/experiments/activation_store/`：真实 pool1/2/3 尺寸 Python 重排/32B 读写通过，RTL 小几何 288B 精确读回通过，覆盖命令/数据/R 延迟、背压、行信用和输出停顿；明确尚未接入现有无 ready 的 pool、原生 DDR 控制器或 PDS，不能宣称整链修复。
- WDMA 原候选反例与修复已持久化 `sim/experiments/wdma_handshake/`，现场重跑 baseline 预期 FAIL、fixed 4943 tap PASS，见 `reports/wdma_handshake_validation_20261101.md`。换组 MAC 错误进一步定位到 wbuf 装载首拍旧 valid 穿透：`grp_start` 边沿状态进 LOAD，但 `rd_vld_q` 从旧 RPY 仍保持 1 一拍。此前 10797 次测试仅检查 grp_start 当拍，未覆盖随后整个 LOAD；正在增强反例与状态/valid 修复。

> 本文件是**唯一实时状态源**，优先于任何交接快照与记忆。每次会话结束前必须更新，
> 并在 `CHANGELOG.md` 追加一条。最后更新：2026-11-01 18:31。

## 2026-11-01 17:18 新确认的整链阻塞（优先于组件 PASS）

- 原版完整 `npu_top` 实验不跳层、不注入完成，50000000 周期停在 layer0 并超时。进一步诊断：conv1 输出 0，参数计数 47/48，WDMA `taps_left=0/emit_beats=1`。
- 已确认半 beat 末 tap 控制缺陷：`wdma.S_TEMIT` 只有耗尽整个 beat 才进入下一组，conv1 的第 9 tap 落在低半 beat 后无法退出。build 副本最小修复后 WDMA 从 grp0 推进到 grp1；卷积仍被独立的参数起始问题阻断。
- 参数起始问题：`grp_start` 与首个 `b_valid` 同拍，卷积参数计数被重置，最终只计入 47/48 拍。正在 build 副本提前起始脉冲并复测；另审查逐 DDR beat 参数索引和通道组索引，尚不宣称整链正确。
- 当前 PDS 输入保持冻结。这些修复在 build 候选中验证，当前 run 即使产出位流也不能证明 NPU 整链推理通过。
- `wdma` 参数表在当前综合中展开为 20480 个存储 FF，未推断为 DRM；资源证据与宽写口候选见 `reports/rv_route_resource_review_20261101.md`。候选尚未综合，不宣称已降低 LUT。
- 只读板卡检查：COM5 存在，原 jtagserver PID9040 / cdt_cfg PID46156 与端口65420保持；FTDI 当前枚举为 ABSENT。未重启/终止下载器，未尝试烧录。诊断 JSON：`build/board_diag_20261101_1714.json`。

## 2026-11-01 15:56 RV 构建持续布线与并行验证

- PDS run `build/pds/20261101-130420-0ed52a5d` 仍在运行，已进入 detail route；17:12 检查到 iteration 192，未布通网络 6638。当前仍无新版 RV 位流、时序报告或板级证据，不能宣称 PNR 完成。已核对 manifest 的 62 个输入文件，SHA256 全部一致。
- 并行 Verilator 回归新增通过：`rv_cpu` C1-C9、`weight_loader` 10 项（WOK/CRC/读回 digest）、`mel` 与 `mel_credit`（16512 特征样本 mismatch 0）、`ui_render`、`ui_overlay`、`npu_chain`、`npu_completion`、`ddr3_subsys`、`ddr3_aw_timeout`、`ctrl_smoke`、`self_test`、`rv_top_ctrl` 均 PASS。
- **UART 误诊已撤回**：同一增强 TB 对原版与宽度扩展临时版均 PASS；7-bit `ram_len` 将 128 编为 0，而结束比较的 7-bit 减法回绕为 127，未复现发送失败。新增正式 `uart_linebuf` 回归验证原版满 128 字节、短/空换行、TX 背压、ready=0 写丢弃及 busy/ready 恢复；不合入无必要的 RTL 补丁。
- `python scripts/check_rtl.py`：53 个 `.v` 文件，0 violation。当前主线工作区未修改 PDS 输入；用户预存的 `cpu/`、PCB、PDF 变化保持未提交。
- UART/sys_ctrl/烧录安全 Python 回归：35 passed。
- 本次心跳检查：PDS detail route iteration 180，未布通 6949，持续运行；无新位流或时序报告。
- 后续心跳：PDS detail route iteration 185，未布通 6608，仍在运行；无新位流或时序报告。新增 `rv_cpu`、`rv_top_ctrl`、`npu_completion`、`self_test`、`ctrl_smoke`、`weight_loader` 仿真均通过；全量 Python 回归 429 passed / 4 skipped，RTL 检查 53 个 .v、0 violation。
- 最新 PDS 监控到 iteration 187，未布通 6600。额外重跑 `npu_chain`、`ddr3_subsys`、`ddr3_aw_timeout` 均 PASS（NPU 数值 bit-exact；DDR3 15/15、AW timeout 6/6 场景）；仍无新位流或时序报告。
- 本次原 14 项 RTL suite 已分组全部重跑通过，新增 `uart_linebuf` 也 PASS（共 15 项）；conv1 792576 值 mismatch 0，Mel 每配置 16512 值 mismatch 0。CPU ROM/RAM 已映射为 6 块 DRM，CPU 顶层 `ENABLE_M=0`，不能靠再次关闭 M 或简单更改存储推断消除拥塞。当前 map：LUT 35840/66600，DRM 80.5/155；placer 物理利用率 81%，路由耗时无可靠 ETA。

## 2026-11-01 11:35 RV32 + AI 最小融合（最新，覆盖下文旧架构结论）

已提交初始集成 `9d0acf1`，新增 `rv_core` / `top_rv_core`，复用 `cpu/rtl` 的 CPU，配置为 RV32I（M/分支预测关闭），8 KiB ROM + 8 KiB RAM。CPU 经 MMIO 请求一次 NPU 推理、读取 DDR/NPU 状态与结果、输出共享 UART、控制 LED。默认 `NPU_ENABLE=0`：CPU 请求是启动必要条件，请求挂起到 DDR 自检通过、权重就绪、完整 Mel 窗口完成且 NPU 空闲才启动。I2S SD 仍接 0、无视频引脚；该顶层不代表真实音频/UI 全功能融合。

本轮补修：STATUS DDR 位布局；UART 满 FIFO 背压与共享串口 stale-ready；结果周期快照；新事件与软件清除竞争；`npu_top.layer_finished` 缺失 `L_SM -> sm_done`（否则 busy 不释放、done 不产生）。真实 npu_top/softmax 的两轮完成与重启仿真已 PASS，前层在 TB 中跳过，不能据此声称整链数值通过。

验证：全量 Python **429 passed / 4 skipped**；RTL 词法检查 53 个 .v、0 violation（不覆盖 .sv CPU，CPU 另经 Verilator/PDS）；RV CPU/固件/MMIO 仿真 C1-C9 PASS，包括真实固件请求、DDR_OK、sticky 清除、周期快照，NPU 完成结果由 TB 注入。conv1 TB 字节/像素计数单位修正后 **792576 值 mismatch 0**。本轮完整 RTL 集合 **14 PASS / 0 FAIL / 0 SKIP，281.0 s**（含真实 UART 控制 slice 15 项、真实 NPU 完成/重启、UI renderer 64 像素和 overlay 6 项、DDR3 子系统）。`audio_cdc_fifo` 独立双时钟、`i2s_rx` bit-level 临时仿真通过；`i2s_clk_gen`+`i2s_rx` 联合仿真也通过（769 ticks、24 LRCK 边沿、24 字，L/R=`A53C`/`5AC3`，NCO 步长为加速值）。详细结论 `reports/rv32_sim_conclusion.md`。发现并修复 `instrec_top` 的 `dbg_tx_ready` 隐式网络；修复旧 `ms72xx_ctl.init_over_rx` 重复声明以便解析。使用 build/sim 临时厂商黑盒 stub 后，Verilator `instrec_top` 结构展开退出码 0、无 IMPLICIT/MODMISSING/Error；stub 仅证明端口/层级结构，不是 IP 功能或时序证据。全量 Python 回归 **429 passed / 4 skipped**。

旧资源 gate `build/pds/20261101-102333-c9e3d804` 于 10:47:22 完成综合：LUT 35804/66600、FF 53813/133200、DRM 80.5/155、APM 90/240。但解析早于 MMIO 修正，且不含本轮完成/启动/UART修复，**不得当作当前 RTL 位流**；无 PNR/位流。详见 `reports/rv_core_synth_gate_20261101.md`。

上一 run `build/pds/20261101-113509-6927c1bf` 在 detail route iteration 21 后异常结束，没有完成标记、时序报告或位流；恢复脚本验证其 PDS 数据库缺少 post-synthesis design，无法从 `pnr`/`dev_map` 续跑，已保留全部日志，不视为成功。

**当前完整构建**：`build/pds/20261101-130420-0ed52a5d`，`rv_core/top_rv_core` 已完成 compile/synthesis/map，正在 detail route；一次只允许此 PDS 实例（父子进程属于同一 run）。RTL/FDC 已冻结；manifest 记录输入 SHA256，结束校验不变后才发布 latest。新增 clk_nco 216MHz 约束，最终必须逐域核对时序。当前**没有新版 RV 位流/板级通过证据**。

顶层审查曾将 `uart_debug.ram_len` 的 7-bit 宽度告警判断为发送缺陷；17:12 原版/临时版差分回归均通过，已撤回该判断。其隐式模 128 长度编码在原版比较表达式中正确结束，正式回归为 `python sim/run_sim.py uart_linebuf --verbose`。本轮只增加仿真资产，未修改构建输入。

板级：用户已恢复下载器；获准沙箱外 `board_check.py --diag-only` 确认 FTDI present、jtagserver PID9040、port65420 open，原 cdt_cfg PID46156 保留未终止。此前沙箱内 FTDI ABSENT 是设备枚举权限导致，不是物理离线证据。待新位流完成后依次验证 RV32 BOOT/MMIO/ISA、DDROK，再权重上传及真实 CPU 请求推理。

## 一句话

**2026-11-01 05:38 — R1 达成：DDR3 已 board-proven。** 精简顶层 `top_core_only`
（裁掉 UI/HDMI，保留 DDR3+NPU+Mel+权重）布通并两次烧录，串口完整输出
`INSTREC BOOT` → `DDR3 SELFTEST...` → **`DDROK`** → `DDR3 STS 01`；`board_core_only.json`
`verdict=PASS`、`expect_missing=[]`、`status_raw=0x081ffca0`、`uart_bytes=48`；
`DDR3 STS 01` 的低两位 `st_done=1`、无超时位 ⇒ self_test 的 16 段写 + 读回全部通过。
位流 SHA-256 `D375A43DBA3D5DB68285CDBA3C5158413379510EA53D29EA8BAEC17F4C4E18A8`。
该位流的 `APM=0` 是常量传播把 NPU/Mel 删掉的取舍结果，**只能证 DDR3，不能证 NPU/Mel**；
正在恢复音频前端后重出。`DDR3 PHY` 专用硬核确在网表（`DDR_PHY 7/24`、`PPLL 2/6`、
`TSERDES 14/48`），`DRM=0` 与 PHY 无关（DRM 是通用分布式 RAM）。

> **架构事实（2026-11-01 交接补充）**：本工程 `instrec_fpga/` 是**纯硬件管线，不含 RISC-V 软核**。
> `instrec_top` 只例化 audio / mel / npu / ui / ddr3 / uart 各组模块，`src/` 下**没有 `cpu/` 目录**。
> 软核及其工具链、bootloader 在独立的 `cpu/` 项目（RV32IM，120 MHz / 383.0 CoreMark），
> 与 InstRec **当前未融合**。赛题要求「RISC-V CPU + AI 加速」，故**总线级融合是首要缺口**，
> 不是接线级工作。详见 `docs/HANDOFF_SNAPSHOT_20261101.md` 的「一点五」节。

## 历史一句话（2026-10-31，R1 尚未达成时）

InstRec 8 类乐器识别（INT8 CNN）正在移植到盘古 100Pro+（PG2L100H-6IFBG676）纯 FPGA 管线。
**全功能位流 m3d（音频→DDR3→Mel→NPU 全链→概率条+波形+文字+谱图四层 UI）已布通归档**：
LUT 34327（52%）、DRM 86、`pix_clk` +0.018、`ddrphy_sysclk` -0.966。
**`DDR3 ERR @FFFFFFFF` 的阻塞已在 2026-10-31 解除**：根因是 `self_test` 的 `done` 端口从未被
使用（AXI watchdog abort 后永久卡在 `ST_WDATA`），已修；`ddr3_diag` 诊断位流实测
**design 配置（`AXI_USER_AP=1` / masked strobe）PASS，16-beat 真实写/读通路首次被真正激励**。
全量侧接线与参数已逐项核对等价于 design 配置，**T10 全量构建进行中，尚未产出位流**。
接手先看 `docs/HANDOFF_SNAPSHOT_20261031.md`，再读本文「当前状态」最新一节与
`reports/ddr3_diag_conclusion.md`（第 10 节为第二轮结论）。

## 里程碑

| 里程碑 | 状态 | 关键证据 |
|---|---|---|
| P0 工具链 + Python 金标准 | 完成 | `pytest -q` **280 passed / 4 skipped**；`golden_pipeline.py` 位级真值 |
| M0 I2S→DDR3→HDMI 波形 | 完成（未上板） | run `20261027-000612-a71f1451`，sha256 `C517736C…`，WNS +1.757 |
| M1 Mel 特征引擎 | 构建完成、时序收敛、待板级对拍 | run `20261027-121101-5c24a968`，sha256 `BD40D10A…`，WNS +1.438 |
| M2 INT8 NPU | 全链布通、已上板；**DDR3 真实读写通路已由诊断位流验证 PASS** | m2/m2b/m2c/m3a 四版归档；`ddr3_diag` design 配置 `result_a=PASS`（`F749A417…`）；m3d `ddrphy_sysclk` -0.966（最差在 DDR3 IP 内部） |
| M3 UI 集成 | **完成：四层 UI 全部在 m3d 位流中**，并已从 DDR3 解耦出独立演示顶层（待上板） | 概率条 + 波形 + 类别文字 + 谱图；`pix_clk` +0.018；`top_ui_demo` 已就绪，UI 位流排在 T10 之后 |
| 全功能位流 | **m3d 布通归档**；**新一轮全量（T10）构建进行中，尚无位流** | `releases/m3d-20261031/`，sha256 `0B2BE8D4…`，LUT 52% / DRM 56% |
| 板级端到端 | **DDR3 自检阻塞已解除（诊断位流证据）；全量 `DDROK` / `WOK` 待 T11** | 诊断两轮：首轮两 cfg TIMEOUT（端点接错）→ 修复后 design PASS（A/B/C/D=16/136/16/128） |

## 当前状态

### 2026-10-31 13:56：DDR3 阻塞根因解除（诊断位流两轮）+ T10 全量构建进行中（本轮最新）

> 证据全在 `reports/ddr3_diag_conclusion.md`（**第 10 节是第二轮结论**）、
> `reports/board_ddr3diag_20261031T053011Z.json`（首轮）、
> `reports/board_ddr3diag2_20261031T054946Z.json`（修复后）。两条 `verdict` 均为 `PASS`，
> `expect_missing=[]`、`jtagserver_pids=[9040]`（全程复用，未新开、未 terminate）。

#### 一、根因与修复（`self_test.done` 端口从未被使用）

- **现象**：`DDR3 ERR @FFFFFFFF` 是 `sys_ctrl` 的 100 ms 看门狗分支，不是地址错。
- **根因**：`self_test` 的 FSM **从未监听 `done`**。AXI watchdog abort 后 `ddr3_ctrl_axi`
  不再推进，`self_test` 就**永久卡在 `ST_WDATA`** 等一个永远不来的 `wready_beat`，
  最后由顶层看门狗判超时。
- **修复**（`src/ctrl/self_test.v`，**端口不变**，只改 FSM）：
  1. 写阶段改为 `if (wready_beat) … else if (done)` —— `wready_beat` **必须先判**：
     正常完成时 `done` 与**第 16 拍 `wready_beat` 同拍**拉起，先判 `done` 会丢掉末拍数据；
  2. 读阶段用**延迟 1 拍的 `done_q`**，且 `rd_valid` 先于 `done_q` 判定；
  3. `cmd_valid` 改为**电平 hold 到 `done`**（F1/F3），只在真正完成时清零。
- 判据：`tests/test_self_test_model.py`（14 项）把三类向量（正常完成 / abort 后 done /
  读通路 done）锁死；`tests/test_plan_contract_guards.py` 防止端口与下标再漂移。

#### 二、诊断方法论（本轮最大收获）

把 PDS 流水**参数化成构建集**，让「一次上板同时回答两个问题」成为常规手段：

- `scripts/build_sets.json` 定义 `full` / `ddr3_diag` / `ui_demo` 三套（top module、设计源、
  IP、约束、hex 复制目录各自独立）；
- `scripts/build_full.tcl` token 化（**8 个 token**，含 `__TOP_MODULE__` / `__DESIGN_FILES__` /
  `__IP_FILES__` / `__CONSTRAINT_FILES__` / `__HEX_COPY_BLOCK__`），六阶段逻辑未改写；
- `scripts/run_pds_full.ps1` 新增 `-BuildSet` / `-DryRun`（dry-run 只打印展开结果，不启动 PDS）。
- `ddr3_diag` 是**最小诊断位流**：7 个设计源 + 1 个 IDF + 2 个约束，资源 LUT 4954（7%），
  离 53.6% 布线临界点极远，因此构建快。
- **实测成本（务必记住）**：`ddr3_diag` 单轮 **4 m 37 s ~ 5 m 13 s**；全量 `full` **约 1.5 h**。
- 一套位流内**同时例化两份不同 AXI bring-up 参数的 `ddr3_ctrl_axi`**：
  `u_ctrl_design`（`AXI_USER_AP=1`、`DUMMY_WSTRB_ALL1=0`，masked strobe）与
  `u_ctrl_demo`（`AXI_USER_AP=0`、`DUMMY_WSTRB_ALL1=1`，all-1 strobe），
  外围 12 条 mux 在轮次间切换 ⇒ **一次上板拿到两套配置的独立结论**，不用两次构建两块板。
- 诊断帧经 `src/diag/diag_uart_report.v` 输出：**91 字节固定 ASCII 帧、显式 case 表、
  无字符串字面量**（规避 PDS 字符串字节序不可预测的老坑），
  `scripts/diag_frames.py` 负责 `parse_frame`/`parse_all` 与位段解码。

#### 三、两轮板级结果

| 轮次 | 位流 SHA-256（前 8） | 配置 | `result` | A `aw_hit` | B `wready` | C `done[3]` | D `rvalid` | `wlast_miss` | `to_err` |
|---|---|---|---|---|---|---|---|---|---|
| 首轮（D-01 未修） | `82095667` | design | **TIMEOUT** | 250 778 | 250 778 | **0** | 250 777 | 0 | 0 |
| 首轮（D-01 未修） | `82095667` | demo | **TIMEOUT** | 261 369 | 261 369 | **0** | 261 369 | 0 | 0 |
| **第二轮（修复后）** | **`F749A417`** | **design** | **PASS(1)** | **16** | **136** | **16** | **128** | **8** | **0** |
| 第二轮（修复后） | `F749A417` | demo | **FAIL(2)** | 9 | 129 | 8 | 3 | 8 | 0 |

- **首轮**：两套 cfg 均 TIMEOUT，特征 **`A==B==D≈25 万、C(done_cnt)=0`**。根因是
  `src/diag/top_ddr3_diag.v` 的 `st_cmd_valid` 写成 `{3'b000, st_cv}`（`self_test` 挂到
  **master 0**），而 `done`/`wready_beat`/`rd_valid` 全取 `[3]` ⇒ 控制器一直在跑
  m0 的 `cmd=0` 空读（读前 dummy-write 恰好 1 拍，故 `A==B==D`）。**该缺陷只存在于诊断顶层**；
  契约 `plan.md §2.2.4` 的示例代码本身也写错（注释说 master 3，代码却是 bit0），**已修正**。
- **第二轮**：`result_a`（design）= **PASS**，`A/B/C/D = 16/136/16/128`、`wlast_miss_cnt=8`、
  `to_err=0`、`st_fail_addr=0`。逐项自洽：`A=16`=8 写 AW + 8 读 dummy-write AW；
  `B=136`=8×16 写拍 + 8 次 dummy 拍；`C=16`=8 写 done + 8 读 done；`D=128`=8×16 读拍；
  `wlast_miss=8`=`S_WLAST` epilogue 首次被进入 8 次。**16-beat 真实写/读通路首次被真正激励。**
- `result_b`（demo）= FAIL 属**预期代价**：`DUMMY_WSTRB_ALL1=1` 的 dummy-write 用全 1 strobe
  覆写被读区域首拍（`F=0x0030_0000` = 首条读命令），与 design PASS 不矛盾，反而互相印证
  **masked strobe 才是正确策略**。
- `wlast_miss_cnt=8` 只是观察项：它不参与完成判定
  （`write_cmpl = (state==S_W) && axi_wready && beat_cnt==cur_len`），无功能影响；修它要动
  `ddr3_ctrl_axi` 时序，**T10 不动**。

#### 四、对全量 `instrec_top` 的含义

`src/ctrl/instrec_top.v:638` 的 m3 拼接本就在 **bit3**（`{st_cmd_valid, …}`），
`ddr3_ctrl_axi` 例化**无参数覆盖**即默认 design 配置（`AXI_USER_AP=1`/masked strobe）。
⇒ **T10 全量收敛预期 0 行 RTL 改动**，diff 只应包含 T2 交付的 `src/ctrl/self_test.v`。
但**仍不能据此宣称全量会 `DDROK`**：全量走的是 m0/m1/m2/m3 四口仲裁 + 真实权重写，
必须由 T10 位流 + T11 板级实测确认。

#### 五、UI 通路已从 DDR3 解耦（尚未上板）

- 新增 `src/diag/top_ui_demo.v` 小顶层：HDMI + `ui_renderer` 四层全接通 + pix 域统计计数器
  （`hdmi_init_over` / `de_nonzero_cnt` / `bars_on` / `text_on` / `spec_on` 等）+ 诊断帧。
- 新增片内假数据源 `src/ui/demo_wave_source.v`、`src/ui/demo_spec_source.v`
  （不依赖 DDR3 / Mel / NPU）。
- 新增 `constraints/top_ui_demo.fdc`：**42 个引脚与 `instrec_top.fdc` 逐项一致**。
- UI 位流构建（`-BuildSet ui_demo`）**排在 T10 之后**（唯一 `pds_shell` 串行），代码已就绪但
  **未构建、未上板**。

#### 六、T10 状态

**进行中（2026-10-31 13:52 启动，纯 `pnr`，预期约 1.5 h），尚未产出位流。**
`build/instrec-latest.{sbit,json}` 仍是 2026-10-31 10:46 的 m3d 产物（3 791 112 B / 2393 B），
**未被覆盖**。判读以 `build/pds/<最新时间戳>/`、`build/instrec-latest.json` 的 `Wns`
与 `reports/full_build_conclusion.md` 为准，**不要**把本文件当成「全量已成功」。

#### 七、已知限制（照实记录）

- 本机**无 Verilog 仿真器**（WSL 不可用，Ubuntu vhdx 缺失），所有时序正确性只能靠
  **Python 周期模型 + 源码静态断言**（`tests/*_model.py`）+ 板级实测，没有波形级证据。
- **UI 画面内容无法脚本化判读**（无摄像头）：只能以 `hdmi_init_over`、`de_nonzero_cnt`、
  各层 `*_on` 计数 + `pix_clk` 域 WNS 作为证据，不能证明画出来的内容"好看/正确"。

### 2026-10-29 夜间：M3 接线恢复 + 板级编排/判据补齐

- **M3 五个模块接线已恢复**（提交 `92d0531`）：`text_disp` / `feat_copy_engine` /
  `feat_page_buf` / `spectrum_disp` / `ui_coord_delay` 重新例化，`ui_renderer` 的
  `spec_rgb/spec_on/text_rgb/text_on` 由常量改回真实信号（此前为缓解拥塞而注释）。
- **分阶段重建脚本 `run_pds_stage.ps1` 首次使用即失败并已修**：不调 `open_project` 时
  PDS 会新建默认 `fab_demo/PGL12G` 工程覆盖原工程，随后 `pnr` 报
  `Flow-0044: Device Map hasn't been run`，使 run `20261029-191053` 报废。
  已加两道防线：运行前校验 `<run>/<project>.pds` 存在且描述 `PG2L100H`，
  生成的 `stage.tcl` 首行 `open_project -file {...}`。**该功能未验证成功，暂不作为常规路径。**
- **首轮 UART 修复版（`191053`）布线停滞**：iteration 148→162 未布网络 7199→7262 基本不动
  （每轮 47 s），判定为布局拥塞边界上的随机性（同 RTL 的 `172919` 曾 886 轮收敛），
  已中止并改用**全量重建 `20261029-212311`**（含 M3 恢复 + UART 握手修复）。
- **M3 全功能版（`20261029-212311`）布线判为不可接受并中止**：LUT 35912 (53.92%)、
  DRM 86.0 (55.48%)、FF 49827、Utilization 79%；布线 iteration 27/33 仍未布 31693/29031，
  且每轮耗时 128→192→250 s 递增（同轮次远差于 M3 关闭版的 m2c，后者 iteration 47 已到 12122）。
  处置：**先用 M3 关闭版拿到 UART 验证位流**（`20261029-231920`，23:19 启动），
  待 `INSTREC BOOT` 确认后，再单独一轮加回 M3 并接受其更长的布局时间。
  `src/ctrl/instrec_top.v` 已临时 checkout 回 `693f1fc` 的关闭状态，**验证后必须用
  `git checkout HEAD -- src/ctrl/instrec_top.v` 恢复，否则 M3 会丢失**。
- **UART 修复版第二次全量（`20261030-0012`→`231920`）同样停滞**：iteration 275 剩 5546，
  与 `191053`（7262）同型；而资源与已布通的 m2c **完全一致**（LUT 35666/53.55%、FF 49690、
  DRM 79.5），说明停滞是**布局随机性**而非资源超限。已中止，第三次全量 `20261030-021342` 启动。
- **增量重建路径两次毁工程**：`open_project -file` 报「option not defined」，随后 PDS 自动新建
  默认 `fab_demo/PGL12G` 工程**覆盖 `.pds`**，`231920` 与 `191053` 的工程状态因此报废。
  已改为 `open_project {path}` 并在运行前备份、失败时自动恢复；**该路径仍未验证成功，
  不要当成常规提速手段**。教训：任何「复用已有 run」的脚本都必须先备份工程文件。
- **`pnr` 选项实测（本轮新增，重要）**：`pnr -help` 实测支持
  `-gplace_seed` / `-gplace_times` / `-seed_step` / `-parallel`（多 seed 并行）、
  `-groute_seed` / `-groute_times`、`-plc_decongestion`（布局解拥塞）、
  `-force_to_run`、`-input_db_file`、`-slack_prior_in_global_router`、
  `-dump_router_congestion_plot`；`-number_of_router_thread` 仍被器件拒绝。
  → **布局是确定性而非随机**：三次同 RTL 构建都停在同样量级的未布网络（~5-7k），
  因为默认 `-gplace_seed` 固定。现已在 `build_full.tcl` 改用 `pnr -gplace_seed 7`
  作为第一个替代布局（构建 `20261030-054801`）。
- **增量重跑布线（复用 netlist）实测不可行**：`pnr` 单独执行报
  `Flow-0044: Device Map hasn't been run`；加 `-force_to_run` 后进入 pnr 但报
  `Flow-0013: input DB '(null)' should be of phase 'DEVMAP'`；指定
  `-input_db_file device_map/dmr.db` 仍报同样错误（且版本告警 DB-4001）。
  结论：PDS 的 phase DB 不能跨会话复用，**每次必须全量走 compile→synthesize→dev_map**。
  相关文档随后更新；`run_pds_stage.ps1` 保留但标注不可用。
- **多 seed 并行布局是唯一能布通的配置（关键突破）**：`pnr -parallel 4 -gplace_seed 7
  -seed_step 3 -route_parallel 4 -groute_seed 7 -route_seed_step 3 -generate_bitstream TRUE`
  使布线在 **iteration 15 就达到未布 0**（单 seed 的默认/种子 7 两次都停在 2400~7200 无法收敛）。
  代价是耗时：4 seed 跑了 5 小时仍未汇总，已改为 **2 seed**
  （`pnr -parallel 2 -gplace_seed 7 -seed_step 3 -generate_bitstream TRUE`，构建 `20261030-105655`）。
  → 「布不通」不是密度问题（同资源 m2c 曾布通），而是**单种子布局落在拥塞解上**；
  `-parallel` 同时给出多个布局候选，是这台器件上唯一可用的并行加速。
- **多 seed 模式的耗时问题已定位并加超时**：`-parallel 2` 时第一个 seed 在
  **iteration 15 即 Unrouted 0**，但 PDS 会继续把第二个 seed 布到数百轮（实测 799 轮
  仍未结束，整轮已超 2 小时）。处置：`pnr -parallel 2 -gplace_seed 7 -seed_step 3
  -timeout 45 -generate_bitstream TRUE`（构建 `20261030-135506`），超时后取已完成的最好结果。
  若该轮仍不产出位流，回退候选是加 `-plc_decongestion`（布局解拥塞）或提高并行数。
- **板级一键 bring-up `scripts/board_e2e.py`**：`boot → weights → capture → compare` 四阶段链，
  任一步失败即停并给出该阶段的排查提示；`--stage boot|weights|layers` 可单独执行
  （stage 3/4 需要 I2S 有真实音频，否则没有窗口完成事件）。
- **新增判据（本轮 26 项，pytest 由 241 → 267 passed / 4 skipped）**：
  - `test_ui_overlay_model.py`(11)：overlay 四层优先级穷举 + 单级寄存；频谱 5 档热图阈值、
    region 边界、`spec_on = de && region && page_ready`；各层矩形不越 1920×1080；
    **text_disp 的 `name_len` 表与 `class_labels.hex` 实际长度逐类比对一致**（百分比列位置依赖它）。
  - `test_feat_page_model.py`(6)：`feat_copy_engine` 周期模型 —— 恰好 DEPTH 字节、顺序
    0..DEPTH-1、**翻页严格晚于最后写入**、读地址恰好 DEPTH 个、读页恒为写页反相、
    `DEPTH == 258*64`、必须受 npu `busy` 门控。
  - `test_compare_layers_selfcheck.py`(4)：把 golden 参考喂回 `compare_layers` 必须 100% 一致；
    篡改单元素只影响该层并报 `max_abs_delta`；形状不符必须抛错。
  - `test_board_e2e_order.py`(5)：阶段顺序、首败即停、单独 stage 不触发烧录。

### 2026-10-29 傍晚：FTDI 掉线根因彻底修复 + 首次上板

**根因（确定，不是推测）**：`scripts/board_check.py` 的 `run_tcl()` 在日志里一出现
`PROGRAM FLOW DONE` 就调用 `proc.terminate()`。但该横幅是 TCL 里 `puts` 打出来的，
**早于 `cfg_disconnect` / `exit`**，所以 terminate 总落在 D2XX 句柄仍打开的时刻。
被杀的 D2XX 进程不释放句柄 → FT2232H 在 USB 总线上停止响应 → 从 PnP 消失
（`CM_PROB_PHANTOM`）→ 只有物理重插能恢复。这就是「一碰板子就掉线」。

**同源的另外两处缺陷**：① 动态生成的 TCL 没有 `exit`，正常路径也退不出，必然被迫 terminate；
② `board_check.py` 里 `if js is None: return 2` 会把「复用已运行的 jtagserver」误判为失败，
逼着每次新起 server，而重启 server 同样会打乱 USB 状态。

**修复（三条硬规则 + 前后取证）**：
- R1 所有 TCL（含动态生成）以 `exit` 收尾，`cdt_cfg` 正常 2~4 秒自行退出；
- R2 任何代码路径都不得 terminate/kill `cdt_cfg`/`cdt_js`；真超时就报告 PID 并**留着不动**；
- R3 端口 65420 已开则复用，绝不重启 jtagserver；
- R4（用户 2026-10-29 补充的关键事实）**那个 UI 就是 jtagserver 本身**：正常状态是**始终只有一个
  cdt_js 实例常驻**、所有扫描/烧录命令都通过它执行。此前的两种错误操作正是掉线的两半——
  **强关 UI**（D2XX 句柄不释放）与**多开 UI**（两个进程抢同一个 FT2232H 句柄）。
  现在 `ensure_server()` 先数实例：已有 `cdt_js` 就**只等不新起**（端口没起来等 30 s，
  仍不通就报 PID 并退出），启动路径只在**一个实例都没有**时才允许；运行前后各数一次
  `cdt_js`/`cdt_cfg`，数量增长直接报警。实测连续三次调用 `jtagserver` 全程为 `[9040]`，未新增、未关闭。
- 脚本在运行前后各查一次 `VID_0403` 数量，掉线时直接指出是哪一步导致的。

**实测验证（同日连续三次操作）**：
- `--status-only`：`cdt_cfg exit code: 0`，设备仍在，`done=1 / crc_err=0`；
- 烧 `releases/m2b-20261029/`：`COMMAND[Program] execute successfully, takes 3.6 secs`、
  `The done bit is 1`、状态 `0x081FFCA0`，**FTDI 全程在线**；
- 再次烧录抓 hex：`cdt_cfg rc 0`、18 字节，设备仍在线。
→ **掉线问题已闭合**，可用 `python scripts/board_check.py --sbit <x> --seconds 15` 反复上板。

**新暴露的板级 bug（UART 字符被丢）**：串口收到 18 字节
`49 54 43 4f 0a | 44 33 45 54 54 2e 44 33 52 40 46 46 0a`，即 `ITCO` / `D3ETT.D3R@FF`。
对照 ROM 表（`INSTREC BOOT\n` 的 idx 0=I,3=T,6=C,9=O）可确认发射的是
**idx 0,3,6,9…（步长 3）**：`uart_debug` 的 `tx_byte_valid` 是单拍 strobe、比
`uart_tx` 的 `byte_wready` 晚一拍，于是每帧推进 2~3 次索引却只送出 1 个字节。
- 修复：把 `tx_byte_valid` 改成**电平握手**（装载后保持，直到 `byte_ready` 才清零并推进索引），
  `ST_RAM/ST_ROM/ST_HEX/ST_EOL` 四个分支同步改造。
- 判据：`tests/test_uart_debug_handshake.py` 的周期模型同时跑新旧两版 —— 新版逐字符全对，
  旧版必丢字符且索引步长 > 1（复现板上现象）。全量 `pytest` 239 passed / 4 skipped。
- 修复版构建 `20261029-191053` 已启动（19:10）。

**时序现状（本轮不再作为阻塞项）**：`releases/m2c` 的 `ddrphy_sysclk` 为 -2.144 ns，
但最差路径已是 `u_npu/u_wdma/c_cnt → m_s32`：**逻辑仅 2 级 0.798 ns、走线 8.818 ns（91.7%）**，
即 FF→FF 被布局拉远，属拥塞散布而非组合深度，插流水无效。三版位流的最差路径
在 `conv MAC(-3.593)` → `requant 乘法(-1.106)` → `wdma 远距离 FF(-2.144)` 之间随布局漂移，
WNS 稳定落在 -1~-3 ns 区间；按「能跑就行」口径不再逐轮追。

### 2026-10-29 上午：全 NPU 系统首次布线收敛

- run `20261029-110719-01d91e40`：compile→gen_bit_stream 六阶段 OK，48m22s，
  位流 sha256 `E793A792B72437BEADC77B15CADF7EC5253CFEE63BE2FC72A051486C0B8C23F2`，
  已归档 `releases/m2-20261029/`（sbit + timing.rtr + manifest + SHA256SUMS + README）。
- **`Unrouted nets 0` at iteration 278** —— 这是全 NPU 系统第一次布线完全收敛。
  此前：conv 四核版本 Place-0114 布局失败；conv 双核版本 iteration 59 仍残留 11368 条未布网络。
- 资源：LUT 35045/66600 (53%)、FF 49478/133200 (37%)、APM 90/240 (38%)、
  DRM 79.5/155 (51%)、DRAM 1501 (8%)、BKCL 6/6、GPLL 4/6。
- 时序（`report_timing/instrec_top.rtr`）：**Some Constraints Violated**
  - `ddrphy_sysclk` WNS **-3.593 ns**，6265 failing endpoints，TNS -5251.8，估计 86.26 MHz（需 125）
  - `pix_clk` +0.260（转正）、`clk_nco` +1.474、`cfg_clk` +92.288、`rst_clk` +4.509；hold 全部满足
- 最差路径定位：`u_npu/u_conv/g0_bank1`(DRM CLKB→QB) → `ram_dout` mux → `x_eff` → APM 乘法 →
  32-bit 累加树 → `acc_a[1][28]`。13 级逻辑、逻辑 4.874 ns、**走线 6.199 ns（56%）**，
  且 DRM(322,306)/APM(239,522)/加法树(159,414) 三点跨度过大 → 属布局分散，不是逻辑层数问题。
- 相较 softmax 267 级组合链版本（`ddrphy_sysclk` -42.057 ns），流水化把违例缩小了 38.5 ns。
- 本轮为腾出布线空间做的**临时让步**（`instrec_top` 中已注释，必须恢复）：
  `text_disp`、`spectrum_disp`、`feat_copy_engine`、`feat_page_buf`、`ui_coord_delay`。
  实测它们合计只占 ~0.3% LUT，说明拥塞主因在 NPU 本身。
- 构建参数：`build_full.tcl` 的 `pnr -fast_router TRUE`（质量低、速度快）；`conv_engine` 已合并为
  **单共享核**（四组行缓冲/计数器独立，仅 MAC+requant 时分复用）；`softmax_top` 已流水化（约 5 级、340 拍、位级不变）。

### 板级（2026-10-27 深夜，关键突破）

- 用 `cfg_read_device_property -device_index 0 -mode 3` 直接读状态寄存器：早期读数为 `0x00180C80`，
  其中 **`done=0`、`done_i=0`**（`pll_lock=1`、`init_complete=1`）→ 说明此前所有“烧录成功”后
  FPGA 内根本没有有效配置，这解释了 M0/M1/探针全部无输出。
- 重新 `program` 后复读为 `0x081FFCA0`：**`done=1`、`done_i=1`、`crc_err=0`**，配置确实生效。
- 无复位探针（27 MHz 发 `P` + `rst_n` 电平编码）烧录后，COM5 **收到 46 个 `P`** →
  27 MHz 时钟、UART 位层、C18/C24 引脚与 CP2102 链路全部正常。
- 但 M1 位流烧录后 `done=1` 而串口仍 0 字节 → 问题已收窄到 **core_clk（DDR3 IP 125 MHz）或 sys_ctrl**。
- 随后 FTDI 下载器再次从系统掉线（CP2102 仍在线），板级工作暂停；恢复后直接做 `core_clk` 探针。

### M1 构建

- 最新构建 `20261027-121101-5c24a968` 已归档 `releases/m1-20261027/`，All Constraints Met，
  WNS +1.438 / WHS +0.224；复位链已改为 `.resetn(rst_n)` 直连，后续重建 WNS +1.603。
- 构建脚本：`Get-FileHash` 在本机 PS 5.1 缺失，已改用 .NET SHA-256；PDS 对该器件不支持多线程
  （`-max_parallel_jobs`/`-number_of_router_thread` 均报 Flow-0182），单线程约 11~13 分钟。

### M2

- `conv_engine.v`：修正两处“先使用后声明”，PDS 单独编译通过；组契约注释明确为
  “每拍一个 valid、16 bias → 16 M → 16 shift”。
- `weight_loader.v`：UART 帧解析 + CRC16 + 按帧写 m1 + ACK/NAK 重传 + 全镜像读回摘要比对（WOK/WERR），编译通过。
- `pool_engine.v`：2×2 floor、奇偶列分 bank、同步读两拍流水，编译通过。
- `scripts/weight_upload.py` + 测试：2701 帧，CRC-16/CCITT-FALSE，8 项测试通过。
- `tests/test_pool_gap_model.py`：形状链 / floor / channel-local / GAP 语义，6 项通过。
- `gap_unit.v`：256 通道 × 64 值累加 + round-half-even >>6，编译通过。
- `uart_frames.py` + `uart_capture.py --frames`：design 9.2 帧解析/重组/对拍，6 项测试通过。
- `core_probe.v`（诊断）：core_clk 域复位后发 16 个 `C`，已集成顶层并构建 run `20261028-002353-43f24360`，
  **尚未烧录**（FTDI 仍掉线）。这是诊断版，验证后决定保留或移除。
- `fc_engine.v`：16 并行输出、组数为上取整（fc2 8 通道 pad 到 1 组）、复用 requant_unit，编译通过。
- `tests/test_conv_model.py`（流式扫描顺序 vs 向量化，2 项）与 `tests/test_fc_model.py`（3 项）通过。
- `npu_top.v`：层序控制壳（conv1→…→fc2）、busy/done、npu_cycles、timeout_flag 已编译通过；
  数据通路与 wdma 尚未接入（`layer_start/layer_done` 为接入点）。
- `scripts/board_check.py`：一键设备检查→烧录→读 done→抓串口。
- `softmax_top.v`：8 路定点 softmax（Q16.15 预缩放、Q6.9 饱和、512 项 exp LUT、
  组合 round-half-up 除法、top1/percent），单编译通过；`tests/test_softmax_model.py` 5 项通过。
- `wdma.v` 初版落盘：整层权重按 32B beat 连续读（AXI burst ≤16）、16 深 FIFO 吸收
  2:1 速率差、16B/8B tap 切分、`w_ready` 反压握手、组边界脉冲；PDS 单编译通过。
  **尚未仿真/板级验证**。
- `npu_top.v` 整合骨架：conv1→pool1→conv2→pool2→conv3→pool3→conv4→pool4→gap→fc1→fc2→softmax
  全链例化，层序列、GAP 结果缓存与 fc1 回放、fc2→logits 总线已接；PDS 编译通过。
- `tests/test_contract_stream.py`（4 项）固定了契约地址与内容：conv 层每组 48 拍
  （16 bias + 16 M + 16 shift），fc 层为 3×COUT 拍；与 layer_contract.json 逐值一致。
- `fc_engine` 接口已补齐：bias/M/shift 拆成 b_valid/m_valid/s_valid 三条独立流，bias RAM
  在每组首拍初始化累加器；`npu_top` 随之重新编译通过。契约流的生产者（wdma）仍是唯一缺口。
- `sys_ctrl` 增加 `ST_WEIGHT` 自检环（REQ-REL-001 第 4 环）：`weight_ok` 放行 RUN，
  `weight_err` 进 SAFE_ERR；参数 `REQUIRE_WEIGHT` 默认 0，接入 weight_loader 后置 1。
- `docs/m2_top_integration.md`：m1 仲裁、自检链、接线与验证顺序。
- `tests/test_requant_model.py`（5 项）：round-half-even 正/负半值、截断反例、u8 饱和、随机向量逐值对拍。
- `bars_disp.v`（M3）：8 条概率条，pct×4 定长、按槽位取色，单编译通过；尚未接入 `ui_renderer`。
- `tests/test_wdma_group_model.py`（3 项）：固定每组「48 拍契约 + 组内 tap」顺序与内容，
  fc2 的 8 通道 pad 到 16 lane。
- `wdma` 契约流已实现：层启动读 bias/M/shift 到片上 RAM，每组先发 48 拍再发 tap。
- `npu_top` 已按层门控把契约送给对应 conv（cb1/cm1/cs1 … cb4/cm4/cs4），四个 conv 共享数据总线。
- `wdma` 增加 fc 模式（3×COUT 拍）；fc1/fc2 的 b/m/s 已按层门控接入，`npu_top` 编译通过。
- **M2 编译闭环**：权重/契约流、conv/pool/gap/fc/softmax 全链、weight_loader、sys_ctrl 自检环均已落地并编译。
- **NPU 资源实测（wrapper 综合，2026-10-28）**：LUT **19522/66600 (29.3%)**、
  DRM **34.5/155 (22.3%)**、APM **35/240 (14.6%)** → 4 个 conv 实例方案资源可控。
  叠加 M0/M1 现有约 16K LUT，整机预计 ≈55% LUT、≈50% DRM。
- `instrec_top` 已例化 `npu_top`（`start/feat` 暂置 0，不改变 M1 行为），全量构建
  **All Constraints Met，WNS +1.059 / WHS +0.248**，sha256 `07062C4E…`。
- mel feat 读口已接：`npu_top` 输出 `feat_rd_addr`、消费 `feat_rd_data`（1 拍同步读），
  顶层删除原 tie-off；全量构建 **WNS +1.361 / WHS +0.157**，sha256 `895E4F43…`。
- m1 仲裁已接：`weight_loader` 忙时独占 m1，空闲时交给 NPU 的 wdma；读数据按 `wl_busy` 门控。
  全量构建 **WNS +1.406 / WHS +0.270**，sha256 `90F531C0…`。
- `npu.start` 已接 mel 的窗口完成脉冲（`NPU_ENABLE` 参数默认 0，置 1 即启用）；
  全量构建 WNS +1.406 / WHS +0.270。
- **M2 顶层接入完成**：唯一剩余是端到端仿真/板级对拍（USB 恢复后）。
- `conv_engine.grp_advance` 已按层 mux 接入 wdma 端口，但 **wdma 仍按自身节奏推进组**
  （等待该脉冲会在脉冲早于 S_NEXT 时死锁，无仿真无法确认）。全量构建 **WNS +1.730 / WHS +0.225**。
- 待仿真确认：wdma 组契约预取与 conv 组边界的相位关系。
- **并行补齐（2026-10-29 下午）**：
  - `wdma` 组数改为 `H_IN*GRP_NUM`（192/192/192/128/8/1），按 `grp_mod` 循环重读同组权重。
  - 新增 `wbuf.v`（单组权重缓存 1728×16B≈32KB/8 DRM），像素间重放，消除 `W_IN` 倍 DDR3 放大。
  - `npu_top` 修正 wdma layer 编码映射、`wdma_start` 仅六层权重层、fc 的 `w_ready` 单独拆线（多驱动）。
  - `feat_copy` 最后一字节延后翻页（修复 1 字节撕裂）。
  - 新增 `text_disp`/`class_labels.hex`（英文类别名 32 字符/类）与 `compare_layers.py`（逐层对拍）。
  - 全量 **160 passed / 4 skipped**（4 项为 wbuf 之前的旧握手模型，已标注 skip）；构建 **WNS +1.356 / WHS +0.248**。
- conv1 组基址非 32B 对齐已修（基址向下对齐 + `beat_off` 取半 beat）。
- **完整系统位流已产出（2026-10-29 01:44）**：`NPU_ENABLE=1`，含 NPU + M3 UI + weight_loader；
  布局布线成功，sha256 `8BB5F645…`。资源 LUT 38365(57.6%)/DRM 85.5(55.2%)/APM 126(52.5%)。
  为解除拥塞做了两项复用：pool 4→1（DRM 32→8）、conv 4→2 共享核（LUT 11580→6054、APM 80→40）。
- **已知时序违例**：`ddrphy_sysclk` -42.057 ns（`u_npu/u_softmax` 267 级组合链：lq 乘法+max+减法+
  LUT+除法全串联），`pix_clk` -0.838/‑0.825/‑0.804（waveform/bars 组合路径）。按“能跑就行”先出位流，
  softmax 流水化正在重做。
- **weight_loader 已接入 `instrec_top`**：UART 字节共用、TX 仲裁（加载优先）、m1 写/读通道、
  `weight_ok/weight_err` 接 `sys_ctrl`；`REQUIRE_WEIGHT=0` 保持 M1 链路不被阻塞。
  全量构建成功（15 分钟，比 M1 多约 3 分钟，资源增加）。
- 布局事实（`tests/test_wdma_layout.py`、`test_wdma_stream_model.py`，9 项通过）：
  所有层权重区 32B 对齐；conv1 每组 144B（27 tap）尾部仅 1 tap；fc2 tap 为 8B/4 个每 beat。

## 降密度的真正金矿：wdma 的 4 个异步读数组（2026-10-31 02:20 定位）

从 `synthesize/instrec_top.snr` 的 "Device Utilization Summary Of Each Module" 拿到精确分布：

| 模块 | LUT | FF |
|---|---|---|
| `u_npu` | 18005 | 34909 |
| ├ **`u_wdma`** | **8004** | **18608** |
| ├ `u_conv` | 4251 | 4399 |
| ├ `u_fc1` | 3334 | 9309 |
| ├ `u_fc2` | 951 | 1355 |
| ├ `u_softmax` | 675 | 744 |
| `u_mel_engine` | 9380 | 5166 |
| ├ **`u_fft2048_sdf`** | **6194** | 3290 |
| ├ `u_stft_framer` | 1250 | 147 |
| ├ `u_mel_filter` | 1011 | 607 |
| `u_weight_loader` | 1612 | 2533 |
| `u_ui_renderer` | **202** | 107 |

**`u_wdma` 是第三大模块，且 FF 占全设计 37%**。根因是 4 个数组全部**异步读**，
PDS 因此推断成 LUTRAM/FF 而不是 DRAM：

```verilog
reg signed [31:0] bram [0:255];   // 8192 bit
reg signed [31:0] mram [0:255];   // 8192 bit
reg        [7:0]  sram [0:255];   // 2048 bit
reg [255:0]       fifo [0:15];    // 4096 bit
// 读法（异步）：bias_s32 <= bram[c_cnt];  wire [255:0] beat_c = fifo[rd_ptr];
```

**改法（明天做）**：把 `bram/mram/sram` 改成「地址寄存 + 输出寄存」的同步读，
加 `(* syn_ramstyle = "block_ram" *)`。这 3 个数组合计 18432 bit，只需 **1~2 块 DRAM**
（当前 DRM 只用 79.5/155），预计可省 **4000~6000 LUT 与 ~15000 FF**，
LUT 由 53.6% 落到 **46% 左右**，彻底离开布线临界点。

**时序要点**：读地址需比 `c_cnt` 提前一拍给出（流水），`bias_s32/m_s32/shift` 与各自
`*_valid` 仍同拍输出，下游 `fc_engine` 按 valid 接收，**拍数契约不变**。
S_GRP 进入前需预置读地址为 0，并在该状态多一拍装载首数据（`cfg_end` 计数同步 +1）。
**没有仿真，改完必须先跑 `test_wdma_stream_model.py` 等 9 项 wdma 判据再构建。**

## 2026-10-31 01:50 布线临界点结论（最终定性，必须记住）

两天布线问题的**完整答案**：

| RTL 变体 | LUT | 纯 pnr 结果 |
|---|---|---|
| m2c / m2d 基线（无 UART 修复） | **35677**（53.57%） | **布通，iteration 1001** |
| + UART 字符间隔计数器（仅 +11 LUT） | **35688**（53.59%） | **停滞在 3023**（iter 440→549 只降 4 条） |

**只差 11 个 LUT，就从「1001 轮布通」变成「永久停滞」。**

→ 这个设计处在**布线临界点**：纯 `pnr` 的布局是确定性的，任何一点 RTL 改动都会改变布局，
一旦越过临界点就落进拥塞解，且 detail routing 只能 rip-up 不能改布局，永远出不来。
**这不是种子问题、不是 UART 实现问题、不是资源总量问题，是余量为零。**

**当前交付基线**：`releases/m2d-20261030/`（`46EE227F…`，纯 `pnr`，布通，时序
`ddrphy_sysclk` -2.144 / `pix_clk` -0.061）。功能范围：音频→DDR3→Mel→NPU 全链→概率条+波形。
**UART 文本为已知限制**（`INSTREC BOOT` 会丢字符成 idx 0,3,6,9），但
`weight_loader` 的单字符握手不受影响，`WOK` 回执可用 —— 调试可依赖状态寄存器 + WOK。

**要让后续功能加得进去，必须先降密度留出余量**（目标 LUT ≤ 50%，约需 -2400）：
优先级 1：`conv_engine` 16 lane → 8 lane（约 -1400 LUT，吞吐减半，按「能跑就行」可接受）；
优先级 2：`fc_engine` 16 → 8 并行；优先级 3：`mel` 侧定点化。
**降完先单独构建确认布通，再加任何新功能。**

## 2026-10-30 22:10 布通结论（决定性）

**纯 `pnr`（无任何参数）在 iteration 1001 布通**：`Unrouted nets 0`、
`Design 'instrec_top' has been placed and routed successfully`，位流
`46EE227F…`，归档 `releases/m2d-20261030/`。时序与 m2c 逐位相同
（`ddrphy_sysclk` -2.144、`pix_clk` -0.061），再次印证布局确定性。

**这条把两天的布线问题彻底定性**：

| pnr 参数 | 结果 |
|---|---|
| **纯 `pnr`** | **iteration 1001 布通**（m2c 与 m2d 两次都成功） |
| `-parallel 2/4`、`-gplace_seed 7`、`-plc_decongestion`、`-dc_duplication` | 四次全部停在 2400~7200 |

→ **是我后来「优化」的参数把布局拖进了拥塞解，不是 RTL、不是资源、不是 UART**。
`-parallel` 虽然在 global routing 阶段很快归零，但会在 detail routing 从 3 万多条重新爬升后
卡死在 2400 附近。**以后一律用纯 `pnr`，不要再动这些参数。**

## 2026-10-30 20:35 关键排除：UART 修复不是布线停滞的原因

对照实验 `20261030-191554`（`uart_debug`/`uart_tx` 回退到 `b463740^`、波形恢复，
LUT 35677 / DRM 79.5，**与 m2c 完全同源**）在 `-parallel 4` 下：
detail routing 29→19035、69→8023、159→3737、**246→2452**，同样停在 2400~2500。

→ **与 UART 改动无关，与关波形无关**。四次不同 RTL 组合停在同一个 2400~2500 区间，
说明这是**该网表在当前 PDS 版本下的结构上限**，不是种子、不是 UART、不是 LUT 总量。

**剩余唯一未排除的变量是 `pnr` 参数本身**：m2c（`20261029-172919`，iteration 981 布通）
用的是**纯 `pnr`**，而我后来试的全部是 `-parallel` / `-gplace_seed` / `-plc_decongestion`。
已恢复纯 `pnr` 启动 `20261030-203315`（RTL 仍为 m2c 状态）作为决定性对照。
若它布通 → 基线锁定为「m2c RTL + 纯 pnr」，然后**每次只加一个变量**（先 UART gap 方案，再 M3）；
若仍停滞 → 说明 m2c 那次是布局运气，必须走真正的降密度。

## 2026-10-30 19:15 两个新事实

1. **FTDI 又消失了，但这次不是我杀进程**：中止 `pds_shell` 前后未触碰任何 `cdt_*`，
   `jtagserver` 仍为 PID 9040 存活，但 PnP 里 `USB Serial Converter A/B` 全部
   `CM_PROB_PHANTOM`。发生在长时间高负载综合期间，怀疑 USB 供电/枚举被拖垮。
   **无法软恢复（非管理员）**，等待设备自行回来；m2c 位流已在 `releases/` 备好，一恢复即可烧。
2. **关波形只省 0.45% LUT，无助于布线**：`waveform_disp` 关闭后 LUT 35665→35364
   （53.10%）、DRM 79.5→75.5，但 detail routing 起点反而更差（39877、每轮 139 s）。
   已撤销该改动。**说明瓶颈不是总量，而是局部结构**。

**对照实验已启动**（`20261030-191554`）：把 `uart_debug`/`uart_tx` 回退到 `b463740^`
（即 m2c 状态、无 UART 修复），波形恢复，其余不变。目的：确认「UART 握手修复是不是
布线停滞的唯一变量」——m2c 同源 RTL 曾布通（886 轮），而加了两处小改后四次构建全部停滞。

## 布线监控的两条修正（2026-10-30 15:35，避免误判）

1. **`pnr -timeout 45` 实测未生效**：`1231506` 那次 45 分钟到点后进程仍在
   `route iteration 162` 继续跑，日志无 timeout/abort 记录。因此**不能靠 timeout 截断**，
   只能在监控侧按曲线判定并手动中止。
2. **日志里的 `Unrouted nets 0` 多数来自 global routing，不代表布线完成**：
   global routing 阶段会打印若干次 `Unrouted nets 0 at iteration N`，随后 detail routing
   从 3 万条重新开始下降。判断「是否布通」只看两件事：
   - `Unrouted nets 0` 出现在 **detail routing** 的最后（同时有 `placed and routed successfully`）；
   - 目录里出现 `report_timing/` 与 `generate_bitstream/*.sbit`。

**停滞判据（本轮实战）**：detail routing 的未布数**回升或原地振荡**即为停滞，例如
`2353 (it357) → 2606 (it397) → 2574 (it403)`，此时继续等待无意义，必须换配置。
本轮 `1231506` 在 2468~2606 徘徊，与单 seed 7 的 2472 结论一致，已中止。

### 「牺牲面积换布线」实测（2026-10-30 16:30，结论：方向反了）

按「用富余资源换布通」的思路实测了 `-plc_decongestion 2 -dc_duplication TRUE`：

| 配置 | detail routing 起点 | 每轮耗时 |
|---|---|---|
| 纯布局（`-parallel 2 -gplace_seed 7`） | **33302** | 19 s |
| 解拥塞 + 单元复制 | **47559** | 82 s |

**比不牺牲更差**：`-dc_duplication` 把高扇出单元复制到接收端附近，虽然缩短了个别长线，
却把逻辑撒得更散、总网表更大，布线起点和单轮耗时都劣化 40%+。已放弃该方向。
当前回到纯布局 + 提高候选数：`pnr -parallel 4 -gplace_seed 7 -seed_step 3 -generate_bitstream TRUE`
（构建 `20261030-162731`）。

## 2026-10-31 11:00 板级首上全功能位流（m3d）——UART 完全恢复，DDR3 自检超时

用户重插 USB 后 FTDI 恢复（`jtagserver` PID 9040 复用成功、单实例稳定），
烧 `releases/m3d-20261031/instrec_top.sbit`：

```
program: True   status: 0x081ffca0 done=1 crc_err=0
uart: 49 bytes
  INSTREC BOOT
  DDR3 SELFTEST...
  DDR3 ERR @FFFFFFFF
```

**判读**：
- **UART 握手修复彻底成功**：三行完整、逐字符正确（字符间隔计数器方案生效），
  这是项目第一次读到可读的启动日志，此前所有「串口乱码」问题闭环。
- **`done=1 / crc_err=0`**：位流配置成功，设计在跑。
- **`DDR3 ERR @FFFFFFFF` 是超时不是地址错**（`sys_ctrl` 的 `timeout_cnt >= DDR_TIMEOUT_CYCLES`
  分支，100 ms @125 MHz，arg 固定填 `0xFFFF_FFFF`）：`self_test` 在 100 ms 内
  既没拉 `st_done` 也没拉 `st_fail` → 卡在自检流程内部或 AXI 握手没回来。

**这条此前被串口乱码掩盖了整整两天**，属新暴露的真问题，按「慢调试」节奏处理：
先用 UART 已修好的 m3b（无 M3 层）做同判据对照，确认是否与 M3 链路相关；
再沿 `self_test → ddr3_ctrl_axi(m3) → DDR3 IP` 逐级查初始化与握手。

## 布线不收敛的定性结论（2026-10-30，必须记住）

**不是资源不够。** 同一份 RTL 实测 LUT 35665（53.55%）、FF 49690（37.30%）、DRM 79.5（51.29%）、
APM 90（37.50%），离器件上限很远；而且同一资源量的 `m2c`（35677）曾经布通（886 轮）。

**是布局解落在拥塞陷阱里。** 实测三组对照：

| 配置 | 结果 |
|---|---|
| 默认 `-gplace_seed`（单解） | iteration 300+ 仍剩 5000~7200 未布，速率衰减为零 |
| `-gplace_seed 7`（单解） | iteration 561 剩 2472，停滞 |
| `-parallel 4`（4 个独立布局候选） | **iteration 15 即 `Unrouted nets 0`** |

单 seed 的 placer 从**固定初始解**出发做局部优化；一旦初始解把逻辑压在同一区域，
布线器（只做 rip-up & reroute，**不改布局**）只能绕远，绕不开就永久留下未布网络。
`-parallel` 同时准备多个独立初始解，其中至少一个不落在陷阱里 —— 这就是唯一有效的解法。
因此「迭代次数多但网络数不降」= 布局问题，**继续等没有意义**，必须换布局候选。

**代价与时序**：`-parallel` 是唯一可用并行（`-number_of_router_thread` 被器件拒绝），
4 seed 全部跑完需 5 小时以上，故用 `-timeout` 截断取已完成的最好结果。

## M3 分步加回计划（下次带 M3 构建时按此顺序）

一次全加 5 个模块会让 DRM 由 79.5 → 86.0、LUT 53.57% → 53.92%，布局明显变慢（已实测停滞）。
按「资源类型」分批加回，每批单独构建并记录布通轮次：

1. **纯 LUT 层**：`ui_coord_delay` + `text_disp` + `font_rom`（不含谱数据，占 DRM 0）。
   目的：把文字层与坐标对齐先验证掉。
2. **谱图显示层（假数据）**：`spectrum_disp` 接一个固定的 258×64 渐变页（常量生成器），
   验证热图与地址映射在位流里工作；此时不引入 `feat_page_buf`。
3. **谱图数据层（DRM 大头）**：`feat_page_buf`（双页 258×64，+6.5 DRM）+ `feat_copy_engine`。
   这是唯一显著增加 DRM 的一步，若此步布线停滞，则考虑单页 + 撕裂可接受，或把页深减半。

每批都要读 `report_timing` 的 `pix_clk` 域（M3 恢复后像素域余量会变），不能沿用上一批的结论。

## 下一步（按序）

1. **T10 全量构建出结果**：读 `build/instrec-latest.json`（`Wns`）与
   `report_timing/*.rtr` 的 `Design Summary`，**逐时钟域**判布通与时序
   （`ddrphy_sysclk` / `pix_clk` / `clk_nco` / `cfg_clk`）；归档 `releases/m4-<date>/`，
   写 `reports/full_build_conclusion.md`。全量位流**尚未产出**，不要预判成功。
2. **T11 板级端到端**：`board_e2e.py --sbit build/instrec-latest.sbit`，判据 token 用
   `"INSTREC BOOT"` / `"DDR3 SELFTEST"` / `"DDROK"`（**不要用 `"RUN"`**：`uart_debug.v` 定义了该行，
   但 `sys_ctrl` 从不置 `dbg_line_id=5`，`--expect "RUN"` 永不命中，会得到 exit 5）
   → `weight_upload.py` 拿到 `WOK`（m1 真实 16-beat 写）→ 有真实 I2S 输入时用
   `compare_layers.py` 逐层对拍，定位第一处不一致的层。
   **注意**：RTL 目前没有逐层 UART 导出（顶层只有 weight/debug 复用 TX），故逐层对拍现阶段
   只能标 `DEFERRED`；注意默认 golden feat 是 int8 全零静音，须显式 `--golden-feat` 指向
   `reports/golden_ref/sine_440_full/feat.npy`。详见 `reports/e2e_runbook.md`。
3. **T9 UI 独立位流上板验证 M3**：`run_pds_full.ps1 -BuildSet ui_demo` →
   `board_check.py --expect "UIDEMO"`，判 `hdmi_init_over`/`de_nonzero_cnt`/各层 `*_on`
   与 `pix_clk` 域 WNS。**必须等 T10 的 `pds_shell` 退出后再启动**（一次只能一个）。
4. **若 T10 布不通**：按「一层一轮」回退（先撤 UI 层，再撤 NPU 层），每次只改一个变量，
   布通并归档后才继续。判死解看 detail routing 未布网络是否回升/振荡，不要等满时间。
5. **core 域时序（可选，低优先）**：`ddrphy_sysclk` 最差路径多在 DDR3 IP 内部
   （`ddrphy_reset_ctrl` / `ddrphy_data_slice_wrlvl`），用户逻辑改不动，只能靠布局；
   按「能跑就行」口径可暂放。

## 验证入口（本轮新增，改动前必跑）

```powershell
python scripts/check_rtl.py     # 49 个 .v，0 violation
python -m pytest -q             # 398 passed / 4 skipped，约 67 s
```

- **跨边界契约护栏** `tests/test_plan_contract_guards.py`（8 条）：防 model / RTL / 脚本三方漂移，
  已做变异敏感性验证（改错一处必红）。
- **周期级模型**：`tests/ddr3_ctrl_model.py`（DDR3 控制器/仲裁，24 项）、
  `tests/test_self_test_model.py`（14 项）、`tests/test_diag_uart_report.py`（26 项）、
  `tests/test_build_tokens.py`（24 项）、`tests/test_board_check_expect.py`（22 项）。
- **板级证据文件**：`board_check.py` 新增 `--json <path>`（UTF-8 无 BOM 证据记录）与
  **退出码 5**（`--expect` 未全部命中）；`--json` 在早期硬件检查失败时也会落盘。

## 验证基线

- `python -m pytest -q` → **398 passed / 4 skipped**（约 67 s，实测 66.91 s）。
- `python scripts/check_rtl.py` → **49 个 .v，0 violation**（hdmi demo 默认排除）。
- 构建集成本实测：`ddr3_diag` 单轮 **4 m 37 s ~ 5 m 13 s**；全量 `full` **约 1.5 h**
  （compile→gen_bit_stream，纯 `pnr`，单线程）。
- 烧录安全：`tests/test_board_flash_safety.py`（14 项）锁死「TCL 必须以 exit 收尾、
  禁止 terminate/kill cdt_*、必须复用已运行 jtagserver」；
  `tests/test_uart_debug_handshake.py`（3 项）用周期模型锁死 uart_debug↔uart_tx 握手。
- 数值对拍只认 `scripts/golden_pipeline.py`；torch 2.14.1 的 oneDNN 有 21~67 LSB tile 噪声。
- 本机无 WSL 仿真（Ubuntu 发行版 vhdx 缺失），RTL 行为只能靠 Python 周期模型 + 板级实测。
- 全 NPU 构建耗时：compile→gen_bit_stream 约 48 分钟（单线程，`-fast_router`；历史数据）。

## 资产位置

| 类别 | 路径 |
|---|---|
| RTL | `src/{audio,ddr3,mel,npu,ui,ctrl,ip,hdmi}/*.v`、`src/diag/*.v`（诊断/UI 小顶层） |
| 顶层 | `src/ctrl/instrec_top.v`（mel_engine 接 DDR3 m2 口）；`src/diag/top_ddr3_diag.v`、`src/diag/top_ui_demo.v`（诊断专用） |
| 约束 | `constraints/instrec_top.fdc`、`ddr3_100h.fdc`、`clock_groups_async.fdc`（顺序敏感）；`constraints/top_ddr3_diag.fdc`、`constraints/top_ui_demo.fdc` |
| 构建集 | `scripts/build_sets.json`（full / ddr3_diag / ui_demo）+ `scripts/build_full.tcl`（8 token）+ `run_pds_full.ps1 -BuildSet/-DryRun` |
| IP | `ipcore/{ddr3_test,pll,pll_audio}/`（重建必需，已入库） |
| 数值真源 | `scripts/outputs/layer_contract.json`、`weights_image.bin`、`mel_tables.*` |
| 金标准 | `scripts/golden_pipeline.py` + `scripts/outputs/golden/*.npy` |
| SDD | `docs/sdd/{spec,design,tasks}.md`（从 `.codeartsdoer` 复制的可交接副本） |
| 证据 | `reports/m0-manifest-20261027.json`、`reports/m1-timing-20261027-104218.txt`（修复前时序） |
| DDR3 诊断证据 | `reports/ddr3_diag_conclusion.md`（两轮全文）、`reports/board_ddr3diag_20261031T053011Z.json`（首轮）、`reports/board_ddr3diag2_20261031T054946Z.json`（修复后） |
| 位流归档 | `releases/m{0,1}-2026102{7}/`、`releases/m2{,b,c}-20261029/`、`releases/m2d-20261030/`、`releases/m3{a,b,c,d}-20261031/`（sbit + manifest + SHA256SUMS + 时序报告） |
| 交接 | **`docs/HANDOFF_SNAPSHOT_20261031.md`（最新，换人第一入口）** + `docs/HANDOFF_SNAPSHOT_20261027.md`（背景）+ 本文件 |
| Agent 规则 | 仓库根 `AGENTS.md` |

## 未纳管 / 已搁置资产（勿误删，也不必入库）

- `ai_pcb/`（67 MB，PCB 缺陷识别视觉，含 ONNX）、`pcb-aoi/`（202 MB）—— 2026-10-26 已停止移植。
- `cpu/rtl/rv32_ai_{accel,conv,dma,silu}.sv`、`cpu/rtl/rv32_axi_arbiter.sv`、`cpu/docs/AI_ACCEL_PCB_100H_PLAN.md` ——
  搁置路线的 WIP，未验证。
- 根目录 `1571364599 paper.pdf`、`account.txt`（凭据，禁止入库）。

## 环境

- PDS 2022.2-SP6.4：`PDS_ROOT=H:\GG\pango\PDS_2022.2-SP6.4`
- License：`PANGO_LICENSE_FILE=E:\License\pango\new_pds_F4A80DA47D72.lic`
- 构建脚本必须 PS 5.1 兼容；一次只能跑一个 `pds_shell.exe`（脚本不查并发）。
- 构建成功 ≠ 时序收敛：脚本只校验位流存在与新鲜度，**不校验 WNS**，必须看 `manifest.json` / `.rtr`。

## 版本基线（git，分支 XSY，未 push）

- `1298395` feat(instrec): 首次纳管 InstRec-FPGA 工程并建立可交接文档（182 文件，含 IP 源文件与 SDD）
- `2abf5ed` wip(cpu): 存档已搁置的 PCB 视觉 AI 加速 RTL（未验证）
- 工作区有意保留未纳管：`ai_pcb/`、`pcb-aoi/`（含大 ONNX，已搁置）、`1571364599 paper.pdf`。
- 位流本体不入库（`*.sbit` 全局忽略）；**例外**：`instrec_fpga/releases/**` 与 `pds_cpu_100h/releases/**`
  的里程碑位流已入库并附 `SHA256SUMS`，`.gitattributes` 设 `-text` 防止二进制被换行改写。
- 里程碑位流：`instrec_fpga/releases/m0-20261027/`（M0）、`instrec_fpga/releases/m1-20261027/`（M1，时序收敛）、
  `instrec_fpga/releases/m2-20261029/`（全 NPU，布线收敛但 core 域 -3.593 ns）、
  `pds_cpu_100h/releases/120mhz-20261025/`（100H 120 MHz 交付）。
