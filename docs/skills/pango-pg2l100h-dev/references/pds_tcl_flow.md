# PDS 批处理 TCL 流程（PG2L100H）

调用方式（由 `run_pds_full.ps1` 包装，等价于手动）：

```
pds_shell.exe -file build_full.tcl -work_dir <project_root> -project_name <name>
```

`pds_shell.exe` 是 PDS 的**命令行 Shell**（Fabric Compiler Shell），不是图形界面 `pds.exe`。
批处理模式不弹 GUI，适合在脚本/CI 中调用。

## 阶段顺序与含义

| TCL 命令 | 阶段 | 说明 |
| --- | --- | --- |
| `add_design` | 添加 RTL | 顶层 Verilog 源，路径用 `/` 分隔 |
| `add_constraint` | 添加约束 | `.fdc` 管脚/时钟约束 |
| `add_simulation` | 添加仿真 | testbench（仅登记，批处理不参与仿真） |
| `set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676` | 指定器件 | Logos2，PG2L100H，-6，FBG676 |
| `compile -top_module <top>` | 编译/解析 | 指定顶层模块 |
| `synthesize -ads -selected_syn_tool_opt 2` | ADS 综合 | PDS 自带综合器，opt 2 |
| `dev_map` | 器件映射 | 映射到 PG2L100H 原语 |
| `pnr` | 布局布线 | Place & Route |
| `report_timing` | 时序报告 | 输出 setup/hold WNS、WHS |
| `gen_bit_stream` | 生成位流 | 输出 `<root>/generate_bitstream/<top>.sbit` |

## 退出与错误判定

- `pds_shell` 进程退出码非零 → 整段失败。
- 即使退出码为 0，若输出含以 `E:` 开头的行（`Select-String '^E:'`）也视为工具报错。
- `gen_bit_stream` 会打印 `C: Bitstream-2001: SCBV has not been set` —— 原厂未提供 PCB
  参数时的正常提示，**不影响位流生成**，不要据此判定失败。
- 时序不通过时 PDS 仍可能生成位流；需要"拒绝未过时序的位流"时，自行解析 `report_timing` 的 WNS/WHS。

## 产物位置

```
<project_root>/
  <name>.pds                      # 工程数据库
  compile/ synthesize/ device_map/ place_route/ report_timing/   # 各阶段中间产物
  generate_bitstream/<top>.sbit   # 最终位流
  build_full.local.tcl            # 展开令牌后的临时 TCL（脚本生成，git 忽略）
```

## 其他可用开关（pds_shell -help）

- `-project <file>`：指定既有 `.pds` 工程文件跑批处理。
- `-run <action>`：只跑单个 action（如 `compile`/`pnr`）。
- `-skip_actions { report_power gen_netlist }`：跳过指定阶段。
- `-continue`：出错也继续（脚本模式）。
