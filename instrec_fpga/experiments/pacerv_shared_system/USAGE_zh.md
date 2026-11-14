# PaceRV 高性能核心与音频整机共享存储、外设

## 当前实现

`src/ctrl/instrec_top.v` 使用完整的五级 PaceRV H3 Base RV32IMC 执行核心，打开乘除法、压缩指令、分支预测、重叠取指和提前数据请求。八个原始执行核心文件保存在 `src/cpu/vendor/pacerv_h3/`，`PROVENANCE.json` 保存来源及逐文件 SHA-256。

音频前端、NPU、显示、UART 和 DDR 控制器沿用同一套整机硬件。CPU 通过原 MMIO 控制 NPU、读取分类和周期计数、输出 UART，并通过新的桥访问系统 DDR。启动代码和栈使用片内的 8 KiB ROM、8 KiB RAM；DDR 应用数据区容量为 1 MiB。

| CPU 字节地址 | 用途 | 访问方式 |
| --- | --- | --- |
| `0x00000000–0x00001fff` | 启动 ROM | 取指、只读数据 |
| `0x20000000–0x20001fff` | 本地数据与栈 | 读写 |
| `0x40000000–0x400fffff` | 应用缓冲区，物理 DDR `0x00600000–0x006fffff` | 读写 |
| `0x41000000–0x415fffff` | 现有 PCM、权重、谱、自检和激活区的观察别名 | 合法子区只读 |
| `0x80000000` 起 | 现有 UART、LED、NPU 与 DDR 状态寄存器 | 按寄存器定义 |

观察别名中的地址空洞和写操作会返回访问异常。读取生产者已完成的缓冲区可获得对应数据；需要整窗一致性时，软件配合整机现有的锁窗协议。

CPU 与 DDR 用户逻辑共用时钟。M3 子仲裁器在启动自检结束后轮转服务诊断、特征导出和 CPU，锁定请求归属直至硬件完成及读数据排空。CPU 字节／半字／字写入直接使用 DDR 字节掩码，读取前的 dummy-write 保持零掩码。

8 KiB 本地 RAM 在 PDS 中推断为两个原生 `GTP_DRM36K_E1`。四个字节读寄存器分别与数组对应，保留原单周期返回及等待期间的数据保持。`probe_ram_inference.py` 可以在独立构建副本中重建 CPU 综合实验；完整工程仍须按下文完成布线与时序检查。

## 环境与运行位置

以下命令在仓库的 `instrec_fpga` 目录执行。使用 PowerShell 7、Python、Icarus Verilog 以及 PDS 2022.2-SP6.4。PDS 的 `PANGO_LICENSE_FILE` 指向本机有效授权文件；授权内容留在本机。完整 NPU 仿真另需 WSL、支持 `--timing` 的 Verilator 5 和 C++ 编译器。

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$taskRoot = [System.IO.Path]::Combine('D:/AAAFPGA', 'ZGTC_RISC_CPU_XSY', 'instrec_fpga')
Set-Location -LiteralPath $taskRoot
python experiments/pacerv_shared_system/build_firmware.py
python sim/experiments/pacerv_integration/run_pacerv_checks.py
python sim/experiments/pacerv_integration/run_standard_cpu_tb.py
pwsh -NoProfile -File sim/experiments/pacerv_shared_ddr/run_pacerv_shared_ddr.ps1 -Mode Modified
python scripts/check_rtl.py
```

固件构建脚本优先使用本机 RV32 GCC，也支持 WSL GCC。`--help` 给出编译器和发行版覆盖参数。新启动固件为 `sw/rv32/main_pacerv.c`，生成 `src/cpu/prog_pacerv.hex`；原 `main.c` 和 `prog.hex` 保留，用于相同指令流的对照测试。

`run_standard_cpu_tb.py` 使用原生Icarus执行仓库原有的 `sim/tb_rv_cpu.sv`，覆盖C1–C10。该旧测试显式关闭M扩展和分支预测；完整RV32IMC配置及性能对照由 `run_pacerv_checks.py` 执行。

完整 NPU 联合测试：

```powershell
python sim/experiments/pacerv_integration/run_native_npu.py --firmware imc --backend wsl-verilator --distro Ubuntu-22.04 --verilator /home/bx/.local/src/verilator-5.040/bin/verilator --run-label new_validation
```

该 runner 为当前生产 48 kHz 模型生成独立 golden 数据，并执行实际 CPU 固件、共享 DDR 控制器、四卷积／四池化、GAP、FC1、FC2 和概率输出。每轮报告保留命令、输入 hash、逐层数值结果和 UART 文本。旧 DDR 行为模型的 IP 地址单位在任务副本中修正，原文件保留。

## 100Pro+ 完整工程

```powershell
python experiments/pacerv_shared_system/prepare_pds.py --scope full --stage map --run --minutes 30
python experiments/pacerv_shared_system/prepare_pds.py --scope full --stage full --mode normal --seed 1 --hold-iterations 12 --run --minutes 120
```

目标器件为 **PG2L100H-6IFBG676**，包含音频、NPU、显示和新 CPU。一次只启动一个 PDS 流程。每轮建立新的 `build/pacerv_shared_system/pds/full-<时间>-<阶段>/`，冻结源码、IP、HEX、约束及 hash。已有正式位流指针保持原样。

新增的时序路径修改可独立复验：

```powershell
python sim/experiments/pacerv_integration/run_activation_mux.py
python sim/experiments/pacerv_integration/run_dashboard_equivalence.py
```

第一项执行生产激活仲裁模块的 24 笔混合读写与反压检查。第二项分别运行原四拍和新七拍显示流水，对照五幅 1080p 完整帧，并检查 RGB 与 DE/HS/VS 对齐。

完整路由结束后检查：

```powershell
python experiments/pacerv_shared_system/inspect_pds.py <本轮独立构建目录> --require-qualified
```

`QUALIFICATION.json` 同时检查冻结输入、十张时序汇总表、设计汇总结论和位流。退出 0 表示这些门槛全部满足；退出 2 表示门槛中存在未通过项。报告单列 LUT、FF、Distributed RAM、DRM 和 APM。

## 远程板卡验证（保留的独立实验）

按用户最新指示，当前任务只以100Pro+完整系统的本地PDS构建和时序检查验收，远程上板工作已结束。以下入口作为后续实验资产保留。

远程平台现有板卡为 **PG2L200H-6FBB676**。`remote/` 提供匹配该器件的 DDR IP、引脚和独立工程，用于验证 PaceRV、真实 DDR、MMIO、UART 和并发主口；完整音频工程继续使用 100Pro+ 的器件和约束。

```powershell
python experiments/pacerv_shared_system/remote/run_protocol_sim.py
python experiments/pacerv_shared_system/prepare_pds.py --scope remote --stage full --run --minutes 40
python experiments/pacerv_shared_system/inspect_pds.py <本轮远程构建目录> --require-qualified
```

上板入口及账户路径参数见 `remote/README.md`。工具直接复用源工程的 `tool/fpga_lab/PlatformClient`，在后台查询、预约、烧写和读取串口。已有预约保持原状，每轮新建采集目录，结束后释放本轮预约。默认通过门槛为连续两段完整的 BEGIN、CRC／EXPECT／零错误和 PASS 记录；原始 UART 字节一并保存。

## 对照与回退

原整机基线为 XSY `852f067db4a4a710f5355e3ab311f035ced5b48d`。`capture_baseline.py` 从 Git 提取原始输入并核验 `BASELINE_MANIFEST.json`。

`sim/experiments/pacerv_shared_ddr/VERIFICATION.txt` 保存 BASELINE／MODIFIED／ROLLBACK 的命令、输入、原始输出和退出状态。回退测试只操作独立验证副本；主工作区继续保留新实现。`ROLLBACK.ps1` 用于恢复指定副本中的两份旧 DDR RTL、移除两份新增模块。

固定整数循环的原固件对照为旧核心 460,012 周期、新核心 180,016 周期，双方均退休 180,008 条指令并得到 `0xf2d8888b`。这项测量对应此循环；新整机的 CoreMark 和最高合格频率应由新固件、布局和实板测量记录给出。

## 本轮时序收敛改动

当前完整系统使用normal布局布线模式、109.375MHz系统时钟、148.5MHz像素时钟，FDC声明0.150ns时钟不确定性；最终还核对报告中的实际扣减值。DDR采用厂商规则生成的875Mbps配置，FDC和UART/音频时间常数同步匹配。DDR桥请求分级，FC系数使用同步DRM，激活写入payload独立于valid，显示控制七拍；ROM物理取指13位，短权重FIFO采用寄存器映射。权重摘要先寄存再比较；GAP为256×14同步块RAM及一拍读改写流水，末拍增加一次drain，舍入语义保持。最新完整NPU标签timing_gap_sync_bram，控制器31,152,094周期、固件结果窗口31,152,093周期，58份输入hash匹配。显示等价记录在build/pacerv_shared_system/dashboard_equivalence_7clock_timing_selector_register。

新构建命令：

```powershell
python experiments/pacerv_shared_system/prepare_pds.py --scope full --stage full --mode normal --seed 4 --hold-iterations 12 --run --minutes 180
python experiments/pacerv_shared_system/inspect_pds.py <构建目录> --require-qualified
```

第二条命令同时检查十个时序汇总表、Design Summary、位流存在和冻结输入hash；退出0表示合格，退出2表示该构建仍有时序或输入问题。

## 原155.25 MHz核心的隔离对照

执行 `python experiments/pacerv_shared_system/compare_original155.py`。脚本读取归档核心，与其实际布线输入逐份核对，仅在build副本中适配原有八字节取指对的地址约定。三项集成测试通过；固定循环同为180,016周期、180,008条退休指令、f2d8888b。主线核心和固件保持原字节。对照记录执行周期，原归档时钟保留为归档属性。

PG2L100H使用厂商单线程路由，不能传通用`-number_of_router_thread`选项。当前电脑24逻辑线程、16GB内存；一个完整布线与轻量仿真可并行。每轮保持独立输入、日志及位流。需要重跑已有冻结工程时，使用`prepare_pds.py --restart <构建目录> --run --minutes 120`；入口先归档原尝试，再重跑完整配方。

连续48kHz音频验证命令为`python sim/experiments/pacerv_integration/run_audio_clock_check.py`。它同时比较125MHz与109.375MHz，各运行两个完整窗口；报告明确记录启动首窗1次补零及稳定第二窗的132,096帧全真实输入。DDR使用512周期行为完成模型。

权重摘要/GAP修改的独立验证采用新label，已有目录保留：

```powershell
python experiments/pacerv_shared_system/run_loader_gap_timing.py --mode BASELINE --label new_study
python experiments/pacerv_shared_system/run_loader_gap_timing.py --mode MODIFIED --label new_study
python experiments/pacerv_shared_system/run_loader_gap_timing.py --mode ROLLBACK --label new_study
```

BASELINE和该控制实验的ROLLBACK使用021145实际冻结输入；整机原始31文件回退另由run_integration_rollback.py核验Git 852f067的原始字节。最终collect_evidence.py加`--loader-gap-study build/pacerv_shared_system/timing_controls/<label>`。构建未完成时可加`--allow-pending-timing`生成明确未合格的功能记录；最终交付去掉此选项并要求inspect_pds.py --require-qualified退出0。旧物理记录保存在evidence/history，当前目录不会混入旧构建的时序表。

最终证据收集完成后，执行`audit_final_acceptance.py --full-build <构建目录>`。审计读取实际六阶段结果、十张快慢角表、时钟与不确定性、位流、资源占用、202份冻结/活源/Git提交字节、完整功能门槛及四件交付。退出0并输出GOAL_ACCEPTANCE_PASS表示这些要求全部通过；未完成的运行退出2，并在evidence/FINAL_ACCEPTANCE.json保存具体未通过项。
