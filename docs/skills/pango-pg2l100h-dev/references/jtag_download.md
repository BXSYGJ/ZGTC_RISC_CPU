# JTAG 下载与固化（PG2L100H · 盘古 100Pro+）

## 硬件准备

1. **供电**：用随板 **+12V** 适配器（不要用其他规格）；先接 JTAG 排线和电源线，再打开底板 **SW1**，
   确认核心板指示灯亮。
2. **JTAG 接线**：USB Cable II（FT2232H）经 10 针排线接底板 **J12**（2.54mm 双排排针）。
   - 排线 **1 脚红线对齐 J12 丝印 1 脚**。
   - 别插到板载 **USB-C 串口口**（那是 CP2102 串口，不是 JTAG）。
   - **通电时禁止插拔 JTAG**。
   - 无底板时可用核心板正面左上角的 JTAG 触点调试。
3. **下载器驱动**：PDS 安装时若提示安装 `USBCableDriver` 要选"是"，否则下载器可能无法工作。

## 路径 A：GUI（最稳，推荐）

1. PDS 菜单 **Tools → Configuration**（或工具栏 Configuration 图标）。
2. 点 **Scan Device** 扫描 JTAG 链；初始化成功后，工作区列出 PANGO 器件，并弹窗选择 `.sbit`。
3. 选 `generate_bitstream/<top>.sbit`，**右键器件 → Program**。
4. 信息区出现 `COMMAND[Program] execute successfully..` 即下载完成。

参考《教程2 通用实验指导手册》§7.7.9 / §7.7.10。

## 路径 B：命令行 `cdt_cfg`（脚本化）

`cdt_cfg.exe` 不直接驱动硬件，而是连接 PDS 提供的 **jtagserver**（默认 `127.0.0.1:65420`）。
jtagserver 由 **PDS Configuration 界面打开时拉起**，所以先开会 Configuration 界面再跑脚本。

### 无 GUI 环境：直接启动/重启 jtagserver

不打开 GUI 也能用：`cdt_js.exe` 就是 jtagserver 本体，可后台直接拉起。

```powershell
# 启动（-work_dir "" 表示空工作目录）
Start-Process -FilePath "$env:PDS_ROOT\bin\cdt_js.exe" `
  -ArgumentList '-work_dir','""','-port','65420' -WindowStyle Hidden

# 检查是否在跑 / 端口是否监听
Get-CimInstance Win32_Process -Filter "Name='cdt_js.exe'" | Select ProcessId,CommandLine
(Test-NetConnection 127.0.0.1 -Port 65420).TcpTestSucceeded
```

**排障：jtagserver 卡死**。若 `cfg_scan_chain` 从"几秒返回"变成"长时间挂起不返回"，
说明服务已卡死（长时间运行/反复失败后常见）。重启即可：

```powershell
Stop-Process -Name cdt_js -Force
Start-Process -FilePath "$env:PDS_ROOT\bin\cdt_js.exe" `
  -ArgumentList '-work_dir','""','-port','65420' -WindowStyle Hidden
```

重启后扫描会恢复"快速返回"；若仍报 `No devices detected`，则是目标侧（供电/排线）问题，见下。

```powershell
# 1) 只扫描链路（确认能扫到器件）
"H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe" -file ".../scripts/test_scan.tcl"

# 2) 下载位流
"H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe" -file ".../scripts/program_full.tcl"
```

`program_full.tcl` 内容（关键步骤）：

```tcl
cfg_connect -ip 127.0.0.1 -port 65420
cfg_set_cable_property -index 0 -freq 10Mhz
cfg_scan_chain
cfg_assign_file -file <abs path>/blink_top.sbit -device_index 0
cfg_program -device_index 0
cfg_disconnect
```

`test_cable.tcl`（`cfg_get_cable_paras`）可单独确认下载器可用；`test_scan_1mhz.tcl` /
`test_scan_lowfreq.tcl` 用更低频率扫描。

## 固化到外部 Flash（`.sfc`，本板尚未验证）

参考《05_FPGA&CPLD的下载与固化_v1.1》：

1. Configuration → **Operations → Convert File**，选择 Flash 厂商/型号与 `.sbit`，生成 `.sfc`。
   （若 Flash 型号不在列表：先右键 PANGO 器件 → Scan Outer Flash 读出 ID，再用 Flash Operator 新增。）
2. 右键器件 → **Scan Outer Flash** → 选 `.sfc` → Open。
3. 右键 **Outer Flash** → **Program…**，进度完成即固化成功。

## 「扫不到器件」排查（重要）

**症状**：`cfg_scan_chain` 失败，jtagserver 日志 `the idcode from the scanning is: 0xffffffff`，
期望 idcode `0x50602899`（PG2L100H）。

**判据**：`cfg_connect` 成功 = USB/驱动/jtagserver 正常，问题在**下载器 → 目标板**这一段。
TDO 恒高 = TAP 无应答。按可能性排序：

1. **板子没上电 / 供电针脚无 3.3V**：J12 上的 `A3V3` 是 USB Cable II 的电平参考，板子不亮时
   下载器收发器不工作 → TDO 恒高。**先确认 SW1 已 ON、核心板指示灯亮。**
2. **核心板未压合**：FPGA 的 JTAG 经**高速板对板连接器**到 J12，未坐实则扫描不到。
3. **J12 排线方向/插错口**：1 脚红线对齐丝印；别插到串口 USB-C 口。
4. **排线/转接故障**：换排线、换 USB 口；或降到 1 MHz / 100 KHz 再试。

> 本板最终排查通过后，blink 位流成功下载、LED 跑马灯运行。若已扫到器件但下载失败，检查是否
> 选错 `.sbit`（器件不匹配）、排线在烧录中松动。
