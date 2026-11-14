# seed85-timing-20261114 — 时序最优位流（种子 85）

**一句话**：这是通宵种子扫描里 WNS 最好的一版，`ddrphy_sysclk` 域 setup 从
−1.234 ns 提到 **−0.809 ns**，失败端点 761 → 352，且上板功能三项全过。

## 位流

- 文件：`artifacts/instrec_top_seed85.sbit`
- SHA-256：`88E10B450CB8657321AD8BDB136F8E395EF48C555BA2DB4C030671ED339FA7FD`
- 构建集：`full`（top `instrec_top`）
- 构建目录：`build/pds/20261114-012325-71b4e17d`（不入库）
- 构建参数：`run_pds_full.ps1 -BuildSet full -PlacementSeed 85`
- 构建时间：1 h 12 m 58 s，六阶段全 OK，`Unrouted 0`

## 时序

| 时钟域 | WNS (setup, slow) | 失败端点 |
|---|---|---|
| `clk` | +33.987 ns | 0 |
| `pix_clk` | +0.128 ns | 0 |
| `ddrphy_sysclk` | **−0.809 ns** | 352 |

hold：`ddrphy_sysclk` WHS **−0.117 ns / 2 端点**（这是代价，见 STATUS 2026-11-14 条目）。

## 种子扫描结果（同一 RTL）

| 种子 | WNS | WHS | 结论 |
|---|---|---|---|
| 7   | −1.234 | +0.050 | 前基线 |
| 40  | −1.902 | +0.017 | 更差 |
| 55  | −1.479 | +0.137 | 更差 |
| 70  | −1.597 | +0.008 | 更差 |
| **85** | **−0.809** | −0.117 | **胜出** |
| 100 | 布不通 | — | 看门狗终止 |
| 115 | 布不通 | — | 看门狗终止 |

## 上板验证

- DDR3 自检 pattern 3/3 逐位一致
- mel 与 golden：**exact 100%、max|d|=0、corr 1.0000**
- 同窗口 NPU：板级 logits `[-28,7,6,-16,17,7,-34,3]` 与 golden **8 个通道完全相同**，top1 均 class4

## 复现

```powershell
pwsh -NoProfile -File scripts/run_pds_full.ps1 -BuildSet full -PlacementSeed 85
```

烧录：

```powershell
python scripts/flash_bitstream.py --sbit releases/seed85-timing-20261114/artifacts/instrec_top_seed85.sbit
```
