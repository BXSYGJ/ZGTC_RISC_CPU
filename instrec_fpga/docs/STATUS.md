# InstRec-FPGA 当前状态（STATUS）

## 2026-11-02 12:44：显示专用修复位流已完成并烧录，待屏幕验收

- codex/display-demo（源提交8d5382a2）补接底板G25物理HDMI复位，固定piano演示柱与文本一致，烧录脚本缺失program成功证据时不再误报PASS。RTL59文件0 violation，烧录契约/安全39项PASS。
- PDS run 20261102-124002-c2bc537c 六阶段成功、SourcesUnchanged=true；完整slow/fast报告All Constraints Met，slow setup+1.191ns、hold+0.338ns；1035LUT/948FF/1DRM/0APM。cfg与pix之间仅有复位/准静态双拍同步路径，显示分支补了对应CDC时钟分组，域内时序仍检查；原始负裕量首候选与报告保留。
- 位流SHA256 20B31B08C7D56982E580A709A26A9E965780437A4BDB79BF6DB04093605854BE。已复用cdt_js9040烧入，program明确成功、done1/CRC0、27300字节UIDEMO，G最终07；未终止/重启原cdt_cfg46156。PDS已全部退出。
- 现在板上是这个修复UI候选（不再是原厂对照版）。**用户尚未确认最新候选屏幕画面，显示未验收**；旧UI位流在底板J9无信号为明确失败证据。原厂对照版成功烧录后未收到屏幕反馈，因此不作硬件链路通过结论。
- 报告reports/display_demo_build_20261102.json、ui_reset_board_20261102.json；原始UART/TCL/日志在显示工作树build/board_ui_reset_20261102。当前只演示固定数据，无真实音频或推理。完整项目今日交付仍低置信度，待显示验收后回到RV串口权重WOK、真实I2S和HDMI整合。

## 显示候选 CDC 约束复核

- 123646-c2b262b4完成六阶段，位流BEAB3C31...3BF70C3，资源1003LUT/948FF/1DRM。像素域setup+1.077，但完整报告cfg_clk->pix_clk setup -1.944/8端点，Some Constraints Violated；脚本摘要未覆盖跨时钟最差路径，不能据此宣称时序收敛。
- 8端点为rstn_pix_meta及init_over/init_fail双拍同步器首级，只有复位释放和准静态状态跨域，不依赖PLL相位。显示专用约束将cfg_clk与clk置同组，与pix_clk作CDC隔离，保留域内时序检查；下一run验证约束生效和全报告。

## codex/display-demo：待验证的显示专用候选

- 恢复G25外部MS7210/MS7200复位，随PLL稳定后cfg_rstn释放；与原厂示例接法一致，尚未证明能修复无信号。
- 72%演示柱改为class4，与piano文本一致；数据是固定演示值，不是真实推理。
- 修复board_check在program未执行但旧done=1时误报PASS；新增离线回归，烧录契约与安全共39 passed；RTL59文件0 violation。
- 下一步只跑ui_demo PDS，读取时序后烧录，并以用户实际画面验收。

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
