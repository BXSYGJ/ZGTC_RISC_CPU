# PDS ILA 接入流程与复现边界

赛题要求用 ILA 波形分析 CoreMark 关键算法期间的流水线效率。软件 GPIO 采样应用、testbench VCD、性能快照均不能替代这一项。

## 已查阅的本机原厂资料

- `D:/PDS_2022.2-SP6.4/doc/Fabric_Inserter_User_Guide.pdf` 第4章说明 PAP_MARK_DEBUG 标记，第5章列出 Inserter Tcl 命令。
- 同目录 `Fabric_Debugger_User_Guide.pdf` 说明运行时调试。提取文本仅保存在忽略目录 `build/vendor-docs/`，不把原厂手册重新许可为本项目源码。
- 原厂 `example/PG2L100H_adc_test/pnr/adc_ctrl_demo_syn.fic` 用于了解 FIC 结构，不复用其器件、引脚或旧网表路径。

## 已验证的工具接口

本机 `bin/cdt_ins.exe -help` 确认支持 `-device`、`-package`、`-speedgrade`、`-netlist`、`-fic`、`-file`。隐藏进程调用 `-file` 成功执行 Tcl 并退出；传给工具的 Tcl 文件参数要转为正斜杠，否则工具二次解析反斜杠时会破坏路径。

运行时 `info commands ins*` 确认存在 `ins_new`、`ins_set_file`、`ins_add_core`、`ins_set_core`、`ins_set_trig`、`ins_set_net`、`ins_list_nets`、`ins_save` 等。已用当前CPU综合ADF真实执行 new → set_file → list_nets → add_core → core_info → save；命令正常退出，记录在 `build/vendor-docs/probe-nets-core.stdout.txt`。尚无核心时执行 core_info 会弹模态提示，因此自动化必须先建立核心，不能把该等待当作成功。

生成的 `build/vendor-docs/cpu-probe.fic` 仅证明工程文件创建成功：时钟和数据尚未连接，不能用于正式下载、抓波形或验收。已查询网表显示优化后名称可能变成 `board/soc/core/board/unused_trace_valid`，时钟为 `nt_clk`。索引和名称绑定必须来自同一次综合，不能复制其他构建的数字索引。

后续已在当前综合网表上按完整名称连接109位信号和 nt_clk，使用真实 cdt_ins 的 ins_open → ins_core_info → ins_save 校验并规范化 FIC。跨进程数字索引可能变化，即使同一 ADF 也不能重用；连接依赖网表名称，改变 RTL 后必须重新验证。原型 `build/ila/prototype/cpu.fic` 已完整接线，不能与早期不完整 cpu-probe.fic 混淆。

## 已跑通的插核实现流程

原厂 Fabric Inserter 手册2.3.6说明保存FIC后Map自动插核，PDS手册9.3说明 add_fic。实际工程采用同一次综合的 ADF 和 Verilog 网表，将 .vm 原样复制为 .v 作为 add_design 输入，再 add_constraint、add_fic、set_arch、compile、dev_map -input_db_file、pnr、report_timing、gen_bit_stream。直接以 .vm 加载的首次尝试被 PDS 的 Synplify模式检查拒绝，未将失败产物用于下载。

`build/ila/prototype/build.tcl` 是已成功执行的完整命令；PDS日志确认生成 DebugCore、ADS综合调试核、插入扫描时钟缓冲并重新布局布线。实板原型的位流和FIC SHA、资源与重新约束后的时序见 `ILA_RESULTS.md`。

已新增 `scripts/run_ila_pds.ps1` 和 `scripts/cpu_ila.fic.in`，在仓库根目录运行：

```powershell
pwsh -NoProfile -File cpu/scripts/run_ila_pds.ps1 -SourceBuild cpu/build/pds/20260906-053005-95ba4365
```

脚本检查源manifest、器件、27 MHz、Cache/预测开启、RemoteLab配置及固件哈希；复制ADF、网表、固件和约束到唯一输出目录；真实调用 Inserter 逐项核对109条连接及深度、时钟，然后运行PDS全流程，拒绝工具错误、过期位流和时序不通过。没有下载或预约硬件的副作用。FIC首行 `#Fabric Core Inserter Project File` 是原厂解析器要求的文件标记，删掉会报 Inserter-0003；已保留。新版指定隐藏进程工作目录为该构建目录，避免工具临时文件散落仓库根目录。

自动全流程已成功输出 `build/ila/20260906-063024-bf641b62`，位流SHA-256 `0826DECC095A576D7F73E341E09BA3DFFBB68B02F6E5C5E4A8ADBC72A87ED644`，FIC SHA-256 `907CE27AFBF796C7C546B7E307822285000EC61AF79D5552C27AF5BE223840E8`，27 MHz时序通过。该次完整运行之后仅追加了进程工作目录设置，已做PowerShell语法检查；该目录设置尚未另跑一次全流程。manifest明确 `HardwareValidated=false`，这些新产物没有冒用原型上板结果。输入无Cache构建的负向试验也已确认在启动PDS之前拒绝。

输入必须是完整的 `run_pds.ps1` 综合构建，不能只给位流。网名依赖当前RTL；变更综合网名时脚本应失败并人工重新映射，而不是静默丢失通道。SCBV原有工具告警仍保留，不能用内部时序通过代替板级电压边界核实。

## RemoteLab 实测操作

1. 核对箱5目标器件，下载插核位流并等待“固件下载完成且设备已唤醒”，不能仅看传输记录。
2. ILA页面导入匹配FIC，显示109通道1024深度。导入后的零值不是已捕获数据。
3. 点击启动，等待“已捕获”，点击导出取得真实CSV；网站默认即时触发，未假设存在没有显示的高级触发控件。
4. 清除会连同FIC配置一起清除，每次重复捕获前需要重新导入。另开同一浏览器会话的串口页发送G，收到完整START行后连续捕获六次，以避免人工操作延迟使窗口落到printf阶段。
5. 保存原始UART、CSV、符号表、网页截图和哈希。结束后关闭串口并释放板卡，本次已确认释放。

已取得矩阵、状态机、CRC/链表的六个真实算法窗口，并通过跨周期PC传递与流水线有效性检查；详情见 `ILA_RESULTS.md`。这完成了首轮真实ILA观察，不代表全部流水线性能问题已优化。
