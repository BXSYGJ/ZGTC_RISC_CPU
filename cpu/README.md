# Packaged CPU releases

Each qualified CPU version has its own folder directly under `cpu/`. V0 performance and V1 validation remain together inside each release. All scores below use 6,000 iterations and archived board cycle counters.

| Release folder | ISA | MHz | V0 CoreMark | V0 CoreMark/MHz | LUT / FF | DRM / APM |
|---|---|---:|---:|---:|---:|---:|
| [H3_Base_145125](H3_Base_145125/README.md) | RV32IMC | 145.125 | 499.506 | 3.441903 | 6,097 / 2,541 | 25 / 4 |
| [H3_Retained_145125](H3_Retained_145125/README.md) | RV32IMC | 145.125 | 499.531 | 3.442075 | 6,150 / 2,541 | 25 / 4 |
| [Original_153000_BestQualified](Original_153000_BestQualified/README.md) | RV32IMC | 153 | 514.958 | 3.365739 | 6,439 / 3,002 | 21 / 4 |
| [Original_155250](Original_155250/README.md) | RV32IMC | 155.25 | 522.531 | 3.365739 | 6,109 / 2,864 | 21 / 4 |
| [Accepted_RV32IM_153000_FullILA](Accepted_RV32IM_153000_FullILA/README.md) | RV32IM | 153 | 511.722 | 3.344589 | 7,312 / 4,023 | 22.5 / 4 |

**Highest absolute throughput:** Original_155250, 522.531 CoreMark. **Highest CoreMark/MHz:** H3_Retained_145125, 3.442075. **Selected full-ILA build:** Accepted_RV32IM_153000_FullILA, 511.722 CoreMark, with 42 data channels, 33 trigger channels and a 1,024-sample depth.

Clock values are configured operating points. CoreMark is `6000 * clock_hz / cycles`; CoreMark/MHz is `6000000000 / cycles`. CoreMark/MHz/kLUT is `(CoreMark/MHz) * 1000 / LUT`. Both normalized and absolute resource-efficiency metrics are recorded in [RELEASES.json](RELEASES.json). V0 and V1 have distinct firmware and counts.

## Use a release

Open its README for exact bitstreams, UART speed, FPGA pin mapping, firmware, raw captures and rebuild commands. The four RV32IMC releases use embedded firmware images at 9600 baud. The ILA release uses a separate UART firmware loader at 115200 baud. All target PG2L200H-6FBB676.

[Shared build/test tools and software](release-support/README.md) include portable physical-project preparation, firmware compilation, simulation and exact UART-frame audits. The compiler is an existing GitHub Release asset; no PDS license is included.

The previous nested 153/155.25 MHz packages have moved to the direct folders above. Their already uploaded timing evidence is retained. The older `experiments/full_fetch_commit_factored` remains a historical 9,502-LUT ILA experiment and is not the selected full-ILA release in this index.

## Verify the checkout

From this directory in PowerShell 7:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    & ([IO.Path]::Combine((Get-Location).Path, 'release-support', 'Test-ReleaseCollection.ps1')) -OutputDirectory ([IO.Path]::Combine('D:/CPUExperiments', 'release-audit'))
    if ($LASTEXITCODE -ne 0) { throw 'Release audit failed.' }
} catch { Write-Error $_ }
```

The test verifies the SHA-256 manifest, original recipe bindings, all 24 RV32IMC board captures, the six final ILA qualification records and all nine archived internal timing reports. The uncertainty is 0.150 ns and already deducted from slack. The manifest covers the five release folders and shared release-support tree, excluding itself. The original local frozen packages remain unchanged.

Publication validation checks archived evidence and prepares relocated build projects. It does not repeat full-length simulation, routing or real-board experiments. The original package-supplied README and historical evidence record earlier qualification.
