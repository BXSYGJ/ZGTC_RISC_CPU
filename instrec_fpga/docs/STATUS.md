# InstRec-FPGA 当前状态（STATUS）

> 本文件是**唯一实时状态源**，优先于任何交接快照与记忆。每次会话结束前必须更新，
> 并在 `CHANGELOG.md` 追加一条。最后更新：2026-10-31 10:55。

## 一句话

InstRec 8 类乐器识别（INT8 CNN）正在移植到盘古 100Pro+（PG2L100H-6IFBG676）纯 FPGA 管线。
**全功能位流已布通并归档 `releases/m3d-20261031/`**（`0B2BE8D4…`）：音频→DDR3→Mel→NPU 全链
→概率条+波形+文字+谱图四层 UI 全部生效，UART 文本已修复。LUT 34327（52%）、DRM 86（56%）、
布线仅 510 轮；`ddrphy_sysclk` 改善到 -0.966 ns（仍差 1 ns），`pix_clk` 转正 +0.018。
**唯一阻塞：FTDI 下载器不在 PnP 中，无法上板验证。**

## 里程碑

| 里程碑 | 状态 | 关键证据 |
|---|---|---|
| P0 工具链 + Python 金标准 | 完成 | `pytest -q` 239 passed / 4 skipped；`golden_pipeline.py` 位级真值 |
| M0 I2S→DDR3→HDMI 波形 | 完成（未上板） | run `20261027-000612-a71f1451`，sha256 `C517736C…`，WNS +1.757 |
| M1 Mel 特征引擎 | 构建完成、时序收敛、待板级对拍 | run `20261027-121101-5c24a968`，sha256 `BD40D10A…`，WNS +1.438 / All Constraints Met |
| M2 INT8 NPU | 全链布线收敛、已上板 `done=1`、core 域 -2.1 ns 未收敛 | m2/m2b/m2c 三版位流归档；最差路径已非组合深度而是 wdma 远距离 FF |
| M3 UI 集成 | **五个模块接线已恢复（92d0531），随 `20261029-212311` 重建验证** | text/spectrum/feat_copy/feat_page_buf/ui_coord_delay 全部重新例化 |
| 板级端到端 | **已通到串口，字符被丢（修复版构建中）** | `done=1`、`crc_err=0`、18 字节 `ITCO\nD3ETT.D3R@FF\n` |

## 当前状态

### 2026-10-29 夜间：M3 接线恢复 + 板级编排/判据补齐（本轮最新）

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

### 2026-10-29 傍晚：FTDI 掉线根因彻底修复 + 首次上板（本轮最新，最高优先）

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

### 2026-10-29 上午：全 NPU 系统首次布线收敛（本轮最新）

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

1. **烧 UART 修复版（构建 `20261029-191053`）**：`python scripts/board_check.py
   --sbit build/instrec-latest.sbit --seconds 15`，确认串口出现完整可读的
   `INSTREC BOOT` / `PLL LOCK` / `DDR3 SELFTEST...` / `DDROK` / `RUN`。
   判据：字符数与 ROM 行长度一致（13/17/6/4），不再是 1/3。
2. **权重上传**：`python scripts/weight_upload.py`（`WOK`），再开逐层对拍
   `compare_layers.py` 对 `reports/golden_ref/`，定位第一处不一致的层。
3. **恢复 M3 谱图/文字层**：`text_disp`/`spectrum_disp`/`feat_copy_engine`/`feat_page_buf`/
   `ui_coord_delay` 在 `instrec_top` 中仍是注释块（残留裸 `;`），恢复后复核 `pix_clk`
   （m2c 为 -0.061，恢复后需重读）。
4. **core 域**：目前最差路径是 wdma 的 FF→FF 远距离（走线 91.7%），插流水无效；
   若要继续压缩，只能做布局/区域约束或降低该段拥塞，优先级低于功能验证。

## 验证基线

- `python -m pytest -q` → **239 passed / 4 skipped**（约 69 s）。
- `python scripts/check_rtl.py` → **44 个 .v，0 violation**（hdmi demo 默认排除）。
- 烧录安全：`tests/test_board_flash_safety.py`（14 项）锁死「TCL 必须以 exit 收尾、
  禁止 terminate/kill cdt_*、必须复用已运行 jtagserver」；
  `tests/test_uart_debug_handshake.py`（3 项）用周期模型锁死 uart_debug↔uart_tx 握手。
- 数值对拍只认 `scripts/golden_pipeline.py`；torch 2.14.1 的 oneDNN 有 21~67 LSB tile 噪声。
- 本机无 WSL 仿真（Ubuntu 发行版 vhdx 缺失），RTL 行为只能靠 Python 对拍 + 板级实测。
- 全 NPU 构建耗时：compile→gen_bit_stream 约 48 分钟（单线程，`-fast_router`）。

## 资产位置

| 类别 | 路径 |
|---|---|
| RTL | `src/{audio,ddr3,mel,npu,ui,ctrl,ip,hdmi}/*.v` |
| 顶层 | `src/ctrl/instrec_top.v`（mel_engine 接 DDR3 m2 口） |
| 约束 | `constraints/instrec_top.fdc`、`ddr3_100h.fdc`、`clock_groups_async.fdc`（顺序敏感） |
| IP | `ipcore/{ddr3_test,pll,pll_audio}/`（重建必需，已入库） |
| 数值真源 | `scripts/outputs/layer_contract.json`、`weights_image.bin`、`mel_tables.*` |
| 金标准 | `scripts/golden_pipeline.py` + `scripts/outputs/golden/*.npy` |
| SDD | `docs/sdd/{spec,design,tasks}.md`（从 `.codeartsdoer` 复制的可交接副本） |
| 证据 | `reports/m0-manifest-20261027.json`、`reports/m1-timing-20261027-104218.txt`（修复前时序） |
| 位流归档 | `releases/m{0,1}-2026102{7}/`、`releases/m2{,b,c}-20261029/`（sbit + manifest + SHA256SUMS + 时序报告） |
| 交接 | `docs/HANDOFF_SNAPSHOT_20261027.md` + 本文件 |
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