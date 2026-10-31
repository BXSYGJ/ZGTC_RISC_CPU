# InstRec-FPGA M3d 位流归档（2026-10-31）—— 全功能版

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676）
- 来源 run：`20261031-085308-2a717fbf`
- SHA-256：`0B2BE8D4116551D14D26608FF4369508A1B52052BD99940F29EB84FA156E7357`
- 布线：`Unrouted nets 0` at **iteration 510**，`placed and routed successfully`

## 这是第一个「功能齐全」的位流

音频 I2S → DDR3 → Mel 引擎 → NPU 全链（单 conv 共享核 + MAC 流水 + requant 四部分积）
→ **概率条 + 波形 + 类别文字 + 谱图** 四层 UI 全部接线生效；
UART 文本已修复（字符间隔计数器）；wdma 参数表已块 RAM 化。

## 资源与时序

| 指标 | 值 |
|---|---|
| LUT | **34327 / 66600（52%）** |
| DRM | **86 / 155（56%）** |
| FF | 52188（39%） |
| APM | 90 / 240（38%） |
| `ddrphy_sysclk` (125 MHz) | **-0.966 ns**（本设计最好） |
| `pix_clk` (148.5 MHz) | **+0.018 ns（转正）** |
| `clk_nco` (216 MHz) | +1.347 ns |
| `rst_clk` / `cfg_clk` | +3.463 / +89.809 |

## 关键经验（写进 STATUS）

- **布线收敛不是「轮次问题」**：m3c（LUT 52.26%）用 1426 轮，m3d（52.16%）只用 510 轮，
  DRM 还多了 6 个 —— 差别全在布局落在哪个解上，而这由 LUT 总量与结构决定。
- **降密度是真的解法**：wdma 参数表块 RAM 化把 LUT 从 35677 降到 34046，
  之后每一次加功能都能布通；加文字层 +377 LUT 曾让轮次翻倍到 1426，
  但再加谱图层（相比 m3c 只 +76 LUT）反而只要 510 轮。
- **纯 `pnr` 是唯一可靠配置**，任何 `-parallel`/`-gplace_seed`/`-decongestion`/`-duplication`
  都会把布局拖进拥塞解。

## 板级状态

FTDI 仍为 `CM_PROB_PHANTOM`，无法烧录。四版位流已按能力递增归档：
m3a（wdma）/ m3b（+UART）/ m3c（+文字）/ **m3d（+谱图，全功能）**。
设备恢复后直接烧 m3d，用
`python scripts/board_check.py --sbit releases/m3d-20261031/instrec_top.sbit --seconds 15 --expect "INSTREC BOOT" "DDR3 SELFTEST" "DDROK"`
验证启动，再 `weight_upload.py` 看 `WOK`。

校验：`sha256sum -c SHA256SUMS`。
