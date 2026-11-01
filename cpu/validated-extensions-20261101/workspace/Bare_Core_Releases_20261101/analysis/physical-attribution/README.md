# Independent native physical area audit

`inspect_native_export.py` reads PDS's actual final `generate_netlist/bare_core_scan_top_sim.v` and the matching final `place_route/bare_core_scan_top.prr`. It does not assign weights to packed `gop*` macros or subtract an estimated fixture cost. The physical export names each actual device slot and includes the original packed-instance provenance in comments.

The audit counts exported physical LUT6/CARRY slots, 64-bit distributed RAM slots, individual flip-flops and arithmetic blocks. A `V_RAM32X2` is one 64-bit physical RAM slot, as is `V_RAM64X1`. These RAM slots are included in PDS's LUT total and also reported separately as Distributed RAM; they must not be added twice. Unique physical `CLMA/CLMS` slot names reject overlapping LUT/RAM counts. Native final per-module counts and exported provenance counts remain separate if the tool's two representations differ. Every difference is explicit; no undocumented scalar weight forces equality.

Tool-created `GND_n` and `VCC_n` LUTs have their actual constant INIT checked. The audit follows each output net through unowned buffers, inverters, muxes and clock glue to owned core/fixture consumers. It records core-only, fixture-only, shared and unresolved sites individually. It retains any native global LUT slot absent from the physical simulation export as an explicit unattributed item. Core area can therefore be reported as the exact native hierarchy count plus a separate generated-overhead interval. Its upper bound assigns every shared, unresolved or unexported LUT slot to the core. No residual is fitted to an undocumented macro weight.

The report also reopens the actual physical build input inventory, all eight frozen RTL hashes, the complete core wrapper and fixed parameter contract. Timing acceptance remains in the physical build receipt and is independent of a successful area inventory.

`compare_packed_to_export.py` independently counts actual registered `Q` output ports on native packed instances, including the two registers in `gopSRL2`, and joins each owner to exported physical FF cells. A simulation-export omission retains its exact packed instance and core/fixture owner. The native FF total and ownership must then reconcile exactly. This uses physical register outputs and native packing composition, not a LUT-weight estimate. `audit_retained_features.py` checks all 64 individual `mcycle` and `minstret` FF bits and eight separate feature cones, including the return stack, plus register-file RAM sites.

PowerShell 7 invocation:

```powershell
$root = [System.IO.Path]::Combine('D:/AAAFPGA','Bare_Core_Releases_20261101')
$build = [System.IO.Path]::Combine($root,'Original_155250','physical','builds','BUILD_ID')
$audit = [System.IO.Path]::Combine($root,'analysis','physical-attribution','inspect_native_export.py')
$netlist = [System.IO.Path]::Combine($build,'implementation','generate_netlist','bare_core_scan_top_sim.v')
$prr = [System.IO.Path]::Combine($build,'implementation','place_route','bare_core_scan_top.prr')
$output = [System.IO.Path]::Combine($root,'analysis','physical-attribution','Original_155250-BUILD_ID-PHYSICAL_PRIMITIVE_INVENTORY.json')
& python $audit $netlist $output --route-report $prr
```

`test_native_inventory.py` uses only temporary, explicitly synthetic fixtures. Five controls cover shared constant fanout, dangling constants, duplicate physical LUT/RAM slots, unknown primitives and a falsely annotated constant INIT. All five passed. The actual release audits read generated PDS data.

The exploratory first Original route `20261101-014253-e76e0df2` failed timing and is retained as an attribution example only. Its independently reopened audit gives:

| Final native/external physical category | LUT/RAM slots | FF | APM |
| --- | ---: | ---: | ---: |
| Native hierarchy-attributed core | 3750 | 1532 | 4 |
| Generated constants used only by core | 146 | 0 | 0 |
| Native hierarchy-attributed fixture | 220 | 791 | 0 |
| Generated constants used only by fixture | 17 | 0 | 0 |
| Native global slot absent from simulation export | 1 | 0 | 0 |
| Full final native physical total | 4134 | 2323 | 4 |

All 312 distributed RAM slots belong to the core and are already included in its 3750 hierarchy LUT/RAM slots. Core area including generated overhead is 3896–3897 LUT/RAM slots; fixture-exclusive area is 237. The 1-slot residue stays explicit. Corrected/selected builds require their own reports; these example numbers do not describe those runs.

Final selected reports use build-specific filenames. Original build `20261101-015541-f15b63fe` reconciles 4386 physical LUT/RAM slots as 4028 core-exclusive + 355 fixture-exclusive + 1 shared constant + 2 global-only slots; its core interval is 4028–4031. Native core FF1543 plus fixture FF1232 equals2775. Retained build `20261101-015628-ffa262ba` reconciles4550 as4143 core-exclusive+403 fixture-exclusive+1 shared+3 global-only, giving4143–4147 core slots. Its native core table counts3923 LUT while the unique exported core slots count3925; both are recorded. The native coreFF1554 contains1553 exported FFs and one specifically localized native-only `ex_decode[14]/opit_0_inv_L5Q_1_perm` L5Q register. Including fixtureFF1296 gives the exact2850 native total. These representation differences are preserved in the evidence rather than converted to guessed primitive weights.
