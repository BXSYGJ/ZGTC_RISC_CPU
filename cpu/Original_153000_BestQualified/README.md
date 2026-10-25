# Original_153000_BestQualified

The best-throughput board-qualified original RV32IMC release at the configured 153 MHz operating point, with the selected area-optimized implementation.

Configured clock: **153 MHz**. Target: Pango Logos2 PG2L200H-6FBB676, 27 MHz board input. V0 is the performance configuration; V1 is the separate validation configuration. Both use 6,000 iterations.

| Image | Cycles | Retired instructions | CoreMark | CoreMark/MHz | LUT / FF | DRM / APM | Setup slack (ns) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 1,782,669,419 | 1,649,428,429 | 514.958 | 3.365739 | 6,439 / 3,002 | 21 / 4 | +0.174 |
| V1 | 1,784,414,808 | 1,649,775,527 | 514.454 | 3.362447 | 6,439 / 3,002 | 21 / 4 | +0.174 |

Scores use `6000 * configured_clock_hz / cycles`; CoreMark/MHz uses `6000000000 / cycles`. UART integer Iterations/Sec is not used. Clock frequency is the configured operating point, not an external frequency-counter measurement. Reported setup slack already includes the 0.150 ns uncertainty. Resource counts belong to these exact archived layouts.

## Program and measure on a board

1. Install PDS 2022.2-SP6.4, its PG2L200H device support, JTAG/UART drivers and a valid license.
2. Check the board pinout against `physical/V0/inputs/constraints/`. The saved images use the RemoteLab AC26/AB26 UART mapping; LocalBoard B24/C24 requires rebuilding with its constraint file.
3. Program `bitstreams/V0.sbit` or `bitstreams/V1.sbit` with the PDS programmer. Each image already includes its corresponding benchmark firmware.
4. Connect the board UART at **9600 baud, 8N1, no flow control**. Use the capture script below, then reset the board. It waits for READY, sends G, and checks the complete frame against the frozen reference. Use a fresh output directory per run.
5. Repeat three cold starts per configuration. Original accepted captures are under `board-references/V0/` and `board-references/V1/`.

Run this PowerShell 7 example from this release directory. Change COM5 and the external output path for your computer.

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $release = (Get-Location).Path
    $scripts = [IO.Path]::GetFullPath([IO.Path]::Combine($release, '..', 'release-support', 'scripts'))
    & ([IO.Path]::Combine($scripts, 'Capture-BoardUART.ps1')) -ReleaseRoot $release -Role V0 -PortName COM5 -OutputDirectory ([IO.Path]::Combine('D:/CPUExperiments', 'V0-run1'))
    if ($LASTEXITCODE -ne 0) { throw 'Board capture did not pass.' }
} catch { Write-Error $_ }
```

## Source, firmware and reproduction

- `recipe.json`: release identity, hashes, exact compiler/simulator arguments, physical options and original provenance.
- `source/`: author RTL, peripherals, cache, CSR, predictor, PLL and tests.
- `physical/V0/inputs/` and `physical/V1/inputs/`: independent frozen physical-build snapshots, constraints and firmware bindings.
- `firmware/V0/` and `firmware/V1/`: CoreMark sources/license, platform port, ELF/BIN/HEX, build records and full simulation UART references.
- `simulation/inputs/`: frozen simulation RTL and driver.
- `evidence/physical/V0/` and `V1/`: archived timing/resource reports and build identities.

Use the included Verilator 4.038 runtime for this inferred-memory functional simulation. This simulation is distinct from the H3 timed native-memory model.

Shared instructions, firmware compiler download and portable firmware/simulation/physical-build scripts: [release-support](../release-support/README.md). The scripts take an explicit release root, so a changed checkout location is supported. Builds write into a separate directory. Original absolute paths in frozen records are provenance, not installation requirements.

The 2026-10-25 publication audit rechecks packaged bytes, all six archived board captures, timing reports and physical-project preparation. It does not claim a new full benchmark simulation, route or live board measurement. Use the archived captures and reports to identify the qualified images; qualify any newly built image separately.
