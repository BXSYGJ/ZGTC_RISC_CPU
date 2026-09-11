# CPU GPIO 波形采集应用

## 当前157.5 MHz物理状态

正式节流固件8A691616的EnableM=0元数据已补齐，重编译HEX保持逐字节相同；旧元数据与构建脚本保存在build/scope-metadata-before-isa。9600波特率、种子2的20260909-151637-4e588209普通实现实际9080 LUT、WNS -0.364 ns，拒绝上板。仅调整布局种子3的独立试验20260909-155033-30e51965正在运行，不预判成功，不复用115200波特率CoreMark的时序结果。

## 2026-09-09正式节奏固件已生成

157.5 MHz正式限速固件现已构建：`build/scope_p2333333_s1260_t4725000000_rv32gcc_f157500000.hex`，SHA256为8A6916168CDCD4586045E8AD0076F8C3B2FF7285750BC5C5E82F3C7257BAF19D。采样1260周期、超时4725000000周期、输出延时2333333周期，串口9600。它与已通过仿真的诊断版本使用相同六份源码，但输出延时由0恢复为正式值，不能把诊断仿真直接说成正式节奏已上板。独立物理入口为build/run_regfile_fanout_scope_pds.ps1，含源、固件、参数和单PDS进程检查；当前只准备好入口，尚未启动其PDS。



## 2026-09-09：157.5 MHz当前CPU迁移（尚未上板）

`sw/scope.c`的头部频率现在来自编译宏APP_CLOCK_HZ，不再固定为27 MHz；采样周期默认按8微秒换算，27 MHz仍为216周期，157.5 MHz为1260周期。旧27 MHz构建默认值和文件名保持兼容。

30秒在157.5 MHz下为4725000000周期，超过32位范围；等待触发计时已改用mcycleh/mcycle/mcycleh一致性读取的64位值。采样窗口内的32位快路径时间戳保持不变。构建脚本支持64位TimeoutCycles，并按ClockHz缩放默认ConsoleDelay；解码器支持27/157.5 MHz及显式expected-clock检查，不接受未知或不匹配频率。

构建157.5 MHz正式节奏固件的入口为 `pwsh -NoProfile -File cpu/scripts/build_scope.ps1 -ClockHz 157500000`。这只生成应用固件，不证明当前CPU的应用PDS通过；后续还必须使用源绑定的DC90363D配置、157.5 MHz和9600串口重新实现并检查时序后才能下载。不要把CoreMark 115200位流当作scope应用。

已完成验证：旧27 MHz真实CPU应用回归通过2381688周期、2次导出、1次超时和1次EMPTY；解码器6项测试通过。当前DC90363D源回归build/scope-fanout-current/20260909-135217-452918e8通过2718764周期，2份各256样本，恢复UART 0x55和KEY 0→1→0，late均为0；两次定向64位mcycle跳变验证跨2^32不提前超时、到4725000000周期正确超时。仿真命令/导出串口加速并记录，计时跳变仅用于超时验证，不冒充连续30秒实板等待。

本次测试固件为scope_p0_s1260_t4725000000_rv32gcc_f157500000，ConsoleDelay=0仅用于仿真。正式限速版本、应用物理实现、实板KEY与30秒等待尚未完成。下文2026-09-06的27 MHz实板记录属于历史版本，不能作为当前157.5 MHz证据。



这是运行在本项目 RV32I 上的裸机应用，不是用 testbench 代替 CPU 采集。CPU 经 MMIO 读取 GPIO，按 mcycle 安排采样，写入缓存 RAM，再经 UART 导出记录。它是软件采样式两通道波形记录器，不是高带宽硬件逻辑分析仪，也不替代原生 PDS ILA（其独立完成证据见 ILA_RESULTS.md）。

## 通道与命令

- 通道 0：KEY1 按下为 1，可用上升沿触发。
- 通道 1：实际 uart_rx 输入引脚的原始电平，内部只读分接到 GPIO 同步器；RemoteLab 为 AC26，Board 为 B24。不新增外部接线，不改变引脚方向。
- A（HEX 41）：等待通道 1 下降沿；收到完整 ARMED 行之后发送 HEX 55，可采集一个 UART 0x55 的实际电平波形。
- K（HEX 4B）：等待通道 0 上升沿，用于按键波形。
- D（HEX 44）：导出已冻结的采集；无有效记录时返回 EMPTY，可重复导出同一记录。
- ?（HEX 3F）：帮助。每次重新 arm 使旧记录失效，默认等待 30 秒无触发则 TIMEOUT。

新应用位流使用 9600 8N1，网站串口也必须设为 9600；原 SoC/CoreMark 位流默认仍为 115200。较低的测试波特率给 CPU 软件采样保留充足过采样裕量。后续 ILA 的高速采样能力不能从本应用外推。

## 编译和运行

```powershell
pwsh -NoProfile -File cpu/scripts/run_scope_tests.ps1
pwsh -NoProfile -File cpu/scripts/build_scope.ps1
pwsh -NoProfile -File cpu/scripts/run_pds.ps1 -UartProfile RemoteLab -UartBaud 9600 -FirmwareHex D:/AAAFPGA/ZGTC_RISC_CPU/cpu/build/scope_p400000_s216_t810000000_rv32gcc.hex
```

构建成功且核验 SHA/目标器件后下载；打开 9600 串口，发送 A，等待 ARMED，再发送 55；收到 DONE 后发 D，等待完整 END 行。每份记录约 3 KiB，默认日志限速约 67 字符/秒，导出约一分钟。ARMED 为短、未限速应答，使 CPU 在主机收到完整行前进入触发等待；长数据报告限速以适配网站读取能力。

LED 低位状态依次为：01 空闲、02 等触发、04 采样、08 记录就绪、10 导出，EE 表示软件陷入。软件 STATUS 分别为 A1100000..A1100004，状态用于调试，不等于独立 LED 实测证据。

## 数据与时间含义

每次 256 个样本，默认目标间隔 216 个 CPU 周期，即 27 MHz 下 8 us。每条记录为 `xxxxxxxx:yy`，前者是相对于捕获起点的 32 位周期，后者是两位 GPIO 电平。头部给出数量、间隔、频率和触发位；尾部给出 rolling checksum 与 late 次数。

时间戳是 GPIO load 完成之后读取的 mcycle，不是硬件锁存边沿时刻，含 MMIO/指令延迟。循环按绝对 deadline 调度；如果晚到至少一个采样间隔，记录 late 并从当前时刻重排下一次，既不伪造等间隔样本，也不把补采突发当作稳定采样率。绘图和解码使用实际记录的时间戳。

校验初始化为 2166136261；逐样本先异或整个 32 位时间戳并乘 16777619，再异或电平值并乘同一常数，按 32 位回绕。它用于传输损坏检测，不是密码校验，也不冒称标准逐字节 FNV 或 CRC。校验只在导出阶段计算，不占用采样区间。

`scope_decode.py` 验证固定数量、单调时间戳、位范围、完整尾部及校验，再输出 CSV、SVG 和 JSON 摘要；可选择独立 UART 解码。解码前检查位中心附近的样本密度，稀疏采样不能强行宣称恢复了串口字节。

## 当前验证边界

仿真使用真实 CPU 执行 scope.c。覆盖 EMPTY、触发超时、RX 下降沿捕获、KEY 上升沿捕获与连续状态转换；注入的 UART 波形保持 2813 周期/位，命令/导出 UART 在 testbench 中加速，不能把仿真总时间当作实板速度。

两份仿真记录共 512 样本已通过校验；第一份从原始 GPIO 波形独立解码为 0x55，第二份恢复按键 1→0→1→0 注入序列，late 均为 0。输出位于 `build/scope-simulation/capture-0.csv/.svg` 和 `capture-1.csv/.svg`，已在浏览器检查波形显示。另有五项解析器测试，包含数据损坏、截断、乱序、错误元数据和稀疏采样拒收，已纳入 `validate.ps1`；完整应用仿真另运行 `run_scope_tests.ps1`。

## 实板记录：2026-09-06（北京时间）

RemoteLab 实验箱5（PG2L200H），网站明确返回“固件下载完成且设备已唤醒”。串口设为 9600 8N1，两次均按 A → ARMED → 测试字节 → DONE → D 顺序执行。CPU 从 GPIO 原始输入采样，而不是将 UART 接收寄存器里的字节直接当作波形。主机只负责注入和离线解码。

| 输入 | 样本数 | rolling checksum | late | 离线解码 | 首末时间戳（周期） |
| --- | --- | --- | --- | --- | --- |
| 0x55 | 256 | 037ad1a4 | 0 | 0x55，通过 | 69 / 55105 |
| 0xAA | 256 | c13fd664 | 0 | 0xAA，通过 | 69 / 55100 |

两组实际相邻样本间隔均为 172–223 周期，平均分别约 215.827 和 215.808 周期。目标 216 周期不等于严格等间隔；late 为 0 也不意味着无抖动。两份波形跨度约 2.038 ms，图中已显示不同输入的实际跳变。KEY1 在这两次捕获中保持 0，不能据此宣称完成实板按键边沿验证。

- 位流构建：`build/pds/20260906-045333-71b3fa93/generate_bitstream/pds_soc_top.sbit`。
- 位流 SHA-256：`D2B24B4EE0C92B467599BE539A5865D9157090CB29F6DA3ECC39A23EF99E36CF`。
- 固件镜像 SHA-256：`E4D80F2AC8532D1339DC9461A381FE8365EAFCB47870F1B79C937C84CCF86088`。
- PDS：4098 LUT、3501 FF、16.5 DRM、0 APM；27 MHz 时序检查通过。报告估算 74.6882 MHz，不作为实板最高频率成绩。
- 原始数据：`build/hardware/scope-box5-55.uart`、`scope-box5-aa.uart`；对应 `-session.txt` 保留界面日志，含打开串口时的旧缓冲乱码，不把乱码补成数据。
- 每组离线输出目录 `build/hardware/scope-box5-55/`、`scope-box5-aa/` 含 CSV、SVG、校验摘要和浏览器检查过的 `waveform.png`。
- 实验箱9 曾报告下载后唤醒失败，未计为应用测试；换箱5后完成上述测试，串口已关闭、设备已释放。

复核第二组使用 `scope_decode.py build/hardware/scope-box5-aa.uart --output build/hardware/scope-box5-aa --expect-uart aa`，第一组将 aa 换为 55。当前证据是两次独立采集，不代表长期稳定性测试、精密时序仪器或 PDS ILA 已验收。
