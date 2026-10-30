# InstRec-FPGA M3a 位流归档（2026-10-31）—— wdma 块 RAM 化，三重收益

- 位流：`instrec_top.sbit`（PG2L100H-6IFBG676，顶层 `instrec_top`）
- 来源 run：`20261031-022725-648fb082`
- SHA-256：`152FEC8BB4C03579AC80E9C985E552E5B04D5DCD504333B55A725B174BD09926`
- 布线：`Unrouted nets 0` at **iteration 477**（m2d 是 1001），`placed and routed successfully`

## 这一版做了什么

把 `u_wdma` 里三个分别寻址、**异步读**的参数表（bias/M/shift）合并成一个
`1024x32` 表（768 有效 + 256 填充），改成**单同步读口**：

```
[  0..255] bias     [256..511] M     [512..767] shift
```

读口晚一拍，`S_GRP` 消费 `pq`（元素 t）、同拍给出 `pa`（元素 t+1）、寄存元素 t+2；
`pa` 在 `S_CS_CMD` 预置 0、进入 `S_GRP` 时置 1。契约拍数不变，下游按 `valid` 接收。
判据见 `tests/test_wdma_param_pipeline.py`（7 项，逐拍比对地址与数据配对）。

## 效果（三处同时改善）

| 指标 | 之前 (m2d) | 现在 (m3a) |
|---|---|---|
| 全设计 LUT | 35677 (53.57%) | **34591 (51.94%)** |
| `u_wdma` LUT | 8004 | **6895** |
| 布线收敛 | iteration 1001 | **iteration 477** |
| `ddrphy_sysclk` | -2.144 ns | **-1.228 ns** |
| `pix_clk` | -0.061 ns | **+0.186 ns（转正）** |
| `clk_nco` | +0.838 | +1.118 |

原因是这三个数组原本被 PDS 建成 LUTRAM/FF（18608 FF），既占 LUT 又把
`c_cnt -> m_s32` 拉成 8.8 ns 的走线；收进一个同步读表后三者一起消失。

## 仍未包含

- **UART 文本修复**：`uart_debug` 仍是未修复版，`INSTREC BOOT` 会丢字符成 idx 0,3,6,9
- **M3 谱图/文字层**：仍为注释关闭状态
- 波形显示、概率条、NPU 全链均在位

**LUT 现在有 51.94%，离实测临界点（53.57% 布通、53.59% 停滞）还有 1.6 个百分点余量，
下一版可以安全地加回 UART 字符间隔计数器（+11 LUT）与 M3 的 LUT 层。**

校验：`sha256sum -c SHA256SUMS`。