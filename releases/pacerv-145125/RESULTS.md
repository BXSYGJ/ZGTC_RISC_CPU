# PaceRV 本轮优化结果

本轮已沿用户允许的 PaceRV 路线完成源码优化、6000 次 RTL 长测、实际 PDS 布局布线、回滚验证和交付归档。最高分配置的性能组为 **3.511833433 CoreMark/MHz**，验证组为 **3.510807712 CoreMark/MHz**。新增选择性加载旁路版本为 **3.511364165 CoreMark/MHz**，145.125 MHz 配置下的 slow setup 改善至 **−0.044 ns**。通过全部时序检查的版本为 **3.484719042 CoreMark/MHz、145.125 MHz**。

建议后续以新增选择性旁路版本继续集成：它相对最高分版本的 V0 成绩下降约 0.0134%，最差 setup 违例缩小 0.174 ns。三个版本各自保留源码、固件、位流及验证记录。下表成绩来自实际 RTL 仿真，频率为物理实现配置值；新增位流的板上烧录与 UART 采集待完成。

## 原始 3.51 工作

论文为 Yiyang Chang 等人的 *Design of a Configurable Five-Stage Pipeline Processor Core Based on RV32IM*，Electronics 2024, 13(1), 120，DOI：https://doi.org/10.3390/electronics13010120 。正文表 2 报告 3.51 CoreMark/MHz，正文报告 Artix-7 原型 200 MHz。公开材料缺少对应 RTL 获取链接、固定源码版本和完整 CoreMark 编译及计时输入。本地保留了单发射公开 RV32IM 的机制重建、实测日志和 145.125 MHz 时序通过的实现；本轮主交付采用用户允许的 PaceRV 优化路线。

论文 PDF 已下载、解析、导入 Zotero，并在本轮再次核验：用户指定下载文献 / 计算机体系结构 / RISC-V FPGA软核；父条目 24QQ4VA2，附件 GL6DBBET，pending=0。原始资料核验见 ../source_research/paper351/SOURCE_VERIFICATION.md，本轮回执见 evidence/PAPER351_CURRENT_RECEIPTS.json。

PaceRV 保留现有 **RV32IMC** 配置；原论文配置为 RV32IM。目标数值用于本项目性能优化参照。

## 6000 次长测

| 配置 | 性能组 V0 cycles | V0 CoreMark/MHz | 验证组 V1 CoreMark/MHz | 名义频率 | V0 实际 slow setup |
|---|---:|---:|---:|---:|---:|
| 冻结 H3 基线 | 1,743,134,699 | 3.442074788 | 3.436119415 | 145.125 MHz | 历史归档 +0.016 ns |
| ID 相等分支提前处理 + Loop16 + noif | 1,721,803,086 | 3.484719042 | 3.480411318 | 145.125 MHz | **+0.030 ns，全部十类检查通过** |
| ID 相等分支 + H6 + load ALU + noif/nocross | 1,708,509,277 | **3.511833433** | **3.510807712** | 145.125 MHz | **−0.218 ns，实验版** |
| ID 相等分支 + H6 + 选择性 load ADD/XOR + tune5 | 1,708,737,607 | **3.511364165** | **3.509956797** | 145.125 MHz | **−0.044 ns，实验版** |

高分 V0 相对冻结 H3 基线增加 2.026645%，减少 34,625,422 cycles。V1 为 1,709,008,437 cycles，相对其基线增加 2.173623%。两组计时区间分别为 11.772673743 秒和 11.776113261 秒，均通过标准算法和最终 CRC：

- V0：e714 / 1fd7 / 8e3a / a14c。
- V1：e3c1 / 0747 / 8d84 / 18e1。

成绩公式采用原子计数器快照 `CoreMark/MHz = iterations × 1000000 / cycles`。V0 在 145.125 MHz 对应 509.654827001563 CoreMark。继承端口的 UART 使用整秒除法，打印的 Iterations/Sec 545 保留在原始日志；交付成绩采用完整周期计算。

新增选择性旁路 V0 相对冻结 H3 提高 2.013012%，减少 34,397,092 cycles；V1 为 1,709,422,750 cycles。两组计时分别为 11.774247077 秒和 11.778968131 秒，算法及最终 CRC 与上列对应种子组一致，UART 和观察器原子计数一致，退出状态均为 0。V0 达到 3.51 目标；V1 距该值为 0.000043203 CoreMark/MHz。选择性旁路 V0 在配置频率下对应 509.586724394 CoreMark。

## 修改机制

1. ID 级提前处理的 BEQ/BNE 从包含 x0 的比较扩展到两个普通寄存器。EX/MEM 写后读依赖、WB 旁路、异常和有效位条件保留。
2. H6 把预测器的运行历史状态宽度扩展到 6 位。短测中独立比较过 H4/H5/H6/H7 和 Loop16/Loop64；H6 的综合收益最好，H6 与 Loop16 叠加收益很小。
3. 普通整数 ALU 消费 load 结果时使用专门的内存响应 ALU 路径，覆盖合法 R/I 整数运算。保留 MUL/DIV、CSR、存储及异常的原有互锁。在同固件 100 次对照中，这一步减少 75,803 cycles。
4. GCC 10.2.0 在已有 O3、unroll 基础上统一加入 `-fno-if-conversion -fno-if-conversion2 -fno-crossjumping`。CoreMark 算法、数据大小、种子和计时区间均使用保存的项目输入。
5. 新增选择性版本把 `load_use_wait` 的豁免收敛到合法 **ADD/ADDI、XOR/XORI**，在 `execute_result` 选择专用加载响应结果。加法采用 8 位分组 carry-select，XOR 使用独立组合路径，其余运算保留原有等待。同 100 次固件对比 H6 原始互锁减少 64,595 cycles，退休指令数保持 27,236,534；该版本编译参数加入 `-mtune=sifive-5-series`。

Loop16 的编译器单独筛选最高为 3.489624544 CoreMark/MHz（100 次短测）。缓存命中控制扇出与前端范围判断也完成等价和实际物理对照；最终选中的选择性旁路 seed3 数据更好，源码保持原始缓存和前端版本。各提案记录保存在 rtl_proposals 与 compiler_followup_20261117。

## 实际物理实现

全部构建保留 PG2L200H-6FBB676、27 MHz 参考时钟、145.125 MHz CPU 配置、0.150 ns setup uncertainty 和板载 UART C24 约束。完整 load ALU 高分配置的 seed1/seed2 分别为 −0.218 / −0.240 ns。控制扇出复制、LUT4 比较器、EX/FETCH 提示、布局疏散、LUT packing 和 PDS 自适应复制均保存实际对照结果。

新增选择性旁路比较 8 个 seed，slow setup 分别为 −0.234、−0.135、−0.044、−0.056、−0.150、−0.116、−0.194、−0.125 ns。选中 seed3 的 TNS 为 −0.086 ns、3 个失败端点，其余九类时序检查通过。该包保留 `experimental_timing_failed` 状态。资源为 **7125 LUT、2541 FF、25 DRM36K、4 APM、1 GPLL**；位流 SHA256 为 `418632AB9C52A72BC42EC6BA140C78BD54EFB335BE9B6784F4356ED07CC172B3`。

高分最佳位流使用 7255 LUT、2541 FF、25 DRM36K、4 APM、1 GPLL，SHA256：`FC32CB8C01917DD48186B0C453C5C3227BC86DAA699EAAB444999045B26B0572`。

通过时序的 Loop16 位流使用 6547 LUT、2813 FF、25 DRM36K、4 APM、1 GPLL；slow setup +0.030 ns、slow hold +0.143 ns、fast setup +2.759 ns、fast hold +0.100 ns；其余 recovery/removal/pulse 检查通过。SHA256：`788038990564CE1CDF007E072B086CC897149D7D5FA0119B67A7AB0A05D2AC94`。

新增配置的验证已覆盖真实 RTL 长测和实际 PDS 布局布线。新增位流的板上烧录和 UART 成绩采集仍待完成。位流名义频率、静态时序状态与板上测量状态分别记录在 manifest。

## 交付文件

- `optimized_releases/PaceRV_H6_LoadALU_145125_Experimental/`：高分实验版，V0 位流、V0/V1 固件、17 个公共 RTL 的准确快照、编译命令、完整日志、时序报告、验证和回滚证据。manifest 明确标记 `experimental_timing_failed`。
- `optimized_releases/PaceRV_Loop16_145125_Verified/`：通过时序版本，V0 位流、两组长测固件及完整对应证据。
- `optimized_releases/PaceRV_H6_SelectiveLoad_145125_Experimental/`：新增选择性旁路版本，推荐作为后续集成起点，含 V0 位流、V0/V1 固件、准确 RTL、编译与长测回执、完整时序报告、证明及回滚证据。

两份已有包各核验 160 个 manifest 文件；新增包核验 **297 个文件**，文件夹和 ZIP 均由独立 verifier 重新打开核验，0 哈希错误、0 未列入文件。包内 17/17 个公共物理和仿真 RTL 文件逐字节相同。每个包带有 V1 固件，位流对应 V0。完整复现脚本使用原工作区路径，包内 README 记录调用方式。

新增主修改字段为 `load_use_wait` 的 ADD/ADDI/XOR/XORI 豁免及 `execute_result` 的专用加载响应结果选择，对应四个文件：

- MODIFIED_FILE：[rv32_core.sv](rtl_proposals/load_simple/rv32_core.sv)
- DIFF_FILE：[DIFF_FILE.diff](rtl_proposals/load_simple/DIFF_FILE.diff)
- VERIFICATION：[VERIFICATION.txt](rtl_proposals/load_simple/VERIFICATION.txt)
- ROLLBACK：[ROLLBACK.sh](rtl_proposals/load_simple/ROLLBACK.sh)，内容为 PowerShell 7，另有同内容的 ROLLBACK.ps1。

父版 SHA256 为 `0E59ABBAA86A691F60317D51E9B07535A3CFCAA69685FC98FC3AE69CFADF2883`；新增修改版为 `5E81F9C56246E502B43C6A48C14342DBB16AC437788AC01D00A482D9A06CA84B`。独立副本回滚恢复父版哈希和原有互锁行为，活动修改版继续保留。完整 load ALU 的旧版修改和证据保存在 rtl_proposals/id_equal_load_alu。

## 主修改验证命令

共同输入为 `rtl_proposals/load_simple/core_token_tb.sv` 的 23 个独立 ISA、内存等待、旁路和异常场景；完整编译命令及原样日志已存 VERIFICATION.txt。以下命令分别运行 BASELINE、MODIFIED 和 ROLLBACK，编译源分别为 BASELINE_FILE.sv、rv32_core.sv 和独立回滚副本 rollback_test.sv：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
try {
    $proposal = '/mnt/d/AAAFPGA/ZGTC_RISC_CPU/pds_minimal_blink_200h/pacerv_h3_optimization/rtl_proposals/load_simple'
    foreach ($image in 'baseline.vvp','modified.vvp','rollback.vvp') {
        & wsl.exe -d Ubuntu-22.04 --cd $proposal --exec vvp $image
        if ($LASTEXITCODE -ne 0) { throw ('Directed test failed: ' + $image) }
    }
} catch { Write-Error $_; exit 1 }
```

BASELINE、MODIFIED、ROLLBACK 三组字面结束输出均为 `CORE_TOKEN_PASS early=1 mode=1 scenarios=23`，退出状态均为 0，595 行退休/异常轨迹一致。回滚动作字面输出为 `LOAD_SIMPLE_ROLLBACK_PASS SHA256=0E59ABBAA86A691F60317D51E9B07535A3CFCAA69685FC98FC3AE69CFADF2883`，退出 0。精确回滚命令、输入与字面输出见 VERIFICATION.txt 的 ROLLBACK_SH_RESULT。

新增选择性路径通过 SAT 全部 65 位二进制算术输入证明；译码证明覆盖全部 2^32 指令字，精确选择合法 ADD/ADDI/XOR/XORI。负向控制成功检出删除旁路与误扩展完整 ALU 的改变。此前 LUT4 对照的等价和周期记录继续保存，各最终包采用实际选中功能 RTL 的直接哈希绑定。

## 交付复核

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $paceRoot = [System.IO.Path]::Combine('D:/AAAFPGA','ZGTC_RISC_CPU','pds_minimal_blink_200h','pacerv_h3_optimization')
    & python.exe ([System.IO.Path]::Combine($paceRoot,'scripts','verify_delivery.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Delivery verification failed' }
} catch { Write-Error $_; exit 1 }
```

本轮字面输出：

```text
DELIVERY_PASS PaceRV_H6_LoadALU_145125_Experimental files=160 timing_pass=False
DELIVERY_PASS PaceRV_Loop16_145125_Verified files=160 timing_pass=True
FROZEN_BASELINE_PASS files=182
```

退出状态为 0。原始 H3 的 182 个冻结文件全部保留原哈希。独立审计见 `evidence/FINAL_INDEPENDENT_AUDIT.md` 和 `evidence/FINAL_INDEPENDENT_AUDIT.json`。

三份经过逐项哈希复核的 ZIP 已生成：

- 高分实验版：`optimized_releases/PaceRV_H6_LoadALU_145125_Experimental.zip`，SHA256 `3B86503BF0A5EBC53B4BADA6D0BFF3D9928792C33816102668DD014FA33BB8BE`。
- 时序通过版：`optimized_releases/PaceRV_Loop16_145125_Verified.zip`，SHA256 `FD144BEF0D634246A9824BF259BF6FA6AEBBE4C272936A4157D1BB110DD03228`。
- 新增选择性旁路版：[PaceRV_H6_SelectiveLoad_145125_Experimental.zip](optimized_releases/PaceRV_H6_SelectiveLoad_145125_Experimental.zip)，SHA256 `6B5F0A7448662B0E440FB04B65F13B33566B2798FF5278D6A389321C5B75BDA2`，1,692,100 bytes。

两个已有 ZIP 保留原哈希，逐项验证各自 160 个 manifest 文件；证据见 evidence/ARCHIVE_VERIFICATION.json。新增 ZIP 重新打开验证 297 项文件，证据见 evidence/continuation_20261117/final_audit/FINAL_AUDIT.json。

最终物理索引：**27 个完整构建，其中 3 个通过全部时序检查**；另有 6 份 prepare/synthesis 测试记录。最终审计补查新增 11 个物理构建的输入、报告和位流哈希，活动 Windows PDS 与 WSL 原生基准测试进程均为 0。

最终独立审计命令为在工作区执行 `python.exe evidence/continuation_20261117/final_audit/audit.py`。输入为冻结清单、V0/V1 RUN/BUILD/UART 回执、全部新增物理构建回执及其输入/报告/位流、旧 ZIP 回执与新交付包。实际字面输出如下，退出状态为 0：

```text
FINAL_AUDIT_PASS frozen=182 simulations=2 new_physical=11 common_rtl=17 old_archives=2 active_windows=0 active_native=0 package_checks=2
FORMAL V0 cycles=1708737607 CM/MHz=3.511364164644 seconds=11.774247077 CRC=0xe714/0x1fd7/0x8e3a/0xa14c
FORMAL V1 cycles=1709422750 CM/MHz=3.509956796819 seconds=11.778968131 CRC=0xe3c1/0x0747/0x8d84/0x18e1
REOPENED FINAL_AUDIT.json FINAL_AUDIT.md
```

证据见 [FINAL_AUDIT.md](evidence/continuation_20261117/final_audit/FINAL_AUDIT.md) 和 [FINAL_AUDIT.json](evidence/continuation_20261117/final_audit/FINAL_AUDIT.json)。新增包文件夹和 ZIP 均独立通过 297 项文件核验，保留 `timing_pass: false` 的实际状态。
