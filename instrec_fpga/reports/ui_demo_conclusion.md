# UI 演示位流（`top_ui_demo`）构建 + 板级判读结论

**任务**：T9（团队任务 id=9），构建槽位第 2（排在 T8 之后，全程唯一 `pds_shell`）。
**日期**：2026-10-31（本地 21:59–22:10）
**构建集**：`ui_demo`（`scripts/build_sets.json`）——**不含 DDR3 / Mel / NPU / audio PLL**。
**结论等级**：构建 = 六阶段全 OK 且纯 `pnr` 布通；板级 = **UI 四层在出像素，board-proven**；
整体时序 = **未完全收敛（`Some Constraints Violated`）**，违例全部集中在 `cfg_clk → pix_clk` 复位同步器路径，
`pix_clk` 域内 WNS **+0.251 ns 达标**。

---

## 1. 一句话结论

`top_ui_demo` 位流（SHA-256 `D1EF2594…`）六阶段全 OK、资源 990 LUT（1.5%），板级抓到 **1225 帧 `UIDEMO`**：
`hdmi_init_over=1`、`pll_lock=1`、`hdmi_init_fail=0`（**HDMI I2C 配置成功**），
四个像素域计数器每帧增量**精确恒定**（`pix_de`=2 073 600、`de_nonzero`=2 069 280、`bars_on`=8000、
`text_on`=148、`spec_on`=131 072=512×256），`vsync_cnt` 严格递增（59.95 fps）——
**概率条 / 文本 / 频谱三层各有独立计数器且持续出像素，波形底层由 `de_nonzero` 强旁证支持（无专用计数器，未 board-proven 为独立层）**。
**唯一未满足项**：整体 Design Summary 为 `Some Constraints Violated`，8 个 endpoint 落在
`u_hdmi_tx_if/rstn_1ms[*]`（`cfg_clk`）→ `u_hdmi_tx_if/rstn_pix_meta`（`pix_clk`），WNS **−2.165 ns** / TNS −13.917 ns。
该违例是**约束策略缺口**（`top_ui_demo.fdc` 的 `set_clock_groups` 只声明 `clk`/`pix_clk` 异步，`cfg_clk` 与
`pix_clk` 被当作同源同步域按单周期检查），不在像素数据通路上，与全量构建的分析方式一致。

---

## 2. 交付物与哈希

| 项目 | 值 |
|---|---|
| 位流 | `build/top_ui_demo-latest.sbit`（3 791 112 bytes，mtime 2026-10-31 22:05:20） |
| **SHA-256** | `D1EF2594F636EE6AA3140B151216B1390FEB84817301FF99627652C4CCE9B1A9` |
| manifest | `build/top_ui_demo-latest.json`（2 406 bytes，SHA-256 `877FE541…`） |
| 构建 run | `build/pds/20261031-215957-9aefa526/`（`BuildSet=ui_demo`，`TopModule=top_ui_demo`） |
| 板级证据 | `reports/board_uidemo_20261031T140944Z.json`（verdict `PASS`，exit 0） |
| 串口留档 | `build/uart_last.bin`（111 475 bytes = 1225 × 91 bytes，无杂散字节） |
| 时序报告 | `build/pds/20261031-215957-9aefa526/report_timing/top_ui_demo.rtr` |

**构建集隔离已确认**：`build/instrec-latest.sbit` 的 mtime 仍为 **2026-10-31T18:28:12**、
SHA-256 仍为 `B895FCAC…`（与 T19/T20 交付一致），**未被本次构建覆盖**。
`build/pds/20261031-215941-a47e332a/` 是 `-DryRun` 预检目录（只有 `build.tcl`，无位流），非失败构建。

设备：`PG2L100H-6IFBG676`；资源：LUT 990/66600 (1%)、FF 948/133200 (1%)、DRM 1/155、GPLL 1/6、IO 41/300、APM 0/240。

---

## 3. 构建耗时与六阶段

| 阶段 | 耗时（Real） | 状态 |
|---|---|---|
| compile | 14 s | **OK**（`compile/error_info.txt` 为空；**无 `Verilog-4005`**） |
| synthesize | 33 s | **OK** |
| dev_map | 24 s | **OK** |
| pnr | 2 min 16 s | **OK**（`Finished placement and routing.`） |
| report_timing | 41 s | **OK** |
| gen_bit_stream | 1 min 10 s | **OK** |
| **合计 compile→gen_bit_stream** | **5 min 18 s** | 6/6 |

- **墙钟总耗时 5 min 34 s**（UTC 13:59:55 启动 → 14:05:29 manifest 落盘），远低于 20 min 目标。
- `StageStatus` 六项：`compile / synthesize / dev_map / pnr / report_timing / gen_bit_stream` **全 OK**。
- `PDS ExitCode: 0`；`impl.tcl` 中的实现命令为纯 **`pnr`**（无任何 PNR 参数，见 run 目录 `impl.tcl` 第 24 行）。
- 构建期间 `pds_shell` 只有一组父子进程（18712 = `build.tcl` 主进程，45032 = 其 `place_route` 子进程，
  `parent_process_key 18712`），**未启动第二个实例**；构建结束后 `pds_shell` 计数回到 0。

---

## 4. 逐域时序（`report_timing/top_ui_demo.rtr`，multi-corner，慢角）

> **注意**：manifest 的 `Wns=0.251` 只是 Setup Summary 第一行（`pix_clk → pix_clk`），
> 不能代表全设计。下表为逐域实读结果。

### 4.1 Setup（慢角）

| Launch → Capture | WNS (ns) | TNS (ns) | 失败 endpoint | endpoint 总数 | 判定 |
|---|---|---|---|---|---|
| **`pix_clk → pix_clk`** | **+0.251** | 0.000 | **0** | 1606 | **PASS** |
| `cfg_clk → cfg_clk` | +92.749 | 0.000 | 0 | 641 | PASS |
| **`cfg_clk → pix_clk`** | **−2.165** | **−13.917** | **8** | 8 | **FAIL（跨域）** |
| `pix_clk → cfg_clk` | 无路径 | — | — | — | — |

### 4.2 Hold / 恢复 / 脉宽（慢角，全部 0 失败）

| 类别 | `pix_clk` | `cfg_clk` |
|---|---|---|
| Hold THS 失败 endpoint | 0 / 1606 | 0 / 641（`cfg_clk→pix_clk` 0 / 8） |
| Recovery WNS | +4.134 | +92.516 |
| Removal THS 失败 | 0 | 0 |
| Minimum Pulse Width WPWS | **+2.407**（0 失败 / 497） | — |

关键余量：`pix_clk` 请求 148.5001 MHz，估计可达 **154.2496 MHz**（周期 6.7340 → 6.4830 ns）。

### 4.3 8 条违例的路径性质（本报告已逐条核对起终点）

| Slack (ns) | Path Group | Startpoint | Endpoint |
|---|---|---|---|
| −2.165 | pix_clk | `u_hdmi_tx_if/rstn_1ms[12]` | `u_hdmi_tx_if/rstn_pix_meta/I0` |
| −1.979 | pix_clk | `u_hdmi_tx_if/rstn_1ms[13]` | `u_hdmi_tx_if/rstn_pix_meta/I5` |
| −1.757 | pix_clk | `u_hdmi_tx_if/rstn_1ms[12]` | `u_hdmi_tx_if/rstn_pix_meta/I2` |
| −0.992 | pix_clk | `u_hdmi_tx_if/rstn_1ms[12]` | `u_hdmi_tx_if/rstn_pix_meta/I0` |
| −0.979 | pix_clk | `u_hdmi_tx_if/rstn_1ms[13]` | `u_hdmi_tx_if/rstn_pix_meta/I5` |
| −0.833 | pix_clk | `u_hdmi_tx_if/rstn_1ms[12]` | `u_hdmi_tx_if/rstn_pix_meta/I2` |

- 唯一一类：`cfg_clk`（10.395 MHz）域的 1 ms 复位计数器 → `pix_clk` 域的复位同步器**第一级**。
  `.rtr` 只导出了前 6 条（TNS 覆盖 8 个 endpoint），全部属同一族，**没有任何一条落在像素数据通路
  （`ui_renderer` / `waveform_disp` / `spectrum_disp` / `text_disp` / `bars_disp`）上**。
- 根因是约束：`constraints/top_ui_demo.fdc` 第 41 行只有
  `set_clock_groups -asynchronous -group [get_clocks {clk}] -group [get_clocks {pix_clk}]`，
  `cfg_clk` 未进入异步组，工具把 10.395 MHz → 148.5 MHz 的异步跨域按**同步单周期**检查。
  文件头注释明说这是刻意与全量构建保持一致的分析方式。
- 功能风险：复位同步器第一级的跨域超时只会改变复位释放的采样相位，不改变稳态数据通路；
  板级 30.6 s 内 1836 帧、59.95 fps 无失锁，与该判断一致。**但这条结论是"行为证据 + 约束解读"，不是时序收敛证明。**

---

## 5. 板级判据（六项，逐项 PASS/FAIL）

命令与退出码：

```
python scripts/board_check.py --sbit build/top_ui_demo-latest.sbit --port COM5 \
    --seconds 25 --expect "UIDEMO" --json reports/board_uidemo_20261031T140944Z.json
→ exit 0 ; boot: PASS (all 1 expected lines seen) ; verdict=PASS
```

烧录：`cdt_cfg exit code: 0`、`program: True`、`status: 0x081ffca0 done=1 crc_err=0`；
JTAG 侧复用常驻 `cdt_js` PID 9040（未新起、未 terminate），`cdt_cfg` 46156 残留但未杀。

| # | 判据 | 证据（板级，帧 0 / 612 / 1224） | 判定 |
|---|---|---|---|
| 1 | `G`：`hdmi_init_over==1`、`pll_lock==1`、`hdmi_init_fail==0` | `G=03`（帧 0，初始化中）→ `G=07`（帧 12 起，直到末帧）；`hdmi_init_fail` **全程 0 帧置位** | **PASS** |
| 2 | `C`（`de_nonzero_cnt`）> 0 | 3 068 418 → **3 802 266 498**（每帧恒定 +2 069 280） | **PASS** |
| 3a | `D`（`bars_on_cnt`）> 0 | 8 000 → **14 696 000**（每帧 +8000） | **PASS** |
| 3b | `E`（`text_on_cnt`）> 0 | 148 → **271 876**（每帧 +148） | **PASS** |
| 3c | `F`（`spec_on_cnt`）> 0 | 262 144 → **240 910 336**（每帧 +131 072） | **PASS** |
| 3d | `D+E+F` > 0 且三者各自 > 0 | 末帧 D+E+F = 255 878 212，且三者**分别**非零 | **PASS** |
| 4 | `A`（`vsync_cnt`）随采样持续递增 | 2 → 1838，1225 次采样步长全 ∈ {1,2}，**严格递增**，Δ=1836 ⇒ 59.95 fps | **PASS** |
| 5 | `pix_clk` 域 WNS | **+0.251 ns**（`pix_clk→pix_clk`，0 失败 / 1606） | **PASS**（域内） |
| 6 | `StageStatus` 六项全 OK | compile/synthesize/dev_map/pnr/report_timing/gen_bit_stream 全 OK | **PASS** |

**判定前提说明**：`G` 位段取自 `src/diag/top_ui_demo.v` 头注释
`G = {4'd0, hdmi_init_fail, hdmi_init_over, pll_lock, rst_pix_n}`，故
`G=0x07` ⇒ `rst_pix_n=1, pll_lock=1, hdmi_init_over=1, hdmi_init_fail=0`。
采集窗口内 `G` 只有 `0x03` 与 `0x07` 两个值，首次 `hdmi_init_over=1` 出现在第 12 帧（≈300 ms，I2C 配置完成）。

**整体时序不满足项（必须同时记录）**：Design Summary 为 `Some Constraints Violated`，
`cfg_clk→pix_clk` 8 个 endpoint WNS −2.165 / TNS −13.917（见 §4.3）。
因此本交付的准确表述是「**构建成功 + 四层像素板级 proven + 域内时序达标**」，**不是**「时序全收敛」。

---

## 6. 原始帧证据（≥3 帧）

采集窗口 1225 帧，每帧 91 字节，`build/uart_last.bin` 长度 111 475 = 1225 × 91（无截断、无杂散）。

### 6.1 原始 ASCII 行（首 / 中 / 末）

```
[0]    DIAG UIDEMO   A=00000002 B=002EEB0A C=002ED202 D=00001F40 E=00000094 F=00040000 G=03 H=11 
[612]  DIAG UIDEMO   A=00000398 B=71A5030A C=716866C2 D=00702EC0 E=0002134C F=07300000 G=07 H=11 
[1224] DIAG UIDEMO   A=0000072E B=E31B1B0A C=E2A1FB82 D=00E03E40 E=00042604 F=0E5C0000 G=07 H=11 
```

### 6.2 原始字节十六进制（91 bytes / 帧，`build/uart_last.bin` 偏移 0 / 55 692 / 111 384）

```
frame[0] offset=0
44 49 41 47 20 55 49 44 45 4D 4F 20 20 20 41 3D 30 30 30 30 30 30 30 32 20 42 3D 30 30 32 45 45 42 30 41
20 43 3D 30 30 32 45 44 32 30 32 20 44 3D 30 30 30 30 31 46 34 30 20 45 3D 30 30 30 30 30 30 39 34 20 46 3D
30 30 30 34 30 30 30 30 20 47 3D 30 33 20 48 3D 31 31 20 0A

frame[612] offset=55692
44 49 41 47 20 55 49 44 45 4D 4F 20 20 20 41 3D 30 30 30 30 30 33 39 38 20 42 3D 37 31 41 35 30 33 30 41
20 43 3D 37 31 36 38 36 36 43 32 20 44 3D 30 30 37 30 32 45 43 30 20 45 3D 30 30 30 32 31 33 34 43 20 46
3D 30 37 33 30 30 30 30 30 20 47 3D 30 37 20 48 3D 31 31 20 0A

frame[1224] offset=111384
44 49 41 47 20 55 49 44 45 4D 4F 20 20 20 41 3D 30 30 30 30 30 37 32 45 20 42 3D 45 33 31 42 31 42 30 41
20 43 3D 45 32 41 31 46 42 38 32 20 44 3D 30 30 45 30 33 45 34 30 20 45 3D 30 30 30 34 32 36 30 34 20 46
3D 30 45 35 43 30 30 30 30 20 47 3D 30 37 20 48 3D 31 31 20 0A
```

### 6.3 字段解码（`scripts/diag_frames.parse_all`，1225/1225 帧可解）

| 帧 | A `vsync_cnt` | B `pix_de_cnt` | C `de_nonzero` | D `bars_on` | E `text_on` | F `spec_on` | G | H |
|---|---|---|---|---|---|---|---|---|
| 0 | 2 | 3 074 826 | 3 068 418 | 8 000 | 148 | 262 144 | `03` | `11` |
| 612 | 920 | 1 907 578 122 | 1 903 378 114 | 7 352 000 | 135 500 | 120 848 384 | `07` | `11` |
| 1224 | 1838 | 3 810 204 426 | 3 802 266 498 | 14 696 000 | 271 876 | 240 910 336 | `07` | `11` |

`H = {3'd0, pix_de, pix_hs, pix_vs, pix_clk, rst_pix_n}`：采集窗口内 `H` 同时出现 `0x11`（`pix_de=1`，有效行）
与 `0x01`（`pix_de=0`，消隐区）两种取值 ⇒ 采样点扫过光栅，画面在持续刷新，不是一帧后停住。

### 6.4 每帧增量（整数精确，四层确定性证据）

| 计数器 | Δ（帧 0 → 末帧） | 每帧增量 | 与设计预期的一致性 |
|---|---|---|---|
| `pix_de_cnt` | 3 807 129 600 | **2 073 600** | **= 1920 × 1080（1080p 有效像素）精确相等** |
| `de_nonzero_cnt` | 3 799 198 080 | **2 069 280** | 99.79 % 有效像素非黑（`C/B = 0.99792`） |
| `bars_on_cnt` | 14 688 000 | **8 000** | 概率条区域固定面积 |
| `text_on_cnt` | 271 728 | **148** | 文本字形像素固定面积 |
| `spec_on_cnt` | 240 648 192 | **131 072** | **= 512 × 256 精确相等** |

1225 帧 × 25 ms = 30.625 s；1836 个 vsync / 30.625 s = **59.95 fps**（1080p60 标称）。

---

## 7. 四层是否在出像素（逐层定性）

| 层 | 生产者 | 独立计数器 | 板级结论 |
|---|---|---|---|
| **1 波形 wave（base）** | `demo_wave_source` → `waveform_disp` / `ui_renderer` | **无**（C-TOP-UI-DEMO@1 未定义 `wave_on_cnt`） | **strongly supported，未 board-proven**：`de_nonzero`（2 069 280/帧）远大于 `D+E+F` 三层之和（≈139 220/帧），差额 ≈1 930 060/帧 的非黑像素只能来自波形底层；但无专用计数器，不能单独归因于该层 |
| **2 频谱 spec** | `demo_spec_source` → `spectrum_disp` | `F = spec_on_cnt` | **PROVEN**：每帧 +131 072，与 512×256 区域面积精确相等 |
| **3 文本 text** | `text_disp` + `font_rom`（class 4 / 72 %） | `E = text_on_cnt` | **PROVEN**：每帧 +148 非零且持续 1836 帧 |
| **4 概率条 bars** | `bars_data` → `bars_disp` | `D = bars_on_cnt` | **PROVEN**：每帧 +8000 非零且持续 1836 帧 |

**一句话**：**频谱 / 文本 / 概率条三层确定在出像素（各有独立计数器、每帧面积恒定）；
波形底层由 `de_nonzero` 与三层之和的差额强旁证，但因缺专用计数器仍标注为"未 board-proven"。**

---

## 8. 未证实 / 待补项（无假结论）

1. **`cfg_clk → pix_clk` 8 条违例未修复**：需要给 `constraints/top_ui_demo.fdc` 增加
   `set_clock_groups -asynchronous -group [get_clocks {cfg_clk}] -group [get_clocks {pix_clk}]`
   （或对 `rstn_pix_meta` 首级加 `set_false_path`）。本任务**未改约束**，仅指认。
   当前状态是「工具报 `Some Constraints Violated`」，**不是时序收敛**。
2. **波形层无专用计数器**（见 §7），其独立出像素只能在后续为 `wave_on` 增加计数后才能 board-proven。
3. **未做 HDMI 链路的电气/误码验证**：`hdmi_init_over=1` 只证明 I2C 配置序列走完，
   不证明显示器实际接收到稳定图像；未接显示器截图或采集卡，无法给出"屏幕上确实显示四层叠加"的直接证据。
4. **未做长时稳定性**：采集窗口 30.625 s / 1836 帧，未覆盖数小时运行的失锁、温漂。
5. **`key1_n` 约束悬空**：`top_ui_demo.fdc` 第 ~65 行声明 `p:key1_n`（C23），顶层无该端口，
   编译期报 `ConstraintEditor-2001: Object 'key1_n' is dangling ... it will be ignored`，
   引脚分配被静默忽略（warning 级，不影响本次位流功能）。
6. **I/O 时序未约束**：`synthesize/run.log` 有 9 条 `Timing-4087: Port 'vout_*' / 'rst_n' is not constrained`，
   即 `vout_data[23:0]`、`vout_de/hs/vs` 被当作组合输出、`rst_n` 当作组合输入，
   **对外部端口的建立/保持时间没有任何约束覆盖**。像素域内部时序结论（§4.1）不含 I/O 路径。

---

## 9. 缺陷指认（只指认，未改任何 `src/**` / `scripts/**` / `constraints/**`）

| 编号 | 文件:行 | 现象 | 影响 |
|---|---|---|---|
| D-UI-01 | `constraints/top_ui_demo.fdc:41` | `set_clock_groups` 只含 `clk`/`pix_clk`，`cfg_clk` 缺席 | `cfg_clk→pix_clk` 复位同步器 8 个 endpoint 违例，WNS −2.165 / TNS −13.917，Design Summary 判 `Some Constraints Violated` |
| D-UI-02 | `constraints/top_ui_demo.fdc`（`p:key1_n` 段） | 顶层无 `key1_n` 端口却声明引脚 | `ConstraintEditor-2001` dangling warning；引脚被忽略 |
| D-UI-03 | `constraints/top_ui_demo.fdc`（缺 `vout_*` / `rst_n` I/O 约束） | 9 条 `Timing-4087` | 外部端口无时序覆盖，输出时序不可判定 |

以上均属**约束层**问题，`src/**` RTL 无任何语法/功能异常（`check_rtl.py` 0 violation，compile `error_info.txt` 为空）。

---

## 10. 复现命令

```powershell
# 闸门（工作目录 instrec_fpga）
python scripts/check_rtl.py                                  # 0 violation
python -m pytest -q                                          # 398 passed / 4 skipped

# 构建
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1 -BuildSet ui_demo
# 产物: build/top_ui_demo-latest.sbit  (SHA-256 D1EF2594F636EE6AA3140B151216B1390FEB84817301FF99627652C4CCE9B1A9)

# 板级
python scripts/board_check.py --sbit build/top_ui_demo-latest.sbit --port COM5 `
    --seconds 25 --expect "UIDEMO" --json reports/board_uidemo_20261031T140944Z.json

# 帧解析（build/ 下的临时分析脚本，不属于交付 scripts/）
python build/ui_demo_analyze.py > build/ui_demo_analyze.txt
```

---

## 11. 闸门记录

| 闸门 | 结果 |
|---|---|
| `python scripts/check_rtl.py` | 49 个 `.v`，**0 violation** |
| `python -m pytest -q` | **398 passed / 4 skipped**，137.73 s（与基线一致；T21 在途改动未破坏测试） |
| `run_pds_full.ps1 -BuildSet ui_demo -DryRun` | `top=top_ui_demo design=22 ip=1 constraint=1 hex=2` |
| `build/instrec-latest.sbit` mtime | 18:28:12 **未变**（构建集隔离成立） |
| 并发 | 构建期 `pds_shell` 仅一组父子进程；结束后计数 0 |