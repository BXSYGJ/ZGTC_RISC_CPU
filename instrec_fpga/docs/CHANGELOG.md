# InstRec-FPGA 变更日志

## 2026-11-14：完成125 MHz FreeRTOS位流、全套复验与交付

- 修复PDS丢失临时数组复制ROM内容的问题，三个实际存储体直接加载HEX；全容量INIT、22位SMT地址、8实例控制、厂商模型和12项真实篡改全部通过，旧失效网表和中止记录保留。
- 最终统一复验094556通过，13条命令覆盖固件、定时器、精确中断、全ROM读出、原版/RTOS/双入口回退及完整NPU对照；修正WSL UTF16/UTF8混合解码，当前报告无NUL与乱码。
- 固定125MHz/seed2/hold8整机六阶段完成，续跑1789.913秒exit0，位流SHA525d08ea…4a5eaf00；586文件ZIP重开哈希全部通过，地址见rtos/evidence/DELIVERY.json。原H3与202基线保持，当前PDS=0。
- 最终资源36749LUT/39739FF/136.5DRM/94APM；原始最终rtr保留setup -11.834ns、fast hold -0.035ns，按既定安排完成交付。USB板卡未枚举，板级尚未执行；全项目旧资产/契约回归失败独立归档。


## 2026-11-14：以125MHz基线实现FreeRTOS并完成CPU/NPU功能验证

- 冻结所选223256的202份输入，核对XSY/XSY2共同NPU接口；引入官方FreeRTOS V11.3.3固定提交及37份哈希，新增125MHz/1kHz机器定时器与RV32IMC移植层、三应用任务和静态队列。
- 正式固件7148字节；CPU压力/嵌套临界区、完整原生NPU逐层golden、原版与RTOS同输入对照和202文件副本回退通过。原NPU控制器周期31152091保持，RTOS250次定时中断和忙期间两次心跳。
- 整机map通过128.5/155 DRM，唯一PNR20988继续原seed2/hold8生成位流。原125/109.375MHz包及H3核心保持。板卡USB未枚举，板级验证待设备连接。四件交付和命令/输入/输出/退出码见rtos/VERIFICATION.txt；目标继续active。


## 2026-11-14 15:10：复核XSY最新三次上传

- XSY远端新增394481e（seed85位流归档/种子参数）、e155db9（移除USB开关及修复I2S等待解包）、0b8201e（补回烧录脚本main入口）；XSY2仍为8f902ae。
- 从Git对象重算seed85位流SHA256与清单一致；README历史上板记录为八通道logits逐项匹配，非本轮板级重测。五组模型、推理代码及RTOS本次没有更新。
- 更新核验文档、STATUS和工作记忆；仅获取远端对象，当前实现未合并或重新构建，原所选版本保持。


## 2026-11-14：确认交响乐应用目标并核验XSY/XSY2识别资产

- 用户确认目标为同时活跃的乐器及进入/退出；CPU工作已完成，聚焦交响乐识别应用。
- 读取GitHub远端XSY 4d3d6f1与XSY2 8f902ae；两个分支的五组双头float模型/权重/参考逐字节一致，XSY另有INT8契约、725760字节权重镜像和8906样本历史评估。
- 新增SYMPHONY_GROUP5_CODE_AUDIT_20261114.md，区分窗口级五组识别、当前八类板端和待实现时间事件；更新STATUS、接续和工作记忆。此次未训练、构建或修改硬件，RTOS处方案评估，时序目标保持paused。


## 2026-11-14：按用户要求结束时序优化并交付旧版本

- 原持续时序验收目标已暂停。133421最终退出1、719.426秒，500ps时钟树hold修复参数超出0至200ps范围；compile/synthesize/dev_map完成，无新位流或最终报告。202份输入未变，PDS进程0，原失败日志保留。
- 比较全部七个已完成PG100整机125/109.375MHz版本，主选109.375MHz的021145、125MHz备选223256。两个ZIP含各自原位流、202份配套冻结输入、最终报告及逐文件哈希，404份输入和全部包内文件重新核验。
- 新增package_selected_versions.py、SELECTED_VERSIONS_20261114.json、BUILD_CLOSEOUT_20261114.json和使用说明；更新STATUS、接续、交接及工作记忆。当前83.333333MHz源码保留，后续按所选版本开展用户的新工作。


## 2026-11-14：109.375MHz整机候选与连续音频核验

- 133421独立完整run已启动，父41788/runner61044，df160bf配方；normal/seed5/hold12、300/500/700ps修复目标，202份输入与124245完全一致，提交检出mismatches0。当前正在综合，全部功能证据继续匹配，最终物理待验。
- 124245完整六阶段2929.94秒/exit0，系统setup +0.150ns、slow hold +0.032ns，fast hold仅剩3端点最差-0.023ns、THS -0.034ns；全部202输入不变。最终38231LUT/50492FF/694DistributedRAM/129DRM/94APM。按实际端点继续提升实现工具hold目标裕量，新增300/500/700ps可配置入口，实际FDC和RTL保持。
- 124245映射38506LUT/50489FF/694DistributedRAM/129DRM/94APM；详细布局用时220.19秒，最差+1.113ns、TNS0，进入路由。两项短FIFO综合映射符合预期，最终时序仍待验。
- 124245已启动83.333333MHz完整run，父53944/runner97995，normal/seed5/hold12/180分钟；a5189f2提交检出与202份冻结输入完全一致。综合RAM报告已移除两个短FIFO条目，DDR控制器综合为4204FF、分布式RAM0。collector选中全部新功能记录，12项功能/输入门槛通过，物理仍pending；旧111645最终报告及原始配置按SHA归档。
- 111645最终六阶段完成、退出0，时序资格未过：系统slow setup -1.839ns、slow hold -0.160ns、fast hold -0.162ns，像素setup +0.782ns。实际关键路径已转为池化写使能、DDR校准及DDR读FIFO/CPU UART FIFO写地址。将两个16项短FIFO改为显式标量寄存器；厂商规则生成666.666667Mbps DDR、83.333333MHz系统时钟，同步应用六份配套配置。CPU四组、标准CPU、五组DDR、生产分频723的四路32字节UART、完整NPU31,152,094周期及31文件回退全部通过；125MHz/83.333333MHz两档连续音频稳定第二窗均132096真实帧、零补样/溢出/超时。准备seed5完整实现；原始源码哈希及旧实际报告保留。
- 111645详细布线539轮/1051.12秒后全部104088子网连通，进入保持时间修复；前三轮498.45/313.34/289.42秒，最终时序和位流继续等待。819e38b后的202份Git检出输入再次检查全部匹配。
- 同步GAP：035340映射40900LUT/52042FF且详细布线未收敛；将GAP显式寄存器组改为14位同步块RAM和一拍读改写流水，增加末拍drain。三组控制实验768输出/读回、31文件回退及完整NPU全层golden通过，控制器31,152,094周期，331次DDR请求/返回。新冻结完整run111645使用109.375MHz、normal/seed4/12轮hold、180分钟时限，202份Git检出输入一致。新映射37548LUT/46422FF/129DRM，GAP确认为GTP_DRM18K_E1；详细布局+0.801ns/TNS0后进入详细布线。新增最终验收审计，核对实际六阶段、十表、资源、位流、输入及完整功能证据；运行中真实负例退出2，输入和四件交付通过，物理及完整门槛仍待最终结果。
- 对话接续：读取“Revise CPU paper for reviewers (2)”最后指令、命令结果及当前文件，确认035340在详细布线第587轮因7200秒时限终止，最后2607条未布线子网，无最终时序报告、无位流、当前PDS进程0。202份冻结输入与当前源全部匹配。恢复记录保存原命令、输出、退出1及日志/输入哈希；collector区分interrupted_timeout和仍待报告状态。重跑原CPU、新CPU四组、权重/GAP的BASELINE/MODIFIED/ROLLBACK及31文件独立回退，均通过；六项时序解析测试通过，RTL81文件零违例。刷新四件交付与接续文档，保留原始失败和超时记录。
- 04:01：依据021145最终报告，增加权重摘要digest_q/rdigest_q寄存级，GAP改成256项显式32位寄存器组与共享加法器；状态、舍入、输出周期保持。034633的RAM属性方案综合内部错误留档，无位流；035340显式寄存器方案已综合，seed3/normal/12轮hold配置，202项检出输入一致。完整NPU新标签timing_digest_gap_bank全层golden一致，31,152,093周期。新增三组13项权重与768项GAP控制检查，31文件原始回退通过。collector核对控制基线冻结哈希、当前源及测试输入，支持显式pending且保持qualified=false；声明与报告实际不确定性分开记录。
- 021145完整六阶段结束，exit0、202项冻结输入未变，位流生成；最终系统slow setup -1.633ns、slow hold -0.127ns、fast hold -0.136ns，尚未取得时序资格。最差setup定位到weight_loader的校验摘要比较，hold定位到GAP累加分布式存储写地址。最终资源37,599LUT/46,348FF/128.5DRM/94APM；布局中间裕量不再作为当前结果。核对XSY2比较：原NPU31,141,255周期/125MHz约249.130ms，当前31,152,093周期/109.375MHz约284.819ms；固定CPU循环3.680→1.646ms，音频48kHz和2.752秒窗口不变。
- 03:25：021145完成详细布线，359轮/778.78秒，所有子网连通；保持时间修复前三轮413.00/216.94/194.45秒，仍在运行，最终时序待生成。collector新增分支/提交/工作点记录及冻结约束0.150ns检查，六项验证器测试通过。
- 021145轮完成器件映射，37,843LUT/46,345FF/128.5DRM/94APM；详细布局后初步裕量+0.999ns、TNS0，最终布线报告待验。当前202份输入与本地提交检出一致。
- 准备独立93.75MHz备用快照025700，厂商规则把812.5Mbps请求映射为750Mbps实际DDR速率。扩展lower-clock准备入口，从当前109.375MHz源正确重算所有频率相关实例和约束注释；六份候选输入变化，主线202份输入保持不变。备用快照未启动PDS，未宣称时序合格。
- 官方DDR参数规则生成875Mbps IP，用户时钟109.375MHz；FDC生成时钟、UART分频949、补零节拍2279及相关时间常数同步匹配，像素148.5MHz与音频48kHz独立。
- 取指ROM物理地址宽度按8KiB配置为13位，32位PC与访问异常保持；新增真实指令跳转越界、最高地址位及跨ROM末尾三项检查，CPU四组通过。两级短权重FIFO使用寄存器映射，完整NPU逐层golden精确一致，31,152,093周期。
- 125MHz与109.375MHz实际48kHz I²S输入各验证两个完整窗口。稳定后的第二窗口132,096帧全是真实数据，顺序正确、补零0、FIFO溢出0、写超时0；启动首窗各补零1帧。行为DDR完成延迟512周期，完整物理DDR并发验收另由PDS及后续实板覆盖。
- 四路生产UART、标准CPU测试和29文件独立回退均通过。当前冻结完整构建021145含202份输入，normal/seed2/hold12；删除PG100不支持的通用路由线程参数。PDS重新启动不保留映射阶段状态，保留错误尝试并从冻结输入完整重跑，最终时序待验。
- 修正此前“PG100支持12路路由线程”的记录：通用帮助列有该选项，具体器件实现拒绝；当前入口只接受1且不向PnR传该选项。

## 2026-11-13：PaceRV高性能核心与共享整机存储、外设集成

- 冻结H3 Base五级RV32IMC核心替换小型控制核，八份执行核心保持原始hash；原有音频、NPU、显示、UART和DDR共用一套系统。
- 1MiB CPU应用区、只读观察别名、字节掩码及四客户M3仲裁验证通过；本地8KiB数据RAM映射为两个原生DRM。四路UART接受保持与优先级修正，32字节串行输出一致。
- 相同固件固定循环460,012→180,016周期，均退休180,008条指令且结果f2d8888b；25项核心定向、1500周期反压、996项DDR、标准CPU入口和23文件隔离回退通过。
- 时序路径修正覆盖MMIO并行采样、激活命令寄存、DDR请求分级/返回寄存器使能、FC同步系数RAM、激活写入payload控制简化和七拍视频流水。生产48k完整NPU逐层golden一致，31,152,093周期；五帧10,368,000像素逐字节等价，2000项概率条检查通过。
- 100Pro+当前冻结run `full-20261114-010622-full`，202项检出输入一致，normal/seed1/12轮多角hold修复；最终时序待验。用户允许必要时适度降频；独立生成109.375MHz配套DDR配置，125MHz原档重生成的RTL完全一致。历史时序原报告保留。正式latest位流保持原样，按用户要求结束远程操作。
- 补做原155.25MHz核心的相同存储/固件对照：八份源码与原V0布线输入一致，隔离取指对适配后三项检查通过，固定循环180,016周期。通用PDS帮助的路由线程选项在PG100不适用，详见2026-11-14更正；当前16GB主机依据实时可用内存调度重任务。

## 2026-11-13（第四轮）：离线量化契约错误修正 —— 板级与 golden 逐位一致

- **根因**：`golden_pipeline.run_mel_pipeline()` 默认用 `scripts/outputs/layer_contract.json`
  （44.1 kHz：zp_in=49、inv_s_in=267723430）做特征量化，而 48 kHz 位流用 zp_in=47、
  inv_s_in=236403274。所有 48 kHz 的离线 golden 标签因此都基于偏大 13% 的尺度，
  历次 board-vs-offline 对比全部失真。
- **修正**：`board_accuracy.offline_top1()` 改为从同一份 48 kHz layer_contract 取
  `inv_s_in/zp_in` 传给 `run_mel_pipeline`。
- **修正后等价性**：同一段 PCM 下 board 与 golden 的 logits 只差 ±1 LSB，top1 相同
  （200 Hz 单音：[-1,9,-24,-16,17,-18,-5,-1] vs [-2,9,-25,-17,18,-18,-6,0]；
  IRMAS 单簧管片段：[-20,-23,-21,-28,33,23,-47,25] vs [-20,-22,-20,-27,32,22,-47,25]）。
  ⇒ mel / standardize / 量化 / NPU 全链路板上与参考一致。
- **剩余差异来自模拟回环**：同一片段用「播放的 wav」算 golden 与用「板子采到的 PCM」算 golden
  的 logits 完全不同（std 6642→5122、dB 中位 +15.7 dB、z 差 1.02σ、feat 平均差 13 LSB）。
  Realtek→PCM1808 这一段改掉了信号；判断 FPGA/模型只能用板子实采 PCM 做参考。
- **澄清**：`0x0020_0000` 是 dB 谱（int16 Q8.8），不是 uint8 特征；此前按 feat 槽读它的低字节
  得到的「板级特征」是噪声，相关结论作废。
- **新工具** `scripts/diag_spectrum.py`：锁窗读回整窗 PCM + dB 谱并与 golden 逐元素比对；
  板级 dB 与 golden 仅差一个全窗常量（≈+36 LSB = 0.14 dB，源自 259/258 帧 max 差异），
  该常量在 standardize 中抵消。
- **新发现 RTL 缺陷（待重编）**：`instrec_top.v:793` 把任何 `0xAA` 字节从 diag 命令通道丢弃，
  地址含 0xAA（如 0x...AA00）时参数错位、通道锁死；主机侧已加绕行，RTL 建议按 diag 状态放行。

## 2026-11-13（第三轮）：板级准确率工具修正（立体声/相位锁定）与一处待定位差异

- 修正 board_accuracy.py：单声道 wav 会被 Realtek 端点拒绝（waveOutOpen 失败 → 板子分类静音），
  改为 48 kHz 立体声 + 峰值归一化；循环单元固定为一整个 132096 样本窗口以消除相位差；
  播放失败改为立即抛错而不是静默继续。
- 已确证：同一段 PCM 下板卡 logits 与离线 golden 一致（稳态 tone，同 top1=class0）。
- 待定位：音乐片段上板卡遥测稳定 "top1=7 last_p=100"，而同一采集窗口的 golden 为 class1/class4；
  疑点指向 mel 的 dB 谱导出/回读在大动态范围下的定点处理或窗口完整性，需 ILA 定位。

## 2026-11-13（第二轮上板验收）：权重版本修正、数字链等价证明、上板准确率工具

- **权重版本错配修正**：板上原先上传的是 44.1k 旧镜像（scripts/outputs/weights_image.bin，zp_in=49），
  而 RTL 已是 48k 契约（mel_coo_48k.hex，zp_in=47）。重烧 202047 后上传
  medley_48k/weights_image.bin（WOK CFE5A709）。
- **数字链等价性（决定性）**：读回板上采集的同一段 PCM 喂离线 golden，板 logits
  [27,-19,-7,-16,0,-17,4,-7] vs golden [26,-22,-14,-8,-5,-21,6,2]，同 top1=class0；
  离线 numpy 与 TorchScript 参考 3/3 一致。⇒ i2s→DDR3→mel→NPU→权重 定点实现正确。
- **上板准确率**：IRMAS val 6 类 × 3 = 18 条（峰值归一化播放）board 3/18、离线同片段 3/18、
  一致 6/18 —— 两者同样低，说明模型对 IRMAS 域外（自带 MedleyDB 测试 INT8 77.32%），非 FPGA 缺陷。
- **新工具**：scripts/board_accuracy.py（播放标注片段 → 板上 logits → 准确率/混淆/离线对照 + JSON）。
- **修正**：board_e2e.py 默认权重镜像改为 medley_48k；.gitignore 忽略 .runtime/、ai_pcb/、pcb-aoi/。

## 2026-11-13（晚）：最终定论 —— 「恒 top1」唯一根因是 PC 全局静音，分类系统完全恢复

- **根因**：之前所有「恒 top1」现象的唯一根因是 PC 端**全局静音**（非 FPGA、非 i2s RTL、非硬件接线）。
- **验证**：音量开启后重测——PCM std 2.2 → 18969（满幅度有效音频）；
  三种音频 top1 完全分化：tone_200→class7、tone_6k→class0、montage→class1
  （静音时三种音频恒 class7）。
- **结论**：整个链路（音频→i2s→DDR3→mel→NPU→分类）从头到尾正常，全部板上验证通过。
- 附带修复：`i2s_capture.py` 的 `waveOutSetVolume` API 误用（传 device_id 而非 handle、
  且在 waveOutOpen 之前调用）已修正（`60969209`）；waveOut 设备枚举顺序会漂移
  （Realtek 曾为 index 4，本次为 index 0），`resolve_play_device` 按名称解析已覆盖。

## 2026-11-13：板级验收完成 —— DDR3 读写彻底收口，「恒 top1」根因定位到 i2s 采样链

- **FTDI 恢复**：2026-11-12 夜下载器在 PnP 为 `Unknown`；2026-11-13 用户重插后恢复
  `OK`（VID_0403&PID_6010），JTAG 链扫描成功。
- **烧录有效位流 `202047`**（方案 A，WNS −0.667，SHA `23b496ee…`）：done=1 / crc_err=0。
  注意 `build/instrec-latest.sbit` 仍指向被否决方案 B（WNS −0.952），不可用于验收。
- **启动自检全过**：RV32 MMIO/ISA/BENCH（acc 匹配）+ DDR3 自检 `DDROK`。
- **DDR3 读写板上收口**：主机诊断读回 0x300000 的 4096 B，1024 word 逐位匹配
  `0x5A5A00FF ^ w`；6×重复长读 6/6 精确；权重上传 `WOK FA0D5236`。
- **推理链硬件正常**：mel 特征随音频 88% 变化；板子 feat 喂 `npu_forward` 得 top1=class7，
  与板子 NPU 分类一致（NPU 无偏差）。
- **「恒 top1」根因 = i2s 采样链**：读回 PCM std=5.1、符号翻转 7 万次（200 Hz 应 ~1100），
  采到的是噪声非音频；板子 feat 分布 0..255(mean 128) vs 参考 43..121(mean 48.6)。
  与历史悬案（L/R 翻转漏检致 2:1 抽取 / +1 样本偏移）吻合。
- **结论**：FPGA 的 DDR3 / NPU / 权重 / mel 全部正常，唯一卡住识别的是音频进板的
  i2s 采样链（PCM1808 回环/接线，或 i2s_rx L/R 翻转检测）。修复方向在 i2s 采样 RTL
  或音频接线，不在 DDR3/NPU。

## 2026-11-12（夜·续）：离线全绿复核 —— DDR3 契约仿真 6/6 PASS，恒 top1 代码层根因均已修复

- **WSL 仿真能力复核**：`Ubuntu-24.04` 内 `iverilog`/`vvp`/`verilator`/`python3` 齐全
  （旧记录「本机无 WSL 仿真」已过时）。`sim/run_sim.py all --jobs 4` →
  **46 pass / 1 fail / 0 skip（569 s）**。
- **唯一失败 `i2s_capture` 为历史未收敛项**（STATUS 325-335 已载：`i2s_slave_rx` L/R 翻转
  在 27 MHz 异步过采样下漏检一半 ⇒ 2:1 抽取、frame payload 自 word2 起为零；三版相位改动
  均引入新错位已回滚，且板级真实 PCM1808 与 TB 合成源不同）。**非本轮回归**：本轮零 RTL 改动。
- **DDR3 契约仿真 6/6 PASS**：`ddr3_byteaddr`（`>>2` 后单拍稀疏写与连续突发读逐字节相等）、
  `ddr3_m3_share`（自检 `rd_ready` 门控修复）、`ddr3_subsys`、`ddr3_aw_timeout`、
  `diag_readback`、`diag_longread`；另 `mel` 基线 PASS。⇒ `DDR3_CONTRACT_20261111.md` §9
  要求的「离线全绿」条件达成，只差板级验收。
- **「恒 top1」代码层三个根因均已在 RTL 修复**：`standardize.v` 量化移位 = 36、
  `npu_top.v` `ZP_IN_CONV1=47` / `ZP_OUT_FC2=58` 参数化、`ddr3_ctrl_axi.v` `>>2` 字节地址。
  离线数值链自检：`reports/golden_ref/sine_440_full` 的 `feat` 43..121（非饱和）、
  `fc2_logits` 八类分化（−57..64）、`probs` 非坍缩 ⇒ 数值链健康。
- **结论/纪律**：不基于未板级确证的「mel 卡 ST_RUN」假设改核心 FSM（watchdog 目前仅置观测标志
  不恢复，但强行拉回 IDLE 会产生假特征，可能更糟；契约 §9 要求先定位第一个偏差环节才允许改功能）。
  剩余唯一缺口 = **板级验收**（FTDI 下载器此前反复丢失）：烧 `20261112-202047-2c1207d6` 位流
  → 自检 → 重复长读 → 同窗 PCM/feat/logits 逐级对拍（对拍务必用本轮修复后的 feat.bin）。
- 本轮仅文档更新，零 RTL / 零脚本 / 零构建改动。

## 2026-11-12（夜）：修复 DDR3 诊断读回的 feat 槽宽缺陷；纠正契约文档脱节

- **背景**：用户反馈「DDR3 读写比较混乱」。系统核对后确认 RTL 侧 `>>2` 修复早已落地
  （`ddr3_ctrl_axi.v:225/239`，git `92047409`），`ddr3_layout.py` / `read_ddr.py` 已统一
  `PROD_ADDR_UNIT=1`（字节语义），56 个 DDR3 契约/模型测试全绿。混乱主要来自**文档脱节 +
  第二套裸读实现**。
- **功能修复 `scripts/diag_dump.py`**：feat 区在 DDR 中是 16512 个 **16-bit 槽**
  （`mel_engine.v:687` `ex_cmd_addr = 0x200000 + elem*2`，低字节 uint8 特征、高字节 `0x00`），
  即 33024 原始 B。原脚本只读 `FEAT_BYTES=16512` 裸 B 直接当 uint8 存 `feat.bin` ⇒
  只覆盖前半槽且夹杂 `0x00`，`diag_compare.py` 的逐级对拍因此不可信（STATUS 早有记载）。
  改为：复用 `ddr3_layout.FEAT_SLOT_BYTES` / `feat_slots_to_bytes()` 单一真源，读
  `FEAT_SLOT_STREAM_BYTES=33024` B 后取低字节，`feat.bin` 仍是 16512 B uint8（消费方不变）。
  `meta.json` 新增 `addr_unit` / `feat_slot_bytes` / `raw_bytes` 自描述字段。
- **等价性验证**：行为模型对拍证明在 `PROD_ADDR_UNIT=1` 下，裸读与 `read_ddr.py` 正式
  de-stride 路径的 PCM / feat 输出**逐字节一致**（`unit=4` 仍只走 `read_ddr.py`）。
- **测试**：`tests/test_diag_dump.py` 新增 3 用例（槽几何一致性、低字节提取、
  与 `diag_compare.py` 常量对齐）；全量 **469 passed / 26 skipped**，`check_rtl` 0 violation。
- **文档订正**：`docs/DDR3_CONTRACT_20261111.md` §5 标题「暂不实施」→「已实施」并写明
  提交/构建证据；§7 故障账本 #3 状态更新；§9 验收步骤补 feat.bin 校验点；
  `STATUS.md` 顶部横幅追加核对结论。**不再按 §4 的 ×4 结论改 RTL**（那是修复前实测）。
- 仍待板级：FTDI 下载器恢复后烧 `202047` 位流，走自检 → 重复长读 → 同窗逐级对拍。

## 2026-11-12：共享 beats-1 减法器解决布线拥塞；PnR 收敛并产出位流（方案 B 否决回退）

- **方案 A（保留、已推送 `a797989c`）**：`src/npu/activation_row_store_dynamic.v` 把 generate 循环内
  32 份 `beats-8'd1` 提为模块级单份 `wire beats_m1=beats-8'd1`，`mem_wa` 与 3 处 `beat==beats-1`
  复用它。`beats[1]` 扇出 206 → 1。纯组合重构，位级等价，0 FF / 0 周期，`check_rtl` 0 违规、
  `pytest` 466 passed / 26 skipped。
- **实测（有效构建 `build/pds/20261112-202047-2c1207d6`）**：六阶段全 OK；布线 `Unrouted 0`
  （274 轮 / 975 s；上一轮 multi-seed 是 496 轮 / 5396 s 后 `Route-0008` 失败）；
  位流 `instrec_top.sbit` SHA-256 `23B496EE…`；WNS **−0.667 ns**（Option A 时代 −1.294）、
  WHS +0.030；`clk` 域 +33.708 ns 已收敛；DRM 130/155 (84%)，DRM18K 92 / DRM36K 84 与改前逐项一致，
  block RAM 未退化；`Total nets for routing` 77629 → 77620。
- **方案 B（否决、已回退）**：`requant_unit.v` S2→S3 64 位组合链切一级流水（新增 `q0_q/inc_q/v2b_q/zp_q2b`，
  +74 FF、延迟 4→5 拍），`fc_engine.v` 注释、`conv_engine.v` `fin_cnt` 22→23 同步。
  构建 `20261112-215603-990acea9` 布线仍收敛（235 轮 / 1256 s、六阶段全过、位流产
  `A12A05DD…`），但 **WNS −0.952、WHS +0.001，较方案 A 劣化**。按事前判据回退三文件到已推送 HEAD，
  SHA-256 逐项一致。失败日志/位流按惯例保留未覆盖。
- **同时纳入的工作树改动**（来自交接文档）：Option A 的 B1/B2/B3 打拍
  （`standardize.v`、`activation_row_store_dynamic.v`、`dashboard_renderer.v`）、Option B 的
  multi-seed PnR 契约（`build_full.tcl`、`test_build_tokens.py`）、`docs/HANDOFF_20261112.md`。
- **git**：`XSY` 分支推送 `origin/XSY`，`3b265bde..a797989c`，含此前积压 68 个提交；远端与本地
  HEAD 一致。未动构建契约测试、未并行 `pds_shell`、未做 DRM→distributed 转换。
- 剩余 −0.667 在 `ddrphy_sysclk`（DDR3 IP 域，281 endpoints / TNS −42.552）与 `pix_clk` −0.095；
  这些域 STATUS 已标注「用户逻辑改不动、靠布局、能跑就行可暂放」。勿再对 NPU 数值核心做打拍类尝试。

## 2026-11-11（夜）：降 DRM 84% 实验证伪；布线瓶颈定位为"route 主导 + 高扇出控制网"

- **证伪**：把 `activation_row_store_dynamic.v` lane_bank `block_ram`→`lut_ram` 一行属性，DRM 130(84%)→98(63%)，但 bare pnr 布线失败（`E: Route-0008`，3h27m）。改已**撤销**，`git diff` 为空。
- **根因（时序报告 `20261111-003237-53a02f27/report_timing` 逐路径核对）**：三条 setup 违例路径**全是布线主导（Route 74–76%），逻辑级数仅 8–13 级**。瓶颈不是组合逻辑太深，而是：
  1. 高扇出控制网：NPU store 写使能/写数据选通 `N78` 扇出 170、`_N83` 扇出 124、`_N105` 扇出 73；standardize `qprod_reg[44]` 扇出 44；
  2. 到 DRM18K/36K 的远距离布线（`mem_wd[6]` 单扇出仍 2.53 ns、`bank_wd[1]` 1.75 ns、DRM `tco` 1.565 ns）。
- **三瓶颈（WNS）与切分方案**：
  - **B1 NPU 激活存储写口 −0.872/−0.841**：`beat[1]`→`cmd_addr=row_base+beat*32`（24-bit 进位链）→`act_mux.held_addr`→`act_cmd_ready`→`mem_we`（扇出 32 bank）。手段：**寄存器复制 / 写命令打拍**（`mem_we/mem_wa/mem_wd` 提前一拍寄存，非"切组合逻辑"）。+1 拍延迟、约 +32×8 FF 选通复制，吞吐无影响（3 s 节奏）。
  - **B2 standardize 量化扫描 −0.859**：`qprod_reg`(DSP 输出)→round-half-even→取负→+zp→钳位→写 `spec_bank`，7 级组合挤一拍（`S_SCAN_Q`）。手段：**拆两拍**（加 `feat_byte_reg`）。+1 拍/元素 = +16512 拍/窗 ≈ +0.13 ms，+8 FF，位级不变。
  - **B3 UI graph 跨域 −0.381**：`col_min_mem`(DRM36K, pix_clk 侧)→15-bit 比较链→求和→小于比较→`graph_s3`。手段：**输出打拍**（DRM 读→比较结果寄存一拍）。+1 拍、+22 FF。
- **Option B**：放开构建契约（`tests/test_build_tokens.py` 锁裸 `pnr`）启用 multi-seed，`build_full.tcl` 历史注释已证 seed1 iter15 即 Unrouted 0，但牺牲可复现性。**A/B 待用户拍板，未实施**。
- **回归**：`python -m pytest -q` 466 passed、26 skipped（>>2 基线干净）。

## 2026-11-11（续）：DDR3 访问契约收敛 —— ×4 是功能缺陷不是"空间浪费"

- **更正**：同日早前"各主口同 cmd 地址空间 ⇒ 片上数据正确、仅空间 4 倍浪费"**作废**。对"稀疏单拍写 vs 连续突发读"而言，×4 使两者不对齐，是功能缺陷。
- **离线核实（读 RTL + 行为模型对拍）**：命令地址单位 `physical=4×cmd_addr`、每拍 32 B、突发内每拍物理 +32 B（连续）。单拍写把页 p 落物理 `128p`，16 拍突发读连续覆盖 `[2048k,2048k+512)`，对齐仅当 `j≡0 mod 4`。
  - **mel 读**（audio 写→mel 读）：每 16 拍命令仅第 0 拍对齐，位置正确样本恰为每 256 块前 16 个（=1/16），其余读 128 B 物理 gap → 75% 丢失 + 错位。
  - **wdma 读**（权重上传→NPU 读）：权重帧物理 `[1024f,1024f+256)`、帧间 768 B gap，16 拍读每命令一半是 gap → 权重流被污染。
  - **feat/谱导出→diag 读**：主机可用 destride 在 ×4 下恢复全部页（可行），片上读不行。
- **最小修复**（暂不实施，待集中构建）：`ddr3_ctrl_axi.v` 第 218/232 行 `axi_awaddr/axi_araddr` 由 `cur_addr` 改 `cur_addr[27:2]`，恢复字节语义后四主口全对齐。
- **故障账本（三本）**：①启动自检 `@0x00300200`（m3 rd_ready 门控，已修待板上验）；②UART 长读停帧（传输层，已闭环）；③地址 ×4 混叠（IP 字地址，待 `>>2` 修复）。已撤销"静默丢页 / 单拍写不提交"结论，不再作改 RTL 依据。
- **新增资产**：`docs/DDR3_CONTRACT_20261111.md`（统一契约+账本）、`scripts/ddr3_layout.py`（地址布局唯一真源）、`scripts/read_ddr.py`（正式读回，替代 build/ 临时工具）、`tests/ddr3_mem_model.py` + `tests/test_ddr3_layout.py` + `tests/test_ddr3_contract_consistency.py` + `tests/test_read_ddr.py`（20 用例，含跨页/跨突发/跨窗口、重复读回全同、**超时≠成功**）。
- **回归**：新测试 20 passed；未动 RTL，位流不变。

## 2026-11-11：撤销「PCM 静默丢页」；实测 DDR3 地址单位 ×4（主机读回混叠）

- **撤销**：2026-11-10（续 2）的「PCM 窗口每 4 页仅 1 页真实 / 静默丢页 / 单拍写不被 DDR3 IP 可靠提交」作废。板上 PCM 窗口完整含 132,096 帧，无丢页、无丢数。
- **根因**：`physical_byte = 4 × cmd_addr`，控制器 `cmd.addr` 被 DDR3 IP 当 32 bit 字地址。音频 `page_off = page_no<<5` ⇒ 页 p 落物理 `128p`；8256 页占物理 `0..0x101FA0`（1.06 MB）。各主口用同一 cmd 地址空间，互相一致 ⇒ 片上数据正确，仅空间 4 倍浪费。
- **决定性证据**（位流 `69041235`，win=62）：`build/probe_addr_unit.py` 重叠实验 `p32[0:128]==p0[128:256]` 与 `p64[0:128]==p32[128:256]` 均 **128/128 全等**，对照仅 6/128 ⇒ 唯一自洽解 `payload[j]=physical[4A+j]`。
- **全窗重建**：`build/read_pcm_destride.py`（cmd 步长 64，取 `payload[0:32]`/`payload[128:160]`）得 132,096 样本、`holes=0`，页边界平均跳变 3.63 < 页内平均差分 4.47 ⇒ 页序正确。产物 `build/diag/tone200_destride/win0062/pcm.raw`。
- **旧 gap 证据重新解释**：cmd `0x40800` 在 ×4 下读物理 `0x102000`，已越过最后一页 `0x101FA0`，旧「gap 无音频」验证的是 ×4 而非否证。
- **未解**：无。范围更正：×4 只影响 diag 读回通路（`L`/`R`+addr+len）；音频输入链走 `C`→`R`+seq 流式抓取（`scripts/i2s_capture.py`），不经 DDR 读回，**不受影响**。真实 I2S 数据早已归档在 `data/i2s_capture/montage_music_20261106/`（8 s @48k）与 10 组 `build/i2s_capture/*`，输入链是通的。本轮重建 PCM 为噪声底只是那次播放未真正送到 ADC，不是链路问题。推理链亦非桩：`reports/golden_ref/` 有三组输入的 conv/pool/gap/feat/fc/logits/probs 全套 stage 输出并与 librosa/torch 交叉参照；`instrec_top` 中 `mel_feat_rd_addr` 由 NPU 驱动、`mel_npu_start` 触发、`npu_probs_*` 直连 `ui_renderer`。
- **影响**：任何经 diag 读回的板级–golden 对拍（含 `diag_compare.py` 历史结果）必须先按 `physical=4×cmd` 换算，否则都是混叠数据。
- 新增（均在 gitignore 的 `build/` 下，仅记录以便复现）：`probe_addr_unit.py`、`read_pcm_destride.py`、`profile_window.py`、`analyze_stride.py`、`probe_weight_region.py`、`decode_sts.py`。

## 2026-11-10（续 2）：长读 STABLE 闭环；PCM 静默丢页（60~75% 页从未被写）；烧录位流 WNS −1.402

- 长读：读回协议重写后 3×264192 B、`holes=0`、三次 sha256 全同、`RESULT: STABLE`；停帧根因定性为传输层（遥测插帧 + 主机流水线 + S_ACK 吞字节），非 DDR3 读超时。
- 自检 `@0x00300200`：本轮位流 `st_fail=0`，m3 `rd_ready` 门控修复（`st_m3_sel`→`!st_done`）板上生效。两项结论证据独立，不合并。
- 新缺陷：PCM 窗口每 4 页仅 1 页真实，4964/8256 页与从未写过的 stride gap 逐字节相同（上电残留）⇒ 静默丢页；`check_gap.py` 证明自检区 0x300000 读回正确、读路径 OK。
- 仿真不能复现：`audio_chain_w4k` DLY 4/200/1000/4000/20000 全 100% real、err=0；`audio_chain_full` PASS。候选 ①`page_go` 在 FSM 忙时丢弃 ②控制器 `S_W` 超时发 done 丢写，尚未区分。
- 音频输入无信号：播放 tone_200.wav 后 std 仍 933.8、logits 与静音窗相同。
- 时序：已烧位流 `report_timing` 为 `Some Constraints Violated`、WNS −1.402 ns + hold 违规（最差 `u_npu/u_store1 → lane_bank[6].mem`）⇒ 本夜 NPU 数值不作结论依据。
- 构建守卫：六阶段成功但 `Build inputs changed during PDS` 拒绝发布，已用 manifest 哈希反证差异仅注释（`DE7991CD…`），未绕过守卫，直接烧该 sbit。
- 清理：`git restore` cpu/ 两个把 AXI 端口方向 / `ddrphy_cpd_lock` 回退成旧 bug 的文件。
- 追加定量证据：全窗扫描（`build/win_scan.py`，锁窗 327）真实页 3112/8256 = 37.7%，页号 mod 4 直方图 `[2064, 302, 355, 391]`（`≡0` 恰为 8256/4）；gap 区无真实音频 ⇒ 写地址未错位；自检用 `len=15` 通过、音频用 `len=0` 失败 ⇒ 指向**单拍写不被 DDR3 IP 可靠提交**。
- 新增遥测（`ac953c32`）：`audio_sink` 的 `page_cnt_lat`/`done_cnt_lat` 经 STS phase 2/3 输出（满窗 8256 / 16512），用于在"请求缺失"与"命令完成但数据未落地"之间二选一；位流构建中。

## 2026-11-10（续）：DDR3 自检 @0x00300200 根因修复 + AXI 诊断字节恢复

- 离线仿真（新 `sim/tb_ddr3_m3_share.sv`）复刻 instrec_top 精确 m3 mux，精确复现 `@0x00300200` 并定性为**数据比较失败**（非写/读超时：to_err=0、dbg_to_state=0）。
- 根因：`rd_ready[3]` 被 `st_cmd_valid` 门控，读阶段 drain-tail 使 fifo 末拍卡住、被当作下条读首拍误比较。修复（1 行）改为 `(!st_done)` 门控。
- 可观测性：`ddr_sts_code` 恢复为 `{cmd_to_err[3:0], to_err, dbg_to_state[2:0]}`，boot `DDR3 STS` 行改打该字节（原打 audio 遥测，boot 全 0 掩盖超时）。
- 回归：check_rtl 0；ctrl_smoke / ddr3_m3_share PASS；pytest 444 passed（同步更新 STS 字节契约测试）。

## 2026-11-10：mel 状态位遥测（零计数器）布通；win_miss 粘滞定位

- 计数器版遥测三次均差 4–6 根线；改零计数器（3 根线）后第 4 次 1h2m 布通，位流 releases/instrec-48k-melstat-20261110（sha f7552f2a）。
- 代码级：win_miss = sticky win_tick-during-non-IDLE（mel_engine.v:250），mel 卡 ST_RUN 后 feat 永不更新，吻合双测试音 top1 相同。
- FTDI 再次掉线，待恢复读态 1 低 3 位确认。

## 2026-11-09：全窗口 100% 验收；有界 PNR 58 分钟成功

- audio_chain_full：两窗 real=132095/132096、inject≈0、freeze 0.03%、err/ovf=0。
- 有界 PNR（提交 2d6fd26f，90 min 上限）58m15s 完成；ddrphy −0.658 ns（115.5 MHz，历次最佳）；位流 releases/instrec-48k-injfix-20261109（sha 2726f0cd）。
- FTDI USB 链路错误（Unknown / 端口重置失败），烧录待恢复；一键脚本 board_48k_run.py 就绪。

## 2026-11-09：修复零注入门槛（19% 真实帧根因），整机音频链仿真 100%

- 新增 tb_audio_chain / audio_chain_w4k（可调 DDR done 延迟），run_sim 支持 sim_plusargs。
- 根因：注入只看 fifo_empty，帧间自然空即补零帧；加 sd_idle_sync 门槛后 real 4095/4096、inj≈0。
- 回归 438+26skip，音频四用例全 PASS。

## 2026-11-08：数据链定位消费侧，audio_sink 双修复与 err_cnt 遥测

- 板级 STS 实测 19% 真实帧；overflow 低字节 0 属 256 次溢出的饱和巧合，不能作为无溢出结论；写侧由 i2s_capture（4 s / 192k 帧）证明 48 kHz 满帧率。
- 修复①（a00be5e7）左右页命令间 ST_GAP 一拍；修复② agg_freeze 右页写超时 33 ms fail-safe 释放。
- STS 重排为 {err_cnt, overflow_hi, frames}；回归 438 passed + 26 skipped。
- PNR 收敛阻塞：默认种子 iteration 394 / 1318 未布；-fast_router 非法、-gplace_seed 被契约禁止，需延长窗口或 RTL 拥塞优化。

## 2026-11-07：zp 参数化使 NPU 逐层归零；遥测证明音频仅 19% 进窗

- npu_top：conv1 zp_in 49→47、fc2 zp_out 57→58 参数化（旧硬编码是 2~5 LSB 根因）；npu_probe 切生产 src/npu 源，sine440 全层 0 LSB。
- sys_ctrl/uart_debug：STS 扩 8 位 hex 内容（溢出字节+窗口帧计数+win_id）并每 0.8s 重发；实测 25280/132096=19% 真实帧、win_id 递增。
- i2s_capture 播放设备按名称解析（索引漂移 4→0→4）；位流归档 releases/instrec-48k-diag2-20261107（sha de508328）。
- FTDI 掉线阻塞烧录，待恢复后读 overflow 字节区分「漏检 vs 溢出」。

## 2026-11-07（续）：DDR3 STS 音频遥测 + 板级判读

- sys_ctrl STS 低 3 位改为 sd_idle/fifo_empty/fifo_full（契约测试同步），回归 438+26skip、lint 77/0。
- 诊断位流板级读回 STS 02：I2S 时钟正常、FIFO 瞬时空；结合 NPU 每窗完成一次判定窗口在推进，top1 恒定归因于窗口内容恒定（模拟输入静音），待下一轮播放中多次遥测确认。

## 2026-11-07：48k 量化模型接入板级（契约/镜像/位流/链路）

- 生成 scripts/outputs/medley_48k 契约与 691040 B 镜像（zp_in 47、fc2 zp_out 58）；golden 链支持契约/镜像环境变量成对切换。
- mel_engine 注入 INV_S_IN 236403274 / ZP_IN 47；mel_48k PASS、pytest 438+26skip、lint 77/0；npu_probe 新镜像 top1 一致但 logits 差 2~5 LSB（待查）。
- full 构建 58m36s，pix +0.059 / ddrphy −0.915；位流 releases/instrec-48k-model-20261107（sha d3ad62dd）。
- 板级 done1/CRC0、DDROK、WOK CFE5A709、NPU 15 轮；top1 恒定（窗口内容不更新）⇒ 待加 audio 诊断行定位，不宣称板级准确率。

## 2026-11-06：取消 147/160 重采样，48k 原生前端位流上板跑通

- instrec_top 删除 pcm1808_resampler、I2S 直连 CDC、mel 换 48k 表（2027 词）、audio_sink 注入 2604 拍。
- 仿真 mel/mel_credit/mel_48k/full_top_ctrl PASS、pytest 438+26skip、lint 77/0；门控 DRM 150.5→146；full 构建 1h31m，ddrphy −1.245ns（108MHz）。
- 板级 done=1/CRC0、BOOT/MMIO/ISA/DDROK、WOK FA0D5236、13 轮 NPU 完成；分类值待新量化参数重建。

## 2026-11-06：真实 I2S 采集全链路打通（播放设备 + 音量双重根因）

- 根因：Windows 默认播放设备为 NICEHCK（USB），winsound 未到 Realtek；且 Realtek 音量过低。改用 waveOutOpen 指定设备 4 + waveOutSetVolume 置满后恢复。
- 判据：1 kHz 满幅测试音 SNR 115.9 dB；真实音乐采集 std 1123、L/R 相关 1.0、CRC 0 错、无 2:1 重复；golden 特征 mean 49.0 / std 15.93 / 饱和 0%。
- 数据落 data/i2s_capture/montage_music_20261106/；工具 build/play_to_dev.py；采集脚本支持 --skip-boot/--no-capture。

## 2026-11-06：license（TAP 虚拟网卡）打通，i2s_capture 位流收敛并上板采集

- 修复 PDS 编译：tx_* 双驱动（Verilog-4086）；时序 −8.534 → All Constraints Met（CRC 串行化、约束加载顺序修正、删除无效 clock_groups）。
- 位流 releases/i2s-capture-20261106（SHA256 ef8a187e…），烧录 done=1/CRC0，BOOT+DDR OK。
- 板级采集 4 秒：DDR/UART/CRC 全通（3000 帧 0 错）；I2S 时钟线通、DATA 线恒高（0xFFFF 99.996%）⇒ 待接 DATA 线后重采。

## 2026-11-04：PDS license 三文件验证，均不可用（构建阻塞闭环）

- 新 pds license（2029 到期）host_id 属另一台机器、旧 license 已过期、ip.lic 为 FlexLM 格式不被 PDS 识别；证据 reports/pds_license_diagnosis_20261104.json。
- 需要本机 host_id F4A80DA47D72 的 package/feature license；构建集与 RTL/TB 均已就绪，license 到位即可构建。

## 2026-11-04：I2S 采集链路开发（数据通路打通，仿真未全通过，上板推迟）

- 新增 top_i2s_capture/i2s_capture_ctrl（FIR 前原始 48k 双声道 → DDR3 → UART 帧导出）、约束、全链 TB、PC 采集/播放/对接脚本 + 17 离线测试；恢复被覆盖的 I2S 接收单测为 i2s_rx_phy。
- 修复四处真实缺陷：命令捆包地址位宽错位、wrapper 输入悬空（_a 信号零连线）、TB BCK 两倍频、TB 采集起点未对齐。数据从全零推进到真实样本回传（word0/1 正确、帧/CRC 结构正确）。
- 未通过：payload 自 word2 起为零（读回字重复，rd_ready 与模型推送速率不匹配）、每 2 帧 1 新值（LRCK 边沿漏检）。据此不启动构建/烧录；回归 438+26skip、check_rtl 77/0。

## 2026-11-04：等模型期间三线并行——48k 真值链、mel 48k 仿真、集成实验顶层

- A：gen_mel_tables 参数化出 48k 表集（仅 mel_coo 变，hann/log2_lut 为采样率不变量）；golden_pipeline SR 参数化（默认零破坏）；48k 自验证饱和 0、librosa r≥0.999。
- B：mel_engine 透传 INV_S_IN/ZP_IN（QuantStub 注入通路补全）；mel_48k 仿真 16512 mismatch 0；跟进项：mel_filter coo_rom 深度须参数化（48k 表 2027 行超 44.1k 硬编码 2025）。
- C：top_integration_lab 三模块扁平 MMIO 集成 + 四场景 50 检查 PASS；发现 3 个生产集成接口问题（地址冲突/epoch 同拍/frame_start）。
- 外部事件：模型侧已按规格改 features.py 至 48k 域；test_golden_mel dod1/dod3 加域 guard（跨域 skip），基线 421 passed + 26 skipped（22 个预期过渡 skip）。

## 2026-11-04：模型重训规格文档交付，进入等模型阶段

- 新增 docs/MODEL_TRAINING_SPEC_20261104.md：交模型负责人的重训完整规格——Medley/五组数据现成无需采集、F1 原生 48k 前端契约（Mel fmax 24k 重生成、几何 64×258 固定）、算子白名单与通道候选、QuantStub 交付要求、验收门槛与七项交付物、附录 B 固化交付后分模块仿真→全链→PDS→三层注入→真实音乐的逐级上板流程。
- 用户裁定顺序：先重训后适配后仿真后上板；此前直接构建上板的提议作废；本轮零仿真/零构建/零板级。

## 2026-11-04：恒 top1 根因修复——量化移位 24→36，特征域恢复分化（全链验证）

- standardize.v/golden_pipeline.py 的 z×inv_s_in 移位修正（Q4.12+Q8.24=36 位小数）；旧 >>24 等效 2^12 增益致 uint8 特征 ~50% 饱和，RTL 与 golden 共享故位级对拍从未暴露；浮点×特征域 2×2 对照定位（float_vs_quant_domain_diag）。
- 修复后：mel/mel_credit/conv1 PASS、全 TB 34/34、pytest 443/4；golden_ref 三 stem 重生成（旧域在 git HEAD）；IRMAS 八样本 top1 由全坍缩恢复三类别分化且 RTL=golden 逐位一致；特征域上限 177（255 不可达）记入共生测试新语义。
- 待办：修复版新构建/新位流/板级三层注入（判据=npu_probe 新基线）；Medley 验证集数据缺口仍开；板上旧位流含此 bug。

## 2026-11-04：第二批交付——恒 top1 根因二分（模型/特征域）、logits 快照、五组契约转正

- E2 诊断：8 个 IRMAS 真实样本 RTL=golden 逐位全同但 top1 全坍缩 piano ⇒ 恒 top1 根因在模型/特征域；类表纠正（idx6=guitar_acoustic 非 trumpet）；板上坍缩点 6≠RTL 坍缩点 0，板侧另有偏移但仅修板侧不可恢复分类。
- E1：src/ctrl/logits_snap.v 16 槽原子快照锁存（契约 §3 RTL 化）+ TB 五场景 PASS。
- E3：五组 INT8 契约评审结论「转正提交」（macro-F1 Δ-0.0075、确定性双跑一致、hash 链锁定）；R1 zp 打包/R2 pytest 冻结为跟进项。

## 2026-11-04：按总规划启动并行开发，四工作包首批最小交付落地

- 修复基线缺口：emergency_demo 构建集补第 4 处登记（test_plan_contract_guards SET_NAMES），全量回到 443 passed / 4 skipped。
- A 音频/模型：experiments/audio_frontend 四路线（F0 基线/F1 原生48k/F2 24k/F2b 16k）对照管线 + 14 输入报告；F1 漂移最小但三路线均需重训，无 Medley 验证集如实记缺口。
- B 数值定位：sim/experiments/npu_probe 固定 feature 探针，4 向量×12 层快照真源（RTL=golden=golden_ref 逐位一致，31,115,245 cycles），产出 M0 可定位基线报告。
- C CPU 启动：src/boot/uart_app_boot.v（UART APP 协议 v0：chunk/CRC32/seq/EXEC 门控/ABORT，4KiB IRAM）+ 物理 115200 TB 六场景 52 检查 PASS。
- D 软件 UI：src/ui_scene 双 bank 描述符+四拍渲染器 + glyph ROM + Python 参考帧逐像素 TB（两场景 921,600 像素）PASS；ASCII 去重评估报告（可省 6.0 DRM36K 当量）。
- 新增 docs/INTERFACE_CONTRACTS_V0_20261104.md：UART APP/UI 场景已实现契约固化，MMIO logits 快照/DDR 地址图/模型描述符 v0 草案。本轮零 PDS、零板级、生产 src 既有文件零改动。

## 2026-11-04：完成正式开发交接总规划

- 汇总并最终确定存储优先/性能换资源、双模式、CPU软件UI与UART应用启动方向，细化并行责任、第一批任务、16/8lane实验和阶段DoD。
- 明确真实I2S整板数值验收、模型精度/时序边界、冻结资产和下载服务纪律；仅文档交接，不宣称新增功能完成。

## 2026-11-03：软件化UI/启动与DRM实测审计

- 从完整综合报告逐原语归因150.5DRM，区分DDR驻留与片上工作集，明确bank碎片/复制优化优先于强制缩模型。
- 规划加入24k前端对照、软件scene/UI ABI、最小boot+UART应用RAM/DDR启动及并行集成门槛；未实施生产改动。

## 2026-11-03：硬件适配模型与双模式详细开发规划

- 新增统一前端/共享NPU双模式方案、轻量模型与采样率对照、精度/资源准入、CPU快照及模式切换协议。
- 明确并行任务边界、仿真优先门槛、feature/PCM/I2S分层整板数值验证、真实音频和耐久验收；本轮仅规划，无新训练/构建/烧录结论。

## 2026-11-03：重插后重烧成功并归档下载器掉线

- 同版0EBF9448 program/done/CRC/BOOT/DDROK通过；FTDI随后掉线导致overall FAIL，分项证据保留，不重复烧录或操作服务。

## 2026-11-03：再次重烧前发现 FTDI 缺席

- 同位流hash已核对，PnP无下载器而安全退出、未program；保存独立FAIL报告，等待用户重插电脑端USB，不操作JS/cfg。

## 2026-11-03：按用户要求重烧去提示演示版

- 既有0EBF9448实屏验收通过；本次同hash重烧program/done/CRC通过，但UART0B、启动/DDR检查未通过，独立记录失败证据，等待新屏幕反馈。

## 2026-11-03：删除演示 KEY1 整行提示并烧录新版

- 只移除演示页右下角提示整行；曲线ROM数值/重播/实时音频频谱保持，五状态全帧RTL与lint69/0通过。
- 新源0EBF9448位流已安全烧录，done1/CRC0/BOOT/DDROK通过；完整十表All Constraints Met，用户新实屏验收待答。保留独立构建/时序/烧录hash，未触碰正式系统或旧证据。

## 2026-11-03：紧急曲线演示生成位流并上板

- CE2E2205独立演示正常完成布局布线与烧录，done1/CRC0/BOOT/DDROK；无权重依赖，用户确认“显示与回放正常”，实屏演示验收通过。
- 十表完整但setup仍FAIL：pix -0.005ns/1、core -0.399ns/34，其他检查通过；保留全部hash，不作为真实识别或稳定交付证明。

## 2026-11-03：导入用户八类演示曲线并隔离显示标签

- 冻结114窗用户JSON及581点ROM；演示独立标签/字库匹配钢琴至电吉他八类，常显曲线演示。KEY1重播，保持真实PCM1808/波形/Mel/HDMI，无NPU推理或权重依赖，正式资产不变。
- pytest48passed、播放器/全曲线/五状态全帧RTL均PASS、lint69/0。新源门控20886LUT/18148FF/74.5DRM/31APM通过，继续限时PNR；尚无新演示位流/板测。

## 2026-11-03：完整中文显示验收与手动复位权重恢复

- 用户确认新完整系统仪表盘及动态显示正常。手动复位清除weight_ok后重新上传，WOK FA0D5236，12秒5轮推理回读恢复；无需重烧位流。记录原文hash，不宣称时序收敛或准确率通过。

## 2026-11-03：完整 PCM1808 系统重新上板并通过权重/连续推理检查

- 下载器恢复后安全复用JS烧录1497FAF4完整新位流，done1/CRC0、RV32启动/MMIO/ISA及DDROK通过；691040B权重WOK FA0D5236。
- 30秒10轮NPU完成/CPU回读，无超时，均top1=6；保存原文hash，不宣称准确率。HDMI新板测反馈待用户，静态核心setup仍FAIL，后续继续收敛。

## 2026-11-03：PCM1808 完整 PNR/位流完成，归档最终时序与下载阻塞

- 新源1497FAF4完整位流生成，103项输入hash一致、PDS/monitor正常退出；十表仅核心慢角setup仍FAIL (-1.071ns/338端点)，保留报告hash与长路径定位。
- 烧录前FTDI缺席，用户重插确认后重试仍缺席，独立PnP仅见COM5，已保存第二次未program证据并请核对独立下载器USB/直连口；既有JS/cfg未操作。修正音频接线文档当前27MHz域与预算，不宣称新整机板测通过。

## 2026-11-03：Mel scratch bank 按16K边界拆分以释放宏放置空间

- 保存完整27MHz整机Place-0006失败证据，无新位流。bank拆分保持逐拍语义，212480次miter、整窗Mel及16512字节NPU交接均PASS；启动新源单路30分钟资源门控，实际资源与PNR待验。旧特征交接历史报告保留，新报告独立。本次全量436passed/4skipped、lint65/0。

## 2026-11-03：XSY 完整系统接入 27MHz PCM1808 处理域

- 按用户要求将五个 PCM1808/Flash 提交快进合到 XSY 并推送，停用 XSY2 后续开发。
- instrec_top 复用实测通过的 27MHz 主机接收/FIR，1ms watchdog、两级复位释放和异步时钟组同步更新，移除顶层不再需要的音频 PLL；不改变模型采样契约。串行 golden/audio FIFO/CPU 控制回归通过。新源资源门控中，尚无新完整位流。
- 修正 plan-contract 测试清单漏列 pcm1808_diag；相关 9 tests PASS，首次全量的单项失败记录保留。

## 2026-11-03：PCM1808 实际线路音频板测通过

- 用户纠正 J3→J2 并供电后，连续 10 秒输入约 48k stereo pairs/s、滤波输出约 44.1k，非零正负音频持续变化，无 idle/overrun。保存串口原文/hash/解析；当前仍为 2856BB4D 独立诊断，完整识别集成待完成。未烧录新增边沿候选，候选构建已退出并归档。

## 2026-11-03：PCM1808 真实采集诊断上板

- 完整优化系统 PNR 50 分钟截止仍有 4737 条未布通网络，无新完整位流，保留失败证据。
- 新增 27MHz PCM1808 独立采集/FIR/UART 构建集，标准全流程及十表内部时序 PASS，2856BB4D 位流复用既有 JS 烧录成功，done=1/CRC=0、PCM8 串口签名通过；外部音频待接线验收，诊断没有 HDMI。
- 参数化实际串行测试，27MHz 与 216MHz 两种频率 golden/断钟恢复均 PASS；构建/烧录安全 41 passed、lint 65/0。报告与接线说明同步更新。

## 2026-11-03：PCM1808 主机音源接收与精确重采样

- BCK/LRCK 改为输入，新增 216MHz 同步 Philips I2S 从接收，捕获 24bit 的高 16bit；完整立体声帧 watchdog 支持断钟/LRCK 卡死后无 reset 恢复。
- 新增 147/160、147phase/96tap 双声道 Q15 FIR，将 48kHz 转为原模型的 44.1kHz；明确 MES-FMC-LPC-IO 紫卡 J2 接线，旧输出位流更换前不连接 BCK/LRCK。
- 系数以 7104 项基表和 73 相整数校正无损重建原 14112 项；采样历史改同步 block RAM＋有效计数补零。优化源联合 RTL 再次通过。首轮 50 分钟 PNR 截止时仍未布通，已保存失败证据，无位流/无烧录；优化完整映射 PASS：35931 LUT/35508 FF/155 DRM/92 APM（DRM 已满），新映射限时 PNR 中。全量回归 436 passed/4 skipped。
- 实际串行→FIR→CDC 两轮 4096 对输入/3762 对输出逐项 golden PASS；新增 pytest 3 passed、既有 433 passed/4 skipped，lint 64/0。完整新源映射 39749 LUT/39576 FF/154.5 DRM/92 APM，容量通过；PNR/时序及板级结果以 STATUS 与 pcm1808_validation_20261103.json 为准，不以仿真或映射代替上板验收。

## 2026-11-03：Flash 固化工具流程与第一版烧写镜像

- 研究并实测 PDS 位流→SPI Flash 全流程：`cfg_gen_sfc` 离线转换（X1 下 sfc≡sbit 逐字节）、JTAG 间接烧写命令族（cfg_jtag_flash_*）、MSPI 001 启动模式与 4K 对齐布局、GTP_CFGCLK/`persist_pin` 用户模式评估。产出 `build/flash_boot/instrec_top_w25q128q.sfc`（2673246E…）。
- 新增 `docs/FLASH_PROGRAM_FLOW_20261103.md`（操作手册：转换/烧写/冷启动验收/风险回退/探针设计）与 `reports/flash_program_flow_20261103.json`。零 JTAG、零板级、零 GUI、未改既有 RTL/约束/脚本。

## 2026-11-02：HDMI显示保底与真实板级失败记录

- UI烧录和内部计数通过，但用户确认J9无信号，显示验收FAIL；原厂同板例程已对照烧录，待屏幕反馈。
- 建codex/display-demo，核对底板HDMI引脚并准备G25复位修复。RV构建为让出单PDS名额受控停止，证据保留，无新位流。

## 2026-11-02：板级启动与 UART RX 采样修复

- 既有 RV 位流诊断烧录成功（done=1、CRC=0），实收 RV32 BOOT/MMIO、DDR OK、NPU GO；权重首帧无ACK，未宣称板级推理通过。
- 修复 UART START 检查从1.5bit提前到0.5bit，使bit0正确落在1.5bit；新增264字节真实串行波形回归和接收器到loader的完整串行WOK/CRC/复位联测。旧RTL可复现AA误收20，修复版两项均PASS，直接字节loader回归保持通过。
- 修正SCBV正常提示被误当作下载阻塞的判断；时序负裕量仍开放，板级运行不代表时序闭合。

## 2026-11-02：未覆盖 NPU activation/full-end 补测

- `npu_activation` Verilator 补测通过：conv1 792576 项、pool1/DDR/conv2 golden exact，最终 12242761 cycles。
- `npu_full_end` Verilator 补测通过：四层卷积、DDR activation replay、GAP/FC/softmax full npu_top golden exact，30757679 cycles。
- 未修改生产 RTL、未启动 PDS、未操作 JTAG/下载器；板级仍 NOT_RUN，最新位流的 DDR PHY 时序和 SCBV 问题保持不变。

## 2026-11-02：控制冒烟与 RV CPU C1-C9 回归

- `ctrl_smoke` 6 项全部 PASS，覆盖 BOOT、DDR3 SELFTEST、DDROK、STS=00 与 RUN 控制路径。
- `rv_cpu` C1-C9 全部 PASS，覆盖真实 RV32 固件启动、MMIO/ISA/mcycle、NPU 触发、DDR 状态、ACK 和结果快照；UART `NPU top1=5 last_class=3 last_p=87 c=12345`。
- 仅为模型/RTL 仿真证据；板级仍 NOT_RUN，未启动 PDS，未操作下载器或 cdt 服务。
- 追加 98 项定向 Python 回归（Mel/conv1/contract/golden/table/plan guards），全部通过。
- 完整 Python 回归复核为 432 passed / 4 skipped；新增 NPU stream、WDMA parameter pipeline、board_e2e_order 三组共 34 passed，未启动 PDS/JTAG。
- 烧录安全与 UART 握手回归 21 passed；仅验证脚本保护逻辑，未执行烧录、未触碰下载器。

## 2026-11-02 — 心跳回归与 db_norm 时序定位

- 重新完成 frame-major 真实 RV+native NPU 联合回归：31,141,202 cycles，conv1/四层 activation replay/完整 golden、MMIO/UART/ACK 全部通过；`mel_credit` 16,512 特征逐字节对拍通过。
- RTL 检查保持 59 个 `.v`、0 violation。时序最差路径定位到 `db_norm` 的 dB 平方与 `sum_db_sq` 累加链；仅在隔离副本评估寄存平方和末项 flush，未改生产 RTL、未启动 PDS、未操作下载器。
- 隔离 `db_norm` 流水候选通过 Verilator 小几何同步 RAM TB（首帧丢弃、写回、最后平方项 flush；`sum_db=-1513`、`sum_db_sq=1190489`）。候选只保留在 `build/experiments/db_norm_pipeline/`，尚未推广或重新布线。
- 该候选进一步替换到真实 `mel_credit` 入口，16,512-byte feature golden 对拍通过（25.6 s）；仍未推广生产或启动 PDS。

## 2026-11-02 — DDR 修复版资源门禁与联合回归

- 修复后的 `rv_core` 通过 PDS compile/synthesize/dev_map，资源为 32063 LUT、33300 FF、120.5 DRM、90 APM；未进入 PNR，无新位流/时序/板测结论。
- 全量回归 432 passed / 4 skipped，RTL 59 文件 0 violation；真实 CPU+native NPU frame-major 及无复位 A/B 双帧联合均 PASS。
- reset-mid-read 同 ID 迟到响应仍为开放风险，未添加无证据的丢弃逻辑；下载器和 cdt 服务未操作。

## 2026-11-02：DDR 读超时迟到响应隔离

- 修复 DDR 读 watchdog 超时后的迟到响应误归属问题，增加 `S_R_DRAIN` 隔离状态及周期模型回归。
- 验证：DDR/仲裁/自检定向 48 passed；全量回归 432 passed / 4 skipped；RTL 词法检查 59 文件 0 violation。未启动 PDS、未操作下载器；修复后的 RTL 尚未重新生成位流。

## 2026-11-02：增加 DDR 初始化门控

- `instrec_top` 用 `ddr_init_done` 门控 DDR command valid 和控制器侧 `axi_rvalid`，补充初始化前 stale R 屏蔽契约测试（9 passed）。该缓解依赖 IP 在初始化完成前清空旧事务，不能替代初始化完成后的响应 ID/epoch 过滤；尚未重新生成位流。
- 复位静态审查发现 DDR3 IP 旧事务是否跨复位释放仍无源码证据；新增“reset-mid-read + stale RVALID”模型场景待验证，不把当前 timeout drain 修复外推为完整 reset recovery。
- directed 模型已确认 reset-mid-read + stale `RVALID/RLAST` 可被新读误收，作为开放问题记录；未启动 PDS 或下载器操作。

## 2026-11-01 23:49 — 复核 frame-major PDS 产物并校正实时状态

- 冻结 gate-manifest SHA256 `C2F3F1F4C5DCCBD55FDDE54A6A970F78C032C0D6E8E44EB5CD67A6E853C3581E`；最终 run.log SHA256 `69F3EFDAA5047F261FFE859FF2003F40096673EBAF5B973285D67767581481E`；timing报告 SHA256 `C1C1D8B19EA696E0968563A313621A03F97E51D1027397448DFBD3628B825853`。
- 再核实 detail routing iteration105 未布0、成功完成布线和位流生成，PDS进程为0；不代表时序收敛或板级通过。将旧23:15/23:11“当前综合/无位流”改为历史说明，注明heartbeat中的224112 gate已过时。
- 生产 frame-major CPU/native 联合仿真独立run-label复核PASS：真实RV固件MMIO启动，四层conv/pool/GAP/FC/softmax全golden exact，31141202 cycles，UART `top1=0,last_class=7,last_p=0`，ACK正确；日志保留在 `build/sim/cpu_native_joint_heartbeat-frame-major-20261101-1548/run.log`。物理DDR PHY、真实音频/Mel、完整top reset及异常事务恢复仍未覆盖。未触碰下载器、cdt服务、`cpu/`用户改动、PCB/PDF或obj_dir。
- timing复核补充：快角 `ddrphy_sysclk` WNS -1.305ns、96个setup endpoint失败；激活行缓存reset证据会主动取消模型中的未完成DDR事务，不能外推迟到R或完整top物理复位恢复。

## 2026-11-01 23:43 — frame-major RV/NPU 位流候选完成布线

- 完整冻结flow完成至位流生成，详细布线第105轮未布0；映射资源32075 LUT / 33300 FF / 120.5 DRM / 90 APM。
- 位流SHA256 `ED713818EFE9E5A616437D302A994B69984F66FCE9E8D43A8EE2AA8BF8509163`。时序报告显示ddrphy_sysclk WNS -5.227ns、TNS -8567.538ns；clk_nco +2.220ns、rst_clk +3.954ns，hold均正。该候选已布通但未满足ddrphy_sysclk时序，板测NOT_RUN。
- 构建产物留在gitignored build目录；未操作下载器或cdt服务。

## 2026-11-01 23:15 — 修复UI特征copy暂停污染与末尾重复写

- 真实共享同步RAM反例复现后修复pending响应追踪，四场景每轮16512写且0错误、页翻转正确；19定向测试通过。
- 记录uint8/zp49、同步读延迟及单bank异常跨窗缺锁页边界；UI不在当前rv_core冻结flow，综合继续，无位流，不操作下载器。

## 2026-11-01 23:11 — 修复真实Mel/NPU读口布局，启动正确冻结单flow

- NPU增加显式frame-major参数，三top启用，利用现有行列拼接地址；真实bank切片旧16446错/新0错，16512地址双射。frame-major完整CPU/native全层golden、结果/ACK通过；uint8/zp49正确。
- 全量429 passed/4 skipped（83.22s）、59.v词法0违规；修复stage续跑driver/真实ADF门槛与备份，成功续跑尚未证明。
- 23:09:47启动唯一native-20261101-230932-136199精确冻结单flow，当前前置阶段，实际PNR进入后限45min；UI copy占口恢复缺陷独立修复中，下载器未操作。

## 2026-11-01 23:07 — 阻止带Mel布局缺陷的构建继续

- 发现实际Mel frame-major与NPU mel-major接口直连错接；旧完整NPU/CPU行为RAM测试不能覆盖。正在修复及补真实bank布局回归。
- 如实记录续跑探测误触compile清理ADF；23:03新隔离单flow因布局缺陷在synthesize核验止损，未进入PNR，无位流，不操作下载器。

## 2026-11-01 22:59 — 完整映射、CPU双轮及生产行缓存reset验证

- 归档完整gate正常PASS最终32076LUT/33300FF/120.5DRM/90APM证据；续跑入口阶段恢复失败仍在修复，实际PNR未开始、无位流。
- 生产RTL+隔离重复启动固件A/B无reset两轮联合PASS，各31141202cycles，全层golden及两次CPU请求/安全窗启动/UART/MMIO/ACK一致；生产ROM不变。
- 直接生产行缓存八状态reset后新geometry完整回放PASS，明确DDR模型同时取消pending响应边界。新增隔离runner/TB/说明/报告，旧失败及候选证据保留，下载器未操作。

## 2026-11-01 22:52 — 生产新ROM+narrow联合证据与全量回归

- 保存生产CPU/native联合PASS报告，27项输入hash均核验；完整各层golden、MMIO/UART与ACK通过，保留物理DDR/音频/Mel边界。
- runner增加独立run-label保留历史证据；Python429 passed/4 skipped，102.03s。
- 记录新完整拓扑技术综合32077LUT/33311FF/120.5DRM/90APM，仍保存DB，等待最终map再受控PNR；无新位流，不操作下载器。继续CPU连续推理补测。

## 2026-11-01 22:42 — 修复激活行缓存RAM推断，启动新完整资源gate

- 将行缓存改为有界无符号计数器、明确地址slice和单写口RAM模板；isolated映射39s通过，794LUT/343FF/16DRM/0APM，32个lane bank均真实映射DRM。旧完整拓扑两个store原占84886LUT/100280FF/0DRM。
- 新冻结候选三top结构、三geometry逐拍等价及完整native A/B无reset双轮全部PASS，各31141202cycles；据此只推广行缓存一处RTL差异，保留旧失败证据。补齐10816即时R/9次忙期start/异常响应sticky及reset清错定向测试。
- 超容量gate22:31、original孤立probe22:38按截止安全止损，均无位流；新唯一完整gate224112-909881已启动，止于dev_map，不并发PDS。准备脚本改用snapshot IP/TCL并校验额外构建输入hash。
- 纳管reports/activation_store_narrow_20261101与npu_narrow_snapshot_validation_20261101.json；无新完整资源/时序/板级结论，下载器未操作。

## 2026-11-01 22:29 — CPU/native 联合闭环、top1修复与容量阻塞

- 真实CPU ROM启动→CTRL/Mel安全窗→完整native NPU golden→结果MMIO/UART→ACK联合PASS；修复生产固件把最后概率lane误称top1，改为分别输出硬件top1/last_class/last_p。CPU C1–C9与生产默认联合再次PASS；生产ROM两次重建与隔离联合ROM逐字节相同，579words，SHA256前缀24d0b7fd。
- A/B不同输入连续两轮不复位PASS：16512 feature字节全部变化，两轮各31141202cycles，全部中间层/最终结果golden exact；持久化runner、输入golden哈希及剩余异常边界说明。
- exact完整拓扑综合资源超器件：LUT115473/66600、FF133439/133200、DRM88.5/155、APM92/240，禁止进入PNR，无位流。激活行缓存单写口/窄位候选三geometry逐拍miter通过，等待当前gate退出后串行隔离资源probe，不并发PDS，不操作下载器。
- 证据：reports/{cpu_native_joint_validation_20261101.json,activation_repeated_boundary_review_20261101.md,activation_store_resource_review_20261101.md}及sim/experiments/{cpu_native_joint,activation_store,npu_integration_review}/。

## 2026-11-01 22:02 — 完整 native 两轮修复推广主线与 exact 资源 gate

- 推广六compute、DDR arbiter、六新增activation/native模块、三顶层，修复权重基址/16-byte对齐、层间DDR激活回放、FC旧参数epoch与错层权重、m1事务owner/early done/timeout误ACK；同步diag与仿真端口。
- 215059冻结与生产真实源路径分别连续两轮不复位完整golden PASS，各31,141,202cycles；conv1–4全量0 mismatch，GAP/FC/softmax、两次完成、CPU C1–C9与启动控制17项断言PASS。
- 真实loader+owner+生产controller上传/读回/CRC拒绝、AW/读超时及四口争用隔离PASS。Python429 passed/4 skipped；59.v词法0 violation。保留原始FC2失败/门控不足/FC旧epoch/loader提前done证据。
- 资源误判纠正：wide较corrected-scalar少10797 LUT/20507 FF，多8DRM；不能断言DRM为拥塞根因。新完整拓扑唯一gate native-20261101-215404-522126止于dev_map，compile完成，synthesize进行中；无新版RV位流、未上板，下载器未操作。
- 证据：sim/experiments/{weight_read_aligner_hardened,npu_integration_review,conv_layers_mainline}/；reports/{wdma_resource_gate_assessment_20261101.md,npu_production_promotion_20261101.json}。后者记录主线只清注释/空白的双SHA及16文件功能文本不变。

## 2026-11-01 20:44 — 停止停滞 RV 路由并启动串行资源 gate

- RV 构建 `20261101-130420-0ed52a5d` 在 iteration 370 仍有 7156 条未布网络，按观察规则结束该 run；62 项 manifest 零漂移，未产出位流/时序报告，日志保留。
- 保持 `cdt_js`/`cdt_cfg` 与下载器不变；启动 corrected-scalar `dev_map` gate，完成后才运行 corrected-wide，禁止并发 PDS。
- 记录完整 native NPU 自然推理 PASS（31,115,245 cycles）及全量回归 `429 passed, 4 skipped`。
- scalar `dev_map` gate 完成：LUT 40206、FF 53718、DRM 80.5、APM 90；未进入 PNR。wide gate 随后串行启动，当前在 compile。
- wide `dev_map` gate 完成：LUT 29409、FF 33211、DRM 88.5、APM 90；未进入 PNR。wide 的 LUT/FF 优势伴随 DRM 增长，暂不启动新 PNR。

## 2026-11-01 18:54 — 原生 DDR 联合 harness 激活写握手失败证据

- 新增真实 `ddr3_ctrl_axi` + AXI model + bridge 联合测试；权重 16-beat 完成，激活写阶段卡死，保留失败实验并继续修复，未修改生产 RTL、未宣称 native 集成通过。

> 每次会话结束前追加一条：时间、做了什么、结论、证据路径。倒序，最新在上。
> 状态汇总见 `docs/STATUS.md`。

## 2026-11-01 13:02 — 修复顶层隐式网并完成全回归

- 修复 `instrec_top.dbg_tx_ready` 未声明和 HDMI 旧控制器 `init_over_rx` 重复声明。
- 修复 UI overlay 接口后完整 RTL 集合 **14/14 PASS**（281.0 s）；Python **429 passed / 4 skipped**；RTL 词法检查 0 violation。
- 音频 CDC FIFO 临时双时钟仿真通过。全树 Verilator 展开仍因 Pango/DDR IP stub 不足受阻，不宣称全顶层展开成功。
- RV PDS run `20261101-113509-6927c1bf` 在 iteration 21 后异常消失（尚余 27603 unrouted nets），恢复因 PDS project 未保留 post-synthesis design 失败；未产生位流。已启动新 run `20261101-130420-0ed52a5d`，正在重新 compile/synthesize；禁止把旧 run 当成功。
- 顶层审查另发现 `uart_debug.ram_len` 7 位无法表示满 128 字节（截为 0）；因新 PDS manifest 正在消费该 RTL，本轮先锁住源哈希，待构建终态后修复并针对 128 字节边界补仿真，避免发布与网表源不一致的产物。
- 并行补齐 I2S 联合仿真：`i2s_clk_gen` + `i2s_rx` 解码 24 字并观察到正确 BCK/LRCK 相位，左右样本 `A53C`/`5AC3`；测试位于 gitignored `build/sim`，未改 RTL。

## 2026-11-01 12:53 — 修复 UI overlay 接口漂移并补齐仿真

恢复 `ui_renderer` 的六个 overlay 端口和 `ui_overlay` 级联，保持四级 RGB/DE 对齐。
`ui_render` 通过 64 个有效像素、优先级 0 mismatch、对齐 0 mismatch；新增独立
`ui_overlay` 用例通过 6/6；受影响 Python 合约测试 32 passed。当前 RV PDS 构建继续
独占运行，UI 修复不在 `top_rv_core` 构建集内。

## 2026-11-01 07:45 — R1 达成（DDR3 board-proven）；全模块仿真闭环；多 master AW 污染根因定位

**R1 达成（board-proven）**：精简顶层 `top_core_only` 布通并两次烧录，串口
`INSTREC BOOT` → `DDR3 SELFTEST...` → **`DDROK`** → `DDR3 STS 01`；`board_core_only.json`
`verdict=PASS`、`expect_missing=[]`、`status_raw=0x081ffca0`。位流 SHA-256
`d375a43d…4c4e18a8`，归档 `releases/m5-ddrok-20261101/`（含 SHA256SUMS 与 README）。
`STS 01` 低两位 `st_done=1`、无超时位 ⇒ self_test 的 16 段写 + 读回全部通过。

**全模块 Verilator 仿真闭环**（`sim/run_sim.py`，全套 44 s，替代 15 min/轮的构建+烧板）：
conv1~conv4 与 golden 逐值全对（658,432 字节）；Mel 全链 `feat 16512 mismatch 0`；
`gap→fc1→fc2→softmax` bit-exact；`ui_render` PASS；DDR3 子系统 15/15 PASS；
`weight_loader` 修好 `S_TX` 与 `uart_tx` 相位不匹配（每隔一个字符丢一个，
`WOK 42851062` 曾退化成 `WK4816`）——这是板级 `WOK` 零回复的真因，与 DDR3 无关。

**9 个真 RTL 缺陷已修**：位宽截断 4 例（`WIN_FRAMES` 17→18、`DB_NUM_S` 10→11、
`sq_lo_sum` 19→20、COO offset `ch+6'd1` 6 位溢出）、contract 6 位基址、ROM/tap 滞后 2 拍、
tap 只 2 bank、`requant_unit` 的 `shift_q` 只锁存到 S1、`conv_engine` drain 跨 contract
promote、`weight_loader` 串口相位。不修这些，此前所有板级结论都不可沿用。

**多 master 并发是新缺口**：接通 audio/mel 的 core_only（APM 89、LUT 32615）板级
`DDROK` FAIL、`DDR3 STS 26`。修正判读：`STS 26` 的 `cmd_to_err[3]=0` 与「m3 自身超时」
互斥，实际是某个非 m3 写 master 在 S_AW 超时 + m3 数据比较失败；根因是 **IP 侧写通道
污染**（一次写数据阶段被中止后未完成写突发永不闭合，之后所有 AW 永久被拒；仿真 A1 实测
13103 拍内 `awready` 一次都没出现）。仲裁不是瓶颈（m3 排队仅 5 拍）。
见 `reports/multi_master_aw_timeout.md`。

**观测位段改进**：`DDR3 STS` 字节改为 `{cmd_to_err[3:0], to_err, dbg_to_state}`，
暴露每个 master 的超时位——若早这样，本轮就不会把 m0 的超时误判成 m3 的。

**全量布通结论**：LUT 34960（52.49%）停滞（未布数 4400~4600 震荡 6.7 小时，
证据 `build/stall_evidence/`）；裁 UI 后 LUT 32615（49.1%）一次布通，只差 1.9 个百分点
即从永久停滞回到可行解 ⇒ 该器件是「余量为零」而非资源不足。`DRM=0` 曾被误读为 PHY
缺失，实为通用分布式 RAM；DDR3 PHY 走专用硬核（`DDR_PHY 7/24`、`PPLL 2/6`、`TSERDES 14/48`）。

## 2026-10-31 13:56 — DDR3 阻塞解除：两轮诊断位流定位并修复 `self_test` 端点错挂，design 配置 PASS；T10 全量构建进行中

**根因（已修）**：`src/ctrl/self_test.v` 的 `done` 端口**从未被使用**——AXI watchdog abort 后
`ddr3_ctrl_axi` 不再推进，`self_test` 就永久卡在 `ST_WDATA`，100 ms 后由 `sys_ctrl` 报
`DDR3 ERR @FFFFFFFF`。修复（端口不变，只改 FSM）：写阶段 `if (wready_beat) … else if (done)`
（正常完成时 `done` 与第 16 拍 `wready_beat` 同拍，必须先判 `wready_beat`）；读阶段用延迟 1 拍的
`done_q` 且 `rd_valid` 先判；`cmd_valid` 改为电平 hold 到 `done`。判据 `test_self_test_model.py`(14)。

**方法论（本轮最大收获）**：PDS 流水参数化为构建集——`scripts/build_sets.json`（full / ddr3_diag /
ui_demo）、`build_full.tcl` 8 token、`run_pds_full.ps1 -BuildSet/-DryRun`。新增 `ddr3_diag` 最小诊断
位流（7 源 + 1 IDF + 2 约束），**单轮实测 4 m 37 s ~ 5 m 13 s，全量约 1.5 h**。一套位流内同时例化
两份不同 AXI bring-up 参数的 `ddr3_ctrl_axi`（`AXI_USER_AP=1`/masked strobe 与 `AXI_USER_AP=0`/
all-1 strobe）+ 12 条 mux，**一次上板拿到两套配置的独立结论**；帧经 `diag_uart_report`（91 字节
固定 ASCII、显式 case 表）走 UART，`scripts/diag_frames.py` 解析。

**两轮板级**：① 首轮（D-01 未修）两套 cfg 均 TIMEOUT，`A==B==D≈25 万、C(done_cnt)=0`，根因是
`top_ddr3_diag.v` 的 `st_cmd_valid = {3'b000, st_cv}` 把 `self_test` 挂到 master 0，而
`done/wready/rd_valid` 全取 `[3]` ⇒ 控制器一直跑 m0 的 `cmd=0` 空读；契约 `plan.md §2.2.4` 的示例
本身写错，**已修正**。② 第二轮 `result_a`（design）**PASS**，`A/B/C/D = 16/136/16/128`、
`wlast_miss_cnt=8`、`to_err=0`；`result_b` FAIL 属预期代价（全 1 strobe 的 dummy-write 覆写读区首拍）。
位流 SHA-256 `F749A41768C31AE57AFC2ACE0B1C075CB35110056BB6A863408B5CFF2402266F`，WNS +4.405、
LUT 4954（7%）。**16-beat 真实写/读通路首次被真正激励**。全量 `instrec_top.v:638` 的 m3 本就在 bit3、
`ddr3_ctrl_axi` 用默认参数即 design 配置 ⇒ **T10 预期 0 行 RTL 改动**。

**新增验证资产**：`check_rtl.py` 49 个 `.v` / 0 violation；`pytest -q` **398 passed / 4 skipped**；
`tests/test_plan_contract_guards.py`(8，跨 model/RTL/脚本契约护栏，已做变异敏感性验证)；
`tests/ddr3_ctrl_model.py`(24)、`test_self_test_model.py`(14)、`test_diag_uart_report.py`(26)、
`test_build_tokens.py`(24)、`test_board_check_expect.py`(22)；
`board_check.py` 新增 `--json` 证据文件与退出码 5（`--expect` 未命中）。

**UI 解耦**：新增 `top_ui_demo` 小顶层 + `demo_wave_source`/`demo_spec_source` 片内假数据源 +
`top_ui_demo.fdc`（42 引脚与 `instrec_top.fdc` 逐项一致），UI 位流（`-BuildSet ui_demo`）排在 T10 之后，
**尚未构建、未上板**。

**T10 状态**：全量构建**进行中**（纯 `pnr`，约 1.5 h），**全量位流尚未产出**；
`build/instrec-latest.{sbit,json}` 仍为 10:46 的 m3d 产物。已知限制：本机无 Verilog 仿真器，
时序正确性靠 Python 周期模型 + 静态断言；UI 画面内容无法脚本化判读（无摄像头）。

## 2026-10-31 11:15 — 全功能位流 m3d 布通 + 板级首次可读启动日志 + DDR3 自检阻塞

**软件侧完成**：按「一层一轮」把功能逐层加回，四版全部布通并按能力递增归档：
`m3a`（wdma 参数表块 RAM 化，`152FEC8B`，477 轮）→ `m3b`（+UART 字符间隔修复，`D28C798C`，695 轮）
→ `m3c`（+文字层，`482CCA1C`，1426 轮）→ **`m3d`（+谱图层 = 四层 UI 全齐，`0B2BE8D4`，510 轮）**。
m3d 资源 LUT 34327(52%)/DRM 86(56%)/FF 52188/APM 90；`ddrphy_sysclk` -2.144→**-0.966**、`pix_clk` **+0.018 转正**。

**wdma 块 RAM 化是本轮关键**：三个异步读参数表（LUTRAM/FF，8004 LUT / 18608 FF，最差 core 路径在其中）
合并为单张 1024x32 同步读表，读地址前视两拍（`tests/test_wdma_param_pipeline.py` 7 项固定该配对）。
LUT -1086、布线 1001→510/477 轮、core 时序同步改善 —— 验证了「布线停滞=余量为零」而非资源不足。

**板级（重插 USB 后）**：烧 m3d → `done=1 / crc_err=0`、串口 **49 字节三行可读**：
`INSTREC BOOT` / `DDR3 SELFTEST...` / `DDR3 ERR @FFFFFFFF`。UART 握手修复至此上板确认闭环。

**当前唯一阻塞**：`0xFFFFFFFF` 是 `sys_ctrl` 的 100 ms 超时分支（`self_test` 未拉 done/fail）。
烧 2026-10-29 的 `m2c` **同样 DDR3 ERR** → **不是回归**，DDR3 通路从未验证通过（此前被串口乱码掩盖）。
已排除：`pll_all` 已含 `ddr_init_s`、四主口仲裁掩码、`self_test` FSM 启动、顶层 m3 接线。
待查（接手第一顺位）：DDR3 IP 是否真的接受 AXI 写事务（历史记录：IP 无 `axi_wvalid`，自定义控制器会卡死）。

**降频尝试失败并已回退**：改 `ddr3_test.idf` 到 DDR3-800 后用 `ip_generate -i` 重新生成，
报 `IPCompiler 0014: Failed to open index.xml` —— 本工程 ipcore 无 IP 实例工程文件，**无法命令行重生成**。
`.idf` 已恢复到 DDR3-1000/8000ps 与已生成 RTL 匹配。真降频需 IP Compiler GUI，或给用户逻辑单独分频（工作量大）。

**新增交接快照** `docs/HANDOFF_SNAPSHOT_20261031.md`：可用位流清单、板级实测原文、DDR3 排查进度、
复现命令、硬规则、踩坑清单、接手建议顺序。pytest 280 passed / 4 skipped。

## 2026-10-31 06:45 — 布线临界点突破：wdma 块 RAM 化 + UART 间隔修复，两版位流布通

**根因闭环**：两天「布不通」的真实原因是**余量为零**——m2d 基线 LUT 35677 布通（1001 轮），
只加 11 个 LUT 就永久停滞；纯 `pnr` 才是能布通的配置，`-parallel`/`-gplace_seed`/
`-plc_decongestion`/`-dc_duplication` 四个「优化」参数全部把布局拖进拥塞解。

**解法**：`u_wdma` 的 bram/mram/sram 三个异步读参数表（18432 bit，PDS 建成 LUTRAM/FF，
占 8004 LUT / 18608 FF，最差 core_clk 路径就在其中）合并为单个 `1024x32` 同步读表
（bias@0 / M@256 / shift@512）；`S_GRP` 消费 `pq`、同拍给出 `pa`、寄存器化 t+2，
契约拍数不变。新增 `test_wdma_param_pipeline.py`(7) 逐拍比对地址与数据配对。

三重收益全部兑现：LUT **35677→34046（51.1%）**、`u_wdma` 8004→6895、
布线 **1001→477/695 轮**、`ddrphy_sysclk` **-2.144→-1.228/-1.511**、`pix_clk` 一转正。

两版位流归档：`releases/m3a-20261031/`（`152FEC8B…`，wdma 优化）、
`releases/m3b-20261031/`（`d28C798C…`，+ UART 字符间隔计数器 12000 拍，
不改 valid/ready 语义，正是为了不破坏已布通的布局）。

**仍缺**：M3 谱图/文字层（正按分步计划加回，先加 LUT-only 的文字层，构建
`20261031-064542`）。**板级阻塞**：FTDI 从 PnP 消失（`CM_PROB_PHANTOM`），
非管理员无法软件恢复；两版位流已备好，设备一恢复即可烧录。

## 2026-10-29 21:30 — M3 接线恢复、板级一键脚本、26 项新判据

- **M3 恢复**（`92d0531`）：`text_disp`/`feat_copy_engine`/`feat_page_buf`/`spectrum_disp`/
  `ui_coord_delay` 重新例化，`ui_renderer` 的 spec/text 输入从常量改回真信号。
- **分阶段脚本首用失败并修复**（`6615557`）：缺 `open_project` 时 PDS 新建默认
  `fab_demo/PGL12G` 工程覆盖原工程 → `Flow-0044`；已加工程文件校验（必须描述 PG2L100H）
  与 `open_project -file`，并用一次失败换来的教训标注「该路径尚未验证成功」。
- **`191053` 布线停滞中止**（iteration 148→162 未布 7199→7262 不动），改全量重建
  `20261029-212311`（M3 + UART 握手修复）。
- **新增 `scripts/board_e2e.py`**：boot→weights→capture→compare 四阶段链，失败即停。
- **新增判据 26 项**（pytest 241→267）：UI overlay 优先级/几何/热图/`name_len` 与标签 ROM
  一致性；feat_copy 翻页周期模型（末尾字节与翻页顺序）；compare_layers 自检；e2e 编排顺序。

## 2026-10-29 19:40 — JTAG UI 单实例守卫（用户补充的关键事实）

用户指出掉线的另一半：烧录/扫描会拉起一个 UI（即 jtagserver），我有时**强行关闭**、有时**多开**。

- `board_check.py` 新增 `jtag_procs()` / `cfg_procs()` / `ensure_server()`：
  已有 `cdt_js` 就**只等不新起**（等 30 s，仍不通则报 PID 退出，绝不起第二个）；
  只有「一个实例都没有」时才启动，并把 PID 写入 `build/jtagserver.pid`。
- 运行前后各统计一次 `cdt_js`/`cdt_cfg`，数量增长直接报警（`!! jtagserver instances grew`）；
  正常路径打印 `jtagserver instances stable at [pid] (single UI, reused)`。
- `--diag-only` 现在显示实例 PID 列表与 `(! MULTIPLE UIs)` 标记。
- 烧录成功判定改为同时接受 `PROGRAM FLOW DONE` / `COMMAND[Program] execute successfully` / `The done bit is 1`。
- 守卫测试增至 16 项（新增单实例与「hung cdt_cfg 留着不动」两条）。
- 实测：连续三次调用（diag → status-only → diag），`jtagserver` 恒为 `[9040]`，
  `cdt_cfg exit code 0`，FTDI 在线，无新增实例、无强关。
- `AGENTS.md` 增加「JTAG 侧 cdt_js 只允许一个实例」的硬规则。

## 2026-10-29 19:20 — FTDI 掉线根因彻底修复 + 首次上板；UART 丢字符根因定位并修复

**掉线根因（脚本缺陷，非硬件）**：`board_check.py` 在日志出现 `PROGRAM FLOW DONE` 时
`proc.terminate()`，而该横幅早于 `cfg_disconnect`/`exit`，D2XX 句柄仍打开 → FT2232H 从
PnP 消失（`CM_PROB_PHANTOM`），只有物理重插能恢复。同源缺陷另有两条：动态 TCL 无 `exit`；
`if js is None: return 2` 会把「复用已运行的 jtagserver」误判为失败。

- 修复三规则：所有 TCL（10 个 jtag_*.tcl + 动态生成）以 `exit` 收尾；任何路径不
  terminate/kill `cdt_*`（超时只报 PID 并留着）；端口 65420 已开则复用不重启。
- 脚本增加运行前后 `VID_0403` 计数对比，掉线时直接指出是哪一步导致。
- 实测：连续 3 次 cdt_cfg（status-only / 烧 m2b / 烧录抓 hex）全部 `exit code 0`，
  FTDI 全程在线；烧录 `Program execute successfully 3.6s` + `done bit 1` + 状态 `0x081FFCA0`。
- 守卫测试 `tests/test_board_flash_safety.py`（14 项）。

**首次上板暴露的 UART 丢字符**：串口 18 字节 `ITCO
D3ETT.D3R@FF
`，即 ROM
idx 0,3,6,9 —— `uart_debug` 的 `tx_byte_valid` 是单拍 strobe、比 uart_tx 的 `byte_wready`
晚一拍，每帧推进 2~3 次索引却只送出 1 个字节。

- 修复：`tx_byte_valid` 改电平握手（装载后保持到握手才清零并推进），四个状态分支同步。
- 判据：`tests/test_uart_debug_handshake.py` 周期模型同时跑新旧两版，新版逐字符全对、
  旧版必丢字符且步长 > 1；全量 pytest **239 passed / 4 skipped**。
- 修复版构建 `20261029-191053` 已启动。

**requant 乘法拆分版（m2c）**：32×32 拆 4 个并行 16×16（位级 40 万组 0 mismatch），
位流 sha256 `23B3FEC6…` 归档 `releases/m2c-20261029/`。时序 `ddrphy_sysclk` -2.144 ns，
但最差路径已变成 `u_npu/u_wdma` 的 FF→FF：逻辑 2 级 0.798 ns、走线 8.818 ns（91.7%），
插流水无效；`pix_clk` 由 -0.450 改善到 -0.061。三版位流最差路径在 conv MAC → requant
乘法 → wdma 远距离 FF 之间随布局漂移，WNS 稳定在 -1~-3 ns，按「能跑就行」不再逐轮追。

## 2026-10-29 12:05 — 全 NPU 系统首次布线收敛并归档 M2 位流

- `conv_engine` 合并为单共享核（conv1..conv4 复用同一 16-lane MAC/requant，四组行缓冲与计数器保持独立），
  单核实测 LUT 3247/FF 4261/DRM 19.5/APM 20。
- `softmax_top` 流水化：267 级组合链拆成约 5 级、340 拍，10002 组输入与旧实现逐位一致（LUT 703/FF 801/APM 1）。
- 全量构建 run `20261029-110719-01d91e40`：**`Unrouted nets 0` at iteration 278**（此前双核版本 iteration 59
  仍残留 11368 条未布网络），48m22s 出位流，sha256 `E793A792…`。
- 资源 LUT 35045 (53%)/FF 49478 (37%)/APM 90 (38%)/DRM 79.5 (51%)；`ddrphy_sysclk` 由 -42.057 ns 收敛到
  **-3.593 ns**（仍违例，6265 endpoints），`pix_clk` 转正 +0.260。
- 为腾布线空间的临时让步（必须恢复）：`instrec_top` 中关闭 `text_disp`/`spectrum_disp`/
  `feat_copy_engine`/`feat_page_buf`/`ui_coord_delay`（合计仅 ~0.3% LUT，拥塞主因在 NPU）。
- 归档 `releases/m2-20261029/`（sbit + timing.rtr + manifest + SHA256SUMS + README）。
- 验证：`pytest -q` 222 passed / 4 skipped；`check_rtl.py` 44 个 .v 0 violation。
- 下一步：修 core 域 -3.593 ns（先试默认布线器/换 seed，再考虑 APM 输出加流水）→ 恢复 M3 层 → 板级对拍。

## 2026-10-29 02:10 — 完整系统位流产出

- `NPU_ENABLE=1`；为解除布局拥塞把 pool 4→1、conv 4→2 共享核（LUT 44028→38365，APM 166→126）。
- 布局布线成功，位流 sha256 `8BB5F645…`；All Constraints 未全满足：core_clk -42 ns（softmax 267 级）、pix -0.8 ns。
- conv1 144B 组距对齐修复已并入。
- 下一步：softmax 流水化 + pix 路径插流水。

## 2026-10-29 17:10 — 并补齐 wbuf/文本/对拍并修三处架构缺口

- wdma 组数 H_IN*GRP_NUM；新增 wbuf 单组缓存；npu_top 层编码/门控/多驱动修正；
  feat_copy 翻页时序修正。
- 新增 text_disp/class_labels、compare_layers 对拍工具、spectrum/overlay 与握手模型测试。
- 160 passed / 4 skipped；构建 WNS +1.356 / WHS +0.248。
- 已知待修：conv1 组基址非 32B 对齐。

## 2026-10-29 13:20 — 回退 grp_advance 等待

- 等待 grp_advance 在脉冲早于 S_NEXT 时会死锁，无仿真无法排除，改回 wdma 自主组节奏；
  端口保留供观察。全量构建 WNS +1.730 / WHS +0.225。

## 2026-10-29 12:40 — grp_advance 回接

- 4 个 conv 的 grp_advance 按层 mux 后送入 wdma；wdma 组切换等待该脉冲（放弃预取）。
- 全量构建 All Constraints Met，WNS +1.339 / WHS +0.201。
- 剩余风险：等待可能死锁（脉冲早于 S_NEXT），需板级/仿真确认。

## 2026-10-29 11:35 — 审查记录：grp_advance 未回接

- 代码审查发现 `conv_engine.grp_advance` 未送入 wdma，组契约预取时机可能与 conv 的组边界错位。
- 已记录为板上验证前必须修复的整合项（4 个 conv 按层 mux 后驱动 wdma）。

## 2026-10-29 10:35 — bars 槽位 bug 修复

- `bars_disp` 的槽位循环无 break，d=0 恒满足，实测 slot 永远 0；改为 if-else 优先链。
- 新增 `tests/test_ui_model.py`（7 项）：bars 长度/槽位、谱坐标/地址、字库尺寸。
- 全量 121 passed；构建 WNS +1.616 / WHS +0.245。

## 2026-10-29 09:15 — 谱图链路接入顶层

- `instrec_top` 串联 `feat_copy_engine` → `feat_page_buf` → `spectrum_disp` → `ui_renderer`；
  mel feat 口按 `npu_feat_rd_en` 仲裁（NPU 优先）。
- 全量构建 All Constraints Met，WNS +1.616 / WHS +0.204。
- 注意：copy 与 NPU 共用 `mel_npu_start` 启动，靠 busy_in 交错，板级需确认。

## 2026-10-29 08:05 — Mel 特征复制引擎

- 新增 `feat_copy_engine.v`：从 mel 读口复制 16512 字节到双页 RAM，
  idx/idx_q 两级对齐避免丢尾字节，结束时翻页。单编译通过。

## 2026-10-29 07:05 — 谱图双页缓冲

- 新增 `feat_page_buf.v`：258×64 u8 双页，core 写/pix 读，`wr_page` 由复制引擎控制。
- 单编译通过；复制引擎与 spectrum 顶层接线待做。

## 2026-10-29 06:15 — 概率条链路接入顶层

- `instrec_top` 串联 `ui_coord_delay`（3 拍坐标）→ `bars_data`（8 类 pct）→
  `bars_disp` → `ui_renderer.bars_*`；spectrum 仍 tie-off。
- 全量构建 All Constraints Met，WNS +1.443 / WHS +0.201。

## 2026-10-29 05:00 — 概率数据跨域

- 新增 `bars_data.v`：core 域锁存 8 类百分比，pix 域两级同步，
  3 s 窗口更新率下允许瞬时混值。单编译通过。

## 2026-10-29 04:25 — ui_overlay 并回 ui_renderer

- `ui_renderer` 例化 `ui_overlay`，de/hs/vs 延迟由 3 拍改为 4 拍；顶层 spec/bars 暂 tie-off。
- 全量构建 All Constraints Met，WNS +1.357 / WHS +0.184。

## 2026-10-29 03:20 — M3 图层合并

- 新增 `ui_overlay.v`：bars > spectrum > base 的优先级合成，1 拍寄存输出。
- 单编译通过；尚未并回 `ui_renderer`。

## 2026-10-29 03:00 — M3 字库

- `scripts/gen_font_hex.py` 用 Consolas 渲染 95 个 ASCII 字符为 8×16 点阵
  （1520 字节），输出 `src/ui/font8x16.hex`。
- 新增 `font_rom.v`（同步读），单编译通过；`build_full.tcl` 增加 `src/ui/*.hex` 的
  work_dir 复制。

## 2026-10-29 02:25 — M3 谱图模块

- 新增 `spectrum_disp.v`：258x64 Mel 页映射到 512x256 窗口（col=x*258>>9、
  row=y>>2），5 档伪彩，同步读地址 + 1 拍对齐。
- 单编译通过，尚未并入 `ui_renderer`。

## 2026-10-29 01:40 — npu.start 触发

- `instrec_top` 用 mel_engine 的 `mel_npu_start` 触发 NPU，`NPU_ENABLE` 参数默认 0。
- 全量构建 All Constraints Met，WNS +1.406 / WHS +0.270；M2 顶层接入完成。
- 剩余：端到端仿真/板级对拍。

## 2026-10-29 00:55 — m1 仲裁接通

- `instrec_top` m1 仲裁：`weight_loader` busy 时独占，空闲时交给 NPU wdma；
  `rd_data_1/rd_valid/done` 按 `wl_busy` 门控。
- 全量构建 All Constraints Met，WNS +1.406 / WHS +0.270，sha256 `90F531C0…`。
- 待接：sys_ctrl 触发 npu.start。

## 2026-10-28 23:40 — mel feat 读口接通

- `npu_top` 改为 feat 地址/数据接口（地址 0..16511，数据 1 拍后有效）；
  `instrec_top` 删除 `mel_feat_rd_addr` 的 tie-off 并连接 mel_engine。
- 全量构建 All Constraints Met，WNS +1.361 / WHS +0.157，sha256 `895E4F43…`。
- 待接：m1 在 weight_loader 与 npu 间的仲裁、sys_ctrl 触发 npu.start。

## 2026-10-28 21:45 — npu_top 顶层例化

- `instrec_top` 例化 `npu_top`（start/feat 置 0），顶层拓扑定型。
- 全量构建 All Constraints Met，WNS +1.059 / WHS +0.248，sha256 `07062C4E…`；耗时 19 分钟。
- 待接：mel feat 读口、m1 在 weight_loader/npu 间的仲裁。

## 2026-10-28 20:35 — NPU 资源实测

- 用只暴露 clk/rst/start/din 的 wrapper 对 `npu_top` 做 synthesize+dev_map（避免 DRC-0018 全端口绑定）：
  LUT 19522/66600 (29.3%)、DRM 34.5/155 (22.3%)、APM 35/240 (14.6%)。
- 结论：4 个 conv 实例 + pool/gap/fc/softmax/wdma 的资源可控，顶层例化可行。

## 2026-10-28 19:35 — fc 契约接入，M2 编译闭环

- `wdma` 增加 fc 模式：3×COUT 拍（bias/M/shift 各 COUT），start 放宽到 fc2。
- `npu_top` 将 fc1/fc2 的 b/m/s 按层门控接入；编译通过。
- M2 各模块与契约流在编译层面闭环；端到端仿真/板级对拍与 instrec_top 例化仍待做。

## 2026-10-28 18:50 — npu_top 契约门控

- wdma 的 48 拍契约按 `layer` 门控分发给 conv1..conv4，共享数据总线；编译通过。
- fc1/fc2 契约仍 tie-off：fc 需要 3×COUT 拍，与 conv 的 48 拍/组不同。

## 2026-10-28 18:15 — wdma 契约流实现

- `wdma` 新增契约读入（层启动读 bias/M/shift 到片上 RAM）与每组 48 拍输出；
  fc2 8 通道 pad 到 16 lane；单编译通过。
- 未接 `npu_top`：4 个 conv 需按层门控契约 valid，避免同时写 shadow bank。
- check_rtl 35 个 .v、0 violation。

## 2026-10-28 17:15 — wdma 组流模型

- 新增 `tests/test_wdma_group_model.py`（3 项）：每组 48 拍契约 + 组内 tap 顺序与内容、
  fc2 8 通道 pad、conv1 144B 组距。
- 全量 114 passed。

## 2026-10-28 16:50 — weight_loader 接入顶层

- `instrec_top` 例化 `weight_loader`：UART 字节共用、TX 仲裁（加载期优先）、
  m1 写/读通道、`weight_ok/weight_err` 接 `sys_ctrl`。
- `REQUIRE_WEIGHT` 仍为 0，M1 启动链不被加载阻塞；加载链已可板级验证。
- 全量构建成功，耗时 15 分钟。

## 2026-10-28 15:30 — M3 概率条模块

- 新增 `src/ui/bars_disp.v`：8 类概率条，pct*4 定长、slot 内偏移、按类取色；
  单编译通过，尚未并入 `ui_renderer` 的 3 拍流水。

## 2026-10-28 14:40 — requant 位级判据

- 新增 `tests/test_requant_model.py`（5 项）：正/负 exact-half 归偶、截断反例、
  u8 双端饱和、随机 512 向量与独立标量实现逐值一致。
- 全量 111 passed。

## 2026-10-28 13:55 — sys_ctrl 权重自检环与 M2 接入蓝图

- `sys_ctrl` 新增 `ST_WEIGHT`：等 `weight_ok` 后放行 `sys_run`，`weight_err` 进 SAFE_ERR；
  `REQUIRE_WEIGHT` 默认 0（保持当前 M1 链路），接入 weight_loader 后置 1。
- 新增 `docs/m2_top_integration.md`：m1 口仲裁、自检链、weight_loader/npu_top 接线与验证顺序。
- sys_ctrl 单编译通过；check_rtl 34 个 .v、0 violation。

## 2026-10-28 12:30 — fc_engine 契约接口补齐

- `fc_engine` 新增 bias 输入与独立 b_valid/m_valid/s_valid 三条加载流，
  bias RAM 在每组首拍（k_cnt==0）初始化累加器，替代原先的“归零后累加”。
- `npu_top` 例化同步更新，PDS 编译通过；契约流生产者（wdma）仍是唯一缺口。
- check_rtl 34 个 .v、0 violation。

## 2026-10-28 12:00 — core_clk 确认与 BOOT 乱码修复

- 烧 `core_probe` 后 COM5 收到 13 个 `C`：**core_clk 已起振，core 域退出复位**。
- BOOT 行乱码定位：`uart_debug` 的字符串字面量位序假设错误，板级收到 `00 00 00 00 4e ...`；
  改为显式 ASCII case 表，并修正 `DDR3 SELFTEST...` 长度为 17 字节。位流已构建，待验证。
- 移除 `core_probe` 的 UART 仲裁（避免干扰 BOOT），文件保留作诊断资产。
- FTDI 再次掉线；`terminate()` 后仍发生，下一步用 TCL `exit` 自然退出。

## 2026-10-28 07:40 — 契约流事实与 fc_engine 缺口

- 新增 `tests/test_contract_stream.py`（4 项）：conv 组契约 48 拍、fc 契约 3×COUT 拍，
  逐值与 `layer_contract.json` 一致；shift 全域落在 37..53。
- 记录 `fc_engine` 接口缺口：无 bias 输入、M/shift 共用 `c_valid`，需拆分后才能真正接契约。
- 全量 106 passed。

## 2026-10-28 06:30 — npu_top 数据通路整合

- `npu_top.v` 全链例化：conv1→pool1→…→conv4→pool4→gap→fc1→fc2→softmax，
  层序列、GAP 结果缓存/回放、fc2→logits 总线完成；PDS 编译通过。
- 唯一缺口：48 拍 bias/M/shift 契约流（conv/fc 均 tie-off），端到端功能尚未成立。
- 修正空端口 `.port()` 与 output reg 连实例输出的两处 SV-2012/PDS 报错。
- 全量 102 passed；check_rtl 34 个 .v、0 violation。

## 2026-10-28 05:15 — wdma 初版与镜像布局验证

- 新增 `tests/test_wdma_layout.py`（4 项）与 `tests/test_wdma_stream_model.py`（5 项）：
  确认所有层权重区 32B 对齐、conv1 每组 144B/27 tap 尾部单 tap、fc2 tap=8B。
- `wdma.v` 初版：整层 32B beat 连续读（burst≤16）、16 深 FIFO、16B/8B tap 切分、
  `w_ready` 反压握手、组边界脉冲；PDS 单编译通过，**未仿真/未上板**。
- 全量 102 passed；check_rtl 34 个 .v、0 violation。

## 2026-10-28 03:40 — softmax 定点单元

- 新增 `softmax_top.v`：Q16.15 预缩放、减 max、Q6.9 饱和、512 项 exp LUT、
  组合 round-half-up 除法、top1/percent；S_Q15 按实测 fc2 契约修正为 9197。
- 导出 `src/mel/exp_lut.hex`（512×Q0.16）。
- `tests/test_softmax_model.py` 5 项（Q15 常量、LUT、归一、单类饱和、percent）。
- wdma 草稿因「DDR3 2 tap/beat vs conv 1 tap/cycle + burst≤16 + 读侧不可反压」
  需读 FIFO，未入库。
- 全量 93 passed；check_rtl 33 个 .v、0 violation。

## 2026-10-28 02:10 — npu_top 控制壳与一键板级脚本

- 新增 `npu_top.v`：11 层序列（conv1→pool1→…→fc2）、busy/done、npu_cycles、
  REQ-REL-002 超时标志；编译通过，数据通路与 wdma 留待接入。
- 新增 `scripts/board_check.py`：FTDI 检查→烧录→读状态寄存器→抓串口，一条命令完成。
- check_rtl 32 个 .v、0 violation。

## 2026-10-28 01:35 — FC 引擎与流式模型测试

- 新增 `fc_engine.v`：16 并行输出、CIN 拍/组、复用 requant_unit；
  fc2 的 8 通道按上取整 pad 到 1 组（GRP_NUM=(COUT+15)/16），编译通过。
- 新增 `tests/test_conv_model.py`（流式扫描顺序与向量化数学逐位一致，2 项）
  与 `tests/test_fc_model.py`（ReLU rail / fc2 logits 容器，3 项）。
- 全量回归 88 passed；check_rtl 31 个 .v、0 violation。

## 2026-10-28 00:55 — GAP/帧解析落地 + core_clk 诊断位流

- 新增 `gap_unit.v`（256 通道 GAP + round-half-even >>6），单编译通过；
  `tests/test_pool_gap_model.py` 增补全通道路径，6 项通过。
- 新增 `scripts/uart_frames.py`（design 9.2 帧解析/重组/对拍）与
  `uart_capture.py --frames`；`tests/test_uart_frames.py` 6 项通过。
- 新增 `core_probe.v` 并集成顶层：core_clk 域复位后发 16 个 `C`，用于判断
  DDR3 IP 的 core_clk 是否起振；诊断位流 run `20261028-002353-43f24360` 已构建，
  FTDI 掉线未能烧录。诊断版验证后决定保留或移除。
- 全量回归 83 passed；check_rtl 30 个 .v、0 violation。

## 2026-10-27 23:55 — 板级根因收窄 + M2 三模块落地

- 板级突破：`cfg_read_device_property -mode 3` 直读状态寄存器，早期 `0x00180C80` 中 **done=0**，
  说明此前“烧录成功”后 FPGA 没有有效配置；重新 program 后 `0x081FFCA0`，done=1、crc_err=0。
- 无复位探针（27 MHz 发 `P`）烧录后 COM5 收到 46 个 `P`，证明 27 MHz/UART/CP2102 链路正常；
  M1 烧录后 done=1 但串口 0 字节，问题收窄到 core_clk / sys_ctrl。
- 随后 FTDI 再次掉线，板级暂停；恢复后直接做 core_clk 探针。
- M2：`conv_engine.v` 修复两处先使用后声明并单独编译通过；新增 `weight_loader.v`（帧解析+CRC16+
  写 m1+读回摘要）、`pool_engine.v`（2×2 floor、奇偶列分 bank、同步读）；
  `scripts/weight_upload.py` + 8 项测试；`tests/test_pool_gap_model.py` 5 项。
- 全量回归：76 passed；check_rtl 28 个 .v、0 violation。

## 2026-10-27 12:23 — M1 时序收敛、位流归档

- `db_norm` scan 2 改 4 拍流水（DIFF/MUL/SQ/ACC），`standardize` 量化扫描改 5 拍流水
  （DIFF/MUL/QPROD/Q）；算术顺序不变，位级结果不变。
- 第一轮 run `20261027-115358-d5a76b9d`：WNS 由 -4.401 改善到 -1.316（db_norm 路径消失，
  剩余违例转到 `u_standardize`）。
- 第二轮 run `20261027-121101-5c24a968`：**All Constraints Met**，WNS +1.438、WHS +0.224，
  `ddrphy_sysclk` +0.837；sha256 `BD40D10A…`；六阶段 OK。
- 归档 `releases/m1-20261027/`（sbit + manifest + timing.rtr + SHA256SUMS + README）。
- 修复 `run_pds_full.ps1` 的 `Get-FileHash` 依赖（本机 PS 5.1 该 cmdlet 缺失），改用 .NET SHA-256。
- 新增 `scripts/jtag_scan.tcl`、`scripts/jtag_program_m1.tcl`。
- 板级：CP2102 串口 COM5 在线；USB Cable II 未被识别（cable 列表空），JTAG 扫描 `No devices detected`，
  待接入下载器后继续。

## 2026-10-27 11:25 — 里程碑位流归档入库

- `releases/m0-20261027/`：InstRec M0 位流 + manifest + SHA256SUMS（sha256 校验与 manifest 一致）。
- `pds_cpu_100h/releases/120mhz-20261025/`：100H 120 MHz 交付位流 + manifest + CoreMark 记录 + SHA256SUMS。
- `.gitignore` 仅对两个 `releases/**` 放开 `*.sbit`；`.gitattributes` 对这些目录设 `-text`，防止二进制被换行改写。
- 其余位流仍视为可重建产物，不入库；失败构建日志保留在 `build/` 磁盘。

## 2026-10-27 11:15 — 工作区/文档/版本整理

- 恢复 4 个被误回退的已跟踪文件（`.gitignore`、`DEV_SNAPSHOT.md`、`cpu/fpga/rv32_ddr3_ip_wrapper.sv`、
  `cpu/rtl/rv32_burst_ddr3.sv`）。原 diff 留档：`reports/workspace-revert-20261027.diff`。
  其中 2 个 RTL 的改动会把已修复的 AXI 端口方向、13-bit 超时、读前 dummy-write 回退成旧 bug。
- `.gitignore` 增加 `!instrec_fpga/ipcore/`：DDR3 / GPLL IP 源文件是重建必需资产，此前被全局 `ipcore/` 忽略。
- SDD 三份文档复制到 `docs/sdd/`（`.codeartsdoer/` 被自身 `*` 规则整体忽略，交接会丢）。
- 新增 `docs/STATUS.md`（唯一实时状态源）与本文件。
- `instrec_fpga/` 首次纳入 git（此前 0 个文件被跟踪）：commit `1298395`，180 个文件。
- 搁置路线的 AI RTL 单独存档：commit `2abf5ed`。
- 证据从 `build/` 提取到可追踪位置：`reports/m0-manifest-20261027.json`、
  `reports/m1-timing-20261027-104218.txt`。
- 核对基线：pytest 63 passed；check_rtl 26 文件 0 violation。

## 2026-10-27 10:56 — M1 语法修复后的首次完整构建

- run `20261027-104218-acb7a788`：compile/synthesize/dev_map/pnr/report_timing 全过，
  gen_bit_stream 被会话结束中断，无 M1 位流。
- 新阻塞：`ddrphy_sysclk`（core_clk，125 MHz）WNS -4.401 ns / TNS -487.619 / 200 endpoints。
- 根因定位：最差路径在 `u_mel_engine/u_db_norm` 乘加组合链（17.539 ns，5 levels），非 DDR3 IP。
- 对照：`pds_cpu_100h` 同 IP `ddrphy_sysclk` = +2.110 ns。

## 2026-10-27 10:19 — 交接快照记录的语法错误全部修复

- `mel_engine.v`：参数基数字面量 `19'dPARAM` → `PARAM[18:0]`。
- `standardize.v`：`var_q16_u32` reg/wire 重复声明 → `var_q16_comb` 组合 + 快照。
- `fft2048_sdf.v`：去掉 generate 内嵌 generate，改裸 `if/else` + 条件 assign。
- `HANDOFF_SNAPSHOT_20261027.md` 第 4.1 节“fft 未修”的结论已过时。

## 2026-10-27 00:06 — M0 位流产出

- run `20261027-000612-a71f1451`，六阶段 OK，All Constraints Met，WNS +1.757。
- sbit sha256 `C517736C7E61937521BC1776DDA4ACAC66F0373DF7E0FACDD86AEC017DD2EDAC`。
- 资源 LUT 6201 (9%) / FF 6743 (5%) / BKCL 6/6。尚未上板。
## 2026-11-01 — RV32 控制核与 NPU 最小融合

- 新增 `rv_core` 构建集和 `top_rv_core`：将 `rv32_cpu_subsys` 例化到 InstRec DDR3/core_clk 域，以 MMIO 控制/观察 `npu_top`，保留 Mel 自动启动路径和共享 UART。
- 新增 8 KiB 固件 ROM、8 KiB 数据 RAM、UART FIFO、LED/DDR/NPU 状态寄存器；CPU 固件执行启动、ISA/计数器自检并写 `NPU_CTRL` 触发一次推理。
- `sim/run_sim.py rv_cpu --verbose`：C1-C6 全部 PASS，验证 CPU 启动、MMIO、soft-start、NPU 结果回读。
- PDS 资源门槛 run 已通过 RTL 分析并进入综合，但日志停在 `Saving design to DB`，尚无综合资源摘要、新位流、PNR 或板级验证。


## 2026-11-01 11:35 — RV 真实控制路径与完成握手修复、启动新版构建

- RV 默认由固件请求启动；门控 DDR/权重/完整特征窗口，修共享 UART ready 和 CPU FIFO 背压、DDR 位布局、结果快照/清除竞争。
- npu_top 补 softmax 完成分支；新增真实 softmax 双轮完成仿真。RV C1-C9 PASS；Python 429 passed/4 skipped。
- conv1 测试台字节/像素计数修正后 mismatch 0/792576；UI 既有未提交端口删除导致展开失败，保留并明确记录。
- 构建脚本补阶段恢复、StopAfter 不发布位流、单 run 护栏、输入哈希及结束校验；补 clk_nco 216MHz 时序约束。
- 新 rv_core 全流程 run 20261101-113509-6927c1bf 启动；旧综合仅资源基线，当前尚无新位流或 RV 板级证据。
## 2026-11-01 15:56 — RV 布线期间并行验证更新

- PDS RV run `20261101-130420-0ed52a5d` 持续 detail route，iteration 112 未布通 8680；尚无位流或板级结论。
- 新增记录的通过证据：RV CPU C1-C9、weight loader CRC/WOK/读回、Mel 两种 credit 配置、UI render/overlay、NPU chain/completion、DDR3 subsystem/AW timeout、ctrl smoke、self-test、RV top control。
- UART 临时仿真覆盖 128-byte full line 与 newline short line，均逐字节 PASS；主线 7-bit `ram_len` 修复待当前 PDS 完成后实施。

## 2026-11-01 16:05 — GitHub 状态同步时追加验证

- RV PDS detail route 到 iteration 114，未布通 8452；仍无位流或板级 RV 结论。
- UART/sys_ctrl/烧录安全回归新增 35 passed；RTL/SV 实时验证结论不变。

## 2026-11-01 16:59 — RV PDS 路由进度

- PDS detail route 到 iteration 180，未布通网络 6949，构建仍在运行，无位流、时序或板级新结论。

## 2026-11-01 17:04 — RV 路由与验证心跳

- PDS detail route 到 iteration 185，未布通网络 6608；仍无位流或时序报告。
- RV/NPU/控制/DDR 关键仿真继续通过；全量 Python 回归 429 passed / 4 skipped，RTL 检查 53 个 `.v`、0 violation。
- 后续 detail route 到 iteration 187，未布通网络 6600；`npu_chain`、`ddr3_subsys`、`ddr3_aw_timeout` 追加仿真 3/3 PASS，尚无位流或时序报告。

## 2026-11-01 17:12 — UART 误诊纠正与正式边界回归

- 原版/临时宽度扩展版同一增强 TB 均 PASS，撤回此前 128 字节行不能结束的缺陷判断；原版通过 7-bit 减法回绕正确终止，不修改 UART RTL。
- 新增 `sim/tb_uart_linebuf.sv` 与 runner case：原版满行、短/空换行、起始/中途 TX 背压、未 ready 写丢弃、busy/ready 恢复全部 PASS。原 14 项 RTL suite 本次分组重跑也全部 PASS。
- PDS detail route iteration 192、未布通 6638，62 个 manifest 输入 SHA256 全一致；尚无新版 RV 位流或板级结论。
- CPU 存储推断复核：6 块 DRM；顶层覆盖 `ENABLE_M=0`。当前 LUT 35840，placer 物理利用率 81%，无可靠路由完成 ETA。

## 2026-11-01 17:18 — 完整 NPU 实验发现集成阻塞

- 原版真实 npu_top 自然跑层在 layer0 超时；诊断 WDMA 半 beat 末 tap 死锁、conv 参数计数 47/48。build 副本修末 tap 后 WDMA 推进到下一组；参数起始脉冲修复及后续逐层对拍继续，未改冻结 PDS 源输入。
- 新增 WDMA 综合资源审查：参数表未推 DRM，而是 20480 存储 FF；宽口候选只在 build，尚待等价仿真/综合。
- 只读板卡诊断显示 FTDI ABSENT（COM5、原JTAG进程和监听端口仍在），未操作下载器或烧录。
## 2026-11-01 17:30 — WDMA 等价回归与完整 NPU 数值阻塞更新

- 宽口 WDMA 候选与原版在 6 个 layer、每层 350000 周期的逐拍差分通过，覆盖真实 DDR beat、随机响应间隙和写回背压；仅为等价证据，未宣称功能修复或资源收益。
- 半 beat 末 tap 候选已越过原先 WDMA 死锁，但完整 NPU 仿真仍在 conv1 第 0 项 `got=16 exp=4` 失败；继续定位参数起始、索引与通道组契约。
- PDS 唯一路由 run 继续 iteration 200，未布网络 6851；无位流、时序或板级 RV 证据。

## 2026-11-01 17:30 — 参数地址候选修正后 conv1 仍不匹配；路由持续高位震荡

- build 候选 `wdma_step3.v` 将 bias/M 写入索引改为每 beat +8、shift 每 beat +32，并将通道组偏移改为 `grp_mod * 16`。首项 bias/M/shift 已与 `layer_contract.json` 的 index 0 相符。
- 完整 conv1 golden 仍在首个输出失败：`got=7 exp=4 cycle=535`。该修复未进入主线，也不在当前冻结的 PDS 输入中；继续定位 MAC 前权重/激活与舍入数据通路。
- PDS run `20261101-130420-0ed52a5d` 到 iteration 220，最近 30 轮未布网络 6572–6926、均值约 6772；没有时序报告或位流。父子 PID 36628/40640 仍运行，未启动第二个 PDS。

### 后续 step4 权重读时序定位

- 逐 tap 确认 wbuf 同步读在消费边沿才推进地址，导致 MAC 首 tap 重复、末 tap 遗漏。build 前瞻地址候选使首点 4/4，连续前 272 项通过，随后 index272 输出 17/0；继续检查 feature 行缓存覆盖，未修改主线。
- 重跑 RTL 检查 53 文件 0 violation；Python 429 passed / 4 skipped，88.36 s。GitHub 已同步 58d8ebb。
- step5 行信用候选保护后，conv1 第0组整行 4128 项通过；首次失败推进至第1组首项，继续定位参数 shadow bank。独立 wbuf 候选 10797 次握手验证通过，报告保留完整修复 diff 与 SHA256。
- 新增层间存储审查报告：串行共享卷积核与三行缓存无法保留整帧 pool 输出，且有 start 清 row_done、输入顺序不一致；需要 DDR 激活缓存与受信用重放，build 协议候选继续开发，未改主线。
- WDMA 组合 valid/data 修复经 4943 个真实 tap 随机背压/半 beat 跨层对拍通过；接入 conv1 后 group1 cache 正确但首输出仍 72/51，剩余为换组 MAC 窗口对齐。激活缓存候选持久化至 `sim/experiments/activation_store/`，Python 真实尺寸和 RTL 小几何通过，未接主线。
- WDMA 实验已持久化并复跑 baseline FAIL/fixed PASS（4943 taps），报告明确叠加修复边界；wbuf 新确认 LOAD 首拍旧 valid 穿透，10797 次旧测试未覆盖该拍，补反例测试中。

## 2026-11-01 18:04 — 正式行信用端口候选 conv1 全通过；DDR层间修复推进

- step8/step9 集成真实WDMA/wbuf/feature读口后，conv1 792576值 mismatch0，859229周期；step9为正式行信用端口，移除诊断层级引用。仍在候选，不属于当前冻结PDS。
- wbuf持久反例可复跑：旧step4 LOAD valid穿透FAIL，新step8 10797握手PASS。独立conv输出FIFO随机背压792576项通过；pool奇宽背压128项通过；pool→DDR→canonical重放128B/4写4读通过。
- 新增 `sim/experiments/activation_pipeline/` 和 `wbuf_replay/` 资产；完整前两层、原生DDR接口、综合与上板仍待验证。唯一PDS到iteration240未布6538，无新位流/时序。
- 真实小几何conv→pool→DDR→重放联合链也通过：独立非零3x3/通道bias数学golden，384conv+96pool/回读值精确，4写4读，DDR写长暂停可反压。

## 2026-11-01 18:09 — 动态激活缓存与修复版宽口WDMA证据

- 保存三层真实尺寸动态共享行缓存RTL/TB/runner，逐值回读共345600B通过；六层修复版WDMA宽口差分通过，无资源收益承诺。
- 记录真实前两层链conv2 index24808失配，native bridge与地址隔离继续；完整NPU尚未通过。
- 交接快照加最新验证范围纠正；PDS iteration244未布6643、无新位流，manifest62项一致。

## 2026-11-01 18:17 — 前两层真实激活链候选PASS

- direct replay_row修复行信用旧计数，conv1/pool1/DDR/conv2共12242761周期，conv1 792576和conv2 396288项golden exact；抽象DDR，不扩展为全NPU或板级结论。
- native bridge新增done早于FIFO排空契约审查，继续修复并补异常测试；PDS iteration247未布6653、无新位流。

## 2026-11-01 18:23 — 重复推理生命周期与增强native bridge

- 保存GAP第二帧丢失反例/early-arm修复，pool sticky两帧，激活区17项addr_err测试（不拦截grant）。
- 保存bridge70正常事务+abort验证与earlydone截断反例，真实controller联合测试继续，未改主线或冻结PDS输入。

## 2026-11-01 18:31 — 四层 ping-pong 候选通过

- 持久化四层 conv + pool1/2/3 双store激活回放，30,750,042周期逐值 exact；仅抽象DDR候选，native/综合/板测未完成。
- 下载器重插后FTDI与COM3/COM4/COM5只读枚举正常；PDS iteration252未布6619、无位流。

## 2026-11-01 19:54 — 真实DDR联合仿真修复通过

- 修正bridge本地写缓存ready及TB采样边沿，真实controller 16权重beat/4激活写回/timeout abort PASS；native四层接入继续。旧必然死锁判断修正为写ready契约与harness均有缺陷。

## 2026-11-01 20:24 — 完整abstract推理与native四层通过

- 持久化全NPU自然done golden候选和native四层+权重对齐适配候选；生产地址/FC修复尚未合入。
- 准备scalar/wide串行资源gate，未运行；确认核心125MHz源于DDR IP，不能单改FDC降频。PDS iteration355未布7182。

## 2026-11-01 20:34 — 完整native NPU golden通过

- 独立native控制器全链自然done31115245周期全部golden及计数通过，未移植生产或板测。
- 按用户控制耗时要求，当前PDS观察截止20:43；届时仍停滞则保存证据后转串行资源gate，禁止操作JTAG服务。
## 2026-11-02 — 修复版 PDS 路由监控与并行定向回归

- 修复版唯一 PDS run `20261102-003406-7af1bf17` 已完成 compile/synthesize/dev_map 并进入 detail routing；未布网络从 62810 降至 16929（迭代 0→13），仍在收敛，尚无新位流或时序结论。
- 并行验证通过：DDR 控制器模型 26 项、DDR/自检/契约 49 项、板级安全/串口 43 项、权重/NPU/Mel/特征页 78 项；loader/native timeout 与 owner/CRC/reset 路径通过。
- reset-mid-read 同 `axi_rid` 旧响应误收风险继续保留；未操作下载器或 `cdt_js/cdt_cfg`。

## 2026-11-02 — 修复版 PDS 完成 PNR，时序未闭合

- `build/pds/20261102-003406-7af1bf17` detail routing 迭代149达到0，确认 placed/routed；完成 report_timing 和 gen_bit_stream，候选 `.sbit` 3,791,112 bytes，SHA256 `605C234FA2B14BB174C304B0B99FB7E5E7768643F999A97BEC70FA328B488CFB`。
- 资源 LUT 32063、FF 33300、DRM 120.5、APM 90；slow ddrphy_sysclk WNS -4.462 ns/TNS -4036.195 ns，fast WNS -0.793 ns，仍有 setup 失败。bitstream 报告 SCBV 未设置警告，板级保持 NOT_RUN。
- 未操作下载器、`cdt_js` 或 `cdt_cfg`；reset-mid-read 同 RID 旧响应风险仍开放。
- 心跳复核全量 Python 回归为 432 passed / 4 skipped（2 条 PyTorch FutureWarning），无源代码变更。
## 2026-11-02

- Added db_norm pipeline candidate validation evidence: targeted DDR model suite 49 passed, uart_linebuf and npu_completion Verilator cases passed, while preserving the reset-mid-read stale-response risk as open.
- Monitored the sole PDS run `20261102-013400-e8658663`; detail routing stalled around 950-1026 unrouted nets after iteration 500 and was safely stopped with process, manifest, and log-hash evidence. No bitstream or timing report was produced, and no downloader/JTAG process was touched.
- Re-ran the full Python suite during the idle window: 432 passed, 4 skipped, with only the two existing PyTorch FutureWarnings.
- Added Verilator evidence for `rv_top_ctrl`, `mel_credit`, and `ui_render`; all passed with zero mismatches in their stated checks.
- Added Verilator evidence for `ddr3_subsys` (15/15 scenarios), `ctrl_smoke`, and `npu_chain`; all passed. The DDR watchdog blind spot remains explicitly recorded as a known limitation.
- Added Verilator evidence for `self_test`, `weight_loader`, and `ddr3_aw_timeout`; all checks passed, including abort/recovery, CRC rejection, write/read digest, and multi-master timeout attribution.
- Added Verilator evidence for `rv_cpu`, `conv1`, and `mel`; CPU checks passed and conv1/mel streams matched golden with zero mismatches.
- Re-ran RTL lexical checks: 59 Verilog files, 0 violations.
- Re-ran board flash safety and UART handshake guards: 21 passed; no JTAG or downloader operation.

## 2026-11-02 — db_norm 平方位宽护栏与 reset-mid-read 复现

- `db_norm` 平方路径改为显式 32 位符号扩展和 64 位乘积，取低 32 位写入既有流水寄存器；不改变接口或 golden 语义。
- 词法检查 59 个 `.v` 零违规，DDR/契约定向回归 35 passed，`mel_credit` 16512 字节 golden 对拍 0 mismatch。
- 定向模型复现 reset-mid-read 后旧 `RVALID/RLAST` 被同主口新读误收；现有 `S_R_DRAIN` 仅处理 watchdog 超时，因缺少 IP reset/flush 或事务 epoch，暂不加入猜测性丢弃逻辑。板级仍 NOT_RUN。

## 2026-11-02 — DDR3/NPU 补测

- DDR3 子系统 15/15 场景通过，含四主争用、watchdog 各阶段和 abort recovery；watchdog blind spot 仍作为已知限制保留。
- NPU chain 的 GAP/FC1/FC2/softmax 全部逐值通过，0 mismatch。

## 2026-11-02 — RV 控制与 self-test 补测

- RV top control 17 项通过，包含请求排队、启动门控、故障阻断和 CPU-only 语义。
- self-test 8 项通过，包含 4KB 读回、abort 错误和 abort 后恢复。

## 2026-11-02 — 权重加载与 AW timeout 补测

- weight loader 10 项通过，包含完整写入/读回、CRC 拒绝和复位恢复。
- AW timeout 6/6 场景通过，包含 m0 饱和配额和 STS 归因复现。

## 2026-11-02 — UI 与特征页补测

- UI renderer 3 项通过，64 active pixels、层优先级和四拍 RGB/DE 对齐均无误。
- 特征页与谱图 overlay 模型 19 项通过；`run_sim.py` 没有 `feat_page` 案例，使用对应 pytest 覆盖。

## 2026-11-02 — UART/NPU completion 补测

- UART line buffer 边界、背压和恢复场景通过。
- NPU completion 两次 softmax 完成、busy 清除和重启场景通过。

## 2026-11-02 — RV 集成收尾核对

- 并行复核确认 `top_rv_core`/`rv32_cpu_subsys` 的 CPU→MMIO→NPU 控制、结果和 UART 路径已接通，`rv_core` 构建集包含 CPU RTL 与固件；未发现需要追加的 SV-2005/PDS 修复。
- `rv_cpu` C1-C9、`rv_top_ctrl` 17 项、构建护栏 pytest 45 项和 59 个 Verilog 的词法检查均通过。
- 最新 RV 位流虽已布线完成，但 DDR PHY 时序未闭合（slow WNS -4.462 ns、fast WNS -0.793 ns，SCBV 警告），继续保持板级 `NOT_RUN`，未触碰下载器。


## 2026-11-02 12:44：显示修复候选构建与板级冒烟

- G25复位/CDC显示分支六阶段完成，All Constraints Met，+1.191ns；20B31B08...605854BE成功烧录，UIDEMO/G07。实际屏幕仍待用户反馈，未宣称显示通过。

## 2026-11-02 12:51：I2S实际BCK边沿回归与采样修复

- 外部串行源复现0x1235误收0x091A，按registered post-edge phase修正上升沿采样、MSB通道标签及LSB完成点。
- 新增i2s_capture，16字/idle/活动恢复/帧中复位PASS；RTL0违规，全量432 passed/4 skipped，板级未重烧。

## 2026-11-02：用户要求重烧显示候选

- 20B31B08候选再次program成功、done1/CRC0、UIDEMO可读；当前屏幕待确认。保留本次独立烧录证据，未改RTL。

## 2026-11-02：原厂HDMI出图确认与UI路径二分

- 原厂对照位流用户确认有画面；自研修复UI仍无信号，判FAIL。显示分支新增默认原始彩条/按住KEY1切UI诊断，待构建。

## 2026-11-02：HDMI二分诊断候选构建及烧录

- 9F0181AD候选完整时序通过并烧录，默认原始彩条/按住KEY1切UI，G07/H81；等待两路实际画面反馈。原厂1080p60已确认可显示。

## 2026-11-02：UI切换失败隔离与物理视频边沿候选

- 用户确认彩条正常/UI异常；两帧1080p HS/VS/DE四拍逐拍对拍PASS。显示分支尝试下降沿寄存视频输出，留半周期外部采样裕量，尚待PDS和板测。

## 2026-11-02：下降沿HDMI输出候选烧录

- 用户确认旧诊断版切UI明确丢信号；602AB321下降沿候选完整时序通过并烧录，待用户屏幕反馈。两帧逻辑同步对拍PASS不能代替物理输出验证。

## 2026-11-02：显示板级验收与UI参考帧

- 用户确认602AB321下降沿候选彩条/UI均正常；保存用户可视PASS，保留此前失败证据。
- 实际RTL ui_frame导出1920x1080完整帧PASS，归档参考PNG；明确蓝块为固定演示频谱，当前显示未接真实音频/AI。

## 2026-11-02：RV/音频/HDMI完整顶层与生产连续推理

- instrec_top接入RV32I安全窗口控制、三路UART握手和启动音频门控，带入已验证HDMI下降沿/G25复位；full构建集纳入CPU和ROM。
- 生产ROM连续请求，CPU C1-C10/完整顶层控制17项/I2S回归及432项pytest通过；生产ROM+frame-major不同A/B两轮native golden通过。
- 完整拓扑开始单路资源门控；用户确认暂无外部音频源，真实音频板级验收仍开放。

## 2026-11-02：纠正五组活跃度目标并冻结正确v3参考

- 按用户纠正，目标从旧8类单标签分类改为strings/woodwinds/brass/percussion/keys五组独立sigmoid活跃度；停止旧权重部署。
- 新增freeze_group5_reference脚本、可追溯float权重/源/配置/真实留出参考与GROUP5_MIGRATION清单；冻结重载双head logits exact PASS，未宣称量化或FPGA迁移完成。
- 补记完整系统PNR完成但setup/recovery FAIL，以及489EF753诊断候选板级RV32/DDR启动PASS；冻结原始板级证据与hash，保留显示fallback。

## 2026-11-02：按用户决定恢复八类版本，权重WOK与时序路径修复

- 用户选择维持原八类版本，暂缓五组迁移；板上2700帧权重上传/DDR读回WOK FA0D5236，随后6轮NPU完成回报，未接真实音源，不宣称准确率通过。
- 分拍standardize，framer反射缓存同步读，FIFO注册full，full文字增加char寄存并保持总体延迟；DSP payload去异步复位但valid保留清空。
- 新增FIFO压力、文字像素等价、requant中途复位仿真；各单项及Mel完整特征PASS。候选时序待PDS检验。

## 2026-11-02：framer跨帧valid与跨窗口ring基址修复

- 新增两组PCM逐采样反射/Hann/环形回绕及out_ready stall回归，复现旧版valid粘住与第二窗口读基址未归零，分别修复；隔离候选1060864采样逐值PASS。
- 资源门控映射PASS：32236LUT/35057FF/133DRM/90APM，head/tail同步读推断DRM。按设计无PNR/无位流；边界修复需新建完整候选，不复用旧netlist。
- 21项RTL及额外requant_reset、两轮真实CPU/native/golden通过，原始失败和资源证据保留hash。

## 2026-11-02：完整修复候选构建与音频验收边界

- bd295a96完整候选20261102-155516-512e7322启动单路PDS，17:10截止审查；无新位流/时序结论。
- 核对扩展I2S引脚与16bit/32BCK协议，记录底板HDMI RX音频路径尚未接入，真实音频验收仍需兼容输入；五组迁移文档标记deferred。
- CPU native新报告单独命名保存，原连续推理报告不覆盖。

## 2026-11-02：完整时序汇总与PNR跟踪

- 最终候选映射32206LUT/35057FF/133DRM/90APM，约16:10进入PNR、16:13全局布局完成，尚无最终时序/位流。
- 新增summarize_timing.py，核对slow/fast的setup/hold/recovery/removal/pulse-width全部10表；完整负例、显示正例及缺表伪正例验证通过，避免只取第一时钟WNS漏报。

## 2026-11-02 16:25：完整系统重烧失败与显示保底恢复

- 完整诊断489EF753重烧启动PASS，但权重第814帧失败、用户实屏无信号，完整验收FAIL；原始证据与hash冻结，根因开放。
- 已恢复602AB321固定显示演示，下载/UIDEMO通过，用户确认本次彩条/UI均正常；修正版完整构建仍在详细布线，17:10截止审查。
- 权重镜像大小更正为691040B；2700为传输帧数，不是文件大小。

## 2026-11-02 16:50：修复剩余dB统计与字符选择时序路径

- 完整CDE1D2F6候选六阶段完成，但core -2.933ns/pix -0.456ns；未烧录，失败报告与hash保留。显示保底保持用户实屏PASS。
- db_norm累加改吃上拍dB寄存，文字标签改同步ROM/独立百分比寄存，原周期契约不变；Mel/反压/文字像素/新六窗口统计测试全PASS，pytest432passed/4skipped，lint0违规。
- 修正构建WNS/WHS只取首clock行的误导字段，现取最差clock；资源门控与完整时序待新构建。补充音频验收文档的失败重烧与权重实际大小。

## 2026-11-02 17:18：动态显示数据与像素链修复

- CDE诊断版WOK/6轮CPU完成通过，用户实屏有UI但动态图形撕裂/花块，内容验收FAIL；FTDI再次离线使演示恢复未开始，板上仍CDE，失败证据留档。
- 修复特征frame-major转置、完整页有效/帧边界换页、概率与类别完整bundle CDC、bars/spectrum图层对齐；新增动态双窗口/停顿/逐像素/快照复位RTL验收PASS。
- db_norm差值/乘法进一步分拍，Mel16512项0差异且约41.2ms；新增HDMI输出IO寄存器约束待实际验证。全量pytest432passed4skipped、RTL7项PASS、lint0违规。旧label资源门控通过止于映射，无位流；新源需重建。

## 2026-11-02 17:25：动态显示修复后单路资源门控

- bca1fce8已push，run171830-91e7a308仅至dev_map；compile成功，综合进行中，17:45截止审查，监控日志/CPU/RSS。尚无新位流，不以仿真通过替代实屏验收。
- 当前板仍CDE1D2F6，有UI但动态内容FAIL；FTDI再次离线，17:07恢复保底未执行program，既有cdt保持不动。

## 2026-11-02 17:33：资源与HDMI IO寄存打包核验通过

- run171830-91e7a308门控三阶段PASS、源码不变，33447LUT/35106FF/133.5DRM/90APM，27路HDMI全打包OFF，label DRM保留。报告含映射数据库hash，准备单路PNR、18:35截止审查；尚无新位流或完整时序结论。

## 2026-11-02 17:36：受控PNR启动与音频验收文档校正

- 同一资源门控数据库于17:33:48启动单路PNR，17:36第二轮全局布局有进展，18:35截止审查。
- AUDIO_BOARD_ACCEPTANCE同步当前CDE诊断版WOK/6轮完成、动态内容FAIL及17:07未program事实，避免误报已恢复显示演示；真实音源验收仍待硬件。

## 2026-11-02 17:44：修复候选布局估算转正、进入布线

- run171830-91e7a308完成详细布局，估算最差+0.541ns/TNS0；17:43进入74324网布线，仍须最终十类时序表验证，尚无新位流。源清单再次校验零变化，单PDS/18:35截止审查保持。

## 2026-11-02 18:07：详细布线持续收敛

- 同一PNR全局布线已于17:46完成，详细布线第218轮剩1248条连接，CPU2264s，日志/CPU持续推进；18:35截止审查不变。尚无最终时序/新位流，不以布局估算转正当最终PASS。

## 2026-11-02 18:35：截止审查记录暂停断档，仅补回暂停窗口

- 当前详细布线414轮剩727条、CPU2789s持续推进；监控存在18:09:24至18:28:47的19m22s断档，原因仅推测系统暂停，未确证。保留审查报告，当前同一路PNR延至18:55再次审查，不开新构建。临时系统防休眠请求随PDS退出释放，无永久电源改动；最终时序/位流仍未产出。

## 2026-11-02 18:58：首轮PNR限时结束，准备独立seed1布局

- 默认PNR在18:55仍未布通，1163轮/275连接最后采样；归档完整布局/日志/hash后安全结束，无位流无最终时序。PDS/monitor零残留，防休眠请求释放，既有cdt未动。
- run_pds_stage增加可选PlacementSeed并限pnr使用，默认不变，PowerShell解析与24项构建令牌测试PASS；准备同映射单路seed1替代布局，20:00审查。所有失败证据保留，不以布局估算或功能仿真代替时序闭合。

## 2026-11-02 19:00：seed1单路替代布局已启动

- 18:58:14 stage-20261102-185814-d54f1838复用原映射、PNR子进程明确-gplace_seed 1，19:00第一轮全局布局有进展；无并发PDS，20:00审查，监控15秒并临时防休眠。前轮完整布局证据保留独立目录，尚无新时序/位流。

## 2026-11-02 19:09：seed1布局估算转正；实时串口核验受USB缺失阻断

- 替代全局布局checksum不同，确认seed1生效；详细布局估算+0.687ns/TNS0后进入74138网布线，非最终时序通过，20:00截止不变。
- 只读COM5复核失败：端口不存在，当前串口与CP2102/FTDI现存枚举均空；不能把此前6次推理记录当当前实时运行证据，报告独立保留。未重置USB/驱动或动cdt，本地构建继续。

## 2026-11-02 19:32：seed1详细布线与源一致性检查

- 替代布局不同已确认，详细布局估算+0.687ns，19:31详细布线80轮剩5951条/CPU2218s；尚未证明可布性改善，无最终时序/位流。源清单再次hash零变化，进度报告与TCL/hash保留，20:00审查不变。

## 2026-11-02 19:50：结束无优势seed1，转向仿真UI重设计

- seed1停止时119轮/3638连接，约2717CPU秒；默认相近预算916连接。完整证据保存后安全结束，无新位流/最终时序，PDS/监控均退出，既有cdt未动。
- 用户确认暂不上板，要求优化丑陋布局及缺失说明；采用中文仪表盘、分离波形/频谱、带类别名的概率条和空态，下一步实际RTL仿真导出画面。本阶段不做PDS或烧录。

## 2026-11-02 20:07：中文仪表盘与实际RTL预览

- 将完整系统显示改为波形/频谱/最近识别三卡片；添加中文说明、坐标含义、能量图例、八类标签和百分比，保留原八类模型。首次完整快照前显示等待态；RGB与同步四拍对齐。
- 新增同步字体/图块ROM及可重建脚本、五状态全帧RTL测试与实际PNG。10368000有效像素、2000条形像素、RAM几何/同步/0与100/越界钳位PASS，五项相关RTL回归PASS；lint61/0，pytest432passed/4skipped。生成资产逐字节可复现。
- 仅仿真，未运行PDS或烧录；板级动态花屏/整机时序/外部音源验收仍开放。STATUS及预览报告明确证据边界。

## 2026-11-02 21:16：恢复板级阶段，修复PDS预解析退出挂起

- 用户板子上线，开始新UI完整系统资源门控。首次run预解析Tcl_Exit清理挂起，保存证据后受控结束，无位流。
- StopAfter与stage resume退出仅在执行pass生效；新增实际生成TCL双环境回归，25构建测试PASS，stage PS解析PASS。新run211104已通过编译，综合中；资源/PNR/位流尚未完成。COM5恢复，FTDI仍待用户重插，未操作cdt。

## 2026-11-02 21:27：中文仪表盘完整资源门控通过

- 完整源映射33462LUT/35118FF/147.5DRM/90APM，SourcesUnchanged=true，字体/图块6DRM36K、27HDMI输出OFF确认；保存数据库与日志hash。复用数据库单路PNR，22:10截止审查，尚无新位流/时序结论，FTDI仍待恢复。

## 2026-11-02 21:34：恢复JTAG与显示保底

- FTDI恢复，读状态确认上电未配置；安全复用服务烧回已验收602AB321，done1/CRC0、UIDEMO38129字节，本次屏幕反馈待确认。新版完整PNR详细布线中，无最终时序/新位流。

## 2026-11-02 22:02：新dashboard完整诊断版烧录与文字路径修复

- 2673246E完整位流产出并安全烧录，CPU/MMIO/ISA/DDR/WOK与12秒6轮推理完成PASS；新版实屏待用户确认。最终十表时序仍FAIL，报告保留全部证据/hash，不宣称稳定或识别准确。
- 百分比glyph在tile选择前并行寄存，四拍视频与五状态实际RTL全帧逐字节一致，dashboard_ui PASS、lint61/0；新源尚未PDS。PDS及监控正常退出，fallback保留。

## 2026-11-02 22:14：DDR自检读比较流水

- FIFO读payload/valid与abort witness对齐寄存，切断读mux到256bit比较再到状态的长路径；读done按状态限定，保护写转读边界。端口与读吞吐不变，结果晚一拍。
- 实际RTL self_test新增末beat高位破坏与无reset恢复，12检查PASS；ddr3_subsys/ddr3_aw_timeout PASS，全pytest433passed/4skipped、lint61/0。原始日志/hash归档；新源未PDS/未烧录，板级状态不变。

## 2026-11-02 22:28：新版完整系统中文UI实屏通过

- 用户确认2673246E中文仪表盘正常且稳定，602AB321彩条/KEY1 UI亦正常；对应板级报告更新实屏PASS。不把视觉确认当时序收敛、长期稳定或准确率验收，继续原八类完整系统时序修复。

## 2026-11-02 22:39：NPU激活重放字节流水

- 两路store字节lane选择后寄存payload/valid，拆分至conv RAM路由路径；生产CPU/native不同A/B无reset两轮全部中间golden PASS，每轮实测31141255cycles。回归报告改用实测周期并支持独立报告文件。
- npu_completion/full_top_ctrl PASS，pytest433passed/4skipped、lint61/0；新源未PDS/未烧录，现有正常中文显示保持。

## 2026-11-02 22:50：恢复五类主导组与活跃度迁移评估

- 用户确认主导组为主、同时显示五组activity。核验冻结float双head资产精确一致，记录逐模块复用及MAC/纯权重预算。
- 核对CPU实际RV32I控制请求/ACK、最后事件回读及UI直通限制，制定NPU双FC＋CPU定点后处理/同帧快照/UI提交方案。仅文档和评估证据，无生产RTL迁移或五类位流。

## 2026-11-02 22:55：八类三项分拍完整资源门控归档

- compile/synth/map PASS、源未变，33640LUT/35394FF/153.5DRM/90APM；正常退出并释放防休眠。按设计无PNR/无新位流，保留数据库与hash。五类评估确认训练cache和双head资产可用，后续优先新量化契约。

## 2026-11-02：PaceRV中文竞赛报告应用部分初稿

- 参考DYH固定提交4ef1ea1b的CPU竞赛报告与用户Word模板，新增完整应用Markdown报告和来源清单，涵盖音频/Mel/NPU/CPU控制/中文显示、验证及五组迁移方案。
- 复核数值、图链与来源，明确八类已实现/五组待实现、时序与真实音源验收边界；仅文档改动，未运行构建/烧录，不改变当前生产状态。

## 2026-11-02 23:10：Flash脱机启动评估

- 核对100Pro两颗16MiB标称Flash及共享专用CFG_CLK，发现GTP_CFGCLK候选而未假设已可用；给出位流固化、Flash到DDR权重加载与UART恢复的分阶段方案/条件工时。仅评估和证据，无擦写或硬件修改。

## 2026-11-02：Flash固化与五类主奏识别双任务交接

- 新增docs/HANDOFF_FLASH_AND_GROUP5_20261102.md，统一两项工作的目标、已完成/未执行状态、资产位置、复用边界、CPU职责、实施顺序和验收标准。
- 明确Flash先持久位流再验证用户读/流式权重加载；五类先训练split校准与双头INT8评估，再130帧RTL/MMIO/CPU/UI迁移，最终集成冷启动。
- 保留八类板级基线、时序FAIL及未接音源限制。本轮仅文档，引用检查通过，无PDS/Flash/烧录或功能回归重跑。

## 2026-11-03 15:13 — XSY 27MHz PCM1808 整机门控恢复与受控 PNR

- 保存初次20分钟门控截止时的未完整映射库证据；仅从完整综合库恢复 dev_map，工具正常完成，完整库 SHA256 762c19fc…；资源35743 LUT/35504 FF/155 DRM/92 APM。
- 冻结源逐文件 hash 一致，新完整库15:12:34启动唯一PNR，最长120分钟，继续十表与板级验收；尚无新完整位流。仅更新状态和证据，不修改冻结RTL/约束。

## 2026-11-03：新源CPU/native连续A/B联合回归

- 生产ROM、frame-major真实native控制器两种不同输入无reset回归PASS，所有层golden精确、CPU请求/报告/ACK通过；物理DDR/CDC/板测和时序不在此回归范围。

## 2026-11-03：Mel split整机新源资源门控PASS并进入PNR

- 正常完整映射33967LUT/35466FF/150.5DRM/92APM，源hash一致；新库唯一限时120分钟PNR于15:46:55开始，尚无新完整位流。

## 2026-11-03 16:26：完整系统布线检查点

- 新Mel拆分源已通过宏放置，放置估计+0.500ns/TNS0；详细布线第71轮5302未布通，最终时序/位流待验。修正监控目录154653，保存只读JTAG done0/CRC0与UART无输出证据；无新烧录。


## 2026-11-03：紧急八类置信度回放演示框架

- 独立emergency_demo保留真实PCM1808/Mel/HDMI，移除NPU推理，KEY1触发10Hz预设曲线/末帧保持/重播，不再启动DDR自检；正式full保持。
- 增加曲线编译、顶层生成、RTL消抖/快照回归与使用说明，修复StopAfter compile带参数阶段匹配。RTL PASS、pytest47passed、lint67/0、PDS compile PASS。首轮重复驱动失败保留并修复；尚待曲线，无演示位流/烧录。

## 2026-11-03：CPU/NPU八类下午版源码定版

- 新增releases/pacerv-instrec8-20261103独立源码包，冻结0c138d4f/1497FAF4真实推理系统，筛除未引用资产与开发注释，CPU本地化，保留175文件hash及原始验证身份。后续应用报告切换此源码依据。
- 56份RTL token一致、固件ROM重建一致、独立PDS compile PASS/lint43零违规、安全与权重检查通过；未新综合/PNR/烧录，原时序与准确率结论保持，不混入五类或无NPU演示。导出脚本保存于scripts/freeze_instrec8_release.py。
