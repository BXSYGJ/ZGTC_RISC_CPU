# InstRec-FPGA M2d 位流归档（2026-10-30）—— 可复现的布通基线

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676，顶层 `instrec_top`）
- 来源 run：`20261030-203315-73475044`（compile→gen_bit_stream 1h25m）
- SHA-256：`46EE227FCEB84125CDBF67FDA88ACB544CC8605BF760C14A915E5A9138FFF85A`
- 布线：**`Unrouted nets 0` at iteration 1001**，`Design 'instrec_top' has been placed and routed successfully`

## 这版的意义

**它证明了布通与否取决于 `pnr` 参数，而不是 RTL。** 同一份 RTL 在
`-parallel 4` / `-gplace_seed 7` / `-plc_decongestion` 下四次都停在 2400~7200 条未布网络，
而**纯 `pnr`**（无任何参数）在 iteration 1001 收敛。m2c（`20261029-172919`）也是同一个
结论：纯 `pnr` 布通。

## 时序（`report_timing/instrec_top.rtr`）

| 时钟域 | Slack (ns) |
|---|---|
| `ddrphy_sysclk`（core 125 MHz） | **-2.144** |
| `pix_clk`（148.5 MHz） | **-0.061**（7 个端点） |
| `clk_nco`（216 MHz） | +0.838 |
| `rst_clk` | +2.281 |
| `cfg_clk` | +90.066 |

数字与 m2c **逐位相同**（-2.144 / -0.061），再次印证 PDS 的布局布线是确定性的。

## 内容范围

- 音频链路、DDR3、Mel 引擎、NPU 全链（单 conv 共享核 + MAC 流水 + requant 四部分积拆分）、
  概率条 UI、**波形显示已恢复**
- M3 谱图 / 文字层：**未包含**（仍为注释关闭状态）
- UART：**本版为未修复版**（`uart_debug`/`uart_tx` 回退到 `b463740^`），
  `INSTREC BOOT` 仍会以 ROM idx 0,3,6,9 的形式丢字符；
  **但 `weight_loader` 的单字符握手不受影响，`WOK` 回执可正常收发**

## 为什么还留着它

这是当前**唯一可复现的布通配置**。后续每次加功能都必须从「纯 `pnr` + 这套 RTL」出发，
**一次只加一个变量**，加完立刻构建验证布通，不能批量叠加。

校验：`sha256sum -c SHA256SUMS`。