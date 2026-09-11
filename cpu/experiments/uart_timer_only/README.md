# UART / timer-only comparison candidate

This is the reduced-peripheral comparison, not a replacement for the competition's complete GPIO/UART system. Target frequency remains **157.5 MHz**. Lower-frequency NoMmioPeripherals builds are diagnostic results and cannot satisfy the non-regression requirement.

## Hardware boundary

- CPU, cache, branch predictor, RAM and PLL originate from the source-checked regfile-valid-fanout stage.
- UART RX/TX, FIFOs, UART interrupts, timer/comparator, software interrupt, status and performance snapshots remain.
- GPIO input synchronization, output registers, enable/pending registers and GPIO interrupts are removed. Reads and writes at all four GPIO addresses return a bus error. The unused external GPIO ports remain for interface compatibility; output is constant zero.
- CoreMark's three out-of-timing GPIO marker writes are redirected to the existing status register. Timed algorithm code and timing hooks are unchanged at source level. Cycle equality is a test requirement, not an assumption; code layout may still affect caches and prediction.
- No ILA is included in this candidate. The full GPIO/UART plus compact-ILA baseline remains separate.

## Reproduce

From PowerShell 7, run `pwsh -NoProfile -File cpu/experiments/uart_timer_only/prepare_stage.ps1`. It creates a unique stage under `cpu/build/uart-timer-only` and saves SHA-256 hashes of the copied sources.

Run `test_uart_timer_only.py` using Python in WSL (Icarus/VVP required). The test contains 39 MMIO transactions, UART RX interrupt and TX waveform comparison, timer/software interrupt comparison, snapshot reads, byte strobes, response backpressure and GPIO-address errors. Three mutations check that output leakage, GPIO interrupt leakage and an incorrectly accepted GPIO register are rejected.

Build both performance and validation firmware using the staged `scripts/build_coremark.ps1` with `-ClockHz 157500000 -EnableM 1 -Optimization O3 -UnrollLoops -LinkerRelaxation -ConsoleDelayCycles 0`. Use `-Iterations 10` only for short CRC/cycle screening. The accepted reference short cycles are 3151519 / 3156276. Full 6000-iteration runs, matched physical implementation, and remote UART evidence are required before reporting an accepted score.

## Evidence boundary

The initial stage is `build/uart-timer-only/20260909-201805-7ed77aa1`. The first short-run attempt used a 2700000-cycle console delay and exceeded its 15000000-cycle watchdog while printing; that failure is retained and does not prove anything about CoreMark CRC or performance. Screening repeats with the reference's zero console delay and 50000000-cycle limit.

At creation, peripheral protocol tests pass. PDS, complete performance/validation runs and board testing remain unproven. Never combine another firmware's score or clock with this candidate's LUT count.

## 长测发现与公平对照修正

十轮两种种子结果与基线完全一致；短测通过不能证明6000轮无退化。首个零串口延时6000轮性能运行 `build/compiled/20260909-202729-77614301` 为1887570281周期，较已接受的1885980108周期多1590173（约0.084315%），I-cache事件相同，D-cache缺失从96027增加到204032。因此零延时长测候选不能作为非退化替换。

ELF核对显示零延时版本的 `static_memblk` 在0x7098，接受基线在0x70f8；恢复相同的 `ConsoleDelayCycles=2700000` 后回到0x70f8。匹配编译配置的性能二进制与基线同为28916字节，仅0x5b63、0x5ca3、0x5cfb三个字节不同（区间外标记写入的地址立即数）。匹配配置性能长测已完成：6000轮、1885980108周期、CRC e9f5/a14c，与完整GPIO/UART性能基线逐周期一致；证据目录为 `build/compiled/20260909-204747-d308d2fc`。验证种子仍在运行，不能用单种子结果替代双种子、PDS或实板证明。

`run_matched_full_pair.ps1 -StageName <目录名>` 使用基线相同的2700000串口延时编译参数，保存独立的 `runtime-matched-v0/v1-configuration.json`。这个延时位于计时区间外，但会影响代码/数据布局，因此不能在跨版本比较时忽略。

`run_pds.ps1` 默认也使用该完整配置，零延时物理试验须显式指定 `-ConsoleDelayCycles 0`。`audit_full_pair.py` 按同一延时参数、固件哈希、RTL和真实物理报告绑定双种子完整运行；输出按延时参数分文件，不混写、不标成实板证明。

零延时布局种子2物理结果：157.5 MHz，9004 LUT，WNS -0.085 ns；种子3为8986 LUT，WNS -0.252 ns，均拒绝。零延时验证种子的6000轮结果也已结束，为1890603705周期，高于参考1888935654周期。完整证据保留在stage/zero-delay-rejection.json，不将这些结果标为已接受的新版本。
