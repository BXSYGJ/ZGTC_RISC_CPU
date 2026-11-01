# m4-20261031 · InstRec 全功能位流（DDR3 自检修复后首次全量）

## 1. 位流

| 项 | 值 |
|---|---|
| 文件 | `instrec.sbit`（3 791 112 B） |
| **SHA-256** | **`44E8F011D44E10254E33BCBE4622BEB3F53966894C00BD1962BE9420414D476C`** |
| 设备 | PG2L100H-6IFBG676 |
| 顶层 | `instrec_top` |
| 项目名 | `instrec_top_pds`（`-project_name` 由 `build_sets.json` 的 `full` 集给出；m3d 时代为 `instrec_fpga`） |
| run 目录 | `build/pds/20261031-135808-f1cb68bd/` |
| 构建墙钟 | 2026-10-31 13:58:06 → 16:00:57 = **2 h 02 m 51 s**（PDS 自报 compile→gen_bit_stream 2h2m31s） |
| 构建集 | `full`（`build_sets.json` 的 `full`，源集与 m3d 逐文件等价 + T2 的 `self_test.v` 修复） |

`SHA256SUMS` 与本文件同级，内容：`44e8f011…d476c *instrec.sbit`。

## 2. 六阶段

| Stage | Status |
|---|---|
| compile | OK |
| synthesize | OK |
| dev_map | OK |
| pnr | OK（**纯 `pnr`，无任何参数**，E-2 满足） |
| report_timing | OK |
| gen_bit_stream | OK |

## 3. 布线判定

- `Unrouted nets 0 at the end of iteration **636**`（route iteration 636）
- `Design 'instrec_top' has been placed and routed successfully.`（`pds.stdout.log`）
- 收敛过程无停滞：48068@iter8 → 41875@iter10 → 17933@iter34 → 9761@iter63 → 5202@iter107 → 2619@iter170 → 1376@iter275 → 244@iter477 → 0@iter636
- 与 m3d 对比：m3d 510 轮布通，本轮 **636 轮**（+126 轮，同属"慢但收敛"）

## 4. 逐域时序（Setup, Slow Corner，WNS 单位 ns）

| 时钟域 | 频率 | m4 WNS | m3d WNS | 变化 | TNS | failing endpoints |
|---|---|---|---|---|---|---|
| `clk_nco` | 216.0002 MHz | **+0.523** | +1.347 | **-0.824** | 0.000 | 0 |
| `pix_clk` | 148.5001 MHz | **+0.556** | +0.018 | **+0.538** | 0.000 | 0 |
| `cfg_clk` | 10.3950 MHz | **+92.287** | +89.809 | +2.478 | 0.000 | 0 |
| `rst_clk` | 125.0000 MHz | **+4.227** | +3.463 | +0.764 | 0.000 | 0 |
| **`ddrphy_sysclk`** | 125.0000 MHz | **-1.740** | **-0.966** | **-0.774** | **-124.797** | **482**（m3d 175） |

Hold / Recovery 全正：`ddrphy_sysclk` WHS +0.116、Recovery +0.066；其余域 WHS +0.159…+0.347。

> `build/instrec-latest.json` 的 `Wns` 字段是 **+0.523**，那是脚本按 `Setup Summary` **第一行**（`clk_nco`）取值，**不是**全局最差域；真正最差域是 `ddrphy_sysclk` **-1.740**。判收敛必须逐域看。

### `ddrphy_sysclk` 最差路径（m4）

- Startpoint（时钟链）：`ddr3_wrapper/refclk_inbuf → clkbufm → ppll → ioclkdiv → gpll → u_sysclk_bufg → HCKBROUTE_30` → `core_clk`
- 数据段：`u_weight_loader/beat_buf[7][212] → m1_wdata[212] → u_weight_loader/acc2[28]`
- Data arrival 14.940 ns；**Logic 1.079 ns (11.5%)、Route 8.311 ns (88.5%)**
- 结论：**本轮最差路径落在用户逻辑 `weight_loader` 的长走线上（88.5% 是布线延迟），不是 IP 内部**——与 m3d（最差在 `ddrphy_reset_ctrl`/`ddrphy_data_slice_wrlvl` 的 IP 内部）不同。T10 不允许改 `weight_loader`，故仅记录为风险。

## 5. 资源

| 资源 | m4 | m3d | 差 |
|---|---|---|---|
| **LUT** | **34407/66600 = 51.66%** | 34327 (51.54%) | **+80** |
| FF | 52193/133200 = 39% | 52191 | +2 |
| **DRM** | **86/155 = 55.48%** | 86 (55.48%) | 0 |
| Distributed RAM | 1501/19900 = 8% | 1501 | 0 |
| APM | 90/240 = 38% | 90 | 0 |
| BKCL | 6/6 = 100% | 6 | 0 |
| GPLL / PPLL | 4/6、2/6 | 4/6、2/6 | 0 |
| HCKB | 32/96 = 34% | 27 | +5 |
| USCM | 11/32 = 35% | 9 | +2 |
| IO | 119/300 = 40% | 119 | 0 |

- **LUT 51.66% ≤ 53.57%（历史布通上限）✔**，余量 **1.91 个百分点**（约 1271 LUT）。
- 不是"运气布通"：本轮 636 轮**稳定收敛到 Unrouted 0**，且资源与 m3d 几乎逐项相同（+80 LUT 来自 `assign st_wready_beat` 一根线 + T2 `self_test` 修复）。

## 6. 与 m3d 的差异（唯一改动）

`src/ctrl/instrec_top.v`，**+6 行 / 0 删除**（1 行有效代码 + 5 行注释）：

```verilog
// master-3 write-beat pulse (C-SELFTEST@1 F2/S1/S2).  Without this tap
// PDS reports "Verilog-2036: Net st_wready_beat ... has no driver, tie
// it to 0"; self_test then never sees a beat handshake and the first
// write command aborts with st_fail at SELFTEST_BASE.
assign st_wready_beat = ddr_wready_beat[3];
```

另含 T2 交付的 `src/ctrl/self_test.v`（+71/-8，done/hold 修复），为本次全量的必需前置，不计入 T10 的改动。

## 7. 复现

```powershell
cd instrec_fpga
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_pds_full.ps1
```

产物：`build/pds/<run>/generate_bitstream/instrec_top.sbit`、`build/instrec-latest.{sbit,json}`。

## 8. 板级验证

本归档**未做板级验证**（T10 只构建）。下一步 T11：`board_check.py --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"`，再 `weight_upload.py` 看 `WOK`。