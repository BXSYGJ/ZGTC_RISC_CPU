# CPU SoC 上板与串口烧录（PG2L100H · 2026-10-24 实测通过）

把主线 RV32IM SoC（`cpu/rtl`）搬到 100Pro+ 板上的完整流程。参考工程 `pds_cpu_100h/`，
实测：PDS 全流程出位流 → JTAG 烧录 → ZBOOT 串口控制台 → 串口加载应用 → **SoC 自试 `ZSOC PASS`**。

## 0. 与 200H/主线的关系

- RTL 直接用主线 `cpu/rtl/*.sv`（16 个文件），**排除** `rv32_board_top.sv` 与 `rv32_burst_ddr3.sv`
  （两者依赖 DDR3；100Pro+ bring-up 板级变体不带 DDR3）。
- `pds_cpu_100h/src/pds_cpu_top_100h.v.in` 是 100H 专用顶层模板：直接包 `rv32_soc`，
  DDR 后端 tie-off（访问 ≥0x10000 报总线错而非挂死），SPI 控制器不外接，
  管脚 clk D18 / rst_n C22 / key C23 / uart_rx B24 / uart_tx C24 / led[0..7] A20/C18/C19/E18/A17/A18/C17/B17。
- **PDS Verilog 前端不支持空端口连接 `.port()`**，所有端口必须显式接信号（主线 RTL 也是如此）。
- 应用/启动文件复用 `cpu/sw/`（start.S、link_soc.ld 链接到 0x1000，boot_start.S/boot_link.ld 链接到 0x0）。

## 1. 构建 bootloader 位流（一键）

```powershell
pwsh -NoProfile -File .\pds_cpu_100h\scripts\run_pds_full.ps1
```

依次：原生工具链（H:/ST/RV32I，xPack riscv-none-elf 15.2）编 bootloader_100h.c → 64KB hex →
展开顶层模板（INIT_FILE 指到位流构建目录的 firmware.hex）→ `pds_shell` 批处理
（compile → synthesize -ads → dev_map → pnr → report_timing → gen_bit_stream）。
产物：`pds_cpu_100h/build/pds/<时间戳>/generate_bitstream/pds_cpu_top_100h.sbit`，
并复制到稳定路径 `pds_cpu_100h/build/pds-latest.sbit`（program_full.tcl 用它）。
判定：退出码 0 且无 `^E:` 行且位流非陈旧。时序 `All Constraints Met`（27MHz 直接时钟，WNS≈25.9ns）。

注意：
- bootloader 用 `-march=rv32i_zifencei`（fence.i 刷 cache）；应用用 `-march=rv32i_zicsr_zifencei`
  （start.S 写 mtvec）。xPack GCC 15 不再把 zicsr/zifencei 隐含进 rv32i，必须显式写。
- `C: Bitstream-2001: SCBV has not been set` 是原厂未给 PCB 参数的正常提示。

## 2. JTAG 烧录

前置：jtagserver 在 127.0.0.1:65420（可直接 `cdt_js.exe -port 65420 -work_dir <脚本目录>` 拉起，
不必开 PDS Configuration GUI；65420 已被占说明已有实例，直接用）。

```powershell
cd pds_cpu_100h\scripts
& 'H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe' -file program_full.tcl
```

成功标志：`The done bit is 1` + `COMMAND[Program] execute successfully`。
**cdt_cfg.exe 前台运行会挂住不返回**：后台运行 + Tee 到日志再读（外壳任务可能报 exit 1，以日志为准）。
另注意：跑 PDS 构建时若沙箱/调度器有 ~2 分钟默认超时，长任务要显式加长超时，否则 pds_shell 会被杀
留下孤儿 lkads（端口/日志停止更新即此症状）。

## 3. ZBOOT 串口控制台

烧录后 bootloader 立即在串口打印 `ZBOOT 100H` + `>`（只打印一次，之后阻塞等命令）。
`tool/serial/serial_cli.py`（自动选 CP2102 口，默认 115200 8N1）：

| 命令 | 作用 |
| --- | --- |
| `list` | 列串口（标出 CP210x） |
| `monitor [--seconds N] [--hex] [--log f]` | 监听输出 |
| `load <app.bin>` | **ZBOOT R 协议上传并启动**（见下） |
| `send --hex 'a5' [--expect 'PASS']` | 发字节/等期望串 |
| `echo` | 交互式收发（Windows msvcrt） |

控制台只在处理完一个字节后才打印 `>`，所以**新开端口通常什么也收不到**——发 `?` 试探：
bootloader 应答帮助文本 `R<len32><bin> load+run`；若 `?` 被原样回显，说明板子在跑应用
（按 KEY0 或重新烧录回 ZBOOT）。

## 4. 串口烧录协议（ZBOOT R）

`load` 实现的协议（主机节奏跟随板子真实消化速度，避免丢字节）：

1. 发 `?` 确认在 ZBOOT 控制台（未见 `>` 时自动探测）。
2. 发 `R`；发 4 字节小端长度；发原始镜像。
3. 板子每收满 256 字节回一个 `K`，末尾再回一个 `K`，然后打印 `RUN` 并跳转到 0x1000。
4. `load` 收齐 `K` 后把随后到达的 `RUN`/应用输出带入 tail 阶段，看到 `RUN` 即成功。

踩过的坑（工具侧，已修）：
- **别把 `K` 之后的 `RUN...` 当协议错误**：一批 read 里既有 `K` 又有 `RUN`，数满 ack 就要停手。
- **中断未清源会死循环**：外部中断 `irq_external` 是电平触发，`uart_control[0] && rx_fifo_valid`
  为源时，处理函数必须 `UART_CONTROL=0`（或读走 UART_DATA）才能清除，否则中断风暴把主程序饿死。
- 上传中断后板子会在 receive_image 里等最多 ~35-67s（27MHz 下 1.2 亿次空转），之后 `ERR rx` 回控制台；
  期间发的字节都会被当成镜像数据。重新开始前等它超时或重新烧录。

## 5. 应用构建与实测

```powershell
pwsh -NoProfile -File .\pds_cpu_100h\scripts\build_app_100h.ps1 -App hello      # 464B：横幅+LED+回显
pwsh -NoProfile -File .\pds_cpu_100h\scripts\build_app_100h.ps1 -App selftest  # SoC 自试（KEY1 外部中断版）
pwsh -NoProfile -File .\pds_cpu_100h\scripts\build_app_100h.ps1 -App selftest -ExternalUart  # UART RX 外部中断版
```

```powershell
python tool\serial\serial_cli.py load pds_cpu_100h\build\app_hello.bin
python tool\serial\serial_cli.py load pds_cpu_100h\build\app_selftest.bin   # -ExternalUart 版
python tool\serial\serial_cli.py send --hex 'a5' --expect 'SOC PASS'          # 自试收尾
```

实测结果（2026-10-24，MES2L676-100HP）：
- `app_hello`：启动打印 `HELLO RV32 FROM 0x1000`，串口字节原样回显，LED 走 LFSR。
- `app_selftest -ExternalUart`：**`ZSOC PASS`** —— 性能计数器、软件中断、定时器中断、
  UART RX 外部中断、UART 数据读校（0xa5 回 0x5a）全过；通过时 LED=0xA5、STATUS=0xCAFE0001。
- 未实测：KEY1 引脚外部中断（`-App selftest` 默认版需要按键时刻与应用运行窗口重合；
  中断通路与 UART 版同 RTL，仿真覆盖）。Flash 固化（.sfc）未做。

## 6. CoreMark 实测（2026-10-24）

```powershell
pwsh -NoProfile -File .\pds_cpu_100h\scripts\build_coremark_100h.ps1          # 1000 迭代 @27MHz
python tool\serial\serial_cli.py load pds_cpu_100h\build\coremark_v0_i1000_rv32im_rv32gcc.bin
python tool\serial\serial_cli.py send --text 'G'                              # 应用就绪后等这个字节
python tool\serial\serial_cli.py monitor --seconds 220                       # 1000 迭代约 40-90s
```

结果（主线默认配置：cache 开/预测器开/无快路径优化，RV32IM，64KiB BRAM）：
`Correct operation validated`（crcfinal 0xd340），cycles=0x412F10A6=1,093,603,494。
**CoreMark = iterations × clock / timed_cycles = 1000 × 27MHz / 1.0936e9 ≈ 24.69**（CoreMark/MHz ≈ 0.91）。
注意：项目规范的 `6000 × clock / timed_cycles` 里的 6000 是**迭代数**——换迭代数必须同步改公式，
否则差 6 倍。0.91/MHz 低是因为没开快路径/大 cache 优化（200H 的 3.34/MHz 是全优化配置）；
在 100H 上开优化配置属于新的 config 实验（要过资源/时序），另立证据。

## 7. 排障速查

| 现象 | 原因 / 处理 |
| --- | --- |
| 烧录后串口无任何输出 | 正常——ZBOOT 横幅只在启动时打印一次；发 `?` 试探 |
| load 报「不在 ZBOOT 控制台」 | 板子在跑应用；KEY0 复位或重新烧录 |
| load 报「协议文本 0x52」 | 旧版工具缺陷（已修）；若仍出现，检查是否两次加载交叉 |
| PDS 编译 `Expression as lvalue` | 顶层里用了 `.port()` 空连接或字面量直连端口；都改成显式 wire |
| 构建日志停止更新、无 pds_shell 进程 | 外壳超时杀了 pds_shell，留下孤儿 lkads；杀掉孤儿重跑，并加长任务超时 |
| 时钟不是 27MHz 时乱码 | 确认位流 CLOCK_HZ 与板载 27MHz 一致（bring-up 用直接时钟） |
| **烧录后串口“没输出” | 90% 是测试方法错**：ZBOOT 横幅只在启动时打印一次，端口开晚了就永远等不到。**发 `?` 试探**：回帮助文本=控制台活着；被回显=在跑应用。别用“监听不到横幅”判断串口坏 |
| **烧录“成功”但板子不动 | 查僵尸 cdt_js/cdt_cfg 进程**：多个实例会霸占 D2XX 会话，后续 program 全变空操作（日志仍报成功）。杀光所有 cdt 进程 → 重启 jtagserver → 用 `tool/serial/d2xx_probe.py` 验证下载器（0xAA→0xFA）→ 重烧 |
| 大位流烧不进/1MHz 报 Program fail | JTAG 通路边际损坏；先断电重启板子+重插下载器，仍不行则送修 |


## 8. DDR3 上板（2026-10-24 构建通过，功能待测）

100Pro+ 核心板有 2 片 DDR3（MT41K128M16XX，32bit），地址空间从 0x0001_0000 起（低 64KB 仍是 BRAM）。

### 8.1 关键结论：DDR3 设施几乎可以直接复用 200H 的

- **IP RTL 完全相同**：官方 100Pro+ demo `2_9_ddr3_test` 的 `ddr3_test.v` / `ddr3_test_ddrphy_top.v`
  与仓库 `cpu/fpga/ddr3/` 下的逐字节相同；唯一器件相关的是
  `rtl/ddrphy/ddr3_test_slice_top_v1_10.v`（PHY 硬宏切片）。
- **只有 .idf 不同**：demo 的 idf 器件目标是 `PG2L100H/FBG676`，仓库的是 `PG2L200H/FBB676`；
  内存型号都是 MT41K128M16XX。
- **DDR3 引脚两板完全一致**：官方 demo 的**生效**引脚表与仓库 200H 的 `cpu/constraints/ddr3.fdc`
  逐针相同（73 针：mem_a[14:0]/mem_ba[2:0]/mem_dq[31:0]/mem_dqs[3:0]/mem_dqs_n/mem_dm/
  mem_ck(P/N)/cke/cs_n/ras_n/cas_n/we_n/odt/rst_n），参考时钟同为差分 125MHz N3/N2。
  注意 demo fdc 前半段是**注释掉的模板（含重复的占位引脚）**，真正的生效表在文件后段。
- 因此 `rv32_burst_ddr3.sv`（burst→AXI 桥）与 `rv32_ddr3_ip_wrapper.sv`（IP 包装）**一行未改**直接复用。

### 8.2 工程改动（pds_cpu_100h）

1. `ipcore/ddr3_test/`：从官方 demo 复制 `ddr3_test.idf`（100H 目标）+ `.v` + `rtl/`。
2. `src/pds_cpu_top_100h.v.in`：加 ref_clk_p/n + mem_* 端口；实例化 `rv32_burst_ddr3` +
   `rv32_ddr3_ip_wrapper`；gpio_input 按 200H 布局接
   `{ddr_dbg_to_err, ddr_dbg_to_state[2:0], ddr_init_done, ddr_pll_lock, uart_rx, ~key}`
   （bootloader 的 `D` 自检读这些位）。
3. `scripts/build_full.tcl`：加入 `rv32_burst_ddr3.sv`（不再排除）、wrapper、idf、`ddr3_100h.fdc`。
4. `constraints/ddr3_100h.fdc`：时钟节从 demo 移植（**实例路径要按本工程层级重写**，见 8.3），
   引脚表直接用 200H 的 73 针表（已验证与 100H demo 一致）。
5. `sw/bootloader_100h.c`：恢复 `D` 命令（单字探针 → 64KB 窗口全写全读 → `DDROK`/`DDRErr @addr`），
   并打印 `D0 pll=/init=/to=/ts=` 状态位以定位卡死阶段。

### 8.3 两个必须踩的坑

- **约束里的实例路径不带顶层模块名**，从顶层模块的**子实例**开始写：
  `ddr3_wrapper.I_ips_ddr_top.u_ddrphy_top...`（不是 `pds_cpu_top_100h.ddr3_wrapper...`）。
  写错会报 `CommandTiming-0057: Nothing matched for 'source_list'`。
- **DDR3 引脚必须在 fdc 里显式约束**。只 `add_design <.idf>` 而不约束 mem_* 时，IP 的
  PAD_* 参数是占位值（PAD_A0=PAD_ODT=PAD_RESET=H1 等），命令/地址组会落到没有 OSERDES 的 bank，
  综合能过、**布局阶段报 `Place-0006: ...oserdes_inst cannot be placed`**。把 73 针表补上即解决。

### 8.4 构建与测试

```powershell
pwsh -NoProfile -File .\pds_cpu_100h\scripts\run_pds_full.ps1      # 含 DDR3，约 8-10 分钟
cd pds_cpu_100h\scripts
& 'H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe' -file program_full.tcl
python ..\..\tool\serial\serial_cli.py send --text 'D'              # bootloader DDR3 自检
python ..\..\tool\serial\serial_cli.py monitor --seconds 20
```

自检输出：`D0 pll=1 init=1 to=0 ts=0` → `DDROK`；失败会打印 `DDRErr @0x<地址>`，
`to=1` 表示总线超时（DDR 未初始化/PHY 未校准），`init=0` 表示控制器初始化未完成。
