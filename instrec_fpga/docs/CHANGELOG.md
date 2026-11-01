# InstRec-FPGA 变更日志

> 每次会话结束前追加一条：时间、做了什么、结论、证据路径。倒序，最新在上。
> 状态汇总见 `docs/STATUS.md`。

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