# ZGTC RISC-V SoC — 开发快照（2026-09-07）

> 目的：给「下一个人」一份可直接接手的状态记录。读完本文件应能知道：
> 项目在做什么、怎么构建、怎么把程序弄到板子上、当前卡在哪、下一步该试什么。

---

## 0. 一句话现状

**RV32IM SoC 已在 Pango PG2L200H (MES2L676-200HP) 上验证跑通（153 MHz，CoreMark 511 分，CRC 校验通过）。**
已融合 DYH 高性能 CPU（`full_fetch_commit_factored`，RV32IM/153MHz/16KB I-Cache/分支预测）与 XSY 串口烧录（简化 bootloader 固化前 4KB，`R` 命令流控载应用）。
**当前推荐交付**：`tool/fpga_lab/coremark_verify.py` 一键烧录验证（找箱 → 烧 153MHz 位流 → R 命令载 CoreMark → 算分）。
**换其他程序**：`tool/fpga_lab/ram_load.py` 载 RAM 运行（断电丢失，换程序快速、无需重综合）。

> 注：2026-09-12 完成最终功能融合，本快照此前的 27 MHz RV32I 描述为历史基线；当前主交付目标是 153 MHz / RV32IM / 511 分。

---

## 1. 目标与背景

- 在 Pango PG2L200H FPGA 上实现一个 RV32I（可选 M 扩展）SoC，含 BRAM、UART、GPIO、SPI Flash 控制器、I-Cache。
- 程序存于板载用户 Flash (U9)，上电由 BRAM 内的 bootloader 读到 RAM 启动。**换程序只烧 Flash，不需重新综合**（这是 `FLASH_BOOT` 设计的核心目的）。
- 开发在**远程实验箱**上进行：板子不在本机，通过 `fpga-lab-bridge` 服务（HTTP + WebSocket 串口）访问。

---

## 2. 环境

| 项 | 值 |
|----|----|
| 本机 RISC-V 工具链 | `H:\ST\RV32I\bin\riscv-none-elf-*`（xPack GCC 15.2.0，需显式 `-march=rv32i_zicsr_zifencei`） |
| 工具链查找顺序 | `$env:RV32_TOOLCHAIN` → `H:/ST/RV32I` → `D:/ST/RV32I` |
| PDS（综合/实现/位流） | 紫光同创 PDS，批处理流程在 `cpu/scripts/run_pds.ps1` |
| 桥接服务 | `fpga-lab-bridge` v0.2.0，监听 `127.0.0.1:8600` |
| 桥接服务目录 | `tool/fpga_lab`（已移入本工作区） |
| 桥接启动命令 | `python -m uvicorn fpga_lab_server.app:create_app --factory --host 127.0.0.1 --port 8600` |
| 串口参数 | 115200 8N1 |
| 实验箱鉴权 | `tool/fpga_lab/account.txt`（untracked，**含凭据，勿提交、勿写进本快照**） |

> ⚠️ 桥接服务是**后台进程**，约 10 分钟无活动会被杀（前台超时也会断）。连不上先 `curl http://127.0.0.1:8600/api/v1/health` 看是否还在；不在就按上面命令重启。

---

## 3. 项目结构与关键文件

```
D:/0000/111/001/Pango/
├── ZGTC_RISC_CPU/cpu/                 # SoC 主体（git 仓库）
│   ├── rtl/                          # 所有 RTL（.sv）
│   │   ├── rv32_soc.sv               # 顶层 SoC
│   │   ├── rv32_board_top.sv         # 板级顶层（引脚/U9 flash）
│   │   ├── rv32_spi_flash.sv         # SPI Flash 控制器
│   │   └── rv32_peripherals.sv       # MMIO 寄存器（含 SPI）
│   ├── sw/
│   │   ├── start.S                   # 复位向量/栈
│   │   ├── link_soc.ld               # 应用链接到 0x1000
│   │   ├── app_big.c                 # 当前大程序（43KB 源码，12980B 二进制，<17KB 上限内）
│   │   ├── app_hello.c               # 最小示例
│   │   └── boot/                     # bootloader 源码（固化进 BRAM 前 4KB）
│   ├── scripts/
│   │   ├── build_boot.ps1            # 只编 bootloader → bootloader.hex
│   │   ├── build_app.ps1             # 编应用 → .bin/.elf/.dis
│   │   ├── run_pds.ps1               # 综合生成位流（支持 -FlashBoot -UartProfile RemoteLab）
│   │   ├── mkflash.py                # 打 Flash 镜像头（magic 'RFCP' + len + bin）
│   │   └── burn.py                   # 生成/发送 bootloader 控制台字节流（W/R 命令）
│   ├── constraints/                  # board.fdc / flash.fdc / uart_*.fdc
│   ├── docs/FLASH_BOOT.md            # ★ Flash 启动权威说明（必读）
│   └── build/
│       ├── app_big.bin               # 当前固件二进制（12980B）
│       ├── bootloader.hex            # 固化进 BRAM 的 bootloader
│       ├── pds-latest.json           # 最近一次 PDS 构建的元信息/SHA
│       └── pds/<run>/generate_bitstream/pds_soc_top.sbit  # 位流
└── tool/fpga_lab/                    # 远程桥接服务 + 测试脚本（独立于 SoC 仓库）
    ├── fpga_lab_server/              # 服务本体（HTTP 设备预约/位流烧录 + WebSocket 串口）
    ├── test_designs/uart_beacon/.../uart_beacon.sbit  # 心跳位流（烧它后板子周期性回显，用于确认链路活着）
    ├── big_load.py                   # 单次整包上传 33KB（R 命令 + K 计数校验）—— 复现 17KB 上限
    ├── big_load_seg.py               # 分段 + 重开 WebSocket 上传 —— 验证「重开不重置上限」
    └── stream_load.py                # 另一种流式上传尝试
```

**有效位流路径（已验证可用）**：
- 固件位流：`cpu/build/pds/20260907-195930-0a2aa5d6/generate_bitstream/pds_soc_top.sbit`
- 心跳位流：`tool/fpga_lab/test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit`

---

## 4. 把程序弄到板子上的「两条路径」

详细见 `cpu/docs/FLASH_BOOT.md`。要点：

**内存布局**：BRAM 64KB。前 4KB（0x0000–0x0FFF）固化 bootloader；应用区 0x1000–0xFFFF（**60KB**）。
链接脚本 `sw/link_soc.ld` 把应用链到 `0x1000`。

**上电流程**：bootloader 读 U9 Flash → 镜像头合法则拷贝到 0x1000 → `fence.i` → 跳转。
按住 KEY0 复位进入 UART 恢复控制台，提示 `ZBOOT`。

**bootloader 控制台命令**（115200 8N1，发 raw 字节）：
- `W<len:u32><bin>` — 擦写 Flash 并启动（**正式换程序**，之后复位自动从 Flash 启动）
  ⚠️ 当前板子受 H13 专用引脚限制，软 SPI 物理够不到 U9，`W` 命令会报 `ERR erase`，不可用。
- `R<len:u32><bin>` — 直接载 RAM 运行（**不写 Flash**，快速迭代）
- `B` — 从 Flash 启动；`E` — 擦扇区；`?` — 帮助

**本机工具**：
```powershell
pwsh cpu/scripts/build_boot.ps1                       # 生成 bootloader.hex
pwsh cpu/scripts/run_pds.ps1 -FlashBoot -UartProfile RemoteLab   # 生成 FlashBoot 位流
pwsh cpu/scripts/build_app.ps1 -Source cpu/sw/app_hello.c -Name app_hello
python cpu/scripts/mkflash.py cpu/build/app_hello.bin cpu/build/app_hello.img
python cpu/scripts/burn.py cpu/build/app_hello.bin --ram --port COM7        # 本地 COM 直连
python cpu/scripts/burn.py cpu/build/app_hello.bin --out app_hello.uart.dat # 远程：生成本地字节流，再去网页串口原样发
```

**当前推荐路径（远程实验箱）**：
```powershell
# 1) 确认桥接服务活着
curl -s --max-time 6 http://127.0.0.1:8600/api/v1/health

# 2) 编译固件
pwsh cpu/scripts/build_app.ps1 -Source cpu/sw/app_big.c -Name app_big

# 3) 用 ram_load.py 流控发送（R 命令载 RAM，13KB/33KB 均实测成功）
python tool/fpga_lab/ram_load.py                                    # 默认 13KB
python tool/fpga_lab/ram_load.py cpu/build/app_huge.bin             # 33KB 大文件
```

---

## 5. 已验证的事实（确定无误）

1. **SoC 功能正确**：RV32I 跑通，CoreMark 达标（120 MHz 目标，硬件验证通过 `git log` 可见）。
2. **位流通道正常**：通过桥接 HTTP `/api/v1/bitstream` 烧录大位流（~9MB）完全没问题。
3. **大文件下发真因不是「17KB 固定上限」，而是串口发送无流控**：旧脚本一次性盲发整个 payload，
   导致 platform 串口 `server→板子` 发送缓冲有限、溢出丢字节，送达量时变（13KB 实测分别只到
   6.5KB/9.5KB/10.5KB/乱码），远低于 17KB，且第三次出现 `ERR no image`/`ERASED` 乱码（字节流被
   截断后串位）。bootloader 每收 256 字节回一个 `K`，本意就是让主机做流控（背压）。
4. **流控方案已实测成功**：改成「逐块发 256 字节 → 等一个 `K` 回执 → 再发下一块」，成功完整送达：
   - 13KB `app_big.bin`（12980B）→ 板子输出 `BIG 3072` + 校验和 `ecedda00` + `OK`
   - 33KB `app_huge.bin`（33460B，校验和 `0x27033f46`）→ `BIG 8192` + `OK`
5. **写 Flash（`W` 命令）在当前板子物理不可行**：bootloader 擦写 U9 Flash 报 `ERR erase`
   （`flash_wait_ready` 超时）。根因：U9 真实时钟引脚 H13 是 PDS 无法布局为用户 IO 的**专用配置
   引脚**，软 SPI 物理够不到 U9；`cpu/constraints/flash.fdc` 里 R15/P18/P14/N14 只是「让设计可
   综合」的占位引脚（真实 U9 引脚 CS=F25 CLK=H13 DI=R14 DO=R15，N14 实为 HOLD、R15 实为 DO、
   P14 实为 WP）。
6. **当前交付路径**：HTTP 烧位流 + `R` 命令载 RAM 运行（RemoteLab UART = RX AC26 / TX AB26，
   真实连通，已被上述两次 `OK` 证实）。断电丢失，但换程序快速、无需重综合。

---

## 6. 未解决的关键问题（下一个人从这里接手）

### ★ 写 Flash（W 命令）受 H13 专用引脚限制，当前板子不可行

- U9 真实时钟引脚 H13 是 PDS 无法布局为用户 IO 的专用配置引脚，软 SPI 物理够不到 U9。
- `flash.fdc` 里 R15(spi_cs)/P18(spi_sck)/P14(spi_mosi)/N14(spi_miso) 只是占位引脚，与 U9 真实
  引脚（CS=F25 CLK=H13 DI=R14 DO=R15）并不对应。
- 后续可选方向：
  - 调研 Pango 器件手册，确认是否可通过专用配置接口（如 SPI 配置引脚复用/ICAP 类机制）在用户
    模式访问 U9；
  - 改走 BRAM INIT 固化（需重新综合，违背 FlashBoot 初衷）；
  - 维持当前 RAM 方案（HTTP 烧位流 + R 命令载 RAM，断电丢失但换程序快速）。

### 验证协议（已知可用）
- 固件格式：`b"R" + len(app).to_bytes(4,"little") + app`（`R` 命令载 RAM 运行）。
- 板子回显：每 256 字节一个 `K`；程序跑完打印 `BIG <n>`、校验和 hex、`OK`/`FAIL`。
- 计数 `K`：`hex.upper().count("4B")`（`K`=0x4B）。完整 = `len(app)//256 + 1` 个 K。

---

## 7. 下一步建议（按优先级）

1. **用 `ram_load.py` 交付大文件加载**：默认 `R` 命令载 RAM，逐块流控，13KB/33KB 均已实测成功。
   ```
   python tool/fpga_lab/ram_load.py                                    # 13KB 默认 app
   python tool/fpga_lab/ram_load.py cpu/build/app_huge.bin             # 33KB 大文件
   python tool/fpga_lab/ram_load.py --flash                            # 尝试 W 写 Flash（当前不可行）
   ```
2. **如需 Flash 持久化**：调研 Pango PG2L200H 器件手册，确认是否可通过专用配置接口访问 U9；
   或改走 BRAM INIT 固化（需重新综合）。
3. **13KB/33KB e2e 已收尾**：`ram_load.py` 已把端到端链路彻底验证绿（`BIG 3072 OK` / `BIG 8192 OK`）。

---

## 8. 操作速查

```bash
# 1) 确认桥接服务活着（不在就重启，见 §2）
curl -s --max-time 6 http://127.0.0.1:8600/api/v1/health

# 2) 编译固件（本机）
"H:/ST/RV32I/bin/riscv-none-elf-gcc.exe" -march=rv32i_zicsr_zifencei -mabi=ilp32 \
  -msmall-data-limit=0 -std=c11 -O2 -ffreestanding -fno-builtin -nostdlib -nostartfiles \
  -Wl,--no-relax -T sw/link_soc.ld -o build/app_big.elf sw/start.S sw/app_big.c -lgcc
"H:/ST/RV32I/bin/riscv-none-elf-objcopy.exe" -O binary build/app_big.elf build/app_big.bin

# 3) 通过桥接烧位流 + 流控发送固件（推荐路径）
python tool/fpga_lab/ram_load.py                                    # R 命令载 RAM（13KB）
python tool/fpga_lab/ram_load.py cpu/build/app_huge.bin             # R 命令载 RAM（33KB）

# 4) 旧路径（已弃用，盲发丢字节）：
#    POST /api/v1/devices/reserve  {"minutes":10}
#    POST /api/v1/bitstream        (file=xxx.sbit)
#    WS   ws://127.0.0.1:8600/ws/serial?baud=115200
#         tx: {"type":"tx","mode":"hex","data":<hex>}
#    POST /api/v1/devices/release
```

---

## 9. 坑与怪现象（踩过的雷）

- **桥接服务 10 分钟被杀**：后台跑长任务（如 33KB 上传 9s + 等待）时，服务可能因前台/后台超时断开，表现为连接被拒或 502。长任务前先确认服务在，必要时重启。
- **508/502 瞬断**：平台偶发瞬时 502，脚本需加重试（参考 `big_load.py` 的预留重试）。
- **早期 512 字节读 bug 已修**：服务器原先按 512 字节块读串口，已修复为按需读取，RX 回传恢复正常。
- **`account.txt` 是鉴权凭据**：在 `tool/fpga_lab/` 下、git untracked，别提交也别写进任何文档。
- **`R` vs `W` 别混**：`R` 只载 RAM 不落 Flash（断电丢失），`W` 写 Flash（持久）。快速迭代用 `R`，交付用 `W`。
  ⚠️ 当前 `W` 命令受 H13 专用引脚限制不可用，交付路径为 `R` 命令载 RAM。
- **大文件下发必须用流控**：旧脚本（big_load.py 等）一次性盲发整个 payload，导致 platform 串口 tx 缓冲溢出、时变丢字节（13KB 实测只送达 6.5~10.5KB）。bootloader 每收 256 字节回一个 `K`，本意就是让主机做流控（背压）。正确做法是「逐块发 256 字节 → 等一个 `K` 回执 → 再发下一块」，见 `tool/fpga_lab/ram_load.py`。
- **Flash 写（`W` 命令）受 H13 专用引脚限制**：U9 真实时钟引脚 H13 是 PDS 无法布局为用户 IO 的专用配置引脚，软 SPI 物理够不到 U9；`cpu/constraints/flash.fdc` 里 R15/P18/P14/N14 只是占位引脚（真实 U9 引脚 CS=F25 CLK=H13 DI=R14 DO=R15，N14 实为 HOLD、R15 实为 DO、P14 实为 WP）。
- **Git 现状**：`ZGTC_RISC_CPU` 有大量未提交改动（RTL、scripts、sw、docs 均为新/改）。接手后先 `git status` 看清楚再动。

---

## 10. 相关文档 / 记忆

- `cpu/docs/FLASH_BOOT.md` — Flash 启动权威说明（内存布局、命令、U9 引脚、寄存器）。
- `tool/fpga_lab/ram_load.py` — 当前推荐的大文件加载命令（流控发送，R 命令载 RAM）。
- 本机 CodeBuddy 记忆（`~/.codebuddy/projects/.../memory`）：含 Pango PG2L200H 工具链、避免 WSL、flash 启动参考、U9 引脚（SCK=P18 为占位，真实 CLK=H13）。

---

## 11. 分支融合记录（2026-09-11）

本节记录 2026-09-11 完成的 XSY × DYH 分支融合，详细冲突解决方案与功能清单见 `docs/MERGE_LOG.md`。

### 11.1 合并概述

| 项 | 值 |
|----|----|
| 合并日期 | 2026-09-11 |
| 合并提交 | `8e92e9e` |
| 分叉基线 | `efdbae2`（120 MHz CoreMark 达标） |
| XSY 末梢 | `08dbfa1`（串口烧录、桥接服务、bootloader、Flash 启动） |
| DYH 末梢 | `ddab723`（153 MHz 性能优化、148 个实验目录） |
| 冲突文件 | `.gitignore`（自动）、`build_pds.tcl`（自动）、`run_pds.ps1`（手动） |

### 11.2 新增性能优化功能（来自 DYH）

- **CPU 性能优化至 153 MHz**：全系统验证通过，证据见 `cpu/docs/evidence/153mhz-20260911/`。
- **148 个实验目录**：`cpu/experiments/` 下涵盖 ALU、BTB、Cache、时钟、前递、取指等多类 RTL 变体与测试脚本。
- **扩展时钟选项**：`run_pds.ps1 -ClockHz` 新增 126 MHz、132 MHz 两个选项。
- **扩展 I-Cache 配置**：`run_pds.ps1 -ICacheSetBits` 范围从 0–8 扩展到 0–10。
- **布局种子支持**：`run_pds.ps1 -PlacementSeed <n>` 支持 `pnr -gplace_seed` 布局复现。
- **性能验证脚本**：`check_frequency_candidate.py`、`check_performance_target.py`、`check_coremark.py` 等。

### 11.3 保留的烧录/启动功能（来自 XSY）

- **串口烧录**：`burn.py` 生成/发送 bootloader 控制台字节流（W/R 命令）。
- **桥接服务**：`tool/fpga_lab/` 的 HTTP 设备预约/位流烧录 + WebSocket 串口。
- **bootloader**：固化进 BRAM 前 4KB，上电读 U9 Flash 启动应用。
- **FlashBoot 构建开关**：`run_pds.ps1 -FlashBoot` 生成仅含 bootloader 的位流。
- **流控大文件下发**：`ram_load.py` 逐块发 256B + 等 K 回执，13KB/33KB 实测成功。
- **Flash 启动流程文档**：`cpu/docs/FLASH_BOOT.md` 权威说明保留。

### 11.4 文档保护说明

DYH 分支提交 `ddab723` 删除了 44 个 `cpu/docs/` 文档文件（含 153 MHz 验证证据）。合并时**恢复了全部被删除文档**，理由：

1. 这些文档是项目重要技术积累（微体系结构、频率验证、Cache 消融、ILA 分析等）。
2. `FINAL_REPORT.md`、`HARDWARE_FREQUENCY.md` 等记录已完成的硬件验证证据，删除将导致历史不可追溯。
3. DYH 自身的 153 MHz 验证证据也在删除范围内，恢复后可供后续核查。

恢复后 `cpu/docs/` 共 46 个文件，与基线 `efdbae2` 一致。完整合并记录见 `docs/MERGE_LOG.md`。

> 补充：后续（提交 `3f10dfd`）又恢复 DYH 分支 85328e4 新增的 93 个优化文档，`cpu/docs/` 现共 **175 个 .md 文档**。

---

## 12. 511 分功能融合成果（2026-09-12）

本节记录**真正的功能融合**（非 git merge）：DYH 高性能 CPU 与 XSY 串口烧录合而为一。完整验证见 `docs/COREMARK_TEST_REPORT.md`，无 WSL 运行方式见 `docs/NO_WSL_TOOLCHAIN.md`。

### 12.1 融合架构

```
511 分高性能 CPU（DYH full_fetch_commit_factored：RV32IM/153MHz/16KB I-Cache/分支预测/全加速开关）
  + 简化 bootloader（XSY，去掉 SPI Flash，只保留 R 命令，固化 BRAM 前 4KB）
  + 应用 R 命令流控载入 0x1000 运行
```

- **关键取舍**：用户已放弃 Flash 持久化，故去掉 SPI Flash，保留 R 命令串口烧录，从而既跑 511 分又支持串口烧录。
- **复位/地址**：CPU 复位 PC=0，BRAM 基址 0，bootloader 链 ORIGIN=0（前 4KB），应用链 ORIGIN=0x1000（60KB）。

### 12.2 153MHz 融合位流

| 项 | 值 |
|----|----|
| 位流路径 | `cpu/experiments/full_fetch_commit_factored/build/pds/20260912-214944-e6a316a5/generate_bitstream/pds_soc_top.sbit` |
| SHA256 | `6870A02B989CCFBD55FBF643964FA9A4D22BA3B45C31F92DBF16950F71F07419` |
| 时序 | All Constraints Met，WNS +0.018ns（估算 153.44MHz） |
| 布局种子 | seed=1（默认 seed 时序 WNS -0.008ns 临界违例，换 seed 收敛） |
| 资源 | LUT 9075，FF 4321，DRM 21，GPLL 1，APM 4 |
| 时钟源 | GTP_GPLL（27MHz × 34/6 = 153MHz） |
| RTL 配置 | ENABLE_M=1、ICACHE_SET_BITS=9（16KB）、CACHE_SET_BITS=6、BTB_INDEX_BITS=8、全加速=1 |

### 12.3 CoreMark 验证结果

| 项 | 值 |
|----|----|
| **CoreMark 分数** | **511.355 Iterations/Sec**（精确公式 `6000 × 153000000 / cycles`） |
| CoreMark/MHz | 3.342（旧 RV32I 主目录仅 0.366，提升 9.1 倍） |
| cycles_hex | `0x6b010a86`（1,795,230,342 周期） |
| retired_hex | `0x6461c936`（1,684,130,102 指令） |
| 校验 | Correct operation validated（CRC 通过） |
| 迭代 | 6000，运行 11.733 秒 |

### 12.4 固件/应用编译（无 WSL）

| 组件 | 配置 | 产物 |
|------|------|------|
| bootloader | rv32i_zifencei，简化（去 SPI），668B（<4KB） | `cpu/build/bootloader.hex`（64KB 固化镜像） |
| CoreMark 应用 | rv32im_zicsr_zifencei、O3、unroll、relax、6000 迭代、153MHz | `cpu/build/coremark_app_i6000_rv32im.bin`（28184B） |

工具链：Windows xPack GCC 15.2.0（`H:\ST\RV32I`），**无 WSL / Icarus**。编译用 `@响应文件` 规避 pwsh 对 `-Wl,--relax` 与字符串宏的引号问题。

### 12.5 一键验证脚本

- `tool/fpga_lab/coremark_verify.py` — 一键完成：找健康箱 → 烧 153MHz 位流 → R 命令流控发 CoreMark → 检测 READY 发 G 启动 → 解析 cycles/retired/clock → 算分 + 校验 CRC。

### 12.6 完整提交链

| 提交 | 内容 |
|------|------|
| `8e92e9e` | XSY×DYH 分支合并 |
| `3f10dfd` | 恢复 DYH 93 个性能优化文档 |
| `16abc74` | 融合 511 分 CPU + 串口烧录 + 去 WSL |
| `4525e27` | 固化 CoreMark 511 分一键验证脚本 |
