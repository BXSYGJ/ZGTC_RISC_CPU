# T10 全量收敛：DDR3 自检修复后唯一一次全量构建

- 日期：2026-10-31
- 构建集：`full`（`instrec_top`，纯 `pnr`）
- 结果：**布通并产出位流，六阶段全 OK**，LUT **51.66%**，SHA-256 `44E8F011…D476C`
- 一句话：**DDR3 自检的三个缺陷已全部修复**（T2 的 `self_test` done/hold + 诊断定位的 master 下标错位 + 全量 `st_wready_beat` 未驱动），全量只需 **1 行**新增；位流已归档 `releases/m4-20261031/`，**可进 T11 板级验证**。

---

## 1. DDR3 自检的修复链（三处缺陷，全量只需其中 1 行）

| # | 缺陷 | 位置 | 现象 | 归属 / 状态 |
|---|---|---|---|---|
| **F-1** | `self_test` 不监听 `done`，`cmd_valid` 单拍发散 → 永久卡死 | `src/ctrl/self_test.v` | 全量 `DDR3 ERR @FFFFFFFF`（100 ms 无 `st_done`/`st_fail`） | **T2 已修**（F1~F7：`cmd_valid` 保持到 done、`wready_beat` 先于 done 判、`done_q` 读保护、done 转 st_fail），diff +71/-8 |
| **F-2** | 诊断顶层把 `self_test` 的 `cmd_valid` 拼到 master 0（`{3'b000, st_cv}`），而完成信号取 `[3]` | `src/diag/top_ddr3_diag.v:282` | 两轮诊断均 TIMEOUT，`A==B==D≈25 万`、`C(done_cnt)=0` | **T4 已修**为 `{st_cv, 3'b000}`；**第二轮诊断 design=PASS** 证实 |
| **F-3** | 全量 `st_wready_beat` 声明后**无驱动**，PDS 自动绑 0 | `src/ctrl/instrec_top.v:227`（声明）/`:753`（仅作 `u_self_test.wready_beat` 输入） | m3d 日志 `Verilog-2036: … Net st_wready_beat … has no driver, tie it to 0` | **T10 本次修复**，+1 行 |

> F-3 的证据（m3d 那一轮就存在）：
> `reports/build_20261031-085308-2a717fbf.pds.stdout.log:4322`
> ```
> W: Verilog-2036: [D:/.../src/ctrl/instrec_top.v(line number: 746)] Net st_wready_beat
>    connected to input port of module instance instrec_top.u_self_test has no driver, tie it to 0
> ```
> 后果：`self_test` 永远收不到 beat 握手 → 第一条写命令在 `ST_WDATA` 看到 `done` 却无 `wready_beat` → 走 C-SELFTEST@1 的 **F2 分支** → `st_fail=1, st_fail_addr=SELFTEST_BASE(0x00300000)`。
> 即：**即使 F-1 修好了，全量也会从 `@FFFFFFFF` 变成 `@00300000`，仍然不是 `DDROK`。**

T10 的修复（`src/ctrl/instrec_top.v:745` 之后）：

```verilog
    // master-3 write-beat pulse (C-SELFTEST@1 F2/S1/S2).  Without this tap
    // PDS reports "Verilog-2036: Net st_wready_beat ... has no driver, tie
    // it to 0"; self_test then never sees a beat handshake and the first
    // write command aborts with st_fail at SELFTEST_BASE.
    assign st_wready_beat = ddr_wready_beat[3];
```

## 2. 改动摘要（diff）

| 文件 | 增 | 删 | 性质 |
|---|---|---|---|
| `src/ctrl/instrec_top.v` | **6** | **0** | **T10 唯一改动**（1 行有效代码 + 5 行注释；属 §2.2.8 L1「`u_self_test` 端口接线」） |
| `src/ctrl/self_test.v` | 71 | 8 | T2 交付（本次全量的必需前置，**不计入** T10） |
| `src/ddr3/ddr3_ctrl_axi.v` | 0 | 0 | **未改**：`:58 AXI_USER_AP=1'b1`、`:62 DUMMY_WSTRB_ALL1=1'b0` 默认值即板上 PASS 的 design 配置 |
| `src/diag/*` | 0 | 0 | 诊断顶层不进 `full` 集（`build_sets.json` 已隔离） |

- **T10 自身 6 行 < L5 的 40 行上限 ✔**
- 工作区 `src/` 合计 77 增/8 删（79 行来自 T2，6 行来自 T10）
- `pnr` 行保持纯 `pnr`（`scripts/build_full.tcl:126` 恰为 `pnr`，E-2 ✔）；**未新增任何 `-parallel`/`-gplace_seed`/`-plc_decongestion`/`-dc_duplication`**

## 3. 构建

| 项 | 值 |
|---|---|
| run 目录 | `build/pds/20261031-135808-f1cb68bd/` |
| 启动 → sbit | 13:58:06 → 16:00:57 = **2 h 02 m 51 s**（PDS 自报 compile→gen_bit_stream 2h2m31s） |
| 六阶段 | compile / synthesize / dev_map / pnr / report_timing / gen_bit_stream **全 OK** |
| PDS ExitCode | 0，`pds.stderr.log` 为空 |
| 归档日志 | `reports/build_20261031-135808-f1cb68bd.pds.stdout.log` |
| **SHA-256** | **`44E8F011D44E10254E33BCBE4622BEB3F53966894C00BD1962BE9420414D476C`** |
| WNS（脚本字段） | +0.523 ns（= `clk_nco`，**非全局最差**，见 §5） |
| WHS（脚本字段） | +0.232 ns |

> 耗时 **2h02m > 预计 1.5h**：原因是布线 636 轮（m3d 为 510 轮），属"慢但收敛"，非停滞。gen_bit_stream 一项就 1m48s。

## 4. 布线判定（只看两件事）

| 判据 | 结果 |
|---|---|
| `Unrouted nets 0` | ✔ `Unrouted nets 0 at the end of iteration **636**` |
| `placed and routed successfully` | ✔ `Design 'instrec_top' has been placed and routed successfully.`（`pds.stdout.log:33016`） |

收敛采样（无停滞）：48068@8 → 41875@10 → 17933@34 → 9761@63 → 5202@107 → 2619@170 → 1376@275 → 244@477 → 5@634 → 3@635 → **0@636**。

中途 iter 168→170 曾出现 2578→2595→2619 的短时回升，但随后继续下降并在 636 轮归零，**未判停滞、未中止**。

## 5. 逐域时序（Setup, Slow Corner）

> **WNS 口径（必须随文传递，禁止只引用单一数字）**：`build/instrec-latest.json` 与
> `releases/m4-20261031/manifest.json` 里的 `Wns = "0.523"`，其**口径是
> `Setup Summary(Slow Corner)` 表格的第一行**（`run_pds_full.ps1` 按第一行提取），
> 而这一行是 `clk_nco`。**它不代表全局最差域**：真实最差域是
> **`ddrphy_sysclk = −1.740 ns`**（TNS −124.797，failing endpoints 482；m3d 为
> −0.966 / 175）。因此「本轮 WNS = 0.523 / 已收敛」的说法是错的，必须逐域报值。
> 构建脚本本身不校验 WNS（产出位流即报成功），建议后续把提取逻辑改为取各域最小值。

| 时钟域 | m4 WNS | m3d WNS | 变化 | TNS | failing endpoints |
|---|---|---|---|---|---|
| `clk_nco`（216.0 MHz） | **+0.523** | +1.347 | **−0.824** | 0.000 | 0 |
| `pix_clk`（148.5 MHz） | **+0.556** | +0.018 | **+0.538** | 0.000 | 0 |
| `cfg_clk`（10.4 MHz） | **+92.287** | +89.809 | +2.478 | 0.000 | 0 |
| `rst_clk`（125 MHz） | **+4.227** | +3.463 | +0.764 | 0.000 | 0 |
| **`ddrphy_sysclk`（125 MHz）** | **−1.740** | **−0.966** | **−0.774** | **−124.797** | **482**（m3d 175） |

- 四域正、一域负；**`pix_clk` 显著改善（+0.018 → +0.556）**，UI 层时序更安全。
- **`ddrphy_sysclk` 恶化 0.774 ns，failing endpoints 175 → 482**：这是本轮唯一时序退步。
- 最差路径（`Path Group ddrphy_sysclk`，`timing.rtr:1943`）：
  - 时钟链：`ddr3_wrapper/refclk_inbuf → clkbufm → ppll → ioclkdiv → gpll → u_sysclk_bufg → HCKBROUTE_30`
  - 数据段：`u_weight_loader/beat_buf[7][212] → m1_wdata[212] → u_weight_loader/acc2[28]`
  - Data arrival **14.940 ns**，其中 **Logic 1.079 ns (11.5%) / Route 8.311 ns (88.5%)**
  - **归因：布线长走线，落在用户逻辑 `weight_loader`，不在 IP 内部**（m3d 的最差路径在 `ddrphy_reset_ctrl`/`ddrphy_data_slice_wrlvl` 的 IP 内部，改不动）。T10 禁止改 `weight_loader`，**本轮不动**，交 T11 板级判定。
- 结论：`Some Constraints Violated`（`ddrphy_sysclk` 一域），与 m3d 同性质（m3d 也是负 slack 但板级可用）。

## 6. 资源

| 资源 | m4 | m3d | 差 | 判定 |
|---|---|---|---|---|
| **LUT** | **34407/66600 = 51.66%** | 34327 (51.54%) | +80 | **≤ 53.57% ✔**，余量 1.91 pp（≈1271 LUT） |
| FF | 52193/133200 = 39% | 52191 | +2 | — |
| **DRM** | **86/155 = 55.48%** | 86 (55.48%) | 0 | — |
| Distributed RAM | 1501/19900 = 8% | 1501 | 0 | — |
| APM | 90/240 = 38% | 90 | 0 | — |
| BKCL | 6/6 = 100% | 6 | 0 | 满 |
| HCKB / USCM | 32/96、11/32 | 27、9 | +5 / +2 | — |
| IO / GPLL / PPLL | 119/300、4/6、2/6 | 同 | 0 | — |

**不是"运气布通"**：636 轮稳定收敛到 Unrouted 0，资源与 m3d 逐项几乎相同（+80 LUT 即 F-3 那 1 根线与 T2 修复的净增量），且余量近 2 个百分点。

## 7. 归档

`releases/m4-20261031/`：

| 文件 | 内容 |
|---|---|
| `instrec.sbit` | 3 791 112 B，SHA `44E8F011…D476C` |
| `manifest.json` | `build/instrec-latest.json` 原件（`BuildSet=full`、六阶段、资源、Wns/Whs、SHA） |
| `SHA256SUMS` | `44e8f011…d476c *instrec.sbit` |
| `timing.rtr` | 逐域 Setup/Hold/Recovery 报告原文（913 573 B） |
| `README.md` | SHA、六阶段、逐域时序、资源、与 m3d 差异、复现命令 |

## 8. 并发事故与处置（单列）

**不是并发，是 PDS 父子进程模型**（team-leader 曾按进程数量误判，已复核澄清）：

| PID | ParentProcessId | 命令行 | 判定 |
|---|---|---|---|
| 45664 | 17320（启动脚本的 powershell） | `-file …/20261031-135808-f1cb68bd/build.tcl -work_dir …` | 全流程 shell（父） |
| 37376 | **45664** | `-action place_route -project_file …/20261031-135808-f1cb68bd/instrec_top_pds.pds` | **同一 run 的 pnr 子进程** |

- 佐证：每阶段的"第二个 PID"都不同（`33148`→`27164`→`30876`→`37376`），父 PID `45664` 恒定。
- **处置：未终止任何进程**（杀掉子进程 = 掐断 place_route = 全量作废，而 T10 只允许跑一次）。
- **踩坑记录**：判断 pds_shell 并发必须看 **ParentProcessId + CommandLine 的 run 目录**，不能只看进程数量；只有"父 PID 不同且 run 目录不同"的两组才是真并发。
- `cdt_js` 全程保持单实例 PID 9040，未新开、未 terminate（本任务不烧板）。

### 另一处工作区事故（本轮已处理并留档）

13:54:39 有另一进程把 `src/ctrl/instrec_top.v` 从 m3d 的 **908 行重写成 639 行的 M0 版本**（删掉 `NPU_ENABLE`、`u_npu`、`u_weight_loader`、bars/text/spectrum 四层与全部 `wl_*` 信号，`git diff` = 51 增/316 删），并把 T10 的编辑撞到 `endmodule` 之后（文件当场语法损坏）。

- 证据：`build/evidence/instrec_top_M0revert_20261031T1354.v`、`build/evidence/instrec_top_workspace_revert_20261031.diff`（470 行）
- 处置：`git checkout HEAD -- src/ctrl/instrec_top.v` 恢复到 m3d 基线（908 行），再重新施加 F-3 的 1 行；构建前用 `sha256sum` 锁定（`2de5f10d…84bc`）并确认未被再次改写
- 教训：**构建前必须 `git status` + `git diff --numstat src/`**，发现非预期 `M` 文件先查清再构建（AGENTS.md 交接纪律第 2/3 条）

## 9. 下一步（T11）

1. `python scripts/board_check.py --sbit releases/m4-20261031/instrec.sbit --port COM5 --seconds 20 --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDR3SELFTEST" "DDROK"` —— 期望 **`DDROK`**（F-3 修好后 `st_done` 才会拉起）。
2. `python scripts/weight_upload.py` —— 期望 **`WOK`**（权重走 m1 真实 16-beat 写；T8 第二轮已证写通道可用）。
3. 若有真实 I2S 输入：`board_e2e.py` 抓帧 → `compare_layers.py` 逐层对拍。
4. **风险提示**：`ddrphy_sysclk` WNS −1.740（m3d −0.966），最差路径在 `u_weight_loader` 的长走线（88.5% 布线）。若 T11 出现 DDR3 自检偶发失败或 `WOK` 不稳定，优先怀疑此处；但修复它需要动 `weight_loader`（超出 L2 容差）或重新布局，须另开一轮并报备 leader。
5. 若 `DDROK` 与 `WOK` 均通过，M4 可宣布交付；`STATUS.md`/`CHANGELOG.md` 待更新（本任务未改，按交接纪律由收尾任务处理）。

## 10. 证据索引

| 文件 | 内容 |
|---|---|
| `build/pds/20261031-135808-f1cb68bd/pds.stdout.log` | PDS 全量日志（33 000+ 行） |
| `build/pds/20261031-135808-f1cb68bd/flow.log` | 布线 iteration 日志（Unrouted nets 趋势） |
| `build/pds/20261031-135808-f1cb68bd/report_timing/instrec_top.rtr` | 逐域时序与最差路径 |
| `build/instrec-latest.sbit` / `.json` | 本轮位流与 manifest |
| `releases/m4-20261031/` | 归档（见 §7） |
| `build/evidence/*` | 工作区回退事故证据 |
| `reports/ddr3_diag_conclusion.md` | 两轮 DDR3 诊断（F-2 的定位与验证） |
| `reports/build_20261031-135808-f1cb68bd.pds.stdout.log` | 归档日志 |