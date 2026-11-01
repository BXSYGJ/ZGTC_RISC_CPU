# Bare-core release scripts

Run with PowerShell 7 or newer. Prepare source copies before preparing a physical build.

```powershell
pwsh -NoProfile -File scripts/Prepare-BareCore.ps1 -Release Original_155250
pwsh -NoProfile -File scripts/Build-BareCore.ps1 -Release Original_155250 -Action Prepare -PlacementSeed 2
pwsh -NoProfile -File scripts/Build-BareCore.ps1 -Release Original_155250 -Action Build -BuildDirectory BUILD_DIRECTORY
pwsh -NoProfile -File scripts/Build-BareCore.ps1 -Release Original_155250 -Action Audit -BuildDirectory BUILD_DIRECTORY
```

The same interface accepts H3_Base_145125 and H3_Retained_145125. Each build is isolated in RELEASE/physical/builds. Preparation copies the eight exact frozen files and both generated wrappers, validates every input and output bit in BOUNDARY.json, writes the physical Tcl and constraints, and tests restoration on a separate copy. Prepare performs no vendor operation.

The core DUT is core_boundary/dut. rv32_bare_core forwards every core port with fixed synthesis parameters. The separate seven-pin scan fixture controls all 176 non-clock core input bits and captures all 439 Original or 471 H3 output bits separately. The clock comes directly from a physical input pin. Both core boundaries use syn_hier=fixed. The synthesis source closure contains eight CPU files and the two wrappers.

New SlowScanStaged physical builds use the configured release frequency, one 0.150 ns clock uncertainty command, and explicitly constrained scan I/O. Every slow and fast setup, hold, recovery, removal, and pulse-width table is audited. Results apply to this physical fixture. LUT and FF totals include the fixture until native post-route attribution is complete. The routed primitive inventory retains every instance, hierarchy, and primitive type for independent attribution.

Builds acquire the shared AAAFPGA_PDS2022_MinimalILA mutex. The runner never terminates another vendor process. Start a new prepared directory for each seed attempt; an existing physical invocation is audited rather than overwritten.

EXTRACTION_QUALIFICATION.json records finite RTL comparisons against the original SoC and source identity joins to the completed 6000-iteration runs. CoreMark execution used the recorded external cached-system services. It does not measure a new standalone memory service. All qualification and waveform evidence comes from local RTL simulation. No board operation is required.

SlowScanStaged is the default for new physical preparations. It changes only each build copy of the physical fixture; the release SOURCE_MANIFEST and the eight core files remain unchanged. The fixture samples every core output on every rising edge into output_snapshot. A capture command loads the previous edge snapshot into the serial bank. scan_phase accepts shift, update, and capture on alternate core edges, so serial data changes at most once every two core edges. A host launches scan controls on the preceding falling edge and samples serial data at the second rising edge before the next shift. Only the physical scan_out port receives a two-cycle setup and one-cycle hold exception. Internal core paths retain single-cycle timing. The fixed core clock has a single 0.150 ns user uncertainty command; actual native setup deductions are read from the resulting timing report.

Before Build, qualify the exact prepared fixture:

```powershell
pwsh -NoProfile -File scripts/Test-ScanFixture.ps1 -Release Original_155250 -BuildDirectory BUILD_DIRECTORY
```

This test binds the fixture SHA256 and checks all 179 patterns, every input port, every serial output bit, alternate-edge hold, and the one-edge snapshot latency. The original release-source fixture test remains a separate historical result. Both observed Initial and SlowScanStaged reports deduct 0.200 ns for setup: the command value is 0.150 ns, with an additional vendor clock jitter allowance. The installed PDS guide documents an automatic 0.050 ns system jitter term. Passing all corners at the observed 0.200 ns satisfies the requested minimum 0.150 ns budget; the exact-match field stays false. Reported slack already includes the actual deduction. Initial fixture failures remain preserved.

Original selected post-route accounting reconciles 4,386 LUT slots as 4,028 core-exclusive, 355 fixture-exclusive, 1 shared, and 2 unexported/unattributed. The conservative core range is 4,028–4,031 LUTs; use 4,031 when forming an external-service performance/area lower bound. Its 1,543 core and 1,232 fixture registers reconcile to 2,775.

Current provenance checks also verify the original source paths recorded in SOURCE_MANIFEST.json. For reproduction with the current scripts, keep the Bare_Core_Releases_20261101 and ILA_Core_Releases_20261101 release trees, and the recorded frozen release tree, at their existing D:/AAAFPGA locations. Every bare physical build nevertheless contains the exact eight RTL files, both wrappers, parameters, boundary map, constraints, and Tcl in its own recorded inputs.
