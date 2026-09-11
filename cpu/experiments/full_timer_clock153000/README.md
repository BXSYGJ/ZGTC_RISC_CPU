# Complete timer-prefix system at 153 MHz

## Scope

This isolated clock experiment retains all twenty physical source files from `full_timer_prefix16` byte-for-byte, including the CPU, GPIO, UART, caches, PLL source and constraints. The PLL already implements 153 MHz when selected by its clock parameter; no PLL RTL is rewritten. The hardware configuration changes only ClockHz from 151200000 to 153000000 and its descriptive purpose. The PDS parameter whitelist and copied result-parser whitelist add only 153000000.

CPU SHA256: `707941FBAF4B5E73EDF3380022C4EA32D109446BA78D3B8CA6608DCAF131065B`. Peripheral SHA256: `AB2D42B769C2493630325E3DB9CB2D5447608F20EF57D884D64A9D2F1B7E2D3E`. The complete parent image uses 9546 LUT with +0.106 ns setup slack at 151.2 MHz.

If the earlier parent long-run execution efficiency were unchanged, 9546 LUT would require at least 152.68333357284476 MHz to meet the resource floor; at 153 MHz the corresponding ceiling would be 9565 LUT. These are conditional planning calculations, not this candidate's score or acceptance. PDS must implement the actual 153 MHz configuration; estimated Fmax is not used as a validated clock.

## Source and firmware evidence

`source-inputs.json` binds twenty unchanged physical sources, seven support inputs, twelve unchanged firmware sources and the source-staging generator. Three input tests reject clock/configuration drift, missing inventories, altered CPU input and changed generator identity. The native build snapshots these inputs again.

Four local firmware builds use the same pinned CoreMark sources, RV32 GCC 10.2.0, optimization/linker flags and seed/iteration settings as the parent, changing only CPU_CLOCK_HZ and resulting output identity. They cover both ten-iteration screens and both 6000-iteration long runs. No benchmark source is changed, fetched or checked out. Exact compiler/objcopy commands and ELF/BIN/HEX hashes are recorded per image, and `audit_clock_firmware.py` validates all four builds. Two firmware-audit methods reject command, source, completion, output and manifest corruption.

Long V0 HEX SHA256: `6DAAE1B97ED63CBD65BFF5A8F6BD15FC4E67378BA3316D790911EF5CF5D545CD`. Long V1 HEX SHA256: `9ECD2172E0412543BB5D55E386D77549B8817F7602ACD2F0D0591F7306BD1FE5`. Firmware creation alone is not a long-run result.

The initial compile attempt exposed an omitted platform.h dependency and stopped. The complete twelve-file source inventory includes that unchanged header; the failed evidence directory is retained. The first short simulation then stopped at the old parser whitelist, despite valid UART output. The isolated parser now adds only 153 MHz; four tests accept its real short UART while rejecting mismatched/unlisted clocks and use of a short run as a long score. The original failed run remains retained.

## Paired short screens

The validated runs are `build/compiled/20260911-091653-f3141158` (V0) and `build/compiled/20260911-091701-ce05cc4f` (V1). They report 3000565 / 3001255 cycles, 2748941 / 2749614 retired instructions and CRC fcaf / c64e, unchanged from the complete timer parent. Cache profiles also match. UART timestamps and clock metadata correctly use 153000000 Hz.

`audit_clock_shorts.py` checks both exact compiler commands, the eighteen captured simulation inputs, configuration/model clocks, executable and firmware hashes, raw UART and stored results. `build/short-qualification.json` records the passing source-bound pair. All twelve input/firmware/parser/short-evidence tests pass, including rejection of changed compile commands, missing source snapshots, false completion, wrong model clocks and stored results that differ from raw UART. These short runs are not reportable CoreMark scores.

## Physical workflow

`run_physical.ps1` rechecks source, firmware and short prerequisites, enforces PDS serialization and memory headroom, then uses the 6000-iteration V0 firmware for ordinary PDS. The actual 153 MHz ordinary run is `20260911-091937-b10d286c`, launch PID 85748, under `build/pds`. It has completed with 8938 ordinary post-route LUT, 4310 FF and setup WNS -0.049 ns; timing fails. Ordinary resources exclude the required ILA and cannot serve as the metric denominator.

The complete ILA stage `build/ila/timer-clock153-seed1` is terminal: 9502 total post-route LUT, 5066 FF and setup WNS -0.223 ns at 153 MHz. Actual Inserter discovery and register-driver checks verify all 42 data / 33 trigger channels and depth 1024. Bitstream SHA256: `141163A197322937E0DB7A2ABB1C198869B58B12C4E16A19FCC91D8C34053965`. Its physical receipt explicitly rejects timing and leaves score and resource-efficiency qualification false. Eleven new ILA audit tests pass, including rejection of clock/firmware/input drift, missing or duplicate probe nets, wrong register drivers, missing actual channels and incomplete invocations. The real failed report is tested at 153 MHz, not the parent clock.

The worst path runs from ex_operand_b[20] through early branch selection, frontend flush, i_req_valid and next_pc_write to next_pc[14].CE: 11 logic levels, 2.110 ns logic and 4.170 ns routing. The next experiment will remove the redundant request-handshake dependency from the next-PC and prediction capture enables using exact Boolean factoring, not relaxed timing constraints or removed functionality. Long-run metric qualification, application image and electrical/SCBV evidence remain pending. No accepted-baseline replacement, remote-board validation or GitHub publication is claimed.
