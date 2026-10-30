# wdma 参数数组同步化改造方案（降密度，2026-10-31 草案）

> 目的：把 `u_wdma` 的 8004 LUT / 18608 FF 降下来，让 LUT 从 53.6% 落到 ~46%，
> 彻底离开布线临界点（实测 35677 布通、35688 停滞）。
> **本方案尚未实施**。改完必须先跑 Python 判据，再构建验证。

## 1. 现状与根因

`src/npu/wdma.v` 里有 4 个数组，全部是**异步读**：

| 数组 | 声明 | 位宽 | 读法 |
|---|---|---|---|
| `bram` | `reg signed [31:0] bram [0:255]` | 8192 bit | `bias_s32 <= bram[c_cnt];` |
| `mram` | `reg signed [31:0] mram [0:255]` | 8192 bit | `m_s32 <= mram[c_cnt - cout];` |
| `sram` | `reg [7:0] sram [0:255]` | 2048 bit | `shift <= sram[...][6:0];` |
| `fifo` | `reg [255:0] fifo [0:15]` | 4096 bit | `wire [255:0] beat_c = fifo[rd_ptr];` |

异步读让 PDS 只能推断成 LUTRAM 或 FF。实测该模块 8004 LUT / 18608 FF，
是全设计 FF 的 37%。三者合计 18432 bit，落 DRAM 只需 **1~2 块**（当前 DRM 79.5/155，余量充足）。

## 2. 目标写法

```verilog
(* syn_ramstyle = "block_ram" *) reg signed [31:0] bram [0:255];
(* syn_ramstyle = "block_ram" *) reg signed [31:0] mram [0:255];
(* syn_ramstyle = "block_ram" *) reg        [7:0]  sram [0:255];

reg [7:0]         par_addr;      // 地址流水：本拍给出的地址，下一拍出数据
reg signed [31:0] b_q, m_q;
reg        [7:0]  s_q;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        b_q <= 32'sd0; m_q <= 32'sd0; s_q <= 8'd0;
    end else begin
        b_q <= bram[par_addr];
        m_q <= mram[par_addr];
        s_q <= sram[par_addr];
    end
end
```

写端口保持同步（`rd_valid` 时写），因此每个数组是「一写一读」的简单双口，DRAM 可推断。

## 3. 时序要点（关键，不能改契约拍数）

`S_GRP` 是 48 拍（conv）/ 3×COUT（fc）的参数发放状态，`c_cnt` 每拍 +1，
在 `c_cnt == cfg_end-1` 时转 `S_TCMD`。改造后：

- **地址提前一拍**：`S_GRP` 每拍 `par_addr <= <下一拍需要的索引>`，
  输出的 `bias_s32/m_s32/shift` 取 `b_q/m_q/s_q`（对应上一拍的 `par_addr`）。
- **进入前预置**：在 `S_CS_CMD → S_GRP` 那一拍 `par_addr <= 8'd0`，
  使 `S_GRP` 第一拍就能拿到 index 0 的数据。`S_GRP` 无需额外拍。
- **两个分支的索引不同**：
  - `is_fc`：索引就是 `c_cnt`（bias）、`c_cnt-cout`（M）、`c_cnt-2*cout`（shift）。
    但三个数组共用 `par_addr`，而它们在**同一个 c_cnt 拍**里只用到其中一个 →
    可直接 `par_addr <= c_cnt + 1`，三个数组并行读同一个地址，用不到的结果丢弃。
  - 非 fc：索引是 `ctr_addr`（且 `ctr_hit` 为假时用 0）。需要把 `ctr_addr` 的
    计算提前一拍得到 `par_addr`，或在 `ctr_hit` 为假时让 `par_addr <= 0` 并强制输出 0。
- **`b_valid/m_valid/s_valid` 与数据同拍**，下游 `fc_engine`/`conv_engine` 按 valid 接收，
  **不需要改下游**。

## 4. 验证要求（无仿真，必须先做）

1. `python -m pytest tests/test_wdma_stream_model.py tests/test_wdma_layout.py
   tests/test_contract_stream.py tests/test_wdma_group_model.py -q` 全绿；
2. 在 `tests/` 里补一个「地址提前一拍」的周期模型：对 fc 与 conv 两条参数流，
   逐拍比对改造前后的 `(value, valid)` 序列，**要求 100% 一致**；
3. `python scripts/check_rtl.py` 0 violation；
4. 构建后先看 `snr` 的 per-module 表确认 `u_wdma` LUT/FF 实际下降，
   再看 `Unrouted nets` 曲线是否越过原来的 2400~3000 停滞区。

## 5. 若 PDS 仍推断成 LUTRAM

说明同步读或写口不满足 DRAM 模板，检查：
- 读地址必须来自寄存器（`par_addr`），不能直接是组合表达式；
- 写使能必须单口、同拍同地址；
- Pango 的 DRAM 不支持「读优先/写优先」以外的异步穿越，`rd_valid` 写与 `par_addr` 读
  不同址时无冲突。

## 6. 备选降密度路径（若 wdma 改造失败）

1. `u_fc1`（3334 LUT）16 → 8 并行输出，约省 1500；
2. `u_conv`（4251）16 → 8 lane，约省 1400~2000（吞吐减半，「能跑就行」可接受）；
3. `u_fft2048_sdf`（6194）是 mel 最大头，但改它等于改算法，最后再动。