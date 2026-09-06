# 真正的 RV32 GNU 裸机工具链

赛题指定 `riscv32-unknown-elf-gcc`。工程现在从固定 GNU 源码构建该目标，不再使用 RV64 multilib 编译器或同名包装脚本冒充它。保留系统原有 RV64 工具，旧硬件记录不改写。

## 构建与调用

宿主为 Windows PowerShell 7，构建在 WSL Ubuntu-22.04 的普通用户家目录中完成。依赖为本机 gcc/g++、make、tar、bison、flex、texinfo、libgmp-dev、libmpfr-dev、libmpc-dev、zlib1g-dev。依赖缺失时先安装；脚本本身不自动提权或升级系统。

```powershell
wsl.exe --distribution Ubuntu-22.04 --user root --exec /usr/bin/apt-get install -y --no-install-recommends build-essential bison flex texinfo libgmp-dev libmpfr-dev libmpc-dev zlib1g-dev
pwsh -NoProfile -File cpu/scripts/build_riscv32_toolchain.ps1 -Jobs 8
pwsh -NoProfile -File cpu/scripts/validate.ps1
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ClockHz 90000000
pwsh -NoProfile -File cpu/scripts/run_coremark_test.ps1 -ClockHz 90000000 -ValidationRun
pwsh -NoProfile -File cpu/scripts/run_scope_tests.ps1
```

默认安装位置是当前 WSL 用户家目录的 `.local/zgtc-riscv32-10.2.0`。成功后写入本机 `cpu/build/riscv32-toolchain.json`；其他构建脚本经 `riscv_toolchain.ps1` 读取该清单，并现场核对编译器目标及版本，不依赖 Windows PATH，也不回退到 RV64 编译器。安装目录已存在时主动拒绝覆盖；重建请指定家目录内另一个 ASCII `-InstallRoot`。中途失败应先看该阶段日志，不能把部分安装当作成功。

## 来源、配置与范围

- GCC 10.2.0 与 Binutils 2.35 从 GNU 官方 HTTPS 发布目录获取，归档及 SHA-512 固定于 `scripts/toolchain_sources.json`，每次构建均重新核验归档内容。
- 首次引入时，GCC SHA-512 对照 GNU `sha512.sum`；Binutils 原始签名经 GNU keyring 的 `gpgv` 校验为 Good signature，签名指纹为 `3A24BC1E8FB409FA9F14371813FCEF89DD9E3C4F`。构建脚本执行固定哈希校验，不声称每次重新执行签名校验。
- GCC 配置为 `--target=riscv32-unknown-elf --with-arch=rv32i --with-abi=ilp32 --disable-multilib --enable-languages=c`，链接自身构建的 RV32 Binutils。保留 10.2.0 是为了与已测固件一致，不声称它是最新版。
- 构建 C 编译器及静态 `libgcc.a`，没有安装 newlib、操作系统、宿主标准库或 C++ 运行时。工程提供裸机启动、链接脚本与打印函数；不能据此承诺普通 hosted C 的 `malloc`、文件系统或完整标准库可用。
- 第三方工具与源码留在 WSL 安装/缓存及忽略的构建目录，不并入工程自有 RTL，也不更改其上游许可。

## 本次实际验证

构建开始于 `2026-09-05T23:44:00Z`，结束于 `2026-09-05T23:52:17Z`，均为日志中的 UTC 时间。逐阶段日志在 `build/toolchain/20260906-074400-6d9d89d7/`，完成清单为该目录的 `installed.json`。目录名来自 Windows 本地时钟，不能与 UTC 时间直接比较日期。

已现场确认：

- `gcc -dumpmachine` 为 `riscv32-unknown-elf`，`-dumpfullversion` 为 `10.2.0`；as 为 GNU Binutils 2.35、同一 RV32 目标。
- 不传 `-march/-mabi` 时，预定义宏仍为 XLEN=32、指针 4 字节、软浮点 ABI，没有 M/A/C 或浮点扩展宏。
- 安装的 `libgcc.a` 对象为 `elf32-littleriscv`，未发现 ELF64 对象。实际 CoreMark ELF 为 ELF32、小端 RISC-V，属性 `rv32i2p0`。
- 新工具链完整 `validate.ps1` 通过，涵盖单元、CPU 差分、Cache/无 Cache、SoC 中断与维护错误、严格 Verilator lint，以及检查器变异测试。
- 90 MHz参数的两组单次 CoreMark 仿真 CRC 均通过，分别为 2733391 / 2910242 周期；短时运行不计分。波形应用仿真两次共 512 点、超时及空捕获路径、校验与波形解码全部通过。

现场探测结果保存为 `build/toolchain/rv32-verification.json`。新 CoreMark 和波形应用构建文件加 `_rv32gcc` 后缀，并在构建清单保存目标、版本和工具前缀，避免覆盖旧工具链产物。

90 MHz、400 次性能种子、输出延迟 1000000 周期的新 HEX，SHA-256 为 `86B46132E514A3752E13BCF2D386C67855FA3A154C8B22AA790063CD5732F208`，与已上板的旧工具链固件逐字节一致。这证明该镜像可以由真实 RV32 工具链重建，不将此前下载过程改写成“当时用了新工具链”，也不凭此推出其他参数镜像必然相同。具体硬件成绩和位流身份仍以 `HARDWARE_FREQUENCY.md` 为准。

相同频率、迭代数及输出延迟的验证种子 HEX 也逐字节一致，SHA-256 为 `0CFB038448E28B34E906FB602F502CDC545F3AA05C044A0ACFC8321A16A5B551`。两组对比的原路径、新路径及摘要均保存于 `rv32-verification.json`，没有替换历史硬件原始记录。
