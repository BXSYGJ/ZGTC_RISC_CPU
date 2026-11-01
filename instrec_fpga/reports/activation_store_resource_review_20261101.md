# Activation row store resource review, 2026-11-01

The dynamic activation store contains no variable-divisor operation. All `/` and `%` expressions divide by the constant 32. The unsigned `scatter/32`, `scatter%32`, and unsigned `scan_next/32` can reduce to wiring. The signed integer `count%32` can require signed-remainder correction unless range analysis removes it. Calling these expressions a dynamic divider would overstate the evidence.

The more urgent risk is memory inference. Each store declares 32 independent 8-bit x 194 lane memories, a raw 49,664 bits; two stores contain 99,328 raw bits. The original template has three syntactically distinct write addresses: native read beat, incoming scatter byte, and final zero padding. Although mutually exclusive functionally, they may prevent inference as a single-write memory. `syn_ramstyle` is a request and does not prove an actual RAM mapping.

The active exact gate's preliminary report at `build/resource_gate/native-20261101-215404-522126/synthesize/apm_drm_lutram_utilization.log` contains no `u_store0` or `u_store1` memory entry. It explicitly lists conv/pool/wbuf/WDMA DRM entries. Its only store entries are two APM multipliers, `u_npu/u_store0/N6_m1` and `u_npu/u_store1/N6_m1` (24-bit unsigned by 2-bit unsigned). This is a strong warning to inspect final FF/LUT totals and final mapped netlist. It is not yet proof of the exact realized store resource count. Raw bit capacity alone cannot establish whether the eventual implementation uses 16, 32, or another number of DRM primitives per instance.

## Exact topology synthesis evidence

The 21:54 native gate's hierarchy report now confirms the failure: `u_store0` uses 42,441 LUT / 50,140 FF / 0 DRM / 1 APM; `u_store1` uses 42,445 LUT / 50,140 FF / 0 DRM / 1 APM. Their combined 84,886 LUT and 100,280 FF dominate the full topology's 115,473 LUT / 133,439 FF / 88.5 DRM / 92 APM. The full topology cannot fit the device. This is synthesis evidence, not a routed result.

At 22:31 the over-capacity gate remained in `Saving design to DB`. Following the coordinator's explicit instruction, its synthesis child PID 36212 was identity-checked and stopped; the parent PID 43724 exited naturally. The resource report, RAM utilization log, SHA256 values and complete process command lines were preserved in `build/resource_gate/native-20261101-215404-522126/interrupted_capacity_evidence/`. No bitstream was generated. The isolated original/narrow serial probe began only after both PDS processes exited.

## Isolated candidate and functional evidence

`sim/experiments/activation_store/activation_row_store_narrow.v` keeps the external protocol and state transitions unchanged while:

- Using bounded unsigned counters: row 6 bits, group/lane 4, column/beat 8, byte count 13.
- Replacing constant-32 remainder/division with explicit byte/bank address slices.
- Using one canonical `if(mem_we) mem[mem_wa] <= mem_wd` write per lane bank, with write-source muxing outside the RAM process.
- Preserving the synchronous RAM read, read-before-write behavior, final half-beat padding, output lookahead, and row-credit timing.

Run `python sim/experiments/activation_store/run_narrow.py`. It compares the original and candidate cycle by cycle for all control/address outputs, plus valid write and read data, while running the existing full-size reorder truth checks with command/write/output stalls, delayed reads, withheld row credit and live configuration changes after start.

Result: PASS all three geometries. Pool1: 198,144 bytes / 6,208 written and read beats. Pool2: 98,304 bytes / 3,072 beats. Pool3: 49,152 bytes / 1,536 beats. Log: `build/sim/activation_row_store_narrow/run.log`. This is simulation equivalence for these supported geometries, not formal proof or physical mapping evidence.

## Prepared isolated mapping comparison

`python sim/experiments/activation_store/prepare_map_probe.py` prepares, never launches, frozen original and narrow single-module probes. Current prepared directory: `build/resource_gate/activation-isolated-20261101-221150-865259/`.

Each variant includes frozen RTL, identical observation wrapper, clock constraint, `build.tcl`, hashed manifest, and `launch.ps1`. `launch_compare.ps1` runs original then narrow serially and each launch refuses to run while any `pds_shell` exists. Both TCLs stop after `compile -> synthesize -> dev_map`; neither contains PnR or bitstream generation. The launch scripts parsed successfully with the local PowerShell parser. No probe has been launched by this review.

The identical wrapper supplies independent read-data words through a 256-bit shift register and observes every write-data word through XOR, keeping top-level I/O count small. Its logic must be included equally in both area totals. Compare final FF/LUT/DRM/APM counts and the actual `unit_under_test/lane_bank` RAM entries; do not infer RAM success from `syn_ramstyle` or successful compilation alone. The isolated probe estimates single-store resource cost and RAM recognition, and has no production functionality, timing closure, routing or board meaning.

## Completed narrow mapping result

At 22:38 the original isolated synthesis was interrupted at the coordinator's deadline during tech-mapping phase 2; its logs and process identity remain in the original build directory. It has no completed isolated result. The exact full-topology synthesis hierarchy above supplies the original store baseline.

The narrow probe then completed compile, synthesis and dev_map in 39 seconds at 22:39:08: **794 LUT / 343 FF / 16 DRM / 0 APM**, including the common observation wrapper. The RAM report contains the lane-bank inferred memory entries. Canonical single writes have therefore restored physical RAM inference in the isolated candidate. The complete synthesis and device-map reports, RAM utilization report, frozen-input manifest, candidate source hash and result manifest are preserved under `reports/activation_store_narrow_20261101/` for Git tracking.

The narrow full-topology snapshot is `build/npu_production_candidate/narrow-20261101-223829`, snapshot manifest SHA256 `90d527f68fdac3cc272802eccf48b7889fad7aaa523b3e4068fec690c5420cb9`. A new gate was prepared at `build/resource_gate/native-20261101-224112-909881` with 45 frozen RTL files, 2 frozen constraints and 89 frozen IP files (99 entries including directories). The helper now requires snapshot IP and build TCL, and includes generated TCL/build-set/snapshot metadata in launch-time hash verification. After native A/B double-run PASS and explicit coordinator approval, all inputs and copied IP hashes were checked and this sole gate started at 22:41:58, parent PID 44080. It stops after dev_map and creates no bitstream. Isolated success does not establish full-topology capacity, timing, routing or board behavior.
