# CoreMark 1.0 移植与证据规则

## 源码与构建

上游为 EEMBC CoreMark，仓库 `https://github.com/eembc/coremark.git`，固定提交 `1f483d5b8316753a742cbf5590caf5bd0a4e4777`。下载到被忽略的 `build/coremark-upstream`，保留上游 Apache-2.0 许可证和所有原文件。构建脚本拒绝错误 revision 或任何工作区改动；未修改五个计分 C 源文件和 coremark.h。自有移植位于 `sw/coremark/`。

使用 RV32I/ILP32、GCC 10.2.0、O2，所有 C 源文件同一组编译选项，关闭 LTO/PGO，volatile 种子，单上下文，静态 2000 字节数据集。CoreMark 输出 Size=666 是每算法分配尺寸，不是把标准数据集缩为 666 字节。编译命令与镜像 SHA 记录在 `build/<run-name>.build.json`。

```powershell
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ValidationRun
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ConsoleDelayCycles 32
pwsh -NoProfile -File cpu/scripts/build_coremark.ps1 -Iterations 200 -ConsoleDelayCycles 400000
pwsh -NoProfile -File cpu/scripts/build_coremark.ps1 -Iterations 200 -ConsoleDelayCycles 400000 -ValidationRun
```

每次实板实现把对应 hex 传给 `run_pds.ps1 -UartProfile RemoteLab -FirmwareHex <绝对路径>`。镜像必须恰为 16384 个 8 位十六进制字，不允许短文件尾部留下未初始化 RAM。PDS 会复制固件快照，之后其他软件构建不会改变正在实现的位流。

## 运行与采集

下载成功且唤醒后，打开 115200 8N1 串口。发送 ASCII G（HEX 模式为 47）启动，串口命令等待和报告输出均不在计时区。STATUS=C0100000 表示待启动；C0100001 表示运行结束，不等于 CRC 验证通过。若陷入异常则打印 ZGTC TRAP 并停机。

远程页面当前每 500 ms 读取 64 字节。首次未限速输出的长报告出现字节丢失，仅保留缺损证据 `build/hardware/coremark-v0-unpaced-incomplete.txt`，不得用它恢复、补猜 CRC 或计分。板用构建设置 ConsoleDelayCycles=400000，使报告每个字符之间等待约 14.8 ms；软件 UART 仍为 115200，限速只发生在 ee_printf 中，不改变计分算法。仿真使用 0 或 32 周期避免无意义的长等待。

计时读 mcycleh/mcycle/mcycleh 重试形成 64 位周期数，避免 RV32 低字进位撕裂。get_time 返回毫秒，CoreMark 的整数时间与迭代率按原程序输出；另输出完整 64 位 cycles_hex、retired_hex 和 clock_hz，主机按周期数计算精确比率。退休计数含两端读取例程的小额开销，不冒充精确无开销 CPI。

## 验证规则

`scripts/check_coremark.py` 检查模式、迭代数、2000 字节选项、四个标准 CRC、周期/毫秒一致性、无陷入及正常结束。默认拒绝不足 10 秒的运行；只有显式 --allow-short 才接受短时 CRC 调试，并且不输出成绩字段。十项单元测试包含 CRC、计时、频率、迭代数、异常和重复记录等变异。

性能种子 0/0/66 的 seed/list/matrix/state CRC 为 e9f5/e714/1fd7/8e3a；验证种子 3415/3415/66 对应 18f2/e3c1/0747/8d84，均来自固定上游 core_main.c。crcfinal 随迭代数变化，不能机械套用单次值。

两组单次仿真均通过算法 CRC：性能 2,763,553 周期、验证 2,939,899 周期；约 0.102/0.109 秒，不构成正式成绩。正式验收需要两组种子完整硬件记录、至少 10 秒有效计时、CRC 全通过，并绑定对应位流身份、真实工作频率、LUT 资源报告。只做完一组不能宣告整个 CoreMark 验收完成。

主机计算：iterations_per_second = iterations × clock_hz / cycles；CoreMark/MHz = iterations × 10^6 / cycles；每 LUT 性能 = iterations_per_second / 本次实现实际 LUT 数。工具估算 Fmax 与实际 27 MHz 不混用，也不声称已经向 EEMBC 提交或获得认证。
