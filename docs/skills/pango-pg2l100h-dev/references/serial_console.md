# 串口连接与调试（板载 CP2102 · UART）

盘古 100Pro+ **自带 USB 转串口**，无需外部串口模块。

## 硬件连接

1. 用一根 **USB Type-C 数据线**，从 PC 接到底板上的 **USB 转串口 Type-C 口**。
   - 板上串口芯片：**Silicon Labs CP2102-GMR**。
   - ⚠️ 这个 Type-C 口与 **JTAG 的 J12 排线**是两回事，别插错。
2. FPGA 侧信号已在 PCB 上连到 CP2102，**无需自己接线**：

| 信号 | FPGA 管脚 | 方向 | 板上连接 |
| --- | --- | --- | --- |
| `uart_rx`（FPGA 接收） | **B24** | INPUT | 接 CP2102 TXD |
| `uart_tx`（FPGA 发送） | **C24** | OUTPUT | 接 CP2102 RXD |

电平 LVCMOS33。

## 驱动与端口号

- 安装 **Silicon Labs CP210x VCP 驱动**（Win10/11 多数可自动安装；不识别时装一次）。
- 设备管理器 → **端口(COM 和 LPT)** 出现
  `Silicon Labs CP210x USB to UART Bridge (COMx)` —— 记下 `COMx`。
- 该 Type-C 口同时可取电（USB_VBUS），但 FPGA 仍应由 +12V/底板供电。

## 串口参数

| 参数 | 值 |
| --- | --- |
| 波特率 | **115200** |
| 数据位 / 校验 / 停止位 / 流控 | **8 / None / 1 / None**（8N1） |

依据：官方 `2_8_uart_test` 顶层 `BPS_NUM = 16'd234`，27 MHz / 234 ≈ 115384 ≈ **115200**。
> 注：《教程2》§8.6 正文写「波特率设置为 9600」，与随板代码不符（疑似旧文案）。若 115200 乱码，
> 再试 9600。

## 上位机

本仓库工具 `tool/serial/serial_cli.py`（自动识别 CP210x 口）：

```bash
python tool/serial/serial_cli.py list                                  # 列串口
python tool/serial/serial_cli.py monitor --seconds 10                  # 监听
python tool/serial/serial_cli.py load app.bin                          # ZBOOT R 协议加载应用
python tool/serial/serial_cli.py send --hex 'a5' --expect 'SOC PASS'   # 发送/等待期望串
python tool/serial/serial_cli.py echo                                  # 交互式
```

任意串口终端亦可：Windows 串口助手 / PuTTY / Tera Term；或 Python：

```python
import serial
ser = serial.Serial('COM5', 115200, timeout=1)   # COM5 换成实际端口
print(ser.readline())
```

## 重要前提

- **流水灯（blink）工程无 UART 逻辑**，插上串口不会有任何输出——串口要搭配**含 UART 的设计**才有数据。
- 想立刻验证串口：烧官方 `2_8_uart_test`（周期性发送字符串；PC 发 `ff` 点亮全部 LED）。
- **已迁移（2026-10-24）**：RISC-V CPU SoC 位流（`pds_cpu_100h/`）烧录后即进入 ZBOOT 串口控制台，
  可用 `tool/serial/serial_cli.py` 收发、并用 `load <app.bin>` 经串口把应用加载进 BRAM 运行。
  完整流程见 `references/cpu_serial_flash.md`。

## 常见问题

- **打不开端口 / 端口被占用**：关闭其他串口软件；确认设备管理器里的 COMx 与实际一致。
- **收到乱码**：波特率不匹配（试 9600/115200）、或设计未烧录 UART、或时钟不是 27 MHz。
- **收不到任何数据**：设计无 UART 发送逻辑；或选错设计；或插的是 JTAG 口而非串口口。
