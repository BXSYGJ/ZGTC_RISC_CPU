# InstRec-FPGA 变更日志

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
