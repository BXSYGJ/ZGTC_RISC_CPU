# 盘古 100Pro+（MES2L676-100HP）PDS 全流程与串口连接

> 面向接手人：本板为线下开发板，芯片 **PG2L100H-6IFBG676**（Logos2，速度等级 -6，FBG676）。
> 本文记录**已验证可用**的本地 PDS 流程（建工程 → 综合 → 实现 → 生成位流 → JTAG 下载 → 上板验证），
> 以及**串口调试**的连接方法。
>
> 状态（2026-10-11）：`pds_minimal_blink_100h` 已在本板跑通——位流下载成功、8 个 LED 跑马灯运行。
> **未验证**：Flash 固化（`.sfc`）、RISC-V CPU 迁移到 100H、DDR3（暂不使用）。

---

## 1. 环境与工具

| 项 | 值 |
| --- | --- |
| PDS 版本 | 2022.2-SP6.4（build 146967） |
| PDS 安装目录 | `H:\GG\pango\PDS_2022.2-SP6.4`（`PDS_ROOT`） |
| 许可证 | `PANGO_LICENSE_FILE` 用户级环境变量 |
| 命令行 Shell | `%PDS_ROOT%\bin\pds_shell.exe`（**批处理，不弹 GUI**） |
| 下载/配置工具 | `%PDS_ROOT%\bin\cdt_cfg.exe`（需 jtagserver，见 §5.3） |
| 下载器 | 紫光同创 **Pango USB Cable II**（FT2232H，VID_0403/PID_6010） |
| 目标芯片 | **PG2L100H-6IFBG676** |
| 板级时钟 | `FPGA_GCLK_27M = D18`（27 MHz） |
| 电源 | +12V DC（用自带电源），底板 **SW1** 电源开关；核心板 5V 经板对板连接器 |

> Windows 上不需要 WSL / Icarus。`pds_shell.exe` 是命令行 Fabric Compiler Shell，不是图形界面 `pds.exe`。

---

## 2. 器件与板卡要点

- 核心板：MES2L676-100HP，主控 **PG2L100H-6IFBG676**，2 片 DDR3（共 8 Gbit，32bit）。
- 底板：MES2L676-BASE-V1.2，板载 USB 转串口（**CP2102 + USB Type-C**）。
- **JTAG**：底板 **J12**（10 针 2.54mm 双排排针）；核心板正面左上角另有 JTAG 触点。FPGA 的 JTAG 信号经**高速板对板连接器**引到底板 J12。
- 关键器件/引脚与 200Pro+（PG2L200H）**不同**，切勿混用 200H 的约束/器件配置。

### 2.1 与 200Pro+ 的引脚差异（本板官方《硬件实验指导手册》确认）

| 信号 | 管脚 | 与 200H 是否相同 |
| --- | --- | --- |
| `clk`（27 MHz） | D18 | **相同** |
| `rst_n` KEY0 | C22 | **相同** |
| `key` KEY1 | C23 | **相同** |
| `led[0..7]` | A20/C18/C19/E18/A17/A18/C17/B17 | **相同** |
| 板载串口 `uart_rx`(FPGA 输入) | B24 | **相同** |
| 板载串口 `uart_tx`(FPGA 输出) | C24 | **相同** |
| **DDR3** | — | **不同**（bank/引脚不同，须按 100Pro+ 官方 2_9 工程重新取） |

> 普通 IO（时钟/按键/LED/UART）与 200H 一致，迁移时基本不用改；**DDR3 约束不能照搬 200H**。

---

## 3. 参考工程 `pds_minimal_blink_100h/`

最小流水灯工程，用来验证「工具链 + 下载链路」是否通。

```
pds_minimal_blink_100h/
├── src/blink_top.v              # 8 灯每 0.5s 移动，KEY1 控制方向
├── constraints/blink_top.fdc    # clk D18 / rst_n C22 / key C23 / led A20...
├── sim/blink_top_tb.v           # testbench（仅登记，批处理不跑仿真）
├── scripts/
│   ├── run_pds_full.ps1         # 一键：综合→实现→位流 + 校验
│   ├── build_full.tcl           # PDS 批处理 TCL（含 __PROJECT_ROOT__ 令牌）
│   ├── program_full.tcl         # CLI 下载（cdt_cfg，需 jtagserver）
│   ├── test_scan.tcl            # 只扫描 JTAG 链
│   └── scan_chain.tcl / test_scan_1mhz.tcl / test_scan_lowfreq.tcl / test_cable.tcl / test_prop.tcl
└── generate_bitstream/blink_top.sbit   # 位流（约 3.79 MB，git 忽略）
```

---

## 4. 构建：综合 → 实现 → 生成位流

### 4.1 一键脚本（推荐）

```powershell
# 在工程根执行；脚本自动展开 TCL 令牌、调 pds_shell、校验 E: 错误与位流存在
pwsh -NoProfile -File .\pds_minimal_blink_100h\scripts\run_pds_full.ps1
```

### 4.2 等价的手工 TCL

```tcl
add_design    "<root>/src/blink_top.v"
add_constraint "<root>/constraints/blink_top.fdc"
add_simulation "<root>/sim/blink_top_tb.v"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -top_module blink_top
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
```

调用：

```
pds_shell.exe -file build_full.tcl -work_dir <project_root> -project_name <name>
```

### 4.3 阶段与判定

| TCL | 阶段 | 产物 |
| --- | --- | --- |
| `compile` | 编译/解析 | compile/ |
| `synthesize -ads` | ADS 综合 | synthesize/ |
| `dev_map` | 器件映射 | device_map/ |
| `pnr` | 布局布线 | place_route/ |
| `report_timing` | 时序报告 | report_timing/ |
| `gen_bit_stream` | 生成位流 | `generate_bitstream/<top>.sbit` |

- 判定：进程退出码非 0 → 失败；即使为 0，输出含 `^E:` 行也算工具报错。
- `C: Bitstream-2001: SCBV has not been set` 是**正常提示**（原厂未给 PCB 参数），不影响位流生成。
- 本工程时序：setup WNS **34.379 ns**（MET），hold WHS 0.274 ns（见 `multiseed_summary.csv`）。

---

## 5. 下载（JTAG）与固化

### 5.1 前置

1. 用 +12V 适配器供电，**先接 JTAG 排线和电源线，再打开底板 SW1**，确认核心板指示灯亮。
2. 10 针排线一端接 **USB Cable II**，一端接底板 **J12**，红线（1 脚）对齐 J12 丝印 1 脚；**通电时禁止插拔 JTAG**。

### 5.2 GUI 路径（最稳，推荐）

1. PDS 菜单 **Tools → Configuration**（或工具栏 Configuration 图标）。
2. 点 **Scan Device**（扫描 JTAG 链）。成功会列出 PANGO 器件并弹窗选择 `.sbit`。
3. 选择 `pds_minimal_blink_100h/generate_bitstream/blink_top.sbit`，**右键器件 → Program**。
4. 信息区出现 `COMMAND[Program] execute successfully..` 即下载成功，观察 LED。

### 5.3 CLI 路径（脚本化，需 jtagserver）

`cdt_cfg` 本身不驱动硬件，它连接 PDS 提供的 **jtagserver**（默认 `127.0.0.1:65420`）：

```powershell
# 先让 PDS Configuration 打开（其会拉起 jtagserver:65420），再执行：
"H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe" -file ".../scripts/program_full.tcl"
```

`program_full.tcl` 依次：`cfg_connect` → `cfg_set_cable_property -freq 10Mhz` → `cfg_scan_chain`
→ `cfg_assign_file -file <sbit>` → `cfg_program` → `cfg_disconnect`。
只扫描不烧录用 `test_scan.tcl`（可先跑它确认链路）。

### 5.4 固化到 Flash（`.sfc`，未在本板验证）

参考《05_FPGA&CPLD的下载与固化_v1.1》与《教程2》§7.7.9：

1. Configuration → **Operations → Convert File**，选 Flash 厂商/型号与 `.sbit`，生成 `.sfc`。
2. 右键器件 → **Scan Outer Flash**，选 `.sfc` → Open。
3. 右键 **Outer Flash** → **Program…**，进度完成即固化。

> 若 Flash 型号不在列表，需先按手册「新增用户 Flash」（用 Scan Outer Flash 得到的 ID 添加）。

---

## 6. 串口连接开发板（UART）

本板自带 **USB 转串口**，不需要外部串口模块。

### 6.1 硬件连接

1. 用一根 **USB Type-C 数据线**，从 PC 接到开发板底板的 **USB 转串口 Type-C 口**（板载串口芯片 **CP2102**）。
   ⚠️ 这个口与 **JTAG 的 J12 排线**是两回事，别插错。
2. FPGA 侧信号（已在 PCB 上连到 CP2102，无需自己接线）：

| 信号 | FPGA 管脚 | 方向 | 电平 |
| --- | --- | --- | --- |
| `uart_rx`（FPGA 接收，接 CP2102 TXD） | **B24** | INPUT | LVCMOS33 |
| `uart_tx`（FPGA 发送，接 CP2102 RXD） | **C24** | OUTPUT | LVCMOS33 |

### 6.2 驱动与端口号

- 装 **Silicon Labs CP210x VCP 驱动**（Win10/11 多数可自动装；不识别时装一次）。
- 设备管理器 → **端口(COM 和 LPT)** 应出现 `Silicon Labs CP210x USB to UART Bridge (COMx)`，记下 `COMx`。

### 6.3 串口参数

| 参数 | 值 |
| --- | --- |
| 波特率 | **115200** |
| 数据位 / 校验 / 停止位 / 流控 | **8 / None / 1 / None**（8N1） |

> 依据：官方 `2_8_uart_test` 顶层 `BPS_NUM = 16'd234`，27 MHz / 234 ≈ 115384 ≈ **115200**。
> 注：《教程2》§8.6 的正文写「波特率设置为 9600」，与随板代码不符（疑似沿用旧文案）；
> 若 115200 收到乱码，再试 9600。

### 6.4 上位机软件

任意串口终端均可：Windows 串口助手 / PuTTY / Tera Term，或 Python：

```python
import serial
ser = serial.Serial('COM5', 115200, timeout=1)   # 把 COM5 换成实际端口
print(ser.readline())
```

### 6.5 重要前提

- **当前 `blink` 工程没有 UART 逻辑**，插上串口不会有任何输出——串口要搭配**含 UART 的设计**才有数据。
- 想立刻验证串口，可先烧官方 `2_8_uart_test`（每秒回 `www.meyeseyesemi.com` 风格字符串，发 `ff` 点亮全部 LED）；
  或等 RISC-V CPU + bootloader 迁移到 100H 后，用其串口控制台做收发。

---

## 7. 踩坑：JTAG「扫不到器件」排查

**症状**：`cfg_scan_chain` 失败，jtagserver 日志里 TDO 恒为 `0xffffffff`，期望 idcode `0x50602899`。

**判定思路**：`cfg_connect` 能成功 → USB/驱动/jtagserver 正常，问题在**下载器到目标板这一段**。按可能性：

1. **板子没上电 / 供电针脚无 3.3V**：J12 上的 `A3V3` 是 USB Cable II 的电平参考，板子不亮时下载器无法收发 → TDO 恒高。**先确认底板 SW1 已 ON、核心板指示灯亮。**
2. **核心板未压合**：JTAG 信号经板对板连接器到 FPGA，未坐实则扫描不到。
3. **J12 排线方向 / 插错口**：1 脚红线对齐丝印；别插到 USB-C 串口口；通电时勿插拔。
4. 排线/转接故障：换线、换 USB 口。

> 本板最终排查通过后，blink 位流成功下载、LED 跑马灯运行。

---

## 8. 相关文件

| 用途 | 路径 |
| --- | --- |
| 参考工程 | `pds_minimal_blink_100h/` |
| 一键构建 | `pds_minimal_blink_100h/scripts/run_pds_full.ps1` |
| CLI 下载 | `pds_minimal_blink_100h/scripts/program_full.tcl` |
| 位流 | `pds_minimal_blink_100h/generate_bitstream/blink_top.sbit` |
| 开发板资料 | `D:\0000\111\001\Pango\docs\盘古100Pro+开发板（MES2L676-100HP）配套资料\` |
| 下载与固化手册 | 资料 `1_Demo_document\工具使用篇\05_FPGA&CPLD的下载与固化_v1.1.pdf` |
| 通用实验手册 | 资料 `1_Demo_document\实验指导手册教程\教程2_通用实验指导手册_盘古676系列100Pro+开发板.pdf`（§7.7.9 下载 / §8 串口） |
| 硬件实验手册 | 资料 `1_Demo_document\实验指导手册教程\教程1_硬件实验指导手册_盘古676系列100Pro+开发板.pdf` |
| 原理图 | 资料 `3_Hardware\原理图\MES2L676-BASE-V1.2原理图.pdf` |
| 技能 | `docs/skills/pango-pg2l100h-dev/` |
| 交接快照 | `docs/开发快照交接说明_20261011.md` |
