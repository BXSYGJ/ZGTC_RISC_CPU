# M2 顶层接入蓝图（instrec_top）

> 状态：2026-10-28。M2 各模块已单独编译通过，`npu_top` 数据通路已整合；
> 尚未接入 `instrec_top`。本文只描述**接线与仲裁**，不重复模块内部设计。

## 1. 待接入模块

| 模块 | 实例名 | 时钟域 | 说明 |
|---|---|---|---|
| `wdma` | `u_wdma` | core_clk | 推理期权重流，占 DDR3 m1 |
| `weight_loader` | `u_weight_loader` | core_clk | 上电加载期权重写入，占 DDR3 m1 |
| `npu_top` | `u_npu` | core_clk | 含 conv/pool/gap/fc/softmax |
| `uart_debug` | `u_uart_debug` | core_clk | 已存在，需扩展 WOK/WERR 行 |
| `sys_ctrl` | `u_sys_ctrl` | core_clk | 需增加 WEIGHT_OK 自检环 |

## 2. DDR3 m1 口仲裁

m1 当前在 `instrec_top` 中 tie-off。接入后由 `weight_loader` 与 `wdma` 分时占用：

- **加载期**（复位后到 `weight_ok`）：`ddr_cmd_valid[1]` 与 `m1_cmd/m1_wdata`
  来自 `weight_loader`；`wdma` 保持 `start=0`。
- **推理期**（`weight_ok=1` 且 `sys_ctrl` 放行）：m1 交给 `wdma`；
  `weight_loader` 不再发起命令。
- 读数据路由：`ddr3_ctrl_axi` 的 `rd_data_1/rd_valid[1]` 同时送到
  `weight_loader`（读回校验）与 `wdma`（权重流），由各自的 `start/busy`
  保证只有一个在消费。

仲裁选择（组合）：

```verilog
wire wl_active = weight_loader_busy;
assign ddr_cmd_valid[1] = wl_active ? wl_cmd_valid : wdma_cmd_valid;
assign m1_cmd           = wl_active ? wl_cmd       : wdma_cmd;
assign m1_wdata         = wl_active ? wl_wdata     : 256'd0;
```

## 3. sys_ctrl 自检链

当前 `ST_BOOT → ST_PLL → ST_DDR → ST_RUN`。插入权重环：

```
ST_BOOT -> ST_PLL -> ST_DDR -> ST_WEIGHT -> ST_RUN
                                  |  (timeout / weight_err)
                                  v
                               ST_SAFE_ERR
```

- `ST_WEIGHT`：等待 `weight_ok`；超时阈值建议 90 s（加载预算 60 s + 余量）。
- `weight_err` 或超时：打印 `WERR @...` 并停在 `ST_SAFE_ERR`。
- `ST_RUN` 之后才允许 `npu_top.start`。

新增端口：

```verilog
input  wire weight_ok,
input  wire weight_err,
output wire weight_start,     // 进入 ST_WEIGHT 时置 1
```

## 4. weight_loader 接线

- `rx_valid/rx_data` 接 `uart_rx` 的字节输出（与 `uart_debug` 共用接收，
  需要按帧头 0xAA 区分：`weight_loader` 只在加载期使能）。
- `tx_valid/tx_data/tx_ready` 接 UART TX 仲裁（加载期 `weight_loader` 优先）。
- `cmd_valid/cmd/wdata/wready_beat/done` 接 m1 写通道。
- `rd_ready/rd_data/rd_valid` 接 m1 读通道（读回校验）。

## 5. npu_top 接线

- `feat_valid/feat_u8` 接 `mel_engine` 的 feat 输出（64×258，按 (row,col) 栅格）。
- `rd_*` 接 m1 读通道。
- `start` 接 `sys_ctrl` 的推理触发（RUN 后每窗口一次）。
- `probs_valid/probs_pct/top1` 接 `ui_renderer` 与 `uart_debug` 导出。

## 6. 验证顺序（USB 恢复后）

1. 烧当前位流，确认 `INSTREC BOOT` 可读（ROM 字符表已改显式 ASCII）。
2. 接入 `weight_loader` + m1 写，UART 跑 `weight_upload.py --dry-run` 与实传，
   读回 `WOK`。
3. 接入 `npu_top`（契约流先由测试向量驱动），跑单层 conv1 对拍。
4. 接入 `wdma` 契约流后跑端到端 `probs` 对拍。

## 7. 已知缺口

- `wdma` 尚未输出 48 拍 bias/M/shift 契约，也未接 `grp_advance`；契约内容与地址已由
  `tests/test_contract_stream.py` 固定，可作为 RTL 的测试向量。
- `fc_engine` 的 bias/M/shift 三条流已就绪，但没有生产者。