# pds_cpu_100h — PG2L100H 上的 RISC-V CPU SoC（BRAM-only bring-up）

把主线 RV32IM SoC（`cpu/rtl`）烧到 **MES2L676-100HP / PG2L100H-6IFBG676** 板上跑的工程。
2026-10-24 实测全链路通过：PDS 构建 → JTAG 烧录 → ZBOOT 串口控制台 → 串口加载应用 →
**SoC 自试 `ZSOC PASS`**。技能文档：`docs/skills/pango-pg2l100h-dev/references/cpu_serial_flash.md`。

## 结构

```
pds_cpu_100h/
├── src/pds_cpu_top_100h.v.in   # 100H 顶层模板（无 DDR3/SPI 引脚；令牌 __INIT_FILE__/__ENABLE_M__/__UART_BAUD__）
├── constraints/cpu_top_100h.fdc # clk D18 / rst_n C22 / key C23 / uart B24,C24 / led A20...
├── sw/
│   ├── boot_start.S  boot_link.ld      # 从 cpu/sw/boot 复制（链接 0x0，4KB）
│   ├── bootloader_100h.c               # ZBOOT 控制台（R 加载 + ? 帮助；去掉了 DDR 自检）
│   ├── irq_probe.c  reg_probe.c        # 中断/寄存器诊断应用（排障用）
├── scripts/
│   ├── build_boot_100h.ps1   # 编 bootloader → 64KB hex（原生 xPack 工具链，无 WSL）
│   ├── build_app_100h.ps1    # 编应用（hello/selftest/irqprobe/regprobe，-ExternalUart 可选）
│   ├── build_full.tcl        # PDS 批处理 TCL 模板（__RTL_ROOT__/__PROJECT_ROOT__/__TOP_SOURCE__）
│   ├── run_pds_full.ps1      # 一键：boot hex → 展开模板 → pds_shell → 校验位流
│   ├── test_scan.tcl         # 只扫 JTAG 链
│   └── program_full.tcl      # cdt_cfg 烧录（目标 build/pds-latest.sbit）
└── build/                    # 构建产物（git 忽略；pds-latest.sbit 为稳定烧录目标）
```

## 一键流程

```powershell
# 1) 构建 CPU 位流（含 bootloader）
pwsh -NoProfile -File .\pds_cpu_100h\scripts\run_pds_full.ps1

# 2) 烧录（jtagserver 需在 127.0.0.1:65420；可直接 cdt_js.exe -port 65420 拉起）
cd pds_cpu_100h\scripts
& 'H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe' -file program_full.tcl

# 3) 串口加载应用并验证
python tool\serial\serial_cli.py load pds_cpu_100h\build\app_hello.bin
pwsh -NoProfile -File .\pds_cpu_100h\scripts\build_app_100h.ps1 -App selftest -ExternalUart
python tool\serial\serial_cli.py load pds_cpu_100h\build\app_selftest.bin
python tool\serial\serial_cli.py send --hex 'a5' --expect 'SOC PASS'
```

## 要点 / 约束

- **DDR3 暂不使用**：顶层把 rv32_soc 的 DDR 后端 tie-off，访问 ≥0x10000 会得到总线错误
  （maintenance_fault 时 LED 显示 0xE1），不会挂死；软件请待在 64KB BRAM + MMIO。
- SPI 控制器在片内但不外接（bootloader 纯 UART/RAM，不依赖 flash）。
- 配置：27MHz 直时钟、cache 开、预测器开、RV32IM（ENABLE_M=1）、115200 8N1。
- PDS Verilog 前端不接受 `.port()` 空连接——顶层所有端口显式接线。
- 工具链：原生 `H:/ST/RV32I`（xPack riscv-none-elf 15.2），**不需要 WSL**；
  bootloader `-march=rv32i_zifencei`，应用 `-march=rv32i_zicsr_zifencei`。
- 详细排坑（cdt_cfg 挂住、外壳超时杀 pds_shell、K-ack 后 RUN 文本、外部中断电平风暴）
  见技能文档 `references/cpu_serial_flash.md` §4/§6。
