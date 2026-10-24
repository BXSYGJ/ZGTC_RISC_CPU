# PG2L100H 管脚与约束

器件 `PG2L100H-6IFBG676`，开发板 `MES2L676-100HP`。电平标准统一 `LVCMOS33`、VCCIO 3.3 V。
来源：官方《硬件实验指导手册》与配套 demo（`2_7_key_led_test` / `2_8_uart_test`）。

## 板载资源

| 信号 | 功能 | 管脚 | 方向 | 备注 |
| --- | --- | --- | --- | --- |
| `clk` | 27 MHz 系统时钟 | D18 | INPUT | `create_clock -period 37.037` |
| `rst_n` | KEY0 | C22 | INPUT | 低有效复位 |
| `key` | KEY1 | C23 | INPUT | 低有效 |
| `led[0]` | LED0 | A20 | OUTPUT | 高有效，DRIVE 8，SLEW SLOW |
| `led[1]` | LED1 | C18 | OUTPUT | 同上 |
| `led[2]` | LED2 | C19 | OUTPUT | 同上 |
| `led[3]` | LED3 | E18 | OUTPUT | 同上 |
| `led[4]` | LED4 | A17 | OUTPUT | 同上 |
| `led[5]` | LED5 | A18 | OUTPUT | 同上 |
| `led[6]` | LED6 | C17 | OUTPUT | 同上 |
| `led[7]` | LED7 | B17 | OUTPUT | 同上 |
| `uart_rx` | 板载串口 FPGA 接收 | B24 | INPUT | 接板上 CP2102 TXD |
| `uart_tx` | 板载串口 FPGA 发送 | C24 | OUTPUT | 接板上 CP2102 RXD |

其余按键 KEY2/3/4 = B22/A22/B20；EEPROM IIC SCL/SDA = A23/A24；SD = F19/H14/F18…。
完整 `.fdc` 见 `template/constraints/blink_top.fdc`。替换 LED 数量/顺序时同步改 RTL 位宽与 `.fdc` 的 `led[N]` 条目。

## 与 200Pro+（PG2L200H）的差异

- **器件/封装不同**：`PG2L200H-6FBB676` → `PG2L100H-6IFBG676`（-6 速度级、FBG676）。
- **普通 IO 相同**：clk D18、KEY0 C22、KEY1 C23、LED A20/C18/C19/E18/A17/A18/C17/B17、
  板载 UART B24/C24 —— 与 200H 完全一致（本板官方 demo 与 200H 官方 demo 一致）。
- **DDR3 引脚/约束不同**：不能照搬 200H 的 `ddr3.fdc`；且 100H 的 FMC 部分引脚为 NC。
  若需 DDR3，须按 100Pro+ 官方 `2_9_ddr3_test` 工程重新取引脚与 generated clock。

## 约束 fragment 写法

```tcl
create_clock -name {clk} [get_ports {clk}] -period {37.037} -waveform {0.000 18.519}

define_attribute {p:clk} {PAP_IO_DIRECTION} {INPUT}
define_attribute {p:clk} {PAP_IO_LOC} {D18}
define_attribute {p:clk} {PAP_IO_VCCIO} {3.3}
define_attribute {p:clk} {PAP_IO_STANDARD} {LVCMOS33}
define_attribute {p:clk} {PAP_IO_NONE} {TRUE}
```

输出脚附加 `PAP_IO_DRIVE {8}` 与 `PAP_IO_SLEW {SLOW}`。

## 其他注意

- 异步复位建议同步释放；UART/GPIO 输入建议过同步器。
- `SCBV` 位流选项原厂未随资料提供，生成位流时不设置，属正常提示。
- 不同时钟频率改 `create_clock -period`；27 MHz 对应 `37.037 ns`。
