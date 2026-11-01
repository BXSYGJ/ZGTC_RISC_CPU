# m5 · DDR3 自检首次 board-proven（2026-11-01）

## 这份归档证明什么

**R1（DDR3 自检）已达成，且是板上证明，不是仿真推断。**

`top_core_only` 是 `instrec_top` 的精简顶层：裁掉 UI 渲染四层与 HDMI（M3 已由独立位流 `top_ui_demo`
板级 PASS），保留 `ddr3_wrapper` + `ddr3_ctrl_axi` + `sys_ctrl`(含 T21 观测链) + `uart_debug` +
`self_test`。目的是把 LUT 降回可布通区（全量 34960 已停滞，见 `build/stall_evidence/`）。

## 关键证据

| 项 | 值 |
|---|---|
| 位流 | `instrec_core_only_ddrok.sbit`（3791112 B） |
| SHA-256 | `d375a43dba3d5db68285cdba3c5158413379510ea53d29ea8baec17f4c4e18a8` |
| 构建 run | `build/pds/20261101-052101-1d885ad2`（六阶段全 OK，`Unrouted nets 0 @ iter 77`） |
| 资源 | LUT 6806/66600 (10%)、FF 7738、**APM 0**、DRM 0、IO 85 |
| 板级 JSON | `board_core_only.json`：`verdict=PASS`、`expect_missing=[]`、`status_raw=0x081ffca0`、`uart_bytes=48` |

串口原文（48 字节，两次烧录逐字节一致）：

```
INSTREC BOOT
DDR3 SELFTEST...
DDROK
DDR3 STS 01
```

`DDR3 STS 01` = `{cmd_to_err[3], to_err, dbg_to_state, st_fail, st_done}` 的低位 →
`st_done=1`、`st_fail=0`、`to_err=0`、无超时位 ⇒ **self_test 的 8 段写 + 8 段读回全部通过**。

## 这份归档**不能**证明什么（必须限定）

- **APM = 0**：本版把音频前端与 PCM 源接成常量（`fifo_empty=1'b0`、无 I2S 输入），导致
  `win_tick` 永不产生 → `mel_engine` 常 idle → `npu_start` 恒 0 → 常量传播把 Mel 与 NPU 数据通路
  整块优化掉。**所以它只能证明 DDR3，不能证明 NPU / Mel。**
- 后续恢复音频前端的版本（`67224B04…`，LUT 32615 / **APM 89**）反而 **FAIL**：
  `DDR3 STS 26 = 0b0010_0110` → `st_fail=1`、`dbg_to_state=001`(S_AW)、`to_err=1`。
  即 **m3 在 AW 阶段 4096 拍超时**——多 master（m0 audio、m2 mel）活跃时 AW 通道竞争导致，
  正在按 `reports/multi_master_aw_timeout.md` 定位。

## 为什么 `DRM = 0` 不等于 DDR3 PHY 缺失（一处早前的误判，已纠正）

`DRM` 是**通用分布式 RAM**；DDR3 PHY 在本器件上用**专用硬核块**。`pds.stdout.log` 实测：
`DDR_PHY 7/24`、`DDRPHY_CPD 1/12`、`DDRPHY_IOCLK_DIV 2/6`、`PPLL 2/6`、`TSERDES 14/48` —— 全在网表中。
全量的 `DRM 86` 来自 `npu wdma` 参数表 + `audio_sink` 波形列 RAM + UI `feat_page_buf`，与 PHY 无关。

同理 `IO 85` 也不是「pad 少了」：85 = 119 − (vout 28 + iic 2 + i2s 3 + key1_n 1)，
`mem 71 + ref_clk 2 + clk/rst_n/uart×2/led 8 = 85`，73 个 DDR3 pad 一个没少。

## 相关

- `reports/core_only_conclusion.md` — 该顶层的裁剪清单与结论
- `reports/sim_ddr3_conclusion.md` — DDR3 子系统 15 场景仿真（控制器逻辑 PASS）
- `build/stall_evidence/flow_20261031-222313.log` — 全量 34960 LUT 停滞证据