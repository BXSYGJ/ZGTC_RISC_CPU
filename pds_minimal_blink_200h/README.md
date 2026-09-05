# PG2L200H 最小 PDS 全流程例程

该目录用于验证紫光同创 Logos2 `PG2L200H-6FBB676`、MES2L676-200HP
开发板、WSL RTL 仿真和 Windows PDS 实现流程。它是后续 CPU 开发前的板级基线，
不包含 RISC-V CPU 实现。

## 功能

8 个 LED 每 0.5 秒移动一次。KEY0 低电平复位；KEY1 松开时向高位移动，按下时
向低位移动。

板级约束来自 `MES2L676-200HP硬件使用手册_v1.2.pdf` 与配套
`2_7_key_led_test` 工程：

| 信号 | 功能 | 管脚 |
| --- | --- | --- |
| `clk` | 27 MHz 系统时钟 | D18 |
| `rst_n` | KEY0，低有效 | C22 |
| `key` | KEY1，低有效 | C23 |
| `led[7:0]` | 高电平点亮 | B17, C17, A18, A17, E18, C19, C18, A20 |

## 运行

环境要求：PowerShell 7+、Ubuntu-22.04 WSL、Icarus Verilog，以及带有效许可证的
PDS 2022.2-SP6.4。

```powershell
pwsh -File .\scripts\run_wsl_sim.ps1
pwsh -File .\scripts\run_pds_full.ps1
```

PDS 不在默认的 `D:/PDS_2022.2-SP6.4` 时，可先在当前 PowerShell 进程设置
`PDS_ROOT` 环境变量。脚本会验证其中的 `bin/pds_shell.exe` 后再运行。

PowerShell 入口会根据仓库当前位置展开 `build_full.tcl` 中的工程路径，再依次执行
Compile、ADS Synthesis、Device Map、Place & Route、Report Timing 和 Generate
Bitstream。生成物位于本目录的对应构建子目录中，不提交 Git。

## 已验证基线

2026-09-05 的本地与远程验证结果：

- WSL 自检通过复位、8 次正向轮转和 8 次反向轮转。
- PDS 六阶段成功，56/56 网络完成布线。
- 27 MHz 慢速角 setup WNS 34.501 ns、hold WHS 0.336 ns。
- 生成位流已成功下载到远程 PG2L200H，摄像头连续帧观察到 LED 按 0.5 秒移动。

PDS 生成位流时会给出与原厂例程相同的 `SCBV has not been set` 提示。本例程不猜测
原厂未提供的配置参数。
