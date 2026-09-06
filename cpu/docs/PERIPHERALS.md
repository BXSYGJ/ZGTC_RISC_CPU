# SoC 外设与板级连接

实际 SoC 使用 27 MHz 时钟、64 KiB 片上 RAM、512 字节两路 I/D Cache。MMIO 不缓存，读写必须遵守 `BUS.md`。以下地址为字节地址，寄存器按 32 位访问；可写寄存器遵守字节使能。未知地址、未对齐地址、只读寄存器写入均返回访问错误且无副作用。

| 地址 | 名称 | 行为 |
| --- | --- | --- |
| 10000000 | STATUS_CODE | 软件状态字，可读写 |
| 10000004 | VERSION | 只读 00010000；不是旧仿真邮箱的 IRQ 注入口 |
| 10000100 | UART_DATA | 写低字节入 TX FIFO，读弹出一个 RX 字节；空读 FFFFFFFF |
| 10000104 | UART_STATUS | bit0 TX 可写，bit1 TX 完全空闲，bit2 RX 可读，bit3 RX FIFO 满，bit4 帧错误，bit5 溢出 |
| 10000108 | UART_CONTROL | bit0 RX 非空中断使能，bit1 TX 空闲中断使能 |
| 1000010C | UART_ERRORS | bit0 帧错误、bit1 溢出，写 1 清除 |
| 10000200 | GPIO_OUTPUT | 低 8 位输出，可读写 |
| 10000204 | GPIO_INPUT | 同步后的低 8 位输入，只读 |
| 10000208 | GPIO_ENABLE | 低 8 位中断使能 |
| 1000020C | GPIO_PENDING | 上升沿挂起，写 1 清除；新事件优先于清除 |
| 10000300/304 | TIME_LOW/HIGH | 64 位逐周期递增定时器，可写 |
| 10000308/30C | COMPARE_LOW/HIGH | 64 位阈值，time >= compare 置定时中断 |
| 10000310 | SOFTWARE_IRQ | bit0 软件中断，可读写 |

表中地址均为十六进制。UART 是 115200 8N1，整数分频 234，27 MHz 下实际约 115384.6 baud。TX/RX FIFO 各 16 字节，接收器另有一个待交付字节缓冲；满 TX FIFO 会反压总线。错误为粘滞位，坏停止位字节丢弃。UART 中断和 GPIO 中断合并为机器外部中断。

GPIO 挂起不受使能位屏蔽；使能只控制是否向 CPU 申请中断。定时器读 64 位用高/低/高重读避免进位撕裂；写比较值先把高字写 FFFFFFFF，再写低字和最终高字，避免误触发。

## 接线环境不能混用

- 共用时钟 D18（27 MHz），KEY0 C22（低有效复位），KEY1 C23；GPIO 输入 bit0 为 KEY1 按下状态。波形应用加入后，bit1 为实际 uart_rx 电平的只读分接，其余为 0；旧自检位流没有该分接。
- LED bit0..7 对应 A20/C18/C19/E18/A17/A18/C17/B17，输出高电平点亮。复位异步置位、两级同步释放，按键和 UART RX 另有两级同步器。
- `Board`：MES2L676-200HP 手册的板载串口 RX B24、TX C24。
- `RemoteLab`：2026-09-06 网站串口面板明确指定工程 RX AC26、TX AB26，连接仪器 FPGA；并不是手册板载串口。截图保存在本地 `build/hardware/remote-uart-pin-evidence.png`。
- 全部使用 LVCMOS33。公共约束不单独指定 UART LOC；构建时必须同时加载相应 UART profile 文件。不能把 Board 位流下载成功但网站 UART 无数据显示认定为 CPU 故障。

## C 自检交互

`start.S` 设置栈和 gp、清零 BSS、配置陷入入口后执行 `soc_selftest.c`。中断入口保存调用者寄存器，C 被调用函数按 ABI 保存其余寄存器，最终 MRET 返回。

1. 启动置 LED=5A，发送 `ZGTC RV32I` 和 CR/LF。
2. 软件依次验证软件、定时中断；Board 版本再等待 KEY1 上升沿对应的 GPIO 外部中断（STATUS=100）。RemoteLab 版本改为使能 UART RX 外部中断，此时直接发送十六进制 A5 即可继续，不需要现场按键。没有输入事件会继续等待，不是假死。
3. 完成 FENCE.I 后 STATUS=101，等待 UART 接收十六进制 A5。
4. 成功发送十六进制 5A，随后 `SOC PASS` 和 CR/LF，LED=A5、STATUS=CAFE0001。该自检不是正式应用或 CoreMark。

仿真通过：两种外部中断来源的普通 SoC 均为 72 项检查、7,768 周期、23 个串口字节、三类中断各一次；维护故障注入 GPIO/UART 版本分别 36/37 项检查。UART 单元覆盖全 256 字节、独立引脚解码、分频 31/33 相对于标称 32 的容差测试。RemoteLab 版本已通过实板交互自检，见 `HARDWARE_SELFTEST.md`，不能把仿真计数当成硬件测量值。
