# Standalone minimal pipeline ILA build

Run these scripts with PowerShell 7 or newer on Windows. PDS 2022.2-SP6.4 is read from `D:/PDS_2022.2-SP6.4`; the existing user `PANGO_LICENSE_FILE` setting is inherited. Every vendor process runs hidden in a unique release build directory. A shared named mutex serializes this runner's synthesis, insertion, and place-and-route jobs. An unrelated live PDS job causes a recorded failure; this runner never stops it.

Prepare an isolated copy:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $runner = [System.IO.Path]::Combine('D:', 'AAAFPGA', 'ILA_Core_Releases_20261101', 'scripts', 'Build-MinimalIla.ps1')
    & $runner -Release Original_155250 -Action Prepare
    if ($LASTEXITCODE -ne 0) { throw 'Preparation failed; inspect its recorded output.' }
} catch {
    Write-Error $_
}
```

Use the printed `BUILD_DIRECTORY` as the explicit `-BuildDirectory` value for `-Action Build`, or run Build without a directory to prepare and build a new copy. `-Action Audit` rechecks the completed directory without invoking PDS. `-StopAfterSynthesis` preserves the synthesis database for native signal inspection. `-PlacementSeed` defaults to the V0 recipe seed: Original 2, H3 Base 2, H3 Retained 1. A prepared directory records its seed and rejects a conflicting override.

The three accepted `-Release` values are `Original_155250`, `H3_Base_145125`, and `H3_Retained_145125`. Each uses its own frozen `physical/V0/inputs`, recipe clock, firmware hash, original constraints, and exact PNR options. Only the top wrapper's `INIT_FILE` path changes to the copied firmware. The CPU RTL, PLL, firmware bytes, and constraints remain byte-identical. Setup paths must show 0.150 ns uncertainty. The native report and final bitstream determine timing status; a failing timing report returns exit 2 and remains preserved for inspection.

The `Shared42` profile has one shared 42-bit capture/trigger port, 1024 samples, and rising `cpu_clk`. Basic With Edges uses native match type 1. The optional `-IlaProfile NativeMinimal` retains the same 42 data bits and uses 33 trigger bits, EX PC [31:0] plus EX transfer, with Basic match type 0. Pass the same profile to Prepare, Build, and Audit. The ordered capture bits are EX PC [31:0], IF/ID/EX/MEM/WB valid, ID transfer, EX transfer, memory flush, frontend instruction transfer, and memory transfer. `frontend_fire` is the frozen RV32IMC frontend handshake. No extra probe registers add sampling latency. Native aliases are selected from `ins_list_nets` and confirmed by `ins_core_info`, the canonical FIC, and `mapping-audit.json`.

Every build includes `frozen_inputs`, `inputs`, source hashes, `DIFF_FILE.txt`, `VERIFICATION.txt`, and `ROLLBACK.ps1`. Rollback requires an explicit target directory inside that build and restores all frozen input hashes onto that separate copy. Preparation tests rollback on `rollback_test/inputs` while leaving the actual build inputs relocated. The final manifest records bitstream/FIC hashes, clock, seed, post-route LUT/FF/DRM resources, and every timing corner, including the debugger clocks. CPU setup paths retain 0.150 ns uncertainty.

The requested waveform deliverable uses local RTL simulation. `Export-LocalIlaWaveforms.ps1 -Release ... -BuildDirectory ...` compiles an observation-only copy of the frozen simulator, records the actual 42 native signal values, and exports three 1024-edge function-entry windows as CSV and VCD. Sample 256 satisfies the exact ELF entry PC and EX transfer predicate. The preceding 256 edges and following 767 edges remain contiguous. Each release's `waveforms/WAVEFORM_MANIFEST.json` records source hashes, entry predicates, exact simulator timestamps, bit mapping, and local window statistics. `-SimulationRunDirectory` regenerates CSV/VCD from an existing successful raw capture without rerunning the simulator. The edge-index axis and actual simulator timestamps are separate from the configured FPGA frequency; the accelerated UART fixture uses a logical 3200 Hz parameter and 100 baud. These artifacts demonstrate local RTL behavior and contain no physical board measurements.
