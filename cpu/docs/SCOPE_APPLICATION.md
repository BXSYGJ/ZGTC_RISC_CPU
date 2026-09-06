# CPU GPIO 波形采集应用

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
