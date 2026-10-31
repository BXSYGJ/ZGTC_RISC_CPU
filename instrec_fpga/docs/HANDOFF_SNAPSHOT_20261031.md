# InstRec-FPGA 开发快照与交接（2026-10-31 11:10）

> 本文是**换人交接的第一入口**。实时状态看 `docs/STATUS.md`，变更史看 `docs/CHANGELOG.md`。
> 写这份时的确切事实，全部来自实测，不含推断。

---

## 一、一句话结论

**软件侧已完成：全功能位流 `m3d` 布通并归档，板级已跑到「串口可读、配置成功」；
唯一阻塞是 DDR3 自检超时（`DDR3 ERR @FFFFFFFF`），因此 NPU 拿不到权重、识别链路无法闭环。**

---

## 二、当前可用的位流（按能力递增，全部已布通归档）

| 版本 | 目录 | SHA-256（前 8） | 内容 | 板级验证 |
|---|---|---|---|---|
| m3a | `releases/m3a-20261031/` | `152FEC8B` | wdma 参数表块 RAM 化 | 未烧 |
| m3b | `releases/m3b-20261031/` | `D28C798C` | + UART 字符间隔修复 | 已烧：BOOT 可读、DDR3 ERR |
| m3c | `releases/m3c-20261031/` | `482CCA1C` | + 文字层 | 未烧 |
| **m3d** | **`releases/m3d-20261031/`** | **`0B2BE8D4`** | **+ 谱图层 = 四层 UI 全齐** | **已烧：BOOT 可读、DDR3 ERR** |
| m2c | `releases/m2c-20261029/` | `23B3FEC6` | wdma 优化前（对照基线） | 已烧：DDR3 同样 ERR |

m3d 资源：LUT **34327 / 66600（52%）**、DRM 86/155（56%）、FF 52188（39%）、APM 90/240（38%）。
时序：`ddrphy_sysclk` **-0.966 ns**（未收敛）、`pix_clk` **+0.018 ns（已转正）**、`clk_nco` +1.347。

---

## 三、板级实测（2026-10-31，重插 USB 后）

烧 m3d 的完整串口输出（49 字节，`build/uart_last.bin`）：

```
INSTREC BOOT
DDR3 SELFTEST...
DDR3 ERR @FFFFFFFF
```

- `program: True`、状态寄存器 `0x081FFCA0`（`done=1`、`crc_err=0`）→ 位流确实在跑。
- **UART 已彻底修好**：三行逐字符正确，这是项目第一次读到可读启动日志。
- **`0xFFFFFFFF` 是超时不是地址错**：`sys_ctrl` 的 `timeout_cnt >= DDR_TIMEOUT_CYCLES`（100 ms
  @125 MHz）分支固定填 `0xFFFF_FFFF`，含义是 `self_test` 在 100 ms 内**既没拉 `st_done`
  也没拉 `st_fail`**。
- **对照结论（重要）**：烧 2026-10-29 的 `m2c`（wdma 优化之前）**同样是 DDR3 ERR** →
  **不是最近几轮改动引入的回归**，DDR3 通路在此前从未被验证通过过
  （此前串口乱码把这条错误一直遮住了）。

---

## 四、DDR3 排查进度（已查 / 未查）

**已排除**：

- `pll_lock` / `ddr_init_done` 已被 `sys_ctrl` 使用：`pll_all = pll_locked_s & ddrphy_lock_s &
  ddr_init_s & hdmi_over_s & ~hdmi_fail_s`，进 `ST_DDR` 前已等 DDR 初始化完成。
- 四主口仲裁有效掩码正确（`arb_valid = cmd_valid & ~(cmd_busy ? (1<<cur_master) : 0)`）。
- `self_test` FSM 启动条件正常（`ST_IDLE: if (st_start)`），`ST_WCMD → ST_WDATA` 无条件推进，
  之后等 `wready_beat`（即等 `ddr3_ctrl_axi` 的 `axi_wready`）。
- 顶层 `self_test` 接线完整（`cmd`→`m3_cmd`、`wdata`→`m3_wdata`、`wready_beat`←`ddr_wready_beat[3]`、
  `rd_data`←`rd_data_3`、`done`←`ddr_done[3]`）。
- FTDI/JTAG 链路与烧录流程完全正常（单实例复用、无掉线）。

**尚未查（接手第一顺位）**：

1. **DDR3 IP 是否真的接受 AXI 写事务**。历史记忆明确记过：官方 demo 的写控制器**没有
   `axi_wvalid` 输出**，自定义控制器写事务会卡在等 `axi_awready` 直至超时、**IP 不接受任何
   AXI 事务**。当前 `DDR3 ERR` 的表现（超时、无 `st_fail`）与该症状高度一致 ——
   应优先核对 `ddr3_ctrl_axi` 的 `axi_awvalid/axi_awready`、`axi_wvalid/wready` 实际波形
   或加观测计数（LED/串口）。
2. **是否需要「先写后读」**：官方 demo 初始化先写满内存再读，当前设计是否满足。
3. **`axi_rready` 不存在**（IP 无此输入、始终推数据），控制器必须每周期就绪接收 ——
   确认 `S_R` 状态没有按标准 AXI 反压。
4. **core 域时序 -0.966 ns**：最差路径在 `ddr3_wrapper/I_ips_ddr_top/.../ddrphy_data_slice_wrlvl`
   与 `ddrphy_reset_ctrl`（**IP 内部**逻辑，不可改），逻辑仅 0.8 ns、走线 6.4 ns（88%）。
   若上述 AXI 检查都正常，这条是次要嫌疑。

---

## 五、关于「降频」（用户多次要求，尚未落地）

- **当前频率**：`ref_clk` 125 MHz（板载晶振，固定）→ DDR3 IP 的 GPLL → `ddrphy_sysclk` 125 MHz。
  该时钟同时是 `core_clk`（全部 NPU/Mel/控制逻辑都跑它），**不能单独降**。
- **已尝试并失败**：改 `ipcore/ddr3_test/ddr3_test.idf` 的 `DESIRED_DDR3_RATE=800` /
  `DFI_CLK_PERIOD=10000`，再用 `ip_generate.exe -i <idf>` 重新生成 →
  报 `IPCompiler 0014: Failed to open file 'index.xml'`。本工程的 ipcore 只有
  `.idf + .v + rtl/`，**没有 IP 实例工程文件（index.xml）**，无法命令行重生成。
  ⚠️ 该 .idf 改动**已回退**，现在仍是 DDR3-1000 / 8000 ps，与已生成 RTL 匹配。
- **若要真降频**，两条路：
  1. 用 PDS **IP Compiler GUI**（`ip_compiler.exe`）打开/重建该 DDR3 实例，把速率降到
     DDR3-800（用户时钟 100 MHz），再 `ip_generate`。需要有人会 GUI 操作。
  2. 保持 IP 不动，**给用户逻辑单独分频**：DDR3 控制器仍跑 125 MHz，NPU/Mel 跑
     125/2 或 /4，中间所有 AXI 接口加异步 FIFO。工作量很大（跨域面广），不建议在
     只剩一天时做。
- **注意**：用户提出「直接降到 10 MHz」。**DDR3 域物理不可行** —— JEDEC DDR3 最低档是
  DDR3-800（DFI 100 MHz），再低 IP 不支持；且 `ref_clk` 是板载 125 MHz 固定晶振。
  可以做到的最低就是 **DFI 100 MHz**，前提是能重新生成 IP（见上）。

---

## 六、布线结论（已彻底定性，别重复踩）

- **纯 `pnr`（无任何参数）是唯一能布通的配置**。`-parallel` / `-gplace_seed` /
  `-plc_decongestion` / `-dc_duplication` 四类参数在两天内逐一试过，**每一次都把布局拖进
  拥塞死解**（iteration 涨而未布网络不降）。
- 但 2026-10-31 的「逐层加回」四轮（m3a→m3b→m3c→m3d）**全部一次布通**，`build_full.tcl`
  当前是纯 `pnr`。
- **判死解的判据**：固定间隔采样的未布网络**下降速率趋零甚至回升**即停滞，主动中止换配置，
  不要等满时间。
- **LUT 有余量**：52%（m3d）。历史临界点是 53.57% 布通 vs 53.59% 停滞 —— 也就是说
  **余量只有约 1.5 个百分点，任何新功能都要按「一层一轮」加回**。
- **降密度已三次证伪**（`spectrum`/`text_disp` 只省 0.3%、波形层无效）→ 瓶颈从来不在 UI 层。

---

## 七、复现命令（全在 `instrec_fpga/` 下）

```powershell
# 环境
$env:PDS_ROOT = 'H:\GG\pango\PDS_2022.2-SP6.4'
$env:PANGO_LICENSE_FILE = 'E:\License\pango\new_pds_F4A80DA47D72.lic'

# 静态检查 + 全量回归（改完 RTL 必跑）
python scripts/check_rtl.py          # 必须 0 violation（当前 44 个 .v）
python -m pytest -q                  # 当前 280 passed / 4 skipped

# 全量构建（约 1.5 小时，单线程，一次只能跑一个 pds_shell）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1

# 判断构建结果（脚本只要出位流就报成功，不看时序）
#   build/instrec-latest.json 的 Wns / report_timing/*.rtr 的 Performance Summary

# 板级：烧录 + 抓串口 + 自动判读
python scripts/board_check.py --diag-only          # 先看 FTDI / jtagserver / 端口
python scripts/board_check.py --sbit releases/m3d-20261031/instrec_top.sbit --port COM5 --seconds 12 --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"

# 一键端到端（boot → weights → capture → compare）
python scripts/board_e2e.py --stage boot
python scripts/board_e2e.py --sbit releases/m3d-20261031/instrec_top.sbit
```

---

## 八、必须遵守的硬规则（违反会浪费数小时）

1. **JTAG 单实例**：`cdt_js`（就是那个 UI）只允许一个实例常驻。已有就**只复用**，
   绝不新开第二个、绝不 `terminate`/`Stop-Process`。所有 TCL 以 `exit` 收尾。
   `tests/test_board_flash_safety.py` 锁死这三条。掉线只能靠物理重插恢复。
2. **一次只能跑一个 `pds_shell.exe`**，单进程内存峰值 2.9~3.9 GB。
3. **`pnr` 不要加任何参数**（见第六节）。
4. **改 RTL → 必须先 `check_rtl.py` + `pytest`，再全量构建**；一次只加一层，
   布通并归档后才加下一层。
5. **不要把 IP 参数改成「半成品」**：改 `.idf` 而不重新生成 `.v` 会让 IP 与约束不一致。
6. 会话结束前：`git status` 干净 → 更新 `STATUS.md` + `CHANGELOG.md` → commit（**不 push**）。

---

## 九、踩过的坑（省时间用）

- `uart_debug` 的 char ROM **必须用显式 ASCII case 表**，PDS 对字符串字面量的字节序不可预测。
- `uart_debug → uart_tx` 握手：生产者 `valid` 是单拍 strobe、消费者 `byte_wready` 是寄存的
  `~busy`（接受后还多保持一拍）→ 索引每帧推进 2~3 次只送出 1 字节（板上表现为
  `ITCO` = ROM idx 0,3,6,9）。现用「字符间隔计数器 12000 拍」解决：
  **它只加了一个 16 位计数器，没改握手结构**，正是为了不破坏已布通的布局。
- `wdma` 的 bias/M/shift 三张参数表**必须**做成单张单口块 RAM（`syn_ramstyle = "block_ram"`）
  且读地址**前视两拍**；之前是三个异步读数组，被 PDS 建成 LUTRAM/FF，占 8004 LUT / 18608 FF，
  且最差 core 时序路径就在里面。块 RAM 化后 LUT -1086、布线轮次 1001→510、core 时序 -2.144→-1.228。
- 参数化存储：单块 DRM 最大深度 **4096**；多读口数组会被复制并漏到分布式 RAM；
  `ram_style` 不生效，**必须 `syn_ramstyle`**。
- PDS 要求**先声明后使用**；一条 wire 被两个实例驱动即报多驱动；禁空 `.port()`。
- 不要相信「全局 WNS 为正」= 收敛，**必须逐时钟域看** `Performance Summary`。
- 分阶段复跑（`run_pds_stage.ps1 -From pnr`）实际不可用：`pnr` 无法跨会话复用 phase DB，
  且 PDS 会把工程文件覆盖成默认 `PGL12G`。该脚本保留但**不要依赖**。

---

## 十、接手后的建议顺序（按优先级）

1. **DDR3 自检超时**（唯一的实质阻塞）：
   先查 `ddr3_ctrl_axi` 的 `axi_awvalid/awready`、`axi_wvalid/wready` 是否真的握手成功
   （最省事的办法：把这两个信号接入现成的 `uart_debug` 状态行或 LED 编码，出一版诊断位流）。
   同时核对历史记忆里的「IP 无 `axi_wvalid`、自定义控制器写事务会卡死」这条。
2. 若 DDR3 通了 → 立刻 `python scripts/board_e2e.py --sbit ...` 走
   boot → 权重上传（看 `WOK`）→ 抓帧 → 逐层对拍。
3. 时序收尾（可选）：`ddrphy_sysclk` -0.966 ns，但最差路径在 **IP 内部**（`ddrphy_reset_ctrl` /
   `ddrphy_data_slice_wrlvl`），用户逻辑改不动，只能靠布局；按「能跑就行」口径可暂放。
4. 若坚持降频：走 IP Compiler GUI 把 DDR3 降到 DDR3-800（DFI 100 MHz），
   同步改 `constraints/ddr3_100h.fdc` 的 `ddrphy_sysclk` 周期为 10.000 ns。

---

## 十一、文档与资产索引

| 内容 | 位置 |
|---|---|
| 实时状态（唯一状态源） | `docs/STATUS.md` |
| 变更史 | `docs/CHANGELOG.md` |
| 位流归档 | `releases/m3{a,b,c,d}-20261031/`、`releases/m2{,b,c,d}-2026102{9,30}/` |
| SDD（69 需求 / 17 模块 / 44 任务） | `docs/sdd/{spec,design,tasks}.md` |
| 顶层接线 | `docs/m2_top_integration.md`、`docs/m0_top_integration.md` |
| wdma 块 RAM 化方案 | `docs/wdma_sync_ram_plan.md` |
| 量化契约（唯一真源） | `scripts/outputs/layer_contract.json` |
| 位级金标准 | `scripts/golden_pipeline.py` + `reports/golden_ref/` |
| 板级脚本 | `scripts/board_check.py`、`scripts/board_e2e.py`、`scripts/weight_upload.py`、`scripts/uart_capture.py`、`scripts/compare_layers.py` |
| RTL | `src/{audio,ddr3,mel,npu,ui,ctrl,hdmi,ip}/*.v`（44 个） |
| 约束 | `constraints/{instrec_top,ddr3_100h,clock_groups_async}.fdc`（**加载顺序敏感**） |
| IP | `ipcore/{ddr3_test,pll,pll_audio}/` |

**git**：分支 `XSY`，最新提交 `8168894`，工作区干净，**未 push**。