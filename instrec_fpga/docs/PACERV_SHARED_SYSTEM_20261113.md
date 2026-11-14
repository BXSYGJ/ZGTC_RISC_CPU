# PaceRV 高性能核心与共享整机集成

日期：2026-11-13。工作分支：XSY。原始基线：`852f067db4a4a710f5355e3ab311f035ced5b48d`。

2026-11-14最新使用安排：用户要求结束当前轮后停止时序优化，选用已有109.375MHz的021145主选版和125MHz的223256备选版。位流、202份配套冻结输入、原报告及使用路径集中在[所选版本](SELECTED_BUILD_VERSIONS_20261114.md)。最后一轮83.333333MHz的133421因工具参数范围错误退出1，无新位流；当前工作区作为实验记录保留。以下架构与实验内容记录各阶段实现，实际使用版本以对应包内输入为准。

## 架构与代码入口

整机采用一套音频前端、NPU、DDR3 控制器、UART 和显示链路。PaceRV H3 Base 五级执行核心替换原来的小型控制核，通过整机既有 MMIO 控制推理、读取结果和输出串口。完整指令集为 RV32IMC，开启分支预测、重叠取指和提前数据请求。

| 内容 | 源码入口 |
| --- | --- |
| 原始 H3 执行核心，8 份源码及逐文件来源/hash | `src/cpu/vendor/pacerv_h3/PROVENANCE.json` |
| 本地 ROM/RAM、成对取指、MMIO、CPU DDR 请求口 | `src/cpu/rv32_cpu_subsys.sv` |
| CPU 地址隔离、字节掩码、返回与超时处理 | `src/ddr3/pace_cpu_ddr_bridge.v` |
| 启动自检/诊断/特征导出/CPU 的锁定式 M3 子仲裁 | `src/ddr3/ddr3_m3_share.v` |
| 原四主口 DDR 控制器，增加 M3 字节写使能 | `src/ddr3/ddr3_ctrl_axi.v` |
| 100Pro+ 完整系统接线 | `src/ctrl/instrec_top.v` |
| RV32IMC 自测及原音频控制程序 | `sw/rv32/main_pacerv.c` |
| 可复现操作说明 | `experiments/pacerv_shared_system/USAGE_zh.md` |

H3 的 8 份执行核心源码与原发布版逐字节一致。整机存储适配采用 8 KiB 本地程序 ROM、8 KiB 本地数据 RAM，以及共享 DDR 数据通路；采用本地程序存储替代原独立 SoC 的缓存层级。程序目前从本地 ROM 运行。原发布版和原固件保留为对照。

## 共享存储

| CPU 地址 | 用途与权限 | DDR 物理地址 |
| --- | --- | --- |
| `0x00000000..0x00001fff` | 本地程序 ROM / 读取 | 片内 |
| `0x20000000..0x20001fff` | 本地数据 RAM / 读写 | 片内 |
| `0x40000000..0x400fffff` | CPU 应用缓冲区 / 读写 | `0x00600000..0x006fffff` |
| `0x41000000..0x415fffff` 中的合法子区间 | 已有 PCM、权重、谱、自检、activation 的只读观察窗口 | `0..0x005fffff` |
| `0x80000000` 起的已定义寄存器 | 原 UART、NPU、DDR 状态、LED 与计数器 | MMIO |

一次 CPU 请求使用一个 256 位 DDR beat，通过字选择与 byte strobe 实现字、半字和字节访问。Pango IP 边界统一把字节地址右移两位。读前 dummy-write 的掩码始终为零。观察窗口的空洞和写入返回访问异常；读取一致窗口时沿用已有锁窗协议。

M3 子仲裁在启动阶段仅向 `self_test` 授权，启动成功后轮转处理诊断、特征导出和 CPU。事务的归属保持到硬件完成及读数据排空，防止尾 beat 落入下一客户。对旧 `self_test` 保留最后写 beat 与原始 done 同拍的契约；CPU 桥独立处理其返回缓存、迟到返回和超时。

## 本地存储与共享串口

本地 RAM 使用四个独立字节读寄存器和寄存后的写地址、数据与掩码。PDS 的专项综合报告确认，8 KiB RAM 合并为两个 `GTP_DRM36K_E1`，此前的四组字节数组各映射到 256 个 `GTP_RAM64X1DP`。核心回归、1,500 周期返回反压以及完整 NPU 联合仿真确认了相同的读写语义和执行周期。RAM 推断报告保存在 `experiments/pacerv_shared_system/evidence/RAM_*_SYNTHESIS.txt`。

四路 UART 发送源沿用权重加载、调试、诊断、CPU 的优先次序。接受保持逻辑覆盖全部四路来源，在注册 ready 返回期间保持一次发送只弹出一个字节。实际顶层与原串口串行器的联合测试取得 32 字节逐位一致输出，覆盖四路同时请求。

MMIO 数据与本地存储并行采样，由通道忙状态保持，减少地址译码对返回寄存器使能的影响。NPU 激活命令先寄存仲裁结果及地址，再执行下游握手；24 笔混合读写测试覆盖即时返回、延迟返回和反压。显示端分级处理通道、字符和字形选择，RGB、DE、HS、VS统一延迟七拍。五幅1080p帧共10,368,000个输出像素与原版逐帧哈希完全一致，2,000次概率条及控制对齐检查全部通过。

## 已完成的执行验证

### 相同固件对照

| 指标 | 原控制核 | PaceRV H3 执行核心 |
| --- | ---: | ---: |
| 固定整数循环周期 | 460,012 | 180,016 |
| 退休指令 | 180,008 | 180,008 |
| 累加结果 | `0xf2d8888b` | `0xf2d8888b` |
| 原音频控制 C1–C10 检查 | 全部通过 | 全部通过 |

该指令流的周期减少约 60.9%，按相同运行时钟折算的速度为原来的约 2.56 倍。新 RV32IMC 固件的对应循环使用 149,878 条退休指令和 179,874 周期；两组计数分别对应各自固件。CoreMark 应使用本次集成后的固件重新测量。

### 核心与共享 DDR

- 25 项定向核心检查通过，包含跨字压缩取指、M 扩展、CSR、访问异常及请求停顿。
- 本地和 DDR 返回分别保持 1,500 周期的反压检查通过；8 项程序 ROM 边界检查通过。
- 共享 DDR 检查通过 996 项断言，覆盖全部 256 个字节掩码位置、音频写入、Mel、activation、诊断竞争和读尾排空。
- 四客户轮转、CPU 超时后迟到返回、随后诊断继续工作，以及原启动 4 KiB 自检均通过。
- 回退在独立副本中恢复两份原 DDR RTL，原字节地址测试再次通过；当前主线保留新实现。

### 生产 48 kHz 完整 NPU 联合仿真

使用生产 `medley_48k/layer_contract.json` 和对应权重，实际 RV32IMC 固件完成共享 DDR 自测、启动 NPU、取得 UART 结果并清除 ACK。

- CPU DDR：331 次请求、331 次返回，CRC=`ab60ce69`。
- 四层卷积、四层池化、GAP、FC1、FC2 logits 和概率输出全部与独立 golden 逐位一致。
- 同步GAP版本的NPU控制器运行31,152,094周期，固件结果窗口计数31,152,093；相对原31,141,255周期增加10,839周期，约0.035%。四卷积、池化、GAP、FC及概率输出与整数golden精确一致。
- 该测试使用既有特征输入验证计算与控制链路；本轮按用户要求采用本地仿真和 100Pro+ PDS 完整构建验收。

详细命令、输入 hash、原始输出和退出状态见 `experiments/pacerv_shared_system/evidence/` 与 `sim/experiments/pacerv_shared_ddr/VERIFICATION.txt`。可运行的回退入口为同目录 `ROLLBACK.ps1`。

## 100Pro+ 本地物理实现

当前完整系统目标为 PG2L100H-6IFBG676，保留正式音频、NPU、DDR3 和显示模块，系统用户时钟为83.333333MHz，像素时钟为148.5MHz。用户已结束远程上板要求，本轮以100Pro+的本地构建与完整时序检查为准。

当前冻结构建为`build/pacerv_shared_system/pds/full-20261114-124245-full`，normal模式、seed5、多角优化和最多十二轮保持时间修复，时限180分钟。202份源码、IP、HEX与约束与a5189f2提交检出逐字节一致。当前采用13位ROM物理地址、短权重FIFO寄存器映射、666.666667Mbps DDR IP、权重摘要寄存级与同步GAP块RAM；DDR读FIFO16×256及CPU UART FIFO16×8改用显式标量寄存器，保持原深度和读出时序，当前正在综合，最终资格待验。上一111645完整六阶段完成，最终37271LUT/46426FF/826DistributedRAM/129DRM/94APM，GAP已推断GTP_DRM18K_E1；最终系统slow setup -1.839ns、slow hold -0.160ns、fast hold -0.162ns，像素setup +0.782ns。其setup来自池化写使能及DDR校准，hold来自两个短FIFO的分布式RAM写地址，为本轮修改依据。035340超时及021145未过的历史报告与原正式位流均保留。

### 原155.25 MHz核心对照及降频预案

归档 `Original_155250` 的八份核心源码与其V0实际布线输入逐份一致。隔离副本只适配原有八字节取指对的地址约定，沿用当前程序ROM、数据RAM、共享DDR和MMIO封装。指令、反压及音频控制固件三项检查通过；固定循环与H3同为180,016周期、180,008条退休指令和结果f2d8888b。该对照支持保留当前H3执行核心，优先缩短NPU和显示的整机关键路径。

83.333333MHz配置已通过官方DDR参数规则并启用，UART分频723、音频空FIFO补样节拍1736与相关时间常数同步匹配。UART测试按生产时钟和分频实际串行输出四路32字节，逐字节一致。当前完整NPU控制器31,152,094周期在125MHz折算249.217ms，在83.333333MHz折算373.825ms；固定CPU循环在原125MHz下460012周期约3.680ms，在当前频率下180016周期约2.160ms。连续48kHz采样由外部PCM1808时钟提供、27MHz域接收。125MHz及83.333333MHz连续I²S仿真各完成两个窗口，稳定第二窗均132,096真实帧、补零0、溢出0、写超时0，首窗各有1次启动补零。该实验用512周期行为DDR完成模型；逐层NPU数值另外由完整native测试验证。

厂商用户指南标明PG2L100H采用单线程路由，具体器件拒绝通用帮助中的`-number_of_router_thread`。当前配方删除该选项；入口只接受1作为记录值。当前电脑24逻辑线程、16GB内存，完整布线阶段剩余约2GB，重任务顺序执行，轻量核心和音频仿真与PDS并行完成。

## 复现入口

在 `instrec_fpga` 下执行；绝对路径与工具覆盖参数见 `USAGE_zh.md`。

```powershell
python experiments/pacerv_shared_system/run_baseline_cpu.py
python sim/experiments/pacerv_integration/run_pacerv_checks.py
python sim/experiments/pacerv_integration/run_activation_mux.py
python sim/experiments/pacerv_integration/run_dashboard_equivalence.py
pwsh -NoProfile -File sim/experiments/pacerv_shared_ddr/run_pacerv_shared_ddr.ps1 -Mode Modified
python sim/experiments/pacerv_integration/run_native_npu.py --firmware imc --backend wsl-verilator --distro Ubuntu-22.04 --verilator /home/bx/.local/src/verilator-5.040/bin/verilator --run-label new_validation
python experiments/pacerv_shared_system/prepare_pds.py --scope full --stage full --mode normal --seed 5 --hold-iterations 12 --run --minutes 180
```

PDS 同时只运行一个流程。既有 PG200 独立实验及其原始记录保存在 `experiments/pacerv_shared_system/remote/`，本轮不继续使用远程平台。

## 时序路径调整记录

DDR桥先采样请求，再在下一拍完成访问范围检查与地址转换；宽数据寄存器的使能由本地忙状态控制。FC系数采用四个原生DRM18K，累加值、乘数、移位量和有效位同步进入requant流水。显示分级完成通道、字符和字形选择，图形与DE/HS/VS统一七拍，像素时钟仍为148.5MHz。权重上传的折叠摘要先寄存再比较；GAP使用256×14同步块RAM，输入上界255×4×16=16320，读改写在下一拍完成，末拍drain后逐通道舍入输出。控制实验的连续帧、停顿、偶数舍入、最大值和同步读回均通过；完整NPU增加一周期。
