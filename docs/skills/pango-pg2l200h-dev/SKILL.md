---
name: pango-pg2l200h-dev
description: >
  紫光同创 Logos2 PG2L200H（MES2L676-200HP 开发板）的 Windows PDS 全流程开发技能。
  覆盖：PDS 环境（PDS_ROOT、PANGO_LICENSE_FILE）、无 WSL 的本地 PDS 批处理综合/实现/生成位流、
  PG2L200H 工程 TCL 流程、板级与 RemoteLab 管脚约束，以及 logicmatrixsemi.com:5174
  FPGA LAB 远程实验平台的调试。
  已具备桥接服务器（D:\0000\111\001\Pango\tool\fpga_lab），把远程调试封装为 REST/WS/CLI：
  预约/烧写/串口已 native 实机验证（见 references/bridge_server.md）；ILA/摄像头仍为人工网页操作。
  当用户要求用 PDS 开发 PG2L200H、生成 .sbit 位流、上板验证或远程调试时使用本技能。
  本机仅有 Windows PDS，没有 WSL / Icarus Verilog，不要尝试本地 RTL 仿真。
---

# 紫光同创 PG2L200H · PDS 开发与远程调试

本技能面向 `PG2L200H-6FBB676`（Logos2 家族）器件与 `MES2L676-200HP` 开发板，
使用 Windows 版 **PDS 2022.2-SP6.4**。链路已验证到：
- 本地 PDS 批处理六阶段成功，生成 `blink_top.sbit`；
- 远程桥接（`tool/fpga_lab`）native 全流程实机通过：预约 PG2L200H 箱→烧录→串口收发→释放。

## 环境前提（本机已配置，缺失时再设）

| 变量 | 本机值 | 说明 |
| --- | --- | --- |
| `PDS_ROOT` | `H:\GG\pango\PDS_2022.2-SP6.4` | PDS 安装根，脚本读取 `bin/pds_shell.exe` |
| `PANGO_LICENSE_FILE` | `E:\License\pango\new_pds_F4A80DA47D72.lic` | PDS 许可证绝对路径 |

两项已写入**用户级**环境变量，新 PowerShell 进程自动继承。若换机器，用
`[Environment]::SetEnvironmentVariable('PDS_ROOT','<path>','User')` 与
`[Environment]::SetEnvironmentVariable('PANGO_LICENSE_FILE','<path>','User')` 重设。

> 本机**没有 WSL，也没有 Icarus Verilog**，不要调用 `run_wsl_sim.ps1` 或任何本地仿真；
> 如需仿真请在远程 FPGA LAB 平台完成，或在具备 WSL 的机器上另行构建。

## 工作流

1. 读取用户工程；没有工程时以 `template/` 下的流水灯基线新建（已验证可生成位流）。
2. 确认 `PDS_ROOT/bin/pds_shell.exe` 与 `PANGO_LICENSE_FILE` 存在，否则报错并提示设置。
3. 综合/实现/生成位流走 PDS 批处理（见下）。**不要**启动图形界面 `pds.exe`。
4. 位流产出在 `<project>/generate_bitstream/<top>.sbit`，sha256 自检后交给远程平台。
5. 远程调试（预约/烧写/串口）**首选脚本化**：`references/bridge_server.md`。串口一律走信标门
   `scripts/serial_session.py`（自动避开串口坏箱/坏会话）。人工网页流程仅作兜底，见 `references/remote_debug.md`。

## PDS 批处理构建（核心命令）

工程入口是 `pds_shell.exe -file build.tcl -work_dir <root> -project_name <name>`。
PDS 在 `build.tcl` 中按以下 TCL 顺序执行（完整说明见 `references/pds_tcl_flow.md`）：

```tcl
add_design    "<root>/src/<top>.v"
add_constraint "<root>/constraints/<top>.fdc"
set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676
compile -top_module <top>
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
```

位流输出到 `<root>/generate_bitstream/<top>.sbit`。`gen_bit_stream` 会打印
`C: Bitstream-2001: SCBV has not been set` —— 这是原厂未提供 PCB 参数时的正常提示，
非错误，不要据此判定失败（参考基线同样如此）。

## 新建工程的推荐脚本

`template/scripts/run_pds_full.ps1` 把上述 TCL 中的 `__PROJECT_ROOT__` 令牌展开为
当前工程绝对路径，再调用 `pds_shell`，并校验 `E:` 错误、位流存在与 sha256：

```powershell
# 在任意 PG2L200H 工程根目录执行（脚本需与本技能 template/scripts 同结构）
pwsh -NoProfile -File .\scripts\run_pds_full.ps1
```

脚本默认 `PDS_ROOT` 回退到本机 `H:\GG\pango\PDS_2022.2-SP6.4`；设置同名环境变量可覆盖。

## 管脚约束要点

- **板载（MES2L676-200HP）**：`clk` D18（27 MHz）、`rst_n` C22（KEY0 低有效）、
  `key` C23（KEY1 低有效）、`led[7:0]` B17/C17/A18/A17/E18/C19/C18/A20（高有效）。
  完整 .fdc 见 `template/constraints/blink_top.fdc`，时钟 `create_clock -period 37.037`（27 MHz）。
- **RemoteLab 网页串口**：`uart_rx` AC26、`uart_tx` AB26，115200 8N1（部分场景 9600）；
  与板载 UART（B24/C24）**不能混用**。约束片段 `cpu/constraints/uart_remotelab.fdc`
  仅两行 `define_attribute`，可直接并入工程。详见 `references/pin_constraints.md`。

## 远程调试（logicmatrixsemi.com:5174）

**推荐路径（脚本化）**：用本技能配套的桥接服务器，把远程调试变成纯接口/CLI。
启动与全部命令见 `references/bridge_server.md`。已于 2026-09-07 实机验证
"native 登录→预约→烧录→串口收发→释放"整条链路。

> 服务器务必在**自己的终端**启动以保持常驻：
> `pwsh -File D:\0000\111\001\Pango\tool\fpga_lab\scripts\run_server.ps1`
> （本助手后台/分离启动的进程有生命周期上限，只用于当次临时验证，不能当常驻服务。）

**人工路径（兜底/平台封锁自动化时）**：FPGA LAB 是网页 SPA，**下载位流、网页串口、ILA 捕获均为浏览器内
手动操作**，无脚本化 API。流程与凭据见 `references/remote_debug.md`。账号密码在
`D:\0000\111\001\Pango\tool\account.txt`（**不要写入任何脚本或提交**）。

## 参考资源

- `template/`：已验证的 PG2L200H 流水灯工程（src / constraints / scripts），新工程起点。
- `references/pds_tcl_flow.md`：PDS TCL 批处理各阶段与退出码判定。
- `references/pin_constraints.md`：板载与 RemoteLab 管脚、电平、时钟约束。
- `references/remote_debug.md`：FPGA LAB 远程实验平台登录、预约实验箱、下载、串口、ILA 步骤。
- `references/bridge_server.md`：**首选**——脚本化桥接服务器（REST/WS/CLI），无需网页操作。
- 完整参考工程：`D:\0000\111\001\Pango\ZGTC_RISC_CPU` 的 `origin/DYH` 分支
  （RISC-V SoC + RemoteLab 约束 + ILA 集成，仅作实现参考，勿污染该分支）。

## 交付格式

```text
器件/板卡:
PDS 环境:
综合实现结果:
位流路径与 SHA-256:
时序(setup/hold WNS/WHS):
远程调试状态:
串口链路验证:
剩余问题:
```

未运行的阶段（如未上板、未做 ILA）必须明确写“未运行”，不得推断通过。
