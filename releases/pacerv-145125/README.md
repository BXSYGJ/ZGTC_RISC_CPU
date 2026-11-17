# PaceRV 145.125 MHz 五版本交付

推荐使用 **H4 Loop16 SelectiveLoad MemoryRange（6621 LUT）**：V0/V1 CoreMark/MHz 均超过 3.5，实际 PDS 布局布线的全部十类内部时序检查通过。五个归档包含对应 RTL 源码、V0 位流、V0/V1 固件、编译与运行回执、布局布线报告和修改/回滚证据。解压即可浏览对应版本的完整文件；复现构建使用包内 README 记录的原工作区路径。

| 版本 | V0 CoreMark/MHz | V1 CoreMark/MHz | Slow setup | LUT | FF | DRM36K | APM | GPLL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [H4 MemoryRange 6621 LUT 推荐使用](PaceRV_H4_Loop16_SelectiveLoad_MemoryRange_145125_LUT6621_Verified.zip) | 3.503527129 | 3.501428774 | +0.043 ns | 6621 | 2557 | 25 | 4 | 1 |
| [H4 Loop16 SelectiveLoad 原基线](PaceRV_H4_Loop16_SelectiveLoad_145125_Verified_r2.zip) | 3.503527129 | 3.501428774 | +0.008 ns | 6812 | 2813 | 25 | 4 | 1 |
| [H6 LoadALU 最高分](PaceRV_H6_LoadALU_145125_Experimental.zip) | 3.511833433 | 3.510807712 | -0.218 ns | 7255 | 2541 | 25 | 4 | 1 |
| [H6 SelectiveLoad 实验版本](PaceRV_H6_SelectiveLoad_145125_Experimental.zip) | 3.511364165 | 3.509956797 | -0.044 ns | 7125 | 2541 | 25 | 4 | 1 |
| [Loop16 时序通过](PaceRV_Loop16_145125_Verified.zip) | 3.484719042 | 3.480411318 | +0.030 ns | 6547 | 2813 | 25 | 4 | 1 |

器件 PG2L200H-6FBB676，CPU 配置频率 145.125 MHz，参考时钟 27 MHz，setup uncertainty 0.150 ns，指令集 RV32IMC。表中 LUT/FF 为各自实际布局布线资源。每版的 V0/V1 均实际运行 6000 次，计时超过 10 秒且 CRC 通过；成绩来自实际 RTL 仿真。MemoryRange、原 H4 与原 Loop16 的十类时序检查全部通过；两个 H6 包保留实验时序失败状态。新位流的板上烧录和 UART 采集待完成。

H4 将 16 项循环预测表与 4 位历史预测器结合，并保留 SelectiveLoad 对合法 ADD/ADDI、XOR/XORI 的加载响应旁路及 8 位分组 carry-select 加法器。正式 V0/V1 运行使用与位流相同的 17 份公共 RTL；V0 位流绑定包内 V0 固件，包内同时保留 V1 测试固件和运行记录。

H6 SelectiveLoad 与 H6 LoadALU 最高分版本相比，V0 成绩相差约 0.0134%，slow setup 改善 0.174 ns。原三份 ZIP 保持原始字节与 SHA256。


最新 MemoryRange 版本保留同样的 SelectiveLoad 功能、145.125 MHz 频率和两组正式 6000 次成绩；相对原 H4 减少 **191 LUT（2.80%）和 256 FF（9.10%）**，slow setup 余量从 +0.008 ns 提高到 **+0.043 ns**。更新包括 BTB 单写口归并、循环状态 RAM 表示、内存范围比较和 LUT packing strategy 1（seed 2）。包内附实际 17/18 份 RTL 绑定、完整长测日志、原始 PDS 报告、修改与回滚记录。

新增包严格核验：`python verify_package_sg30.py --zip PaceRV_H4_Loop16_SelectiveLoad_MemoryRange_145125_LUT6621_Verified.zip`。该命令重新计算包内文件哈希、正式周期数与成绩，核对源码、固件、位流、十类原始时序数据及实际资源。

## 文件与核验

- [verify_package_sg30.py](verify_package_sg30.py)：最新 6621 LUT 归档的自包含严格校验器，核验 536 项清单和完整资格证据。
- [SG30 资格核验](evidence/SG30_QUALIFICATION.json)与[独立审计](evidence/SG30_INDEPENDENT_AUDIT.json)。
- [SHA256SUMS.txt](SHA256SUMS.txt)：五份 ZIP 的 SHA256。
- [Verify-Archives.ps1](Verify-Archives.ps1)：使用 PowerShell 7 核对 ZIP 哈希、每个 MANIFEST 文件的大小和 SHA256，以及完整文件清单；也支持指定远端提交复核。
- [verify_package_h4.py](verify_package_h4.py)：H4 严格自校验入口，与同目录 [closure_proofs_h4.py](closure_proofs_h4.py)、[h4_proof.py](h4_proof.py) 一起使用，核对两组正式成绩、源文件绑定、位流及时序和功能验证证据。
- [verify_package.py](verify_package.py)：原 H6 SelectiveLoad 自校验入口。
- [UPLOAD_VERIFICATION_H4.json](UPLOAD_VERIFICATION_H4.json)：新版 H4 归档重新打开后的校验回执；[H4 资格核验](evidence/H4_QUALIFICATION.json)记录正式成绩、资源、RTL 绑定及十项时序结果。
- [UPLOAD_VERIFICATION.json](UPLOAD_VERIFICATION.json)：原三版上传前 ZIP CRC、清单文件哈希、固件及位流核验结果。
- [evidence/FINAL_AUDIT.md](evidence/FINAL_AUDIT.md) 与 [evidence/FINAL_AUDIT.json](evidence/FINAL_AUDIT.json)：原 H6 SelectiveLoad 的独立审计结果，含周期、CRC、RTL 绑定与时序状态。
- [RESULTS.md](RESULTS.md) 与 [FINAL_STATE.json](FINAL_STATE.json)：当前五版交付报告和状态快照；五版的对应源码、证据和资格状态以本页及各归档 MANIFEST.json 为准。

在此目录打开 PowerShell 7，可执行以下命令核验五版，再对最新 MemoryRange 做完整自校验：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
try {
    $releaseRoot = (Get-Location).Path
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($releaseRoot, 'Verify-Archives.ps1'))
    if ($LASTEXITCODE -ne 0) { throw 'Archive verification failed' }
    & python ([System.IO.Path]::Combine($releaseRoot, 'verify_package_sg30.py')) --zip ([System.IO.Path]::Combine($releaseRoot, 'PaceRV_H4_Loop16_SelectiveLoad_MemoryRange_145125_LUT6621_Verified.zip'))
    if ($LASTEXITCODE -ne 0) { throw 'MemoryRange package verification failed' }
} catch { Write-Error $_; exit 1 }
```

原三份归档各自的 MANIFEST.json 记录全部文件的大小和 SHA256：LoadALU 160 项、H6 SelectiveLoad 297 项、Loop16 160 项。LoadALU 和原 Loop16 的文件位于 ZIP 根目录，H6 SelectiveLoad 包含一层同名根目录；通用 PowerShell 校验器会读取各包实际根目录。H4 的完整文件清单和证明链由其 MANIFEST.json 与严格自校验器共同核验。

对原 H6 SelectiveLoad 包，还可执行 `python verify_package.py --zip PaceRV_H6_SelectiveLoad_145125_Experimental.zip`。其余旧包的逐项清单核验使用 `pwsh -NoProfile -File ./Verify-Archives.ps1`。
