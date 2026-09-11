# Parallel-prefix timer increment, complete-system candidate

## Motivation and exact change

Parent: `full_relation_reuse1`, CPU SHA256 `707941FBAF4B5E73EDF3380022C4EA32D109446BA78D3B8CA6608DCAF131065B`. Its complete 42/33/1024 ILA implementation passes 151.2 MHz at 9653 LUT and +0.108 ns setup slack, but has no resource-efficiency qualification. Its limiting path crosses the 64-bit timer increment and comparator; the next CPU paths have +0.131 / +0.132 ns slack.

This child changes only `rv32_peripherals.sv`: the single 64-bit increment becomes four parallel 16-bit increments. Each upper chunk adds the reduction-AND of all lower bits. The output is mathematically the same 64-bit increment modulo 2^64; there is no extra register or delayed interrupt. The existing increment output preservation attribute remains.

Peripheral SHA256: `AB2D42B769C2493630325E3DB9CB2D5447608F20EF57D884D64A9D2F1B7E2D3E`. The exact one-substitution reconstruction is in `change-receipt.json`. The CPU, BTB, GPIO, UART, MMIO map, byte strobes, timer writes/comparisons, interrupts, performance snapshots, cache configuration, PLL and constraints are preserved. Full ILA remains mandatory. This change has no proven timing or area benefit yet.

## Completed functional checks

`build/functional-31c16833/manifest.json` records three passing methods, eight bound source inputs and five compiled cases. The positive case includes the complete peripheral testbench, cycle-by-cycle comparison to the unchanged original module, all 2048 low offsets, 10752 high-bit alias reads, sixteen snapshots, 57 bus-driven timer boundary scenarios and 512 partial writes. It reports 58536 checks; carry coverage is 51 at bit 16, 34 at bit 32, 17 at bit 48 and one full 64-bit wrap. No timer state is forced directly; boundary values are written through MMIO.

Four compiled negative controls are rejected: disabled low increment, an incorrect prefix carry, lost upper counter values, and a suppressed timer interrupt. The paired module outputs include IRQ, timer value, GPIO, serial output and response/backpressure fields. These checks do not establish CoreMark performance or physical timing.

Three staging-audit tests pass, rejecting missing/tampered sources and outputs, failed positive execution and missing negative controls. `stage_timer_physical.py` binds the exact parent CPU and complete twenty-file physical inventory, changes only the peripheral module, and captures the generator and existing PDS support scripts.

## Current workflow

`run_physical.ps1` checks PDS serialization and memory headroom, stages a new immutable source snapshot, runs both matched full-SoC short screens in WSL, and only then invokes ordinary Windows PDS. It refuses to overwrite an existing staged project. The width-corrected paired screens pass: V0/V1 are byte-identical to the immediate parent at 3000565 / 3001255 cycles and CRC fcaf / c64e. Seven complete-source/firmware/short-run binding tests pass. Ordinary PDS `20260911-084958-ea943cd6` is terminal at **151.2 MHz / 9119 LUT / 4327 FF / setup WNS -0.065 ns** and is rejected for timing. The bitstream SHA256 is `EE2812E2C986ABB23F94582ACCCB13C7F3779702386F2F3E4A34E1458FDC1287`. This ordinary count excludes inserted ILA and is not the resource-efficiency denominator.

The first full-ILA staging attempt stops before implementation because the parent MEM-valid alias is no longer exposed. A native net listing identifies all four pipeline-valid signals as core-local in this synthesis. The corrected `timer-prefix16-seed1-native-core` stage passes actual 42-data / 33-trigger / 1024-depth Inserter verification and ten source/mapping tests; native register Q drivers are checked. Its full-ILA PDS run is terminal and passes at **151.2 MHz / 9546 total LUT / 5076 FF / +0.106 ns setup WNS**. The bitstream SHA256 is `CC44051D358026C55969C52CB49A4D75D3A32A8E6D70BCFB2BC5F2474FEAE928`. It saves 107 complete-system LUT versus relation reuse while preserving the complete ILA. The failed `timer-prefix16-seed1` stage remains retained, not silently repaired.

`audit_native_timer.py` and four parser/rejection tests prove the intended structural change in the actual synthesized peripheral: maximum consecutive CIN/COUT carry cells feeding the increment decrease from 63 to 17, with complete coverage of output bits 1 through 63. This is not total logic depth or routed timing. `build/synthesis-comparison.json` binds raw reports: global LUT 8727 -> 8633, inclusive peripheral LUT 732 -> 711, total FF unchanged at 4305. Nested counts must not be added.

The ordinary critical path moves away from the timer to EX operand comparison/control, with 1.653 ns logic and 4.364 ns route delay and -0.065 ns slack. Thus physical timer improvement does not by itself establish complete-system timing closure.

The first `build/v0` attempt stops before native PDS because strict Verilator checks reject an implicit one-bit-to-16-bit ADD operand. The carry is now explicitly zero-extended to 16 bits. All three functional methods and all three staging tests pass again on the corrected source. `build/initial-width-warning.json`, the original staged project and failed short logs are retained; they are not physical qualification.

The full-system critical path now starts at MEM result bit 20 and ends at fetch-prediction enables (+0.106 ns, 2.095 ns logic and 4.021 ns routing). Complete-image timing passes, but no new paired long-run metric result exists. Under the explicitly conditional assumption of unchanged earlier parent execution efficiency, the 9546-LUT image would require at least 152.68333357284476 MHz to meet the resource floor. Therefore `full_timer_clock153000` tests a 153 MHz clock with identical RTL and clock-adjusted firmware; neither timing nor resource efficiency at that clock is inferred from estimated Fmax.

Long-run metric qualification and application/electrical review remain pending. Ordinary LUT or estimated Fmax cannot substitute for a complete-image denominator or a validated clock. No remote-board access or GitHub publication is authorized by this experiment.
