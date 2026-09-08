# Flash Boot & 免综合换程序（U9 QSPI Flash）

让 CPU 程序存储在板载**用户 QSPI Flash (U9)**，上电由 BRAM 里的 bootloader
读到 RAM 再启动。**更换程序只烧 Flash，不需要重新综合/生成位流。**

⚠️ **当前状态（2026-09-08）**：U9 写路径受硬件限制不可行。U9 真实时钟引脚 H13 是
PDS 无法布局为用户 IO 的**专用配置引脚**，软 SPI 物理够不到 U9；`flash.fdc` 里
R15/P18/P14/N14 只是「让设计可综合」的占位引脚，与 U9 真实引脚不对应。因此
`W` 命令（写 Flash 持久化）在当前板子会报 `ERR erase`。**当前交付路径为 `R` 命令
载 RAM 运行**（断电丢失，但换程序快速、无需重综合）。详见 `DEV_SNAPSHOT.md` §6。

## 内存与镜像布局

- BRAM 共 64 KB。前 4 KB（0x0000–0x0FFF）在综合时固化 **bootloader**
  （`INIT_FILE`，只编一次）。应用区 0x1000–0xFFFF（60 KB），链接地址为
  `0x1000`（`cpu/sw/link_soc.ld`）。
- U9 Flash 0 扇区镜像：
  - 0x0..3：magic `'R','F','C','P'`
  - 0x4..7：负载字节数（小端）
  - 0x8..：应用二进制（拷贝到 0x1000 后 `fence.i` 并跳转）

## 上电流程

1. bootloader 上电先读 U9：镜像头合法 → 拷贝到 0x1000 → `fence.i` 刷缓存 → 跳转。
2. 镜像非法，或复位时**按住 KEY0**，进入 UART 恢复控制台（115200 8N1），提示 `ZBOOT`。
   命令：`W<len32><bin>` 擦写 Flash 并启动；`R<len32><bin>` 直接载 RAM 运行(不写 Flash)；
   `B` 从 Flash 启动；`E` 擦扇区。

## 工具链（本机）

原生 RISC-V 工具链：`H:\ST\RV32I\bin\riscv-none-elf-*`（xPack GCC 15.2.0）。
脚本按 `$env:RV32_TOOLCHAIN` → `H:/ST/RV32I` → `D:/ST/RV32I` 顺序查找。
GCC15 需显式 `_zicsr`/`_zifencei`，见 `build_boot.ps1`/`build_app.ps1` 的 `-march`。

## 构建步骤

```powershell
# 1) 只编 bootloader（不依赖应用），生成 bootloader.hex
pwsh cpu/scripts/build_boot.ps1

# 2) 生成“FlashBoot 版”位流（RemoteLab 串口引脚 AC26/AB26）
pwsh cpu/scripts/run_pds.ps1 -FlashBoot -UartProfile RemoteLab
#    产出 build/pds/<run>/generate_bitstream/pds_soc_top.sbit

# 3) 编译一个应用（示例 app_hello.c，链接 0x1000）
pwsh cpu/scripts/build_app.ps1 -Source cpu/sw/app_hello.c -Name app_hello

# 4) 打 Flash 镜像（可选用）：
python cpu/scripts/mkflash.py cpu/build/app_hello.bin cpu/build/app_hello.img
```

## 烧录/运行（UART）

bootloader 控制台收到 raw .bin 会自动加镜像头，所以直接发 `.bin`：

```powershell
# 写进 U9 Flash 并启动（正式换程序，之后断电/复位自动从 Flash 启动）
⚠️ 当前板子受 H13 专用引脚限制，软 SPI 物理够不到 U9，`W` 命令会报 `ERR erase`，不可用。
python cpu/scripts/burn.py cpu/build/app_hello.bin --port COM7

# 只载入 RAM 运行（不写 Flash，快速迭代）
python cpu/scripts/burn.py cpu/build/app_hello.bin --ram --port COM7
```

**远程实验箱（推荐路径，流控发送，13KB/33KB 均实测成功）**：
```powershell
# 1) 烧位流（POST /api/v1/bitstream）
python tool/fpga_lab/ram_load.py                                    # R 命令载 RAM（13KB 默认 app）
python tool/fpga_lab/ram_load.py cpu/build/app_huge.bin             # R 命令载 RAM（33KB 大文件）
```

**远程实验箱（旧路径，已弃用，盲发丢字节）**：先在本机
`python cpu/scripts/burn.py cpu/build/app_hello.bin --out app_hello.uart.dat`
生成待发字节流（文件名前缀 `W` 写Flash / `R` 运行），再在网页串口按原样
发送该 .dat 内容（115200 8N1）。发 `?` 可让 bootloader 回显帮助。
⚠️ 旧路径一次性盲发整个 payload，导致 platform 串口 tx 缓冲溢出、时变丢字节。
必须用「逐块发 256 字节 → 等一个 `K` 回执 → 再发下一块」的流控方式，见 `ram_load.py`。

## U9 引脚（MES2L676-200HP）

⚠️ 下表为**占位引脚**（让设计可综合），与 U9 真实引脚**不对应**。U9 真实引脚为
CS=F25、CLK=H13（专用配置引脚，PDS 无法放置）、DI=R14、DO=R15、WP=P14、HOLD=N14。
软 SPI 无法复用 H13，故 U9 写路径当前不可行。

| 信号 | 占位引脚 | 说明 |
| --- | --- | --- |
| spi_cs   | R15 | U9 CS#（占位，真实 CS=F25） |
| spi_sck  | P18 | U9 CLK（占位，真实 CLK=H13，专用配置引脚，不可放置） |
| spi_mosi | P14 | U9 D0/DI（占位，真实 DI=R14，P14 实为 WP#） |
| spi_miso | N14 | U9 D1/DO（占位，真实 DO=R15，N14 实为 HOLD#） |

1-bit SPI mode 0，SCK = 27 MHz / 4 ≈ 6.75 MHz。D2/WP#、D3/HOLD# 依赖板上拉。

## 寄存器（外设 MMIO，供 bootloader/驱动使用）

- `0x10000500 SPI_CTRL`：bit0 = CS 选中(1=选中)
- `0x10000504 SPI_TX`：写一字节，阻塞到 8 bit 移位完成
- `0x10000508 SPI_RX`：读最近接收字节
- `0x1000050c SPI_STAT`：bit0 = busy

对应 RTL：`cpu/rtl/rv32_spi_flash.sv`（控制器）、`rv32_peripherals.sv`（寄存器）。
