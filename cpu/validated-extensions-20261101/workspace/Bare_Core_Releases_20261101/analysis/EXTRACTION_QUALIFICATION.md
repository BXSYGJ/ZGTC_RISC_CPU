# Bare-core extraction qualification

All three pure-core wrappers passed fresh local RTL extraction tests. Each baseline and restored run compared every core input/output with an independent original SoC reference over 2,000,000 CPU edges. The reference and bare DUT each used a separate copy of the same existing cached memory and peripheral services, outside the eight-file DUT.

| Core | Compared bits | Comparisons per run | Retired | List / matrix / state entry retirements | Full-port digest |
| --- | ---: | ---: | ---: | --- | --- |
| Original_155250 | 614 | 4,000,000 | 1,834,318 | 13 / 27 / 27 | `cbcd7a3d93db2dce` |
| H3_Base_145125 | 646 | 4,000,000 | 1,875,092 | 13 / 28 / 28 | `31cacc7862e90ed8` |
| H3_Retained_145125 | 646 | 4,000,000 | 1,875,199 | 13 / 28 / 28 | `dcae4a8359c9a932` |

The shared clock and reset are identically driven. Original exposes 616 total port bits; H3 exposes 648, including its separate pair-fetch address. All remaining 614/646 bits are compared without masking invalid-cycle payloads, before every edge and after its settled high/low clock evaluation. This includes requests, responses, retirement PC/instruction/register write, trap fields, pipeline-valid bits, maintenance, timer/interrupt inputs and both full 64-bit counters. Ten additional service/MMIO/serial status groups are compared. The digest records the compared frames; direct signal equality is the pass criterion.

For every release, the negative control changed only the bare DUT's `d_rsp_data` input at edge 10000. The comparator detected that exact first difference and the process exited 1. A separate fault-free process then ran another 2,000,000 edges with exit 0 and reproduced the complete baseline JSON byte hash. Functional RTL and original source files were unchanged.

## Source and completed benchmark join

Each release preserves exactly these eight RTL files: `rv32_core`, `rv32_rvc_frontend`, `rv32_rvc_expand`, `rv32_decode`, `rv32_alu`, `rv32_muldiv`, `rv32_btb`, and `rv32_machine`. Every source hash joins the bare wrapper, accepted waveform build and the actual compiled source copies of its completed 6000-iteration original SoC simulation. Parameters and complete port widths match. Both firmware identity and the external cache/peripheral RTL identity also match.

| Completed original source simulation | 6000-iteration measured cycles | Retired | IPC |
| --- | ---: | ---: | ---: |
| Original_155250 | 1,782,669,419 | 1,649,428,429 | 0.925257600 |
| H3_Base_145125 | 1,743,221,870 | 1,649,428,429 | 0.946195351 |
| H3_Retained_145125 | 1,743,134,699 | 1,649,428,429 | 0.946242668 |

The full simulation rows above are completed original SoC executions. The new bare wrapper has a fresh finite 2M-edge extraction qualification. It was not rerun for all 6000 iterations. Exact unchanged source/configuration/firmware identity and the extraction miter support the behavior-preservation join; this finite test is not an exhaustive formal proof or additional full benchmark execution.

## Memory service and area interpretation

The synthesized DUT excludes all caches, backing RAM, arbiters, uncached bridges and MMIO peripherals. Its unchanged RV32IMC frontend/predictor, register file/pipeline, full machine CSR/interrupt/exception logic, 64-bit counters and multiply/divide unit remain inside. Existing services are external testbench components: enabled I-cache (set bits 9), D-cache (set bits 6), 64KiB RAM, original pair-fetch metadata, ready/valid timing, UART/MMIO and timer behavior. Two independent instances avoid feeding the DUT the reference's responses.

Any joined execution-efficiency or CoreMark-per-area metric must say **core-only area with explicitly external cached-system services**. It is conditional on this service and is not a standalone cacheless-memory CoreMark result or whole-system area efficiency. Physical resource/frequency receipts must use the same source/parameters and separate core area from the scan fixture. The physical pipeline owns those receipts.

All results are LOCAL RTL SIMULATION. The configured FPGA targets are 155.25 / 145.125 / 145.125 MHz. Simulation UART parameters are CLOCK_HZ=3200 and BAUD=100; neither is a measured hardware clock or baud. Original retains its established Verilator 4.038 behavioral memory recipe; H3 uses Verilator 5.032 and the actual timed native memory model. No remote board or hardware measurement was used.

## Reproduce and review

PowerShell 7:

```powershell
$runner = [System.IO.Path]::Combine('D:/AAAFPGA','Bare_Core_Releases_20261101','analysis','qualification','Invoke-ExtractionMiter.ps1')
& $runner -Release Original_155250,H3_Base_145125,H3_Retained_145125 -Cycles 2000000
```

`EXTRACTION_QUALIFICATION.json` contains the independently reopened source joins, complete commands, literal outputs and actual 0 / 1 / 0 process statuses. Per-release `*-EXTRACTION_QUALIFICATION.json` links the immutable run directory, compile receipts, source snapshots, full signal map, raw stdout/stderr, baseline/rollback JSON and simulator hash. `qualification/audit_extraction_results.py` reopens and verifies these chains without rerunning the benchmark.
