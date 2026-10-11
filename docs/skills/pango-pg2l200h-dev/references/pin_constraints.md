# PG2L200H 管脚与约束

器件 `PG2L200H-6FBB676`，开发板 `MES2L676-200HP`。电平标准统一 `LVCMOS33`、VCCIO 3.3 V。

## 板载（MES2L676-200HP）资源

来自厂商 `MES2L676-200HP硬件使用手册_v1.2.pdf` 与配套 `2_7_key_led_test` 例程。

| 信号 | 功能 | 管脚 | 方向 | 备注 |
| --- | --- | --- | --- | --- |
| `clk` | 27 MHz 系统时钟 | D18 | INPUT | `create_clock -period 37.037`（27 MHz） |
| `rst_n` | KEY0 | C22 | INPUT | 低有效复位 |
| `key` | KEY1 | C23 | INPUT | 低有效；本基线按下向低位移 |
| `led[0]` | LED0 | A20 | OUTPUT | 高有效，DRIVE 8，SLEW SLOW |
| `led[1]` | LED1 | C18 | OUTPUT | 同上 |
| `led[2]` | LED2 | C19 | OUTPUT | 同上 |
| `led[3]` | LED3 | E18 | OUTPUT | 同上 |
| `led[4]` | LED4 | A17 | OUTPUT | 同上 |
| `led[5]` | LED5 | A18 | OUTPUT | 同上 |
| `led[6]` | LED6 | C17 | OUTPUT | 同上 |
| `led[7]` | LED7 | B17 | OUTPUT | 同上 |

完整 `.fdc` 见 `template/constraints/blink_top.fdc`。替换 LED 数量/顺序时同步改
RTL 位宽与 `.fdc` 的 `led[N]` 条目，二者必须一致。

## RemoteLab 网页串口（logicmatrixsemi.com:5174）

远程实验箱的串口**不是板载 UART**，由网站仪器面板明确标出：

| 信号 | 管脚 | 电平 |
| --- | --- | --- |
| `uart_rx` | AC26 | LVCMOS33 |
| `uart_tx` | AB26 | LVCMOS33 |

波特率常用 115200 8N1，部分低速场景 9600。**板载 UART（B24/C24）与 RemoteLab（AC26/AB26）
不能混用**；切换上板环境时要换对应约束。RemoteLab UART 约束片段只有两行：

```tcl
define_attribute {p:uart_rx} {PAP_IO_LOC} {AC26}
define_attribute {p:uart_tx} {PAP_IO_LOC} {AB26}
```

并入工程时注意补充 `PAP_IO_DIRECTION` / `PAP_IO_VCCIO` / `PAP_IO_STANDARD` 等属性
（与板载约束同款写法）。

## 其他注意

- 异步复位建议同步释放；UART/GPIO 输入建议过同步器，避免远程箱跨时钟域亚稳态。
- `SCBV` 位流选项原厂未随资料提供，生成位流时不设置，属正常提示。
- 不同时钟频率改 `create_clock -period`；27 MHz 对应 `37.037 ns`。
