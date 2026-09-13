# 不带 WSL 工具链的运行方式

> 本文档记录在**没有 WSL / Icarus Verilog** 的 Windows 机器上，完成 RV32 SoC/CoreMark 的编译、综合、位流生成与串口烧录验证的完整运行方式。
>
> **背景**：DYH 分支原环境用 WSL Ubuntu-22.04 承载 GNU 工具链（GCC 10.2.0 手工构建 `riscv32-unknown-elf`）+ Icarus 仿真 + Verilator 检查，Windows 侧只做 PDS 综合。本机**不带 WSL**，因此全部改用 Windows 原生工具链，实际已跑通并复现 511 分。

---

## 1. 环境前提

| 项 | 值 | 说明 |
|----|----|----|
| RISC-V 工具链 | `H:\ST\RV32I\bin\riscv-none-elf-*` | xPack GCC 15.2.0（Windows 原生，无 WSL） |
| 工具链查找顺序 | `$env:RV32_TOOLCHAIN` → `H:/ST/RV32I` → `D:/ST/RV32I` | 见 `build_boot.ps1` |
| PDS | `H:\GG\pango\PDS_2022.2-SP6.4` | 综合/实现/生成位流（`pds_shell.exe`） |
| PDS 许可证 | `E:\License\pango\new_pds_F4A80DA47D72.lic` | 用户级环境变量 `PANGO_LICENSE_FILE` |
| Python | 3.10+（本机 3.12） | 报告解析 + 桥接服务 + 烧录脚本 |
| 桥接服务器 | `D:\0000\111\001\Pango\tool\fpga_lab` | 远程实验箱封装（REST/WS/CLI，纯 Python） |

**明确不需要**：WSL、Icarus Verilog、Verilator、任何本地 RTL 仿真。仿真请在远程 FPGA LAB 平台完成或另行构建。

---

## 2. 编译（固件 / 应用，无 WSL）

### 2.1 bootloader（RV32I，前 4KB）

```powershell
pwsh cpu/scripts/build_boot.ps1 -Out cpu/build/bootloader.hex
```

- 工具链自动定位 Windows xPack GCC（见上），`-march=rv32i_zifencei`（`fence.i` 用于刷缓存跳转）。
- 产物 `bootloader.bin` 必须 **< 4096 字节**（前 4KB boot 区），`bootloader.hex` 为 16384 行（64KB，后 60KB 填 0）。
- 本融合版 bootloader 已**去掉 SPI Flash**，只保留 R 命令（`cpu/sw/boot/bootloader.c`）。

### 2.2 CoreMark 应用（RV32IM，ORIGIN=0x1000）

关键：应用链接到 **0x1000**（bootloader 载入地址），用 GCC **响应文件**规避 pwsh 对 `-Wl,--relax`（`--` 前缀）与字符串宏的引号解析问题。

`cpu/build/build_coremark.rsp` 内容（节选）：

```
-march=rv32im_zicsr_zifencei
-mabi=ilp32
-O3
-funroll-loops
-DITERATIONS=6000
-DPERFORMANCE_RUN=1
-DCPU_CLOCK_HZ=153000000u
-DFLAGS_STR=\"rv32im-O3-unroll-relax\"
-Wl,--relax
-Tcpu/sw/link_soc.ld
-o cpu/build/coremark_app_i6000_rv32im.elf
... (coremark-upstream 5 个 .c + start.S + core_portme.c + ee_printf.c)
-lgcc
```

编译 + 转 bin：

```powershell
H:\ST\RV32I\bin\riscv-none-elf-gcc.exe @cpu/build/build_coremark.rsp
H:\ST\RV32I\bin\riscv-none-elf-objcopy.exe -O binary cpu/build/coremark_app_i6000_rv32im.elf cpu/build/coremark_app_i6000_rv32im.bin
```

### 2.3 无 WSL 编译的三个坑

1. **GCC 15.2.0 需显式 `_zicsr_zifencei`**：新版规范把 CSR/`fence.i` 从 `-march=rv32i` 拆出，须写 `rv32im_zicsr_zifencei`。
2. **`FLAGS_STR` 必须是字符串字面量**：`core_main.c` 以 `%s` 打印 `COMPILER_FLAGS`→`FLAGS_STR`，响应文件里用 `\"...\"` 转义保留字面双引号，使宏值为字符串 `"rv32im-O3-unroll-relax"`。
3. **pwsh 对 `--relax` 的解析问题**：`-Wl,--relax` 里 `--` 前缀会触发 pwsh 参数解析错误，用 `@response_file` 传入即可规避。

---

## 3. 综合（生成位流，无 WSL）

`full_fetch_commit_factored/scripts/run_pds.ps1` 已去掉 WSL 依赖（报告解析由 `wsl.exe python3` 改为 native `python pds_report.py`）。

```powershell
pwsh -NoProfile -File cpu/experiments/full_fetch_commit_factored/scripts/run_pds.ps1 `
  -ClockHz 153000000 -EnableM 1 `
  -ICacheSetBits 9 -CacheSetBits 6 -BtbIndexBits 8 `
  -DataOverlap 1 -EarlyDRequest 1 -FastDCacheWrite 1 -FastDCacheRead 1 `
  -FetchOverlap 1 -FastICacheHit 1 -LoadUseBubble 1 -Predictor 1 `
  -UartProfile RemoteLab `
  -FirmwareHex D:\0000\111\001\Pango\ZGTC_RISC_CPU\cpu\build\bootloader.hex
```

- 非 27MHz 固件须有配套 `.build.json`（`bootloader.build.json`：`EnableM=0 / ClockHz=153000000 / HexSha256`）。
- **时序临界注意**：默认 seed 时序 WNS -0.008ns 违例，加 `-PlacementSeed 1` 收敛至 WNS +0.018ns。

---

## 4. 烧录 + 串口验证（无 WSL）

启动桥接服务器（纯 Python，`tool/fpga_lab` 目录）：

```powershell
# 在 D:\0000\111\001\Pango\tool\fpga_lab 下
python -m uvicorn fpga_lab_server.app:create_app --factory --host 127.0.0.1 --port 8600
```

流程（参考 `tool/fpga_lab/ram_load.py`，CoreMark 需自定义脚本）：

1. 预约健康实验箱（beacon 门，自动避开坏箱）
2. HTTP API 烧 153MHz 位流
3. 串口连接，bootloader 打印 `ZBOOT` / `>` 提示
4. **R 命令流控**发 CoreMark `.bin`：`R` + 4 字节小端长度 + 数据，每 256 字节等 `K` 回执
5. 应用载入 0x1000 后直接运行（`RUN` → CoreMark 输出）
6. 解析 `cycles_hex` / `retired_hex` / `clock_hz`，分数 = `iterations × clock_hz / cycles`

账号凭据：`D:\0000\111\001\Pango\tool\account.txt`（**勿写入脚本或提交**）。

---

## 5. 与 WSL 工具链的差异对照

| 环节 | DYH 原环境（WSL） | 本机（无 WSL） |
|------|------------------|---------------|
| 工具链 | WSL Ubuntu-22.04 手工构建 GCC 10.2.0 `riscv32-unknown-elf` | Windows xPack GCC 15.2.0 `riscv-none-elf` |
| 编译 | `wsl.exe ... gcc` | 直接 `riscv-none-elf-gcc.exe`（或 `@rsp` 响应文件） |
| 仿真 | Icarus / Verilator（WSL） | **不做**（远程平台验证） |
| PDS 报告解析 | `wsl.exe python3 pds_report.py` | native `python pds_report.py` |
| 架构标志 | `-march=rv32im` | `-march=rv32im_zicsr_zifencei` |

**验证结果**：本机无 WSL 链路已完整跑通，CoreMark **511.355 Iterations/Sec @ 153MHz**（CRC 校验通过），详见 `docs/COREMARK_TEST_REPORT.md`。

---

## 6. 相关文档

- `docs/COREMARK_TEST_REPORT.md` — 511 分烧录验证报告
- `cpu/scripts/build_boot.ps1` — bootloader 编译（内建工具链定位）
- `tool/fpga_lab/ram_load.py` — 串口烧录流控脚本
- `cpu/docs/TOOLCHAIN.md` — 原始 WSL 工具链说明
- `cpu/docs/COMPILED_SIMULATION.md` — WSL 仿真说明（本机不适用）