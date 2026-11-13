# PaceRV 共享整机的 PG200 远程验证

本目录提供独立的 **PG2L200H-6FBB676 / 125 MHz** 验证工程。完整 PaceRV H3 RV32IMC 核、程序 ROM、数据 RAM、共享 UART、CPU DDR 桥、四主口 DDR 控制器和物理 DDR3 IP 共同工作。CPU 与 DDR 用户端使用同一 125 MHz 时钟。

远程硬件测试覆盖 CPU、DDR、外设寄存器和并发内存访问。竞争主口采用可校验的 4 KiB 模式发生器；音频采集、正式 NPU 和 HDMI 使用 100Pro+ 整机另行验证。

## 测试内容

- RV32I 运算与控制流、显式 C 扩展指令、MUL、MULHU、DIV/REM 和除零结果。
- 启动时由现有 `self_test` 完成物理 DDR 4 KiB 写入和逐字读回。
- CPU 访问 `0x40000000`，映射到物理 DDR `0x00600000`。逐字写入 256 个模式字，并用 SB/SH 改写同一字的不同字节，核验字节掩码和 CRC32。
- CPU 启动模拟加速器主口，在物理 `0x00010000` 执行独立 4 KiB 写读测试；CPU 同时访问 APP 区，然后通过只读 `0x41010000` 别名逐字检查该主口的结果。
- 固件输出 ISA、CRC 和错误计数，成功标记为 `PACERV_SHARED PASS`。固件重复测试和输出，远程串口在烧写后打开也能获得完整结果。

## 重建

PowerShell 7 中执行；路径均可通过 `Join-Path` 或 `[System.IO.Path]::Combine()` 构造。

1. `python build_firmware.py` 使用本机 RV32 GCC；未找到本机编译器时，直接调用 `wsl.exe -d Ubuntu-22.04 --cd / --exec` 下的 GCC 10.2.0。默认 Linux 编译器为 `/home/bx/.local/zgtc-riscv32-10.2.0/bin/riscv32-unknown-elf-gcc`；`--gcc`、`--distro` 和 `--wsl-prefix` 可覆盖。
2. `pwsh -File prepare_build.ps1` 生成 `build/build.tcl` 和带 SHA-256 的 `build/BUILD_MANIFEST.json`，并将固件复制到 PDS 工作目录。该步骤仅准备输入。
3. 在统一 PDS 构建槽空闲时，由主任务运行 `pds_shell.exe -file <build.tcl> -work_dir <build> -project_name remote_pg200`。配方依次执行 compile、synthesize、dev_map、pnr、report_timing 和 gen_bit_stream。

`vendor/ddr3_test` 是官方 200Pro+ 参考工程生成的 **PG2L200H/FBB676** DDR3 IP，仅复制 IDF 的 74 个源码依赖及 IDF 本身。逐文件源路径、大小和 SHA-256 保存在 `vendor/MANIFEST.json`。重建使用本目录副本，其他电脑无需原参考目录。`constraints/pg200_ddr3.fdc` 保存对应 73 个 DDR/参考时钟 IO 的映射；参考时钟 N3/N2，UART TX AB26，复位 C22。

`rtl/ddr3_wrapper.v` 是独立的 PG200 板级适配：CK delay 关闭，PHY debug enable 使用官方示例的常量1，由IP内部执行PLL与PHY复位时序。D18的27MHz板载时钟驱动上电复位计数器，使远程烧写无需人工按KEY0。启动条件独立于DDR派生时钟，CPU、共享桥和DDR控制器仍共用125MHz；100Pro+生产wrapper保留原配置。`run_clock_boot_sim.py` 检查派生时钟尚未启动时的独立PHY enable、按键复位和CK delay设置；`run_protocol_sim.py --no-key-reset` 检查物理复位输入始终为高时的固件启动与DDR协议。

初次从参考工程重新取件可用 `prepare_build.ps1 -VendorIp <官方 PG200 ddr3_test IP目录>`；脚本核验 IDF 的器件和封装后复制。

## 仿真

`python run_protocol_sim.py` 使用 Windows Icarus，对同一固件、CPU、桥、仲裁器和控制器进行联合测试。仿真在 DDR 用户端连接行为模型，并检查 CPU/竞争主口重叠、两次部分写入、请求数量、启动自检和全部错误状态。该行为模型仅用于协议测试；PDS 工程使用生成的 DDR3 IP 和物理管脚。

联合仿真还逐位解码顶层UART引脚，并将每个串行字节与CPU FIFO的接受顺序核对。远程顶层采用与生产系统相同的接受保持逻辑，适配现有UART模块的注册ready，保证每次发送只弹出一个FIFO字节。

`--audio --firmware <src/cpu/prog_pacerv.hex绝对路径>` 也可运行正式音频控制固件，检查 M/C/CSR、自测CRC、48次部分写入、整数循环和第一次模拟NPU结果；它与专项固件分别保留在 `sim_build/audio` 和 `sim_build/shared`。已执行结果见 `VALIDATION.md`。

PDS 启动前用 `python verify_inputs.py` 核验96项构建输入。创建后续构建时使用独立目录冻结这些输入和配方；已完成的构建目录继续保留其原始版本。`CLOCK_CONSTRAINT_AUDIT.md` 说明第三份约束 `pg200_ip_cdc.fdc` 的官方来源及0.150ns用户时钟对预算。

`python -m unittest discover -s tests -p test_remote_capture.py -v` 检查采集脚本的分包重组、超时记录、已有预约保护以及异常后的释放。

## 远程上板采集

默认 `capture_remote.ps1` 只执行状态查询。运行参数为：

`pwsh -File capture_remote.ps1 -Action run -Bitstream <sbit绝对路径> -OutputDirectory <全新结果目录> -AccountFile <既有account.txt> -Seconds 90`

该入口直接复用 `tool/fpga_lab` 的原生 `PlatformClient`，不依赖浏览器、桥服务或旧信标位流。流程为检查当前预约 → 新预约 → 烧写 → 115200/8N1 串口累计采集 → 关闭串口 → 释放。已有预约保持原状。结果目录含位流 SHA-256、板卡 ID、原始 UART 字节、带时间戳的分包和成功标记匹配结果；脚本不输出认证内容。

单次运行须使用全新结果目录。默认要求连续两轮完整BEGIN、同轮CRC/EXPECT一致、ERR为零和PASS，并在释放成功后返回0。采集流中的错误CRC、非零ERR和显式FAIL保留为失败结果；开串口过晚收到的前缀残片不计入通过轮数。准备、编译、仿真与硬件抓取分别保存实际记录。

## 独立时钟诊断

`python run_probe_sim.py` 检查独立探针的参考计数和全部26个串行字符。`python probe_clock.py --run-pds` 单独构建D18/27MHz驱动UART的探针，测量N3/N2参考时钟；该工程不含CPU、DDR IP或DDR访问。它与整机验证共用PDS构建槽，须顺序运行。

`probe_clock.py --capture <探针sbit> --output <新目录> --account <既有账号文件>` 采集 `PG200_REF E=XXXXXXXX R=1`，其中E为10ms内参考时钟八位分频器最高位的翻转次数，频率估计为 `E × 12800 Hz`。`compare_uart_control.py` 可在同一次预约内先跑已知控制位流、再跑候选位流，分别保存各波特率的原始字节。控制位流的通过结果独立于候选设计的验收。
