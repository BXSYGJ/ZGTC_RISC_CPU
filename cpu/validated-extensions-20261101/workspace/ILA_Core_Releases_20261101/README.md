# Three independent CPU releases with a minimal ILA

This workspace contains independent ILA implementations and local simulation observations for Original 155.25 MHz, H3 Retained 145.125 MHz, and H3 Base 145.125 MHz. Source releases remain in `D:/AAAFPGA/Current_Paper_and_Sub7000_Core_Releases_20261012/cores`.

## Demonstration requirements

The CPU topic in the supplied competition guide requires a performance-analysis document with ILA waveform analysis of the pipeline during important CoreMark algorithms (PDF page 11, printed page 9). The selected observation points are the linked-list, matrix, and state-machine kernels. Each waveform records 1,024 consecutive CPU edges.

The user's final instruction selects **local simulation recordings and screenshots**. All new waveforms are labeled **LOCAL RTL SIMULATION**. The simulation observes the signals selected for ILA insertion; it does not read physical DebugCore capture RAM. Hardware programming and remote-board operations are excluded from the current workflow.

## Contents

- `Original_155250`: frozen inputs, independent physical builds, functional qualification, and local algorithm traces.
- `H3_Retained_145125`: the same materials for the retained-preparation core.
- `H3_Base_145125`: the same materials for the base core.
- `scripts`: the common PDS synthesis, insertion, timing-audit and rollback tools.
- `analysis`: waveform figures and the consolidated analysis, once generated.
- `requirements`: the extracted guide and rendered relevant pages.
- `transport`: waveform rendering and protocol research. Remote-operation scripts are retained as unused research tools and are not part of this simulation workflow.

`RELEASES.json` identifies selected builds and their exact qualification status. Build directories also retain intermediate experiments. Use the selected paths in the catalog when opening bitstreams, FIC files, mapping audits, and timing reports.

## Minimal observation set

Original uses 42 data bits: EX PC [31:0], IF/ID/EX/MEM/WB validity, ID transfer, EX transfer, memory redirect, frontend transfer, and memory completion. Its trigger uses EX PC [31:0] and EX transfer (33 bits). Both H3 implementations use a smaller 24-bit data set: EX PC [15:0], five pipeline-valid bits, and ID/EX/MEM transfer. Their 17-bit trigger uses EX PC [15:0] and EX transfer. All profiles use rising CPU-clock edges and a depth of 1,024 samples. Earlier development layouts remain separate from the selected builds.

The selected triggers identify a function-entry address when the instruction advances. Sixteen PC bits cover this firmware image within 64 KiB. Exact V0 ELFs are copied into each release's firmware directory. Local simulation records a 42-bit superset independently for every core. SOURCE_TO_SELECTED_BINDING.json maps the smaller H3 physical probe sets to the recorded signals.

## Rebuild or audit

PowerShell 7 and licensed PDS 2022.2-SP6.4 are required. The runner inherits the existing user `PANGO_LICENSE_FILE` setting. Vendor programs run hidden. A named mutex serializes PDS jobs. The original 0.150 ns CPU clock uncertainty remains in the constraints.

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $root = [System.IO.Path]::Combine('D:/AAAFPGA', 'ILA_Core_Releases_20261101')
    $runner = [System.IO.Path]::Combine($root, 'scripts', 'Build-MinimalIla.ps1')
    & $runner -Release H3_Base_145125 -Action Build -IlaProfile NativeMinimal
    if ($LASTEXITCODE -ne 0) { throw 'Inspect the new build manifest and timing report.' }
} catch {
    Write-Error $_
}
```

Use `-Action Audit -BuildDirectory <selected build>` to audit existing outputs without rerunning implementation. Each build has a `ROLLBACK.ps1` which restores its frozen inputs onto an explicitly selected separate copy inside that build. The actual instrumented build is preserved. Exact source, firmware, mapping, timing and output hashes are recorded beside the artifacts.

## Interpreting the evidence

Physical timing reports establish closure for the particular placed-and-routed ILA layout, including debugger clocks. They do not measure a physical board's maximum frequency. Local simulation checks establish behavior over their recorded execution interval; fresh full 6,000-iteration results are recorded separately in each selected release and in RELEASES.json.

Waveform plots use CPU-edge indices. Their metadata preserve the simulator's actual timebase and the accelerated UART settings. The configured implementation clock is a separate annotation. Window-level WB event rates and holding cycles describe only the captured interval; they are not substituted for whole-benchmark CoreMark or IPC measurements.

## Selected results

All three selected ILA layouts meet their configured timing requirements. Fresh full 6,000-iteration runs reproduce their respective reference UART bytes, CRCs, cycles and retired instructions. Open [implementation results](analysis/IMPLEMENTATION_RESULTS.md), [the waveform index](analysis/README.md), or [the verified catalog](RELEASES.json). The related pure-core extraction is stored separately in `D:/AAAFPGA/Bare_Core_Releases_20261101`.
