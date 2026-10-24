# 常见问题速查（PG2L100H · 盘古 100Pro+）

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| JTAG 扫不到器件，TDO 恒 `0xffffffff` | 板子没上电 / 核心板未压合 / J12 排线方向错 / 插到串口口 | 见 `jtag_download.md`（先查 SW1 与供电、压合、排线 1 脚） |
| `cfg_connect` 成功但 `cfg_set_cable_property` 失败 | jtagserver 未就绪或状态异常 | 重开 PDS Configuration 界面，再跑 `cdt_cfg` |
| 下载报错 | 选错 `.sbit` / 烧录中排线松动 | 确认器件匹配、重插排线重下 |
| 综合/实现失败（`E:` 行） | RTL 语法 / 约束引脚不存在 | 看 `compile/`、`place_route/` 的 run.log |
| `SCBV has not been set` | 正常提示 | 忽略，不影响位流 |
| 串口无输出 | blink 无 UART / 选错设计 | 烧含 UART 的设计（如官方 `2_8_uart_test`） |
| 串口乱码 | 波特率不匹配 | 试 115200 / 9600，确认 8N1 |
| 找不到 COM 口 | 未装 CP210x 驱动 | 装 Silicon Labs CP210x VCP 驱动 |
| 时序不收敛 | 关键路径太长 | 降频（改 `create_clock -period`）/ 换布局种子 |

## 环境检查命令

```powershell
# PDS shell 是否存在
Test-Path "$env:PDS_ROOT\bin\pds_shell.exe"
# 许可证
$env:PANGO_LICENSE_FILE
# 下载器枚举（FTDI）
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "*VID_0403*" }
# 串口
[System.IO.Ports.SerialPort]::GetPortNames()
```

## 不要做的事

- 不要通电插拔 JTAG。
- 不要把 200H 的器件/封装（PG2L200H/FBB676）或 DDR3 约束用到本板。
- 不要用其他规格电源（必须随板 +12V）。
- 不要在本机跑本地 RTL 仿真（无 WSL / Icarus）。
