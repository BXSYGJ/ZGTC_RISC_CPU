# InstRec-FPGA M3c 位流归档（2026-10-31）—— 含 M3 文字层

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676）
- 来源 run：`20261031-064542-c94db505`
- SHA-256：`482CCA1C1B481EC30A402D3926D4F5894F80F19621257DD073E611F15A779F36`
- 布线：`Unrouted nets 0` at **iteration 1426**，`placed and routed successfully`

## 相对 m3b 的变化

按「分步加回」计划补上 **M3 文字层**（`text_disp` + `font_rom`，LUT-only，不占 DRAM）：
`ui_renderer` 的 `text_rgb/text_on` 从常量改回真实信号，`ui_overlay` 的文字层生效。

| 指标 | m3b | m3c |
|---|---|---|
| LUT | 34046 (51.1%) | **34423 (52%)** |
| DRM | 79.5 | **80.0** |
| 布线收敛 | iteration 695 | iteration 1426 |
| `ddrphy_sysclk` | -1.511 | **-1.280** |
| `pix_clk` | -0.298 | **+0.113（转正）** |

文字层只增加 377 LUT / 0.5 DRAM，但让布线轮次翻倍（695→1426）——再次印证
「每加一点都在逼近临界点」，所以下一层（谱图，需 +6.5 DRAM）必须单独一轮验证。

## 功能范围

音频 I2S → DDR3 → Mel 引擎 → NPU 全链（单 conv 共享核 + MAC 流水 + requant 四部分积）
→ 概率条 + 波形 + **类别文字**。UART 文本已修复（字符间隔计数器）。
**仍缺**：谱图（`spectrum_disp` + `feat_page_buf` + `feat_copy_engine`）。

## 板级状态

FTDI 下载器仍为 `CM_PROB_PHANTOM`（不在 PnP），m3a/m3b/m3c 三版位流都已归档，
设备恢复后按顺序烧：m3c（最全）→ 看 `INSTREC BOOT` → `weight_upload` 看 `WOK`。

校验：`sha256sum -c SHA256SUMS`。
