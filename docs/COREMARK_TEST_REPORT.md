# CoreMark 串口烧录测试报告

> 本报告记录通过串口烧录功能（桥接服务 + bootloader R 命令载 RAM）在 FPGA 板子上运行 CoreMark 基准测试的完整过程与结果，覆盖两代配置：27MHz 基线验证与 153MHz 融合验证。

---

## 1. 核心结论（511 分融合验证）

| 项 | 值 |
|----|----|
| 测试日期 | 2026-09-12 |
| 目标硬件 | Pango PG2L200H (MES2L676-200HP)，远程实验箱 |
| SoC 配置 | **RV32IM**，**153 MHz**，16KB I-Cache + 大 D-Cache + 分支预测 + 全加速开关 |
| 交付方式 | HTTP 烧位流 → bootloader R 命令载 RAM（流控发送）→ 直接运行 |
| **CoreMark 分数** | **511.355 Iterations/Sec** |
| CoreMark/MHz | 3.342 |
| **校验结果** | **通过（Correct operation validated）** |

> **这是「既要 511 分，又要启动和串口烧录」融合目标的达成结果**：DYH 分支的 153MHz 高性能 CPU 与 XSY 分支的串口烧录（bootloader R 命令）合而为一。

---

## 2. 融合架构

融合方案 = **511 分高性能 CPU（RV32IM/153MHz）+ 简化 bootloader（前 4KB 固化）+ 应用 R 命令载入 0x1000 运行**。

| 组件 | 来源 | 说明 |
|------|------|------|
| 高性能 CPU RTL | DYH `full_fetch_commit_factored` | RV32IM、153MHz、16KB I-Cache、分支预测、全加速开关 |
| bootloader | XSY（简化去 SPI） | 固化 BRAM 前 4KB，复位后进串口控制台，R 命令载应用 |
| 串口烧录 | XSY | R 命令 + 256 字节块 + K 回执流控，零丢字节 |
| 应用加载地址 | 0x1000 | 复位 PC=0 跑 bootloader，应用载入 0x1000 运行 |

关键取舍：DYH 原版位流把 CoreMark 直接固化整个 BRAM（无 bootloader），XSY 原版有 SPI Flash + bootloader。融合时**去掉 SPI Flash**（用户已放弃 Flash 持久化），保留 R 命令串口烧录，从而既能跑 511 分又能串口烧录。

---

## 3. 烧录链路验证（153MHz 融合位流）

| 步骤 | 状态 | 说明 |
|------|------|------|
| 桥接服务启动 | ✓ | `fpga_lab_server` 监听 127.0.0.1:8600 |
| 设备预约 | ✓ | 实验箱，鉴权通过 |
| 153MHz 位流烧录 | ✓ | 位流 SHA256 `6870A02B...`，HTTP API 烧录成功 |
| bootloader 运行 | ✓ | R 命令流控正常，K 回执 112 个，零丢字节 |
| R 命令载入 CoreMark | ✓ | 28184 字节应用载入 0x1000，`RUN` 打印后直接运行 |
| CoreMark 运行 | ✓ | `Correct operation validated`，CRC 校验通过 |
| 结果收集 | ✓ | 完整串口输出，含 cycles/retired/clock |

---

## 4. 153MHz 融合位流综合结果

| 项 | 值 |
|----|----|
| 时序 | **All Constraints Met**，WNS +0.018ns（估算 153.44MHz） |
| 布局种子 | seed=1（默认 seed 时序 WNS -0.008ns 临界违例，换 seed 收敛） |
| 资源 | LUT 9075，FF 4321，DRM 21，GPLL 1，APM 4 |
| 时钟源 | GTP_GPLL（27MHz × 34/6 = 153MHz） |
| 位流 SHA256 | `6870A02B989CCFBD55FBF643964FA9A4D22BA3B45C31F92DBF16950F71F07419` |

---

## 5. CoreMark 详细结果（511 分）

### 5.1 板子原始输出

```
ZGTC COREMARK START iterations=6000 validation=0
2K pern-chip RAM; cache mode/geometry in ZGTC config
CoreMark Size    : 666
Total ticks      : 11733
Iterations/Sec   : 545
Compiler version : GCC 15.2.0
Compiler flags   : rv32im-O3-unroll-relax
seedcrc          : 0xe9f5
[0]crclist       : 0xe714
[0]crcmatrix     : 0x1fd7
[0]crcstate      : 0x8e3a
[0]crcfinal      : 0xa14c
Correct operation validated. See README.md for run and reporting rules.
ZGTC cycles_hex=000000006b010a86 retired_hex=000000006461c936 clock_hz=153000000
ZGTC config=0e8e96fd ihit=... imiss=... dhit=... dmiss=... writebacks=...
ZGTC COREMARK FINISHED
```

### 5.2 性能数据

| 指标 | 值 |
|------|-----|
| 迭代次数 | 6000 |
| 总周期数 | 1,795,230,342（0x6b010a86） |
| 退休指令数 | 1,684,130,102（0x6461c936） |
| 时钟频率 | 153,000,000 Hz（153 MHz） |
| 总运行时间 | 11.733 秒 |
| **CoreMark 分数** | **511.355 Iterations/Sec**（精确公式 `6000 × 153000000 / cycles`） |
| CoreMark/MHz | 3.342 |
| IPC（指令/周期） | 0.938 |

> 注：`Iterations/Sec : 545` 是整数秒打印值，非精确分数。以 64 位 `cycles_hex` 精确计算的 511.355 为准。

### 5.3 校验数据

| 校验项 | 值 |
|--------|-----|
| seedcrc | 0xe9f5 |
| crclist | 0xe714 |
| crcmatrix | 0x1fd7 |
| crcstate | 0x8e3a |
| crcfinal | 0xa14c |
| **校验状态** | **通过** |

---

## 6. 编译配置（511 分固件 / 应用）

| 项 | 值 |
|----|----|
| 工具链 | xPack RISC-V GCC 15.2.0（Windows 原生，**无 WSL**） |
| 架构 | rv32im_zicsr_zifencei |
| ABI | ilp32 |
| 优化级别 | -O3 -funroll-loops |
| 链接 | -Wl,--relax（linker relaxation） |
| 迭代次数 | 6000（-DITERATIONS=6000） |
| 运行模式 | 性能运行（-DPERFORMANCE_RUN=1） |
| 时钟常量 | 153MHz（-DCPU_CLOCK_HZ=153000000u） |
| 链接脚本 | link_soc.ld（应用链至 **0x1000**，适配 bootloader 载入） |
| bootloader | rv32i_zifencei，668 字节（<4KB） |

---

## 7. 历史基线（27MHz 参考，2026-09-11）

| 项 | 值 |
|----|----|
| SoC 配置 | RV32I（无 M 扩展），27 MHz |
| **CoreMark 分数** | **9.87 Iterations/Sec** |
| 总周期数 | 2,734,276,728（0xa2f9c078） |
| CoreMark/MHz | 0.366 |
| 校验结果 | 通过 |

> 该基线是主目录 `cpu/rtl`（XSY 旧 CPU）27MHz 位流的结果，CoreMark/MHz 仅 0.366。融合后采用 DYH 高性能 CPU，CoreMark/MHz 提升至 3.342（约 9.1 倍），配合 153MHz 高频，最终达 511 分。

---

## 8. 结论

1. **融合目标达成**：511 分高性能 CPU 与串口烧录（bootloader R 命令）成功合而为一，核心指标 511.355 CoreMark @ 153MHz，CRC 校验通过。
2. **串口烧录功能正常**：桥接服务、设备预约、153MHz 位流烧录、bootloader R 命令流控（112 个 K 回执零丢字节）、应用运行全链路验证通过。
3. **时序收敛**：默认 seed 时序 WNS -0.008ns 临界违例，换 placement seed=1 收敛至 WNS +0.018ns。
4. **工具链无 WSL 依赖**：编译（Windows xPack GCC 15.2.0）、综合（run_pds.ps1 去 WSL）、烧录（桥接服务器纯 Python）全程无需 WSL / Icarus 仿真。

---

## 9. 相关文档

- `docs/MERGE_LOG.md` — 分支融合记录（XSY × DYH）
- `docs/NO_WSL_TOOLCHAIN.md` — 「不带 WSL 工具链」运行方式
- `cpu/docs/COREMARK.md` — CoreMark 测量规范
- `cpu/docs/PROJECT_HANDOVER_153MHZ.md` — DYH 153MHz 交接文档
- `cpu/docs/AI_HANDOFF_153MHZ.md` — DYH 153MHz AI 交接文档
- `DEV_SNAPSHOT.md` — 开发快照