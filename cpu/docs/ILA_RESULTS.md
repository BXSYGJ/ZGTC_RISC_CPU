# 实板 CoreMark 原生 JTAG ILA 分析

本页为旧27 MHz原型的历史结果；2026-09-06达标配置120 MHz插核版的独立证据见ILA_TARGET120.md，不将本页六个窗口复用为新配置覆盖。

## 证据范围

在 RemoteLab 实验箱5烧录插入 PDS DebugCore 的 CPU 位流，上传严格匹配的 FIC，通过网页“启动”捕获并“导出”原始 CSV。六次算法捕获的请求时间为 UTC 2026-09-05 22:10:15 至 22:10:27，来自同一次200迭代性能种子运行。它们不是仿真 VCD，也不是软件 GPIO 采样器输出。

实板使用的构建目录 `build/ila/prototype`；原始综合构建 `build/pds/20260906-053005-95ba4365`。固件 SHA-256 为 `65C44A3AAD525029A0BCF371A3C9C732C13202F2FF0E8576F73AB52926EA0E74`；插核位流 SHA-256 为 `6A597AE920C2A0E1FD439D0579FEBD938231026B4F47BF16F079CD44E89A9FE4`；FIC SHA-256 为 `8F617110B92B7BB6CC0F9469BFD1EFE091815030B955E2192D3655AAA9BFFCAE`。后续已固化 `scripts/run_ila_pds.ps1` 并成功自动重建，详见 `ILA_INTEGRATION.md`；重新生成的不同哈希产物尚未上板，不能冒用本节原型的实测证据。

- 算法原始数据：`build/hardware/ila-algorithm-0.csv` 至 `ila-algorithm-5.csv`，每份1024行、109位通道。
- 请求时间和实际页面文字：`build/hardware/ila-algorithm-captures.json`；网页截图 `ila-algorithm-5-ui.png`。
- 同固件 ELF 符号表：`build/hardware/ila-firmware-symbols.txt`，来自 `nm -S -n`。
- 分析结果：`build/hardware/ila-analysis/summary.json`、各窗口 decoded CSV、SVG；窗口4另有渲染检查后的 PNG。
- `ila-idle.csv` 是真实等待命令的空闲捕获；`ila-coremark-0.csv` 是初次操作错过算法区间后捕获的 printf。二者明确排除于关键算法分析。

## 通道与可信性检查

采样时钟是 CPU 的 `nt_clk`，实际27 MHz，上升沿采样。1024个周期槽宽37.9259微秒，首末采样边沿相距37.8889微秒。不是连续覆盖整段20秒运算。

| 通道 | 信号 |
| --- | --- |
| 0–31 / 32–63 / 64–95 | EX / ID / IF 的32位 PC，低位在前 |
| 96–100 | IF、ID、EX、MEM、WB valid；WB 对应实际 trace_valid |
| 101–102 | id_fire、ex_fire |
| 103–105 | mem_sent、mem_load、mem_flush（redirect） |
| 106–108 | I响应有效、D存储响应有效、I行填充命令有效 |

`scripts/ila_analyze.py` 严格拒绝缺列、缺行、乱序采样号和非二进制值，并检查 fire 时该级必须有效。对每窗口1023个相邻周期进一步检查：ID fire 后 EX valid 且 EX PC 等于前一拍 ID PC；EX fire 后 MEM valid。六份真实数据全部通过。符号地址来自同一固件 ELF，按函数实际大小映射；未知地址不猜测归属。

## 关键算法窗口

| 窗口 | WB有效周期 / 1024 | 局部退休率 | ID保持 | EX保持 | 已发出load等响应 | I命令有效周期 | EX fire时的函数分布 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 291 | 0.28418 | 0 | 0 | 4 | 0 | __mulsi3 258；matrix_mul_matrix_bitextract 34 |
| 1 | 293 | 0.28613 | 0 | 0 | 6 | 0 | crc16 278；core_bench_list 16 |
| 2 | 276 | 0.26953 | 0 | 0 | 8 | 0 | __mulsi3 213；matrix_mul_matrix_bitextract 62 |
| 3 | 293 | 0.28613 | 0 | 0 | 14 | 0 | __mulsi3 239；matrix_mul_matrix 54 |
| 4 | 199 | 0.19434 | 6 | 8 | 34 | 80 | core_state_transition 182；core_bench_state 17 |
| 5 | 298 | 0.29102 | 0 | 0 | 0 | 0 | crcu32 297 |

这里的保持指 valid 且没有 fire，不能无条件解释成数据冒险。load等待条件是 MEM valid、load、sent 且本拍无D响应；I命令有效可因后端背压保持多拍，80拍不等于80次 Cache miss。WB和EX计数允许因窗口边界尚在途指令略有不同。

矩阵窗口大量执行 `__mulsi3`，符合当前 RV32I 没有 M 扩展、乘法由软件例程实现的设计。状态机窗口4的局部退休率最低，同时有34拍load等待、80拍I命令有效以及ID/EX保持，支持把访存与取指等待作为此窗口的优化重点；不能仅凭相关性精确分摊每类周期损失。其他窗口几乎没有ID/EX保持但退休率仍低于0.3，说明检查前端空槽、取指握手及控制流恢复比只盯住依赖暂停更有价值；这只是局部证据，不代表完整算法各因素占比。

六窗口 redirect 分别25、24、33、25、18、22拍。该信号本身包含多种冲刷原因，不能直接命名为预测错误次数，更不能据此计算分支预测准确率。全程 IPC 应使用计时区 mcycle/minstret；此处只报告短窗口退休率。

## 插核开销与计分扰动

插核版实际使用5011 LUT、5342 FF、20 DRM36K等效块；未插核对应版本4087 LUT、3493 FF、16.5块。实际运行仍为27 MHz。插核后 setup WNS 22.654 ns、最差 hold 0.100 ns，报告 All Constraints Met；CPU估计最高频率69.5265 MHz只作为实现报告，不是实板最高频率。PDS同时自动加入20 MHz DebugCore_JCLK和10 MHz DebugCore_CAPTURE及时钟组约束，不能遗漏调试域。

插核版两次完整200迭代运行均通过性能种子 CRC：seed e9f5、list e714、matrix 1fd7、state 8e3a、final 382f。计时均为549984604周期，退休150505761条，与未插核对应版本的两次结果完全一致；第二次运行中实际执行了六次JTAG捕获。原始记录为 `build/hardware/coremark-ila-r1.uart`、`coremark-ila-r2.uart`，对应 JSON 均以实际5011 LUT重算。

20.369800秒、9.8184567 CoreMark、0.36364654 CoreMark/MHz；插核版0.00195938 CoreMark/LUT，未插核版0.00240236。只能说这两次运行未观测到周期计分扰动，不能说插核没有资源/时序开销，也不能将未插核LUT数用于插核成绩。

## 复现分析

在仓库根目录使用 PowerShell：

```powershell
python cpu/scripts/test_ila_analyze.py
$captures = Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($PWD.Path, 'cpu', 'build', 'hardware')) -Filter 'ila-algorithm-*.csv' | Sort-Object Name | Select-Object -ExpandProperty FullName
python cpu/scripts/ila_analyze.py @captures --symbols cpu/build/hardware/ila-firmware-symbols.txt --output cpu/build/hardware/ila-analysis
```

分析器单元测试5项已通过，真实六窗口通过同样的格式和时序校验。原始CSV及符号表仍是不可替代的输入；源代码不凭空生成实板证据。
