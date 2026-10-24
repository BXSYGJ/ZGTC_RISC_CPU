# 盘古 100Pro+ UART 串口实验（PG2L100H）

在 **MES2L676-100HP / PG2L100H-6IFBG676** 上验证板载串口（CP2102）收发。
来源：官方 100Pro+ `2_8_uart_test` 例程；本目录整理了源/约束/脚本，并保留官方**预编译位流**
`generate_bitstream/uart_top.sbit`，可**免综合直接烧录**验证。

## 功能

- 约每秒向 PC 发送一次 ASCII 字符串 `www.meyesemi.com` + CR/LF。
- 收到 PC 的字节后回显：写入的 8bit 值点亮 `led[7:0]`（发 `ff`(十六进制) → 8 灯全亮）。

## 引脚

| 信号 | 管脚 | 说明 |
| --- | --- | --- |
| `clk` | D18 | 27 MHz |
| `uart_rx` | B24 | FPGA 接收（接板上 CP2102 TXD） |
| `uart_tx` | C24 | FPGA 发送（接板上 CP2102 RXD） |
| `led[0..7]` | A20/C18/C19/E18/A17/A18/C17/B17 | 收字节的二进制显示 |

## 串口参数

**115200 8N1**（`BPS_NUM=234`，27 MHz）。板载 CP2102 → PC 端 COM 口（本例 COM5）。

## 步骤

### 1) 烧录位流（二选一）

- **GUI（推荐）**：PDS → Tools → Configuration → Scan Device →
  选 `pds_uart_100h/generate_bitstream/uart_top.sbit` → 右键器件 Program。
- **CLI**：先打开 PDS Configuration 拉起 jtagserver(65420)，再
  `cdt_cfg.exe -file .\scripts\program_full.tcl`。

> 想自己重建：`pwsh -NoProfile -File .\scripts\run_pds_full.ps1`（产出覆盖同名 sbit）。

### 2) 打开串口看数据

```bash
python tool/serial/serial_cli.py list                       # 确认 CP210x 端口
python tool/serial/serial_cli.py monitor --baud 115200      # 每秒应打印 www.meyesemi.com
python tool/serial/serial_cli.py send --hex "ff"            # 8 个 LED 全亮
```

若 115200 乱码，试 `--baud 9600`，或用 `autobaud` 自动探测。
