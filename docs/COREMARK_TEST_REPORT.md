# CoreMark 串口烧录测试报告（2026-09-11）

> 本报告记录通过串口烧录功能（桥接服务 + R 命令载 RAM）将 CoreMark 基准测试载入 FPGA 板子并运行的完整过程与结果。

---

## 1. 测试概述

| 项 | 值 |
|----|----|
| 测试日期 | 2026-09-11 |
| 测试类型 | EEMBC CoreMark v1.0（性能基准） |
| 目标硬件 | Pango PG2L200H (MES2L676-200HP)，远程实验箱2 |
| SoC 配置 | RV32I（无 M 扩展），27 MHz，I-Cache + D-Cache |
| 交付方式 | HTTP 烧位流 + R 命令载 RAM（流控发送） |
| **CoreMark 分数** | **9.87 Iterations/Sec** |
| **校验结果** | **通过（Correct operation validated）** |

---

## 2. 烧录链路验证

本次测试完整验证了 XSY 分支的串口烧录功能，各环节均正常：

| 步骤 | 状态 | 说明 |
|------|------|------|
| 桥接服务启动 | ✓ | `fpga_lab_server` 监听 127.0.0.1:8600 |
| 设备预约 | ✓ | 实验箱2（box_id=7），鉴权通过 |
| 固件位流烧录 | ✓ | `pds_soc_top.sbit`（~9MB）通过 HTTP API 烧录成功 |
| CoreMark 载入 RAM | ✓ | R 命令 + 流控发送，75/75 K 回执全部收到，零丢字节 |
| G 命令启动运行 | ✓ | 通过 WebSocket 串口发送 G 命令，CoreMark 开始运行 |
| 结果收集 | ✓ | 串口输出完整接收，含 CoreMark 验证信息与性能数据 |

---

## 3. CoreMark 详细结果

### 3.1 板子原始输出

```
ZGTC COREMARK START iterations=1000 validation=0
2K pern-chip RAM; cache mode/geometry in ZGTC config
seedcrc          : 0xe9f5
[0]crclist       : 0xe714
[0]crcmatrix     : 0x1fd7
[0]crcstate      : 0x8e3a
[0]crcfinal      : 0xd340
Correct operation validated. See README.md for run and reporting rules.
ZGTC cycles_hex=00000000a2f9c078 retired_hex=000000002ba565b9 clock_hz=27000000
ZGTC config=0e020401 ihit=850755112 imiss=15545714 dhit=67677702 dmiss=1660679 writebacks=647070
ZGTC COREMARK FINISHED
```

### 3.2 性能数据

| 指标 | 值 |
|------|-----|
| 迭代次数 | 1000 |
| 总周期数 | 2,734,276,728（0xa2f9c078） |
| 退休指令数 | 732,259,769（0x2ba565b9） |
| 时钟频率 | 27,000,000 Hz（27 MHz） |
| 总运行时间 | 101.27 秒 |
| **CoreMark 分数** | **9.87 Iterations/Sec** |
| IPC（指令/周期） | 0.268 |

### 3.3 Cache 统计

| Cache | 命中 | 未命中 | 命中率 |
|-------|------|--------|--------|
| I-Cache | 850,755,112 | 15,545,714 | 98.20% |
| D-Cache | 67,677,702 | 1,660,679 | 97.60% |
| Writebacks | 6,470 | — | — |

### 3.4 校验数据

| 校验项 | 值 |
|--------|-----|
| seedcrc | 0xe9f5 |
| crclist | 0xe714 |
| crcmatrix | 0x1fd7 |
| crcstate | 0x8e3a |
| crcfinal | 0xd340 |
| **校验状态** | **通过** |

---

## 4. 编译配置

| 项 | 值 |
|----|----|
| 工具链 | xPack RISC-V GCC 15.2.0（Windows 原生） |
| 架构 | rv32i_zicsr（CSR 指令需显式指定，GCC 15 遵循新规范） |
| ABI | ilp32 |
| 优化级别 | -O2 |
| 迭代次数 | 1000（-DITERATIONS=1000） |
| 运行模式 | 性能运行（-DPERFORMANCE_RUN=1） |
| 数据大小 | 2000（-DTOTAL_DATA_SIZE=2000） |
| 链接脚本 | link_soc.ld（应用链至 0x1000） |
| 二进制大小 | 18,724 字节（18.29 KB，< 60KB 应用区上限） |

---

## 5. 结论

1. **串口烧录功能完全正常**：从桥接服务启动、设备预约、位流烧录到 R 命令载 RAM、流控发送、G 命令启动，全链路验证通过。
2. **CoreMark 验证通过**：CRC 校验全部正确，"Correct operation validated" 确认结果有效。
3. **CoreMark 分数 9.87 Iterations/Sec**：在 27 MHz / RV32I 配置下，该分数与硬件能力匹配（IPC 0.268，I-Cache 命中率 98.2%）。
4. **分支融合后功能完整**：XSY 的烧录链路与 DYH 的性能优化代码共存，CoreMark 在融合后的代码树上编译、烧录、运行均正常。

---

## 6. 相关文档

- `docs/MERGE_LOG.md` — 分支融合记录（XSY × DYH）
- `cpu/docs/COREMARK.md` — CoreMark 测量规范
- `cpu/docs/COREMARK_RESULTS.md` — 历史 CoreMark 结果
- `cpu/docs/FLASH_BOOT.md` — Flash 启动与串口命令说明
- `DEV_SNAPSHOT.md` — 开发快照（含烧录流程）