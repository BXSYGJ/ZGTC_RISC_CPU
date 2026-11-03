# PDS 位流 → 板载 SPI Flash 固化操作手册（2026-11-03）

本手册打通 `instrec_top.sbit` → 外挂 SPI Flash 固化 → 断电冷启动的完整工具流程。
依据：PDS 2022.2-SP6.4 `Fabric_Configuration_User_Guide.pdf`、`DS04001_Logos2系列FPGA器件数据手册.pdf`、
原厂《05_FPGA&CPLD的下载与固化_v1.1.pdf》、MES2L676-CORE-V1.2 原理图、本机实测转换（2026-11-02 深夜）。
配套结构化证据：`reports/flash_program_flow_20261103.json`。

## 0. 结论摘要（先读）

| 问题 | 结论 |
|---|---|
| .sbit 写 Flash 前要不要转换 | **要**，流程上必须经 Convert File 产出 `.sfc`；但实测 X1 模式（opcode 0x0B）下 `cfg_gen_sfc` 输出与源 `.sbit` **逐字节相同**（SHA256 一致）。`.sbit` 本身即 Flash 线性字节镜像，转换仅在 X2/X4/X8、起始偏移、附加用户数据时才产生差异 |
| 转换工具 | `cdt_cfg.exe -file <tcl>` 里的 `cfg_gen_sfc` 命令，**可完全离线运行**（无需 cfg_connect、不碰 JTAG），已实测产出 |
| 烧写通路 | JTAG 间接烧写外部 Flash（原厂推荐路径）：`cfg_jtag_flash_scan_device / assign_file / erase / program / verify`，FPGA 配置引擎作桥，复用既有 cdt_js（端口 65420） |
| 启动模式 | 板上 M[2:0]=001/MSPI（原理图明文标注 `001,MSPI`，R14 1K 上拉 M0，R13/R15 NC），断电重启自动从外挂 Flash 加载，无需改硬件 |
| 镜像布局 | 位流必须从 Flash **地址 0** 开始；如需偏移或多版本，起始地址必须 **4KB 整数倍**（扇区边界）。3,791,112 B 位流占约 926 个 4K 扇区（≈3.62 MiB），两颗 16 MiB Flash 均容量充裕 |
| 已产出镜像 | `build/flash_boot/instrec_top_w25q128q.sfc`（3,791,112 B，SHA256 `2673246E…`，与源 sbit 逐字节一致） |

## 1. 术语与硬件事实

- 两颗 SPI Flash：**U15/SPI0** 与 **U9/SPI1**（W25Q128JVEIQ / XT25BF128FSSIGU-W 二选一实装，标称 128Mbit=16MiB）。
  - W25Q128JV JEDEC ID = `EF 40 18`（cdt 内建 `W25Q128Q` 条目直接支持）
  - XT25BF128F JEDEC ID = `0B 40 18`（原厂手册明确 configuration 工具**暂不支持**，需 Flash Operator 自定义，见 §6）
- 两颗**共用 SPI_CLK**，接 FPGA 专用配置时钟脚 **H13（CFG_CLK）**（原理图 p3 实证：`CFG_CLK` 网络右侧引脚号 H13，外部网络名 `SPI_CLK`）。
- 两颗片选独立：`SPI0_CS` 与 `SPI1_CS` 分开布线。Logos2 主 SPI 配置口原生有 **FCS_N / FCS2_N 两个片选**（DS04001 表 4-11），对应双 Flash 挂配置口设计。
  - **哪颗是 FCS_N（冷启动第一加载源）未在文本层确认**——原理图连线为纯图形线。上板 `cfg_jtag_flash_scan_device` 可实证（§5 步骤 2）。历史 200HP 板 U9 标注为"用户 QSPI Flash"、U15 为配置器件，100Pro 同系核心板大概率沿用，但**以板上扫描为准**。
- Master SPI 时序上限：CFG_CLK ≤ 40MHz（低速档 15.38MHz、菊花链 25MHz、初始 2.99MHz，占空比 45/55%）。
- 上电时序：TPL ≤ 11ms、TPOR ≤ 71ms、TICCK(CFG_CLK 输出延时) ≥ 400ns（DS04001 表 4-10/4-11）。
- 当前板级状态：JTAG 直载为易失加载，断电即丢；此前记录过重上电后 done=0（Flash 中无有效镜像或未从 Flash 启动），**不排除有一颗存有原厂出货镜像**——擦写前必须备份（§5 步骤 3）。

## 2. 第一步：格式转换（.sbit → .sfc）

### 2.1 工具与命令（已实测，2026-11-02）

转换工具是 PDS 自带 cdt 客户端的 TCL 命令 `cfg_gen_sfc`（Fabric Configuration 手册 §4.5.6-1）。
**不需要连接板子、不碰 JTAG、不弹 GUI**——`cdt_cfg.exe -file` 批处理模式 + TCL 内不写 `cfg_connect` 即为纯文件转换。

```tcl
# build/flash_boot/gen_sfc_w25q128q.tcl（本仓库已存档）
cfg_set_tcl_break -flag false
cfg_gen_sfc -sbit D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/pds/20261102-211104-aedccc03/generate_bitstream/instrec_top.sbit \
            -sfc  D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/flash_boot/instrec_top_w25q128q.sfc \
            -opcode 11 -device_name W25Q128Q
exit
```

运行（bash / powershell 均可）：

```powershell
& 'H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe' -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/flash_boot/gen_sfc_w25q128q.tcl
```

实测输出（`build/flash_boot/gen_sfc_w25q128q.log`）：

```
Executing : cfg_gen_sfc ... successfully.
The Start Address of bit file ...: 0x0
```

### 2.2 参数语义（Fabric Configuration 手册 §4.5.6-1 + 本机 `-help`）

| 参数 | 含义 | 本设计取值 |
|---|---|---|
| `-sbit` | 输入位流（必填） | `instrec_top.sbit`（2673246E…） |
| `-sfc` | 输出文件（默认 sbit 同名同目录） | `build/flash_boot/instrec_top_w25q128q.sfc` |
| `-opcode` | Flash 读命令码：11(0x0B) Fast Read X1/24bit；59(0x3B) Dual；107(0x6B) Quad；12/60/108 为 32bit 地址版本。**默认 11** | `11`（与 MSPI X1 兼容；改 X4 前必须先证明板级布线与配置正确） |
| `-device_name` | 兼容 Flash 型号（默认 N25Q256）。**必须用 cfl 表内确切名** | `W25Q128Q`（JEDEC EF4018；填 `W25Q128` 会被警告 "not supported" 并忽略，实测） |
| `-sbit_start_address` | 位流起始地址（十六进制），会在文件头填充 0xFF | 不用（默认 0） |
| `-is_x8` | X8 双字节流（需第二个 sfc） | false |
| `-fast_mode` | 下降沿采样（Logos 系列选项） | 不用 |
| `-file_list` / `-user_address_list` | 位流后附加用户数据（如权重镜像）及其起始地址 | 首版不用，留作权重固化扩展 |

### 2.3 转换产物实测结论

- **X1 模式下 sfc ≡ sbit（逐字节相同）**：3,791,112 B，SHA256 `2673246ECAC0ECB3E00721C53EFD6B941CC0E8CA44022064AE36C21941D89318`，与源 sbit 完全一致。即 `.sbit` 的 PANGO 头（`...PANGO MICROSYSTEMS, INC...instrec_top...Logos2-PG2L100H--6-FBG676`）本身就是 FPGA 从 Flash 读配置时认可的镜像格式，Flash 里从地址 0 线性存放即可。
- **偏移语义实测**：`-sbit_start_address 0x1000` 产出 3,795,208 B 文件 = 头部 4096 字节 `0xFF` + 原 sbit 原样后移。多版本/双启动布局时按 4K 对齐使用。
- **bit 反转说明**：`cfg_gen_chain_file` 的 `-reverse_bit_in_a_byte` / `-reverse_byte_in_a_word` 仅作用于其生成的 `.bin`（菊花链场景），sbit/sfc 不反转——Logos2 MSPI 无需位序/字节序手工交换。
- GUI 等价操作：`Tools → Configuration → Operations → Convert File → Generate Flash Programming File`（原厂手册 §2.(3)-(5) 同流程）。

### 2.4 GUI 里怎么做（对照参考，本次未用 GUI）

原厂《05_FPGA&CPLD的下载与固化》标准路径：Configuration 工具 → Scan Device → 右键 PANGO 器件 → Scan Outer Flash（可先看 Flash ID）→ Operations → Convert File → 选 Flash 厂家/型号 + sbit → OK 生成 sfc → 右键 Outer Flash → Program。

## 3. 第二步：JTAG 间接烧写外部 Flash（通路与命令）

### 3.1 通路选择

Fabric Configuration 手册给出三条外挂 Flash 操作通路：

| 通路 | 命令族 | 适用 | 本板 |
|---|---|---|---|
| **JTAG 直接编程外部 Flash**（§4.3.11） | `cfg_jtag_flash_*` | Logos/Compact 系列直接 JTAG 操控外挂 Flash | Logos2 走 §4.3.26 间接模式，命令族相同 |
| **JTAG 间接烧写外部 flash**（§4.3.26） | 同上（"operate outer flash through fpga"） | Logos、Logos2、Titan2 部分器件 | **本板采用**（原厂手册同路径） |
| SPI Flash Configuration 模式（§4.3.12-4.3.17） | `cfg_flash_*` | 下载器直连板上 SPI 口的调试场景 | 本板无此连接，不用 |

间接烧写原理：JTAG → FPGA 配置引擎 → CFG_CLK(H13)/FCS_N/DI/DO 配置引脚 → 目标 Flash。烧写期间 FPGA 处于配置态，**Flash 归配置引擎管**；这也意味着被写的是挂在配置口上的那颗（活动配置器件）。sfc 若是 SPI X8 需两个文件（本设计 X1 单文件）。

### 3.2 TCL 命令级流程（上板执行，本次未运行）

Fabric Configuration 手册 §4.5.4 全部命令（`-device_index` 默认 0）：

```
cfg_jtag_flash_scan_device        # 扫描外挂 Flash（列出器件与 JEDEC ID）
cfg_jtag_flash_assign_file -file <path.sfc>
cfg_jtag_flash_erase              # 擦除（属性默认 Erase before Program，见 §4.3.18）
cfg_jtag_flash_program            # 编程
cfg_jtag_flash_verify             # 校验（回读比对）
cfg_jtag_flash_readback -file <path.sfc>   # 整片/按属性回读（备份用）
```

完整烧写 TCL 模板（复用既有 cdt_js，端口 65420；**严禁新起/终止 cdt_js**）：

```tcl
# scripts/jtag_flash_program.tcl（拟新增，本轮未写入 scripts/，先在手册固化）
cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
cfg_set_cable_property -index 0 -freq 10Mhz
cfg_scan_chain
# 1. 扫描外部 Flash：确认 JEDEC ID（EF4018=Winbond 直接支持；0B4018=XTX 需 §6 自定义）
cfg_jtag_flash_scan_device -device_index 0
# 2. 备份原内容（擦写前必做！）
cfg_jtag_flash_readback -device_index 0 -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/flash_boot/backup_before_flash.sfc
# 3. 指定镜像并三步烧写
cfg_jtag_flash_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/flash_boot/instrec_top_w25q128q.sfc -device_index 0
cfg_jtag_flash_erase -device_index 0
cfg_jtag_flash_program -device_index 0
cfg_jtag_flash_verify -device_index 0
cfg_disconnect
exit
```

纪律要点（沿用 `tests/test_board_flash_safety.py` 锁死的三条）：

1. cdt_cfg 以 `exit` 自行收尾，任何脚本不得 terminate/Stop-Process `cdt_js`/`cdt_cfg`；
2. 一律复用已运行的 cdt_js（127.0.0.1:65420 端口没起来就等，绝不新起）；
3. 烧写失败/卡住时报告 PID 并人工处理，不强杀。
   编程不稳定时（手册 §4.3.14）：降低 Cable 频率 + 选 Slow Program（等待时间最长档）。
   Flash 属性（擦除模式/回读大小/起始块）在 GUI `Set Device Properties` 配置；TCL 侧由 assign 的 sfc 尺寸驱动 Auto 擦除（默认 Flash Erase before Program 勾选）。

## 4. 第三步：冷启动验证与镜像布局

### 4.1 启动模式确认

- 原理图 p3 明文标注 **`001,MSPI`**；模式网络 `FPGA_M0/M1/M2` 接 R14(1K 实装，上拉 A3V3)/R13(1K/NC)/R15(1K/NC) → M0=1, M1=M2=0 → M[2:0]=`001`。
- Logos2 每次上电 SRAM 型配置：主 SPI 模式下 FPGA 自己产生 CFG_CLK（初值 2.99MHz，可升到 40MHz 内），用 FCS_N 片选外挂 Flash 从**地址 0** 顺序读配置流。
- **无需任何模式拨码改动**，断电重启即自动尝试从活动配置 Flash 加载。

### 4.2 镜像布局（首版）

```
Flash(16MiB) 0x000000 ───────────── 0x39E1C8 ────────────────── 0xFFFFFF
             └── instrec_top.sfc ──┘ 空闲(约12.4MiB)
             (3,791,112 B ≈ 926 个 4K 扇区)
```

- 位流从地址 0 线性存放（sfc 即完整字节镜像，含 PANGO 头，无附加填充）。
- 权重固化扩展位（后续）：建议从 `0x400000`（4MiB，4K 对齐、远离位流尾部余量）开始；用 `cfg_gen_sfc` 的 `-file_list`+`-user_address_list` 可把权重镜像打进同一个 sfc，或独立分区另写。
- 多启动/回退（Logos2 支持 Multi Boot Data Stream、看门狗超时回退）：非首版范围，需要时用 Convert File 的 Generate Multi Revision File（各 revision 起始地址强制 4K 对齐）。

### 4.3 冷启动验收步骤（上板）

1. 烧写+verify 通过后，**完全断电**（不能只按 reset），移除下载器参与；
2. 重新上电，JTAG 只读查状态（`cfg_read_device_property -mode 3`）：`done=1`、`crc_err=0`、`id_err=0`；
3. 串口 COM5 应收到 `RV32 BOOT / MMIO OK / ISA OK / DDR OK`（位流内已含 CPU 固件，无需独立程序 Flash）；
4. HDMI 显示中文仪表盘（2673246E 已验收过的 UI 行为）；权重仍走 UART `weight_upload.py`（WOK FA0D5236）后 NPU 推理回读。
5. 若 done=0：读状态寄存器定位（`crc_err`→镜像错；`id_err`→器件/模式错；timeout→看门狗超时回退触发），按 §7 回退。

## 5. 上板操作序列（谁先谁后）

> 本次任务未执行任何 JTAG/板级操作；以下是拿到授权后的执行顺序。

| # | 动作 | 工具/命令 | 判据 |
|---|---|---|---|
| 1 | 确认 cdt_js 在线 | 复用 127.0.0.1:65420（PID 9040 实例；端口未开则等待，不起进程） | 端口可连 |
| 2 | 只读扫链+扫外挂 Flash | `cfg_scan_chain` → `cfg_jtag_flash_scan_device` | 列出 Outer Flash 与 JEDEC ID；**同时回答"哪颗是活动配置器件"与"实装型号"** |
| 3 | **备份原 Flash 内容** | `cfg_jtag_flash_readback -file backup_before_flash.sfc`（两颗都备份，若都可寻址） | 备份文件非全 FF/非空，hash 留档 |
| 4 | （仅当 ID=0B4018）新增自定义 Flash | GUI Flash Operator（§6）或改用 W25Q128Q 兼容条目 | Scan 能识别 |
| 5 | 擦除+编程+校验 | §3.2 TCL（assign→erase→program→verify） | `COMMAND[...] execute successfully` |
| 6 | 断电冷启动 | 拔电重上电 | §4.3 验收全过 |
| 7 | 失败回退 | §7 | 恢复 JTAG 直载 |

## 6. 已知坑（原厂手册与实测）

1. **`-device_name` 必须用 cfl 确切名**：填 `W25Q128`（表 21 的显示名）会得到 `W25Q128 is not supported` 警告且被忽略（实测）；`arch/vendor/pango/arch/cdt/flash_list_cd.cfl` 内的正确条目是 `W25Q128Q`（0x00EF4018）与 `W25Q128M`（0x00EF7018）。W25Q128**JV** 的 JEDEC 是 EF 40 18 → 用 `W25Q128Q`。
2. **XT25BF128F（芯天下）不被 cdt 内建支持**：JEDEC `0x0B4018`。原厂手册 §2.(2) 的解法：右键 PANGO 器件 → Scan Outer Flash 读到 ID → Operations → Flash Operator → 新增（厂商/系列/容量/ID 0xb4018）→ 重启 Configuration 工具后可扫到 `x25f128`。TCL 侧等价命令未在手册 §4.5 列出（`cfg_flash_write_register` 之外的自定义器件命令族未公开），**XTX 实装时该步需 GUI 完成**。
3. **烧的是外挂 Flash ≠ JTAG 直载**：`cfg_program`（现有 `jtag_program_latest.tcl`）是易失 CRAM 配置；Flash 固化必须走 `cfg_jtag_flash_*`。两者烧写属性互不相干。
4. **擦除后状态**：SPI Flash 擦后全 1（0xFF）；Compact 嵌入式 Flash 才是全 0。备份文件全 FF 即原片为空。
5. **一次只能一个 pds_shell / 一个 cdt_cfg**；cdt_js（jtagserver，持有 FT2232H D2XX 句柄）全局唯一，复用不新建（`tests/test_board_flash_safety.py` 锁死）。
6. 烧写速率档（Typic/Fast/Slow Program）与 Cable 频率：失败先降频再换 Slow。

## 7. 风险与回退

- **主要风险**：
  1. 覆盖原厂出货镜像（未备份即不可逆）→ 步骤 3 强制备份；备份文件与 hash 存 `build/flash_boot/`；
  2. 实装为 XT25BF128F 时 cdt 不识别 → §6.2 GUI 自定义；或按 W25Q128Q 兼容条目先试（命令集兼容，仅 ID 不同——擦写前 Scan 确认）；
  3. 冷启动 done=0（镜像 CRC 错/模式引脚接触/看门狗回退）→ 状态寄存器定位；verify 已过而冷启失败优先怀疑模式电平与器件选择；
  4. `SCBV has not been set` 是原厂缺省 PCB 参数的正常提示，不是错误（既有结论）。
- **回退 = 恢复 JTAG 直接加载**（永不受 Flash 内容影响，JTAG 模式优先级最高）：

```tcl
# 现有 scripts/jtag_program_latest.tcl 原样可用
cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
cfg_set_cable_property -index 0 -freq 10Mhz
cfg_scan_chain
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/instrec-latest.sbit -device_index 0
cfg_program -device_index 0
cfg_disconnect
exit
```

- 想清空 Flash 恢复"无固化"状态：`cfg_jtag_flash_erase`（擦后全 FF，FPGA 上电找不到有效同步字→保持未配置，done=0，JTAG 仍可入）。

## 8. GTP_CFGCLK 与用户模式读 Flash（次优先，为权重固化铺路）

### 8.1 原语事实

- 仿真模型 `arch/vendor/pango/verilog/simulation/GTP_CFGCLK.v` 与综合库 `logos2/common/lib/gtp_lib.v`（PG2L100H 映射存在）端口均为：

```verilog
module GTP_CFGCLK ( input CLKIN, input CE_N );
```

- 语义：把用户时钟 `CLKIN` 接到专用 CFG_CLK（H13）输出通路，`CE_N` 低有效使能。**无数据端口**——它只解决"用户逻辑驱动配置时钟"，不提供 Flash 数据通路。
- 端口语义（推断+库佐证）：单向输出到 H13；不占用用户时钟树；`CE_N=1` 时钟门控关断。

### 8.2 用户模式访问的整体可行性（更新此前评估）

PG2L100H 器件配置数据（`arch/vendor/pango/logos2/pg2l100h/data/config/ini_data/Logos2-PG2L100H.ini`）默认值：

```
(persist_pin          "Release For USER")     // 配置复用引脚用户态释放（另一选项 Persist For Configuration）
(persist_slave_spi_pin "No")
(flash_read_mode      "X124-bit")
(create_mask_file     "True")
(bitstream_security   "enable reconfigure, enable readback")
(encrypt_bitstream    "No")
```

即 **Logos2 默认把配置复用引脚（CS/DI/DO 等 IO）在用户模式下释放**（persist_pin 写入 ctrl0_data[2]），配合 GTP_CFGCLK 的时钟通路，用户逻辑理论上可以自己驱动 SPI 总线读两颗 Flash。历史 cpu/ 工程"普通 IO 无法布局 H13"只约束了时钟脚，不否定该组合路径。**PG2L100H 实际可用性仍未证明**（位流生成时 persist_pin 选项如何进 PDS GUI、释放的是哪些具体引脚号，需 UG040005《Logos2 配置用户指南》，本机无此文档，列为未决）。

### 8.3 最小 JEDEC 读回探针设计（不写 RTL，仅设计）

目标：证明用户模式能读 Flash（读 JEDEC ID 0x9F，三字节应答），区分 U15/U9。

- **时钟域**：PLL 25MHz → `GTP_CFGCLK(CLKIN, CE_N=1'b0)` → H13（≤40MHz 上限内留裕量）；
- **数据/片选**：`SPI0_CS`、`SPI0_DI(IO0)`、`SPI0_D1(IO1)` 按 §8.2 释放的复用 IO 指定约束（引脚号待 Scan Outer Flash / UG040005 确认，**禁止猜普通 IO**——历史 flash.fdc 占位引脚教训）；
- **状态机**：IDLE → 发 0x9F（CS 拉低，8 拍 MOSI）→ 采 24 拍 MISO → CS 抬高 → LATCH ID → UART 打印 `JED ec:xx:xx`；
- **验收**：Winbond 期望 `EF 40 18`，XTX 期望 `0B 40 18`；两颗分别用 SPI0_CS/SPI1_CS 各测一次即同时解决"哪颗是谁"；
- **隔离原则**：独立诊断分支/试验位流，不混入主线 RTL；DDR/音频/NPU 全部不例化。
- 后续权重加载若此路不通：回退方案是 UART loader（现有）或外接 3.3V SPI 模块（可行性文档既定边界）。

## 9. 未决事项清单（上板前必须逐项确认）

| # | 事项 | 确认手段 |
|---|---|---|
| 1 | 实装 Flash 型号（W25Q128JV vs XT25BF128F）与两颗是否都焊 | `cfg_jtag_flash_scan_device` 读 JEDEC |
| 2 | 哪颗是 FCS_N（冷启动第一加载源） | 扫描结果 + 备份内容比对（有原厂镜像的即启动源）；必要时分别烧试验镜像冷启验证 |
| 3 | 间接烧写能否寻址两颗（FCS2_N 第二颗是否也可经 cdt 操作） | 扫描列表观察；仅第一颗可用则第二颗留给用户模式探针 |
| 4 | XT25 自定义 Flash 的 TCL 化（GUI-only 风险） | 实装为 XTX 时按原厂手册 §2.(2) 走 GUI 一次并记录等效 TCL |
| 5 | GTP_CFGCLK 用户模式可用性与释放引脚号 | §8.3 探针位流 + UG040005（需获取文档） |
| 6 | 冷启动后 NPU/DDR/HDMI 全链在非 JTAG 供电时序下稳定 | §4.3 验收 + 长时观察 |
