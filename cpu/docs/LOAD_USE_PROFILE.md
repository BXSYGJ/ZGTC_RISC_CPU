# 加载依赖退休跟踪与选择性停顿依据

2026-09-07。本页是十轮RTL诊断，不是实板成绩、正式CoreMark成绩或物理极限证明。生产RTL、已发布120 MHz版本均未修改；没有GitHub上传。

## 边界与证据

新增的 experiments/load_use_profile/coremark_compiled.cpp 只读取既有trace_valid、trace_pc、trace_instruction、cycle_count端口，没有改变输入、时钟推进或eval调用。每条退休记录为小端16字节：64位周期、32位PC、32位指令。

scripts/run_load_use_profile.py 从每份ELF的start_time/stop_time反汇编提取唯一mcycle低位读取指令，校验ELF经objcopy生成的binary补零后与实际64 KiB固件逐字节相同。性能种子边界为0x5a70/0x5a8c；验证种子为0x5a78/0x5a94，不能混用。驱动SHA-256：54E439C391BEA141D0E1D87074AC614743B8A6B8D1838C976CDE63E73BB2D114。

四次观察运行的18项输入均已核验：相对各自原始运行只改变C++观察驱动；RTL、两个编译/判分脚本、固件、硬件参数不变。四次UART逐字节与各自原版相同，CRC、周期、退休指令和缓存统计相同。跟踪首尾周期差恰好等于UART测量周期，无经验偏移修正。

| 种子/模式 | 观察运行ID | 记录数 | 测量周期 |
| --- | --- | ---: | ---: |
| performance 原前递 | 20260907-184508-3da389b7 | 2748929 | 3199743 |
| performance 全停顿 | 20260907-185848-4d10b190 | 2748929 | 3394605 |
| validation 原前递 | 20260907-185902-dd357cec | 2749602 | 3206720 |
| validation 全停顿 | 20260907-185916-ec805e47 | 2749602 | 3406171 |

运行位于build/load-use-profile-stage/build/compiled。最终报告指针见build/load-use-profile-local-state.json。每种子两种模式的全部退休PC/指令序列相同；分别比较了2748928和2749601个相邻间隔。序列SHA-256分别为FC8008C0292D6F2CDCD890B4434BB0BE69863F4BB0A427FA67285BF0A50BE221、657B228592FBE668295B6128C8D7620D99302432866B3AC98B0DE05A601604C6。

跟踪记录数比UART retired少12：mcycle测量窗口与minstret快照窗口不是同一个括号。这里不把二者强行设为相等。

## 测得的周期差分类

下表把同一退休序列中“当前指令相对上一条退休指令的时间间隔差”按相邻加载寄存器依赖分类。它不是内部stall信号的逐拍计数，也不证明任一类可独立、线性地消除；负补偿项明确保留。

| 消费者类别 | performance间隔数 | performance周期差 | validation间隔数 | validation周期差 |
| --- | ---: | ---: | ---: | ---: |
| 条件分支比较 | 132120 | +132108 | 135820 | +135819 |
| 下一次load的地址 | 57440 | +57439 | 59310 | +59309 |
| 整数加减 | 2840 | +2839 | 2400 | +2399 |
| 整数移位 | 1113 | +1113 | 1142 | +1142 |
| 整数逻辑 | 960 | +959 | 440 | +439 |
| store数据 | 420 | +418 | 360 | +358 |
| 无相邻加载依赖 | 2554035 | -14 | 2550129 | -15 |
| 合计 | 2748928 | +194862 | 2749601 | +199451 |

完整逐PC分类与差值直方图保存在build/load-use-profile-performance.json和build/load-use-profile-validation.json。大头是加载后分支比较，约占性能种子额外周期的68%；不是乘除法或通用加法。0x4f0→0x4f4→0x4f8与0x850→0x854→0x858等链同时呈现指针加载和分支依赖。

因此下一候选采用“通用ALU保留加载停顿，分支比较器单独前递”，而不是对所有执行路径恢复同一个高扇出load数据选择器。已开始的具体候选见LOAD_USE_BRANCH_BYPASS.md；分类数值不替代该候选自己的仿真、时序或长运行。

## 检查与复现

- scripts/test_load_use_profile.py：11个方法，覆盖固件大小/字序、计时边界、RV32I/M源寄存器分类、非法指令、截断记录、非单调周期、PC/指令损坏、首尾错位、序列差异和负补偿求和。
- scripts/test_load_use_observer.py --build <观察构建>：12个实际编译驱动拒绝控制，覆盖缺失/非法/不对齐/相同边界、错误CSR、起止颠倒及未出现的起点。最终报告位于build/load-use-observer-negative/20260907-190402-1b3ecd58/report.json。
- scripts/run_load_use_profile.py --baseline <原运行> --firmware-manifest <十轮固件.build.json> [--existing-profile <观察运行>]：新运行或重新审计；拒绝不止观察驱动发生变化的输入。
- scripts/compare_load_use_profiles.py --baseline-report <原前递观察报告> --bubble-report <全停顿观察报告> --output <输出.json>：重新核验原版/观察版源、固件、ELF、UART、记录哈希，再比较完整序列与周期求和。

该观察器默认不加入正式硬件构建，也不进行6000轮全量记录，避免把仅诊断的巨大跟踪文件混入发布工程。

