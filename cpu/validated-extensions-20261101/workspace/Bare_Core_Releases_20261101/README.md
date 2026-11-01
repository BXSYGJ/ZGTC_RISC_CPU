# Three independent cache-free, peripheral-free CPU cores

Each release provides an exact-source RV32IMC core with its existing pipeline, compressed-instruction frontend, predictor/return stack, register file, multiply/divide unit, machine CSRs, interrupts/exceptions and full 64-bit counters. The source closure has eight RTL files. No cache, backing memory, arbiter, MMIO, UART, GPIO, timer generator, PLL or ILA is inside the DUT.

- `Original_155250/source/rv32_bare_core.sv`: Original core interface and frozen parameters.
- `H3_Base_145125/source/rv32_bare_core.sv`: H3 Base interface, including its separate pair-fetch address.
- `H3_Retained_145125/source/rv32_bare_core.sv`: retained-permission H3 interface.
- `<release>/source/rtl`: eight unchanged, hash-bound implementation files.
- `<release>/SOURCE_MANIFEST.json`: source provenance, configuration and exact interface.
- `<release>/physical/builds`: isolated physical fixtures, constraints, native reports and rollback evidence.
- `analysis/EXTRACTION_QUALIFICATION.md`: fresh behavior comparison and join to complete benchmark runs.
- `analysis/physical-attribution`: native post-route resource attribution and reconciliation.

## Functional use

Instantiate `rv32_bare_core` with the eight files listed in its source manifest. Connect the complete instruction/data ready-valid interfaces, compressed metadata, maintenance, timer and interrupt inputs. Original and H3 have different companion-instruction address contracts; `analysis/BARE_CORE_PREPARATION.md` describes them. The RTL wrapper passes all ports directly to the unchanged core.

The bare core requires external memory and system services to execute firmware. The supplied extraction test keeps those services outside the synthesized DUT. It compares the bare wrapper against an independent original SoC instance before and after two million CPU edges. Every exposed port is compared, including invalid-cycle payloads, counters and trap information. A deliberate input mismatch is detected, and a separate restored run reproduces the baseline.

## Execution efficiency

The actual completed 6,000-iteration reference simulations use identical V0 firmware and the original cached-system services. All eight core hashes and parameters match these completed executions. The fresh bare extraction test verifies the new boundary over its recorded interval. These are complementary pieces of evidence; the new bare wrapper has not itself completed a new 6,000-iteration run.

Any CoreMark-per-area value here uses **core-only area with explicitly external cached-system services**. It is not the efficiency of a complete SoC or a new standalone cacheless-memory benchmark. Changing external memory latency, pairing or throughput requires a new performance measurement.

## Physical use and timing

The full interface exceeds the device package I/O count. A separately identified scan fixture provides variable input registers and independently observable output bits with a small physical pin count. Core hierarchy, fixture hierarchy and tool-generated resources are counted separately. The fixture is a measurement shell, not a standalone board application.

The selected staged fixture snapshots all outputs every CPU edge and shifts serial data once every two edges. Its input update is atomic. Only the serial output uses a two-cycle setup/one-cycle hold timing contract; internal CPU and core-boundary paths retain their full target period. Inputs follow the documented falling-edge launch protocol. All setup, hold, recovery, removal and pulse-width summaries are audited at slow and fast corners. The minimum setup uncertainty budget is 0.150 ns. Reports preserve the actual effective deduction, which can be larger. A route passes only when every checked timing requirement passes under a deduction at least this large. No excess uncertainty is added to the reported slack.

Use `SELECTED_BUILD.json` within each release and `RELEASES.json` for selected paths and measured status after final audits. Earlier build attempts remain distinct evidence. A generated native simulation netlist or successful PDS process is not by itself timing closure.

## Reproduction

PowerShell 7, licensed PDS 2022.2-SP6.4, Python and the recorded WSL/Verilator toolchain are used. Scripts inherit the existing `PANGO_LICENSE_FILE` setting and run vendor tools in the background. PDS jobs share a named mutex with the ILA workflow. No remote board or hardware operation is part of this task.

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $root = [System.IO.Path]::Combine('D:/AAAFPGA', 'Bare_Core_Releases_20261101')
    $runner = [System.IO.Path]::Combine($root, 'scripts', 'Build-BareCore.ps1')
    $selection = Get-Content -LiteralPath ([System.IO.Path]::Combine($root, 'Original_155250', 'SELECTED_BUILD.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    & $runner -Release Original_155250 -Action Audit -BuildDirectory $selection.build_directory
    if ($LASTEXITCODE -ne 0) { throw 'Read the actual resource and timing receipts.' }
} catch { Write-Error $_ }
```

See `scripts/README.md` for fixture-test invocation and audit/rollback commands. Frozen sources and prior source manifests remain unchanged; physical fixture adjustments are confined to independent build inputs.
## Completed results

All three selected bare-core fixtures pass their requested clock targets. Open [resource efficiency](analysis/RESOURCE_EFFICIENCY.md) for the conservative core-area bounds and service-dependent performance, or [RELEASES.json](RELEASES.json) for exact selected paths. CoreMark/MHz remains 3.365739 for Original and 3.441903 / 3.442075 for H3 Base / Retained under their unchanged external services.
