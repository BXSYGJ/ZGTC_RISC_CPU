# 2026-11-01: minimal ILA systems and extracted bare cores

Three independent RV32IMC systems with minimal ILA, their local simulation waveforms, and three separately routed bare-core extractions. Included: frozen RTL, firmware, selected PDS outputs, raw results, plots and audit records. Existing board-qualified releases remain in the [CPU index](../README.md).

**Evidence scope:** new waveforms are **LOCAL RTL SIMULATION**, not board ILA captures. No remote FPGA platform was used. Configured-frequency CoreMark scores below are derived from completed source-system simulation counts, not new board measurements. All six selected implementations meet their checked internal timing constraints.

## Complete systems with minimal ILA

| System | Configured MHz | CoreMark/MHz | Derived CoreMark | Routed LUT / FF | DRM / APM | Setup slack, ns | Data / trigger / depth |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original | 155.250 | 3.365739 | 522.531 | 6,609 / 3,573 | 22.5 / 4 | +0.119 | 42 / 33 / 1024 |
| H3 Retained | 145.125 | 3.442075 | 499.531 | 6,456 / 3,024 | 26 / 4 | 0.000 | 24 / 17 / 1024 |
| H3 Base | 145.125 | 3.441903 | 499.506 | 6,421 / 3,024 | 26 / 4 | +0.074 | 24 / 17 / 1024 |

Each system also uses one PLL. Slack already includes **0.150 ns clock uncertainty**. H3 Retained's zero is the report's printed precision. Placement variability is separate from clock uncertainty.

The three complete 6,000-iteration source executions preserve firmware, UART bytes, CRCs, cycles and retired-instruction counts relative to their references. Original uses 1,782,669,419 cycles, H3 Retained 1,743,134,699 and H3 Base 1,743,221,870; all retire 1,649,428,429 instructions in the measured interval. Original uses Verilator 4.038 with behavioral memory; H3 uses Verilator 5.032 with native timed-memory models. Saved results identify each simulator and source binding.

- [ILA catalog](workspace/ILA_Core_Releases_20261101/RELEASES.json) and [implementation summary](workspace/ILA_Core_Releases_20261101/analysis/IMPLEMENTATION_RESULTS.md)
- [Nine waveform windows, plots and raw VCD links](workspace/ILA_Core_Releases_20261101/analysis/README.md) and [contact sheet](workspace/ILA_Core_Releases_20261101/analysis/LOCAL_WAVEFORM_CONTACT_SHEET.png)
- [Original system](workspace/ILA_Core_Releases_20261101/Original_155250/) / [H3 Retained system](workspace/ILA_Core_Releases_20261101/H3_Retained_145125/) / [H3 Base system](workspace/ILA_Core_Releases_20261101/H3_Base_145125/)

Each system has list, matrix and state function windows containing 1,024 consecutive CPU rising-edge observations, CSV/VCD data, full-window and zoom PNGs, and editable SVGs. Local recordings contain a 42-bit superset; the H3 physical ILA uses the documented 24-bit subset. Simulator timestamps use a 10 ns clock and accelerated UART settings; these are separate from configured FPGA frequencies.

## Extracted bare-core physical results

| Core | MHz | Core-only LUT range | Core FF | Core DRM / APM | Whole scan fixture LUT / FF | Setup slack, ns | CoreMark/MHz/kLUT, lower bound |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original | 155.250 | 4,028–4,031 | 1,543 | 0 / 4 | 4,386 / 2,775 | +0.176 | 0.834964 |
| H3 Retained | 145.125 | 4,143–4,147 | 1,554 | 0 / 4 | 4,550 / 2,850 | +0.019 | 0.830016 |
| H3 Base | 145.125 | 4,095–4,107 | 1,528 | 0 / 4 | 4,498 / 2,826 | +0.047 | 0.838058 |

These routed tests use a staged serial boundary fixture, not a complete standalone SoC. The core retains eight byte-identical RV32IMC RTL files, predictor, register file, multiply/divide, machine CSRs, interrupts, exceptions and 64-bit counters. Caches, backing RAM, peripherals, PLL and ILA are external to bare-core area. The fixture is accounted for separately. Distributed RAM LUT sites are included in core LUT counts. Unattributed or shared LUT sites are conservatively assigned to the upper bound; efficiency uses that upper bound.

Bare-core reports contain **0.200 ns effective clock uncertainty**, already deducted from slack, despite scripts requesting a 0.150 ns minimum. No PLL is instantiated. Only the serial output has the documented multicycle exception; core and parallel boundary paths remain single-cycle.

Source/extraction miter runs compare all core output ports for 2,000,000 edges per baseline/rollback execution. Source identities join these extractions to completed full source-system runs. **A new standalone bare-core 6,000-iteration CoreMark run and new bare-core board validation were not performed.** Efficiency combines core-only physical area with externally supplied cached-system service; it is not a cacheless-memory performance result.

- [Bare-core catalog and exact efficiency ranges](workspace/Bare_Core_Releases_20261101/RELEASES.json)
- [Original bare core](workspace/Bare_Core_Releases_20261101/Original_155250/) / [H3 Retained bare core](workspace/Bare_Core_Releases_20261101/H3_Retained_145125/) / [H3 Base bare core](workspace/Bare_Core_Releases_20261101/H3_Base_145125/)
- [Physical attribution and extraction audits](workspace/Bare_Core_Releases_20261101/analysis/)

CoreMark/MHz = `6000000000 / measured_cycles`; CoreMark = `CoreMark/MHz * configured_MHz`; CoreMark/MHz/kLUT = `CoreMark/MHz * 1000 / LUT`; CoreMark/LUT = `CoreMark / LUT`. Complete-system and core-only denominators describe different scopes.

## Verify the download

Use Python 3.11+ and PowerShell 7. From this directory:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    & python ([IO.Path]::Combine((Get-Location).Path, 'verify_snapshot.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot verification failed.' }
} catch { Write-Error $_; exit 1 }
```

[SNAPSHOT_MANIFEST.json](SNAPSHOT_MANIFEST.json) maps each archived file to its original location, byte count and SHA-256. Original receipts retain historical absolute paths as provenance; their checkout paths are in this manifest. [OMITTED_GENERATED_FILES.json](OMITTED_GENERATED_FILES.json) lists excluded generated objects, intermediate databases and nonselected outputs. Compiler object trees, licensed vendor model libraries and tool installations are not bundled. Selected bitstreams, timing reports, physical inputs and waveform data are retained.

## Prepare a fresh physical rebuild

The relocation helper creates a fresh workspace without editing archived evidence. Prerequisites: Windows, PowerShell 7, Python 3.11+, licensed **PDS 2022.2-SP6.4**, and `PANGO_LICENSE_FILE`. Target: **PG2L200H-6FBB676**. Obtain vendor simulation models from your own PDS installation. A RISC-V compiler is needed only when changing supplied firmware. Linux/WSL Verilator is needed for scan-fixture tests and RTL simulation.

Example for Original with minimal ILA, using a new destination:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $release = 'Original_155250'
    $newWorkspace = [IO.Path]::Combine('D:/CPUExperiments', 'original-ila-rebuild')
    & python ([IO.Path]::Combine((Get-Location).Path, 'prepare_rebuild.py')) --destination $newWorkspace --release $release --variant ila --pds-root ([IO.Path]::Combine('D:/', 'PDS_2022.2-SP6.4'))
    if ($LASTEXITCODE -ne 0) { throw 'Workspace preparation failed.' }
    $runner = [IO.Path]::Combine($newWorkspace, 'ILA_Core_Releases_20261101', 'scripts', 'Build-MinimalIla.ps1')
    & pwsh -NoProfile -File $runner -Release $release -Action Prepare -PlacementSeed 1 -IlaProfile NativeMinimal
    if ($LASTEXITCODE -ne 0) { throw 'ILA source preparation failed.' }
} catch { Write-Error $_; exit 1 }
```

For H3, set release to `H3_Base_145125` or `H3_Retained_145125` and use `-IlaProfile Lean24`. Preparation prints the new build directory. Set `$buildDirectory` to that actual directory. Run the same runner with `-Action Build -BuildDirectory $buildDirectory` and the same release/profile/seed for synthesis, insertion, routing and timing. It runs in the background and refuses to overwrite a completed physical invocation.

For bare-core rebuilding, invoke `prepare_rebuild.py` with `--variant bare` and a different new destination. Then:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $runner = [IO.Path]::Combine($newWorkspace, 'Bare_Core_Releases_20261101', 'scripts', 'Build-BareCore.ps1')
    & pwsh -NoProfile -File $runner -Release $release -Action Prepare -PlacementSeed 1 -FixtureProfile SlowScanStaged
    if ($LASTEXITCODE -ne 0) { throw 'Bare source preparation failed.' }
    # Set $buildDirectory to the physical build directory printed above.
    $test = [IO.Path]::Combine($newWorkspace, 'Bare_Core_Releases_20261101', 'scripts', 'Test-ScanFixture.ps1')
    & pwsh -NoProfile -File $test -Release $release -BuildDirectory $buildDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Scan fixture test failed.' }
    & pwsh -NoProfile -File $runner -Release $release -Action Build -BuildDirectory $buildDirectory -PlacementSeed 1 -FixtureProfile SlowScanStaged
    if ($LASTEXITCODE -ne 0) { throw 'Bare physical build failed.' }
} catch { Write-Error $_; exit 1 }
```

Archived simulation drivers and run receipts document the original qualification commands. Re-running historical commands requires relocating their manifest paths and supplying matching simulators and PDS memory models; they are not portable one-command launchers. Helpers above automate fresh **physical source preparation**, not full CoreMark or board qualification. Board programming and board ILA capture are separate operations.

## Publication checks

[PUBLICATION_VALIDATION.json](PUBLICATION_VALIDATION.json) records snapshot verification and six fresh, relocated source preparations. These checks do not repeat routing, full-length simulation or hardware qualification. Original experiment receipts remain byte-identical to frozen sources.
