# InstRec-FPGA M2c 位流归档（2026-10-29）

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676，顶层 `instrec_top`）
- 来源 run：`20261029-172919-3b0485f3`（六阶段 OK，compile→位流 1h29m52s）
- SHA-256：`23B3FEC6FAE2BBF26F24FD610D06C55556850DB33E59F608CE42E27787ADA476`
- 相对 `m2b` 的变化：`requant_unit` 的 32×32 乘法拆成 4 个并行 16×16 部分积
  （原综合成 3 个 APM 串联、逻辑 4.5 ns + 走线 4.2 ns）。深度与位级结果不变，
  40 万组随机+边界值比对 0 mismatch。
- 时序：**Some Constraints Violated**
  - `ddrphy_sysclk` WNS **-2.144 ns**（估计 98.58 MHz，需 125）
  - `pix_clk` **-0.061**（从 m2b 的 -0.450 明显改善，仅 7 个端点量级）
  - `clk_nco` +0.838、`cfg_clk` +90.066、`rst_clk` +2.281
- 关键观察（本轮结论）：最差路径已**不在数据通路上**，而是
  `u_npu/u_wdma/c_cnt[3] → m_s32[12]`：**逻辑仅 2 级、0.798 ns，走线 8.818 ns（91.7%）**。
  即 FF→FF 被布局拉远，属拥塞散布而非组合深度问题，无法用插流水解决；
  并且每轮布局不同，最差路径在 `conv MAC (-3.593)` → `requant 乘法 (-1.106)` →
  `wdma 远距离 FF (-2.144)` 之间摆动，WNS 在 -1~-3 ns 区间随布局漂移。
- 资源：见 `manifest.json`（LUT 约 53.6%、FF 37.3%、APM 90、DRM 79.5）
- 结论：可作为「功能完整、时序基本可跑」的候选位流，但**不含 UART 握手修复**，
  串口输出仍是被丢字符的旧行为（见下条），因此不用于板级功能验证。
- 板级事实（同日实测）：`board_check.py` 已修复 FTDI 掉线根因（详见 `m2b` 段与
  `releases` 目录外的 `docs/STATUS.md`），本轮烧 `m2b` 得到 `done=1`、
  串口 18 字节 `ITCO\nD3ETT.D3R@FF\n` —— 即 ROM 索引 0,3,6,9，证明
  `uart_debug` 的 valid 是单拍 strobe 而 `uart_tx` 的 ready 滞后，每帧丢掉 2/3 字符。

校验：`sha256sum -c SHA256SUMS`。