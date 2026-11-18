# PaceRV 145.125 MHz 六版本交付

推荐使用 **SG51 H4 Loop16 SelectiveLoad MuxLUT6D（6571 LUT）**。实际 PDS 布局布线通过全部十类内部时序检查，V0/V1 的 6000 次 RTL 仿真均超过 3.5 CoreMark/MHz。归档包含 RTL、V0 位流、两组固件、原始时序报告和验证证据；复现步骤见包内 README。SG51 位流尚未做板上测试。

| 版本 | V0 CoreMark/MHz | V1 CoreMark/MHz | Slow setup | LUT | FF | DRM36K | APM | GPLL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [SG51 MuxLUT6D 6571 LUT 推荐使用](PaceRV_H4_Loop16_SelectiveLoad_MuxLUT6D_145125_LUT6571_Verified.zip) | 3.503527129 | 3.501428774 | +0.099 ns | 6571 | 2557 | 25 | 4 | 1 |
| [H4 MemoryRange 6621 LUT](PaceRV_H4_Loop16_SelectiveLoad_MemoryRange_145125_LUT6621_Verified.zip) | 3.503527129 | 3.501428774 | +0.043 ns | 6621 | 2557 | 25 | 4 | 1 |
| [H4 Loop16 SelectiveLoad 原基线](PaceRV_H4_Loop16_SelectiveLoad_145125_Verified_r2.zip) | 3.503527129 | 3.501428774 | +0.008 ns | 6812 | 2813 | 25 | 4 | 1 |
| [H6 LoadALU 最高分](PaceRV_H6_LoadALU_145125_Experimental.zip) | 3.511833433 | 3.510807712 | -0.218 ns | 7255 | 2541 | 25 | 4 | 1 |
| [H6 SelectiveLoad 实验版本](PaceRV_H6_SelectiveLoad_145125_Experimental.zip) | 3.511364165 | 3.509956797 | -0.044 ns | 7125 | 2541 | 25 | 4 | 1 |
| [Loop16 时序通过](PaceRV_Loop16_145125_Verified.zip) | 3.484719042 | 3.480411318 | +0.030 ns | 6547 | 2813 | 25 | 4 | 1 |

器件 PG2L200H-6FBB676，CPU 配置频率 145.125 MHz，参考时钟 27 MHz，setup uncertainty 0.150 ns，指令集 RV32IMC。表中 LUT/FF 为各自实际布局布线资源。每版的 V0/V1 均实际运行 6000 次，计时超过 10 秒且 CRC 通过；成绩来自实际 RTL 仿真。MemoryRange、原 H4 与原 Loop16 的十类时序检查全部通过；两个 H6 包保留实验时序失败状态。新位流的板上烧录和 UART 采集待完成。

H4 将 16 项循环预测表与 4 位历史预测器结合，并保留 SelectiveLoad 对合法 ADD/ADDI、XOR/XORI 的加载响应旁路及 8 位分组 carry-select 加法器。正式 V0/V1 运行使用与位流相同的 17 份公共 RTL；V0 位流绑定包内 V0 固件，包内同时保留 V1 测试固件和运行记录。

H6 SelectiveLoad 与 H6 LoadALU 最高分版本相比，V0 成绩相差约 0.0134%，slow setup 改善 0.174 ns。原三份 ZIP 保持原始字节与 SHA256。


SG51 在 MemoryRange 基础上将比较器映射到双输出 LUT6D，采用 LUT packing strategy 3（seed 1）。布线后减少 **50 LUT**，FF 和基准成绩保持不变，慢角 setup 裕量由 +0.043 ns 提高至 **+0.099 ns**。

新增包严格核验：`python verify_package_sg30.py --zip PaceRV_H4_Loop16_SelectiveLoad_MemoryRange_145125_LUT6621_Verified.zip`。该命令重新计算包内文件哈希、正式周期数与成绩，核对源码、固件、位流、十类原始时序数据及实际资源。

## 文件与核验

- [verify_package_sg51.py](verify_package_sg51.py)：6571 LUT 归档校验器，核验 379 项文件、两组长测和十类时序检查。
- [verify_package_sg30.py](verify_package_sg30.py)：6621 LUT 归档校验器，核验 536 项清单和资格证据。
- [SG30 资格核验](evidence/SG30_QUALIFICATION.json)与[独立审计](evidence/SG30_INDEPENDENT_AUDIT.json)。
- [SHA256SUMS.txt](SHA256SUMS.txt)：六份 ZIP 的 SHA256。
- [Verify-Archives.ps1](Verify-Archives.ps1)：使用 PowerShell 7 核对 ZIP 哈希、每个 MANIFEST 文件的大小和 SHA256，以及完整文件清单；也支持指定远端提交复核。
- [verify_package_h4.py](verify_package_h4.py)：H4 严格自校验入口，与同目录 [closure_proofs_h4.py](closure_proofs_h4.py)、[h4_proof.py](h4_proof.py) 一起使用，核对两组正式成绩、源文件绑定、位流及时序和功能验证证据。
- [verify_package.py](verify_package.py)：原 H6 SelectiveLoad 自校验入口。
- [UPLOAD_VERIFICATION_H4.json](UPLOAD_VERIFICATION_H4.json)：新版 H4 归档重新打开后的校验回执；[H4 资格核验](evidence/H4_QUALIFICATION.json)记录正式成绩、资源、RTL 绑定及十项时序结果。
- [UPLOAD_VERIFICATION.json](UPLOAD_VERIFICATION.json)：原三版上传前 ZIP CRC、清单文件哈希、固件及位流核验结果。
- [evidence/FINAL_AUDIT.md](evidence/FINAL_AUDIT.md) 与 [evidence/FINAL_AUDIT.json](evidence/FINAL_AUDIT.json)：原 H6 SelectiveLoad 的独立审计结果，含周期、CRC、RTL 绑定与时序状态。
- [RESULTS.md](RESULTS.md) 与 [FINAL_STATE.json](FINAL_STATE.json)：交付报告和推荐版本状态。

在此目录打开 PowerShell 7，可执行以下命令核验全部归档，再对 SG51 做完整校验：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
try {
    $releaseRoot = (Get-Location).Path
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($releaseRoot, 'Verify-Archives.ps1'))
    if ($LASTEXITCODE -ne 0) { throw 'Archive verification failed' }
    & python ([System.IO.Path]::Combine($releaseRoot, 'verify_package_sg51.py')) --zip ([System.IO.Path]::Combine($releaseRoot, 'PaceRV_H4_Loop16_SelectiveLoad_MuxLUT6D_145125_LUT6571_Verified.zip'))
    if ($LASTEXITCODE -ne 0) { throw 'SG51 package verification failed' }
} catch { Write-Error $_; exit 1 }
```

原三份归档各自的 MANIFEST.json 记录全部文件的大小和 SHA256：LoadALU 160 项、H6 SelectiveLoad 297 项、Loop16 160 项。LoadALU 和原 Loop16 的文件位于 ZIP 根目录，H6 SelectiveLoad 包含一层同名根目录；通用 PowerShell 校验器会读取各包实际根目录。H4 的完整文件清单和证明链由其 MANIFEST.json 与严格自校验器共同核验。

对原 H6 SelectiveLoad 包，还可执行 `python verify_package.py --zip PaceRV_H6_SelectiveLoad_145125_Experimental.zip`。其余旧包的逐项清单核验使用 `pwsh -NoProfile -File ./Verify-Archives.ps1`。
