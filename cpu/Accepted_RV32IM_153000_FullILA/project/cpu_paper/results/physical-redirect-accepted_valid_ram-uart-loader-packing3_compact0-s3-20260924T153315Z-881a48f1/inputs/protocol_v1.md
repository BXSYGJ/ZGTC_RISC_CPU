# Evaluation protocol v1 — 2026-09-18

## Material Passport

- Origin: user-authorized engineering evaluation; academic-research-suite experiment workflow, performed inline.
- Verification status: prospective protocol; no new performance or physical result implied.
- Version: v1. Amendments require a new numbered file and identify affected runs.

## Research questions and frozen controls

Evaluate Embench portability, workload-dependent redirect-priming effects, and controlled complete-system comparisons. Positive gains are hypotheses. Accepted historical measurements are context only.

Reference: `../cpu/experiments/full_fetch_commit_factored`. Preserve all reference and upstream bytes. All new inputs and outputs live under `cpu_paper`. Verify every file in `third_party/SOURCES_LOCK.json` before execution. Record tool binaries, versions, commands, source hashes, firmware hashes, and all failures in unique run directories; never reuse a completed run directory.

A is final RTL with only early redirect-target allocation disabled; B is byte-identical final behavior. Keep fetch-commit enable factoring, nominal 256-entry BTB, cache sizes, pipeline, GPIO, UART and full 42-data/33-trigger/1024-sample ILA fixed. Audit the exact RTL diff before A/B use. Historical DC90363D is not A. Validate outstanding/draining fetches, backpressure, repeated redirects, reset, conditional branches, JAL/JALR, exceptions, interrupts and FENCE.I before performance interpretation.

## Firmware and memory

Freeze GCC 10.2.0 from the recovered historical toolchain where usable: RV32IM, ILP32, no compressed instructions, O3, loop unrolling, linker relaxation, no LTO. Archive the full flags and compiler/library hashes. Embench uses its locked 19-workload inventory, unchanged workload sources and local scale factors, global scale factor 1 and warm-up heat 1 for initial functional runs. These are smoke/cycle observations, not an official normalized Embench score. Increasing scale requires a new configuration shared by both members of each pair.

The accepted SoC has one 64 KiB memory, beginning at zero. Reserve at least 4096 bytes for stack; document code/rodata/data/BSS and remaining capacity, and assess dynamic stack/heap separately. Do not enlarge memory or reduce optimization selectively to conceal failures. Soft floating-point library use is permitted with an RV32IM compiler and must be recorded. Keep missing library support, link failures, verification failures, timeouts and memory limits visible.

Call initialization, then warm-up, then start timing, benchmark, stop timing, then verification/output. Require the upstream verifier to return 1; -1 is unverified. Use the SoC's atomic 64-bit cycle/retirement snapshot register at 0x10000400 and subtract snapshots modulo 2^64. Both counters cover the same interval; timing includes snapshot-read/start-hook overhead and stop-hook entry, which must be disclosed. Record raw deltas without guessed overhead subtraction. An empty interval characterizes overhead but does not justify universal subtraction. UART is outside timing. CPI is null unless both same-boundary counters are valid.

CoreMark V0 performance and V1 validation are separate configurations. Pair identical ELF/BIN/HEX, flags, input, initial state, warm-up and iteration count; never compare V0 to V1 as repeats. Short runs are smoke tests; reportable CoreMark requires upstream validation and duration rules.

## Execution and physical gates

Use fresh reset for each run. First smoke each available workload on B. Then validate A and run matched A/B pairs. Three deterministic repeats are planned for scored pairs; retain each result and investigate any mismatch. Simulation randomization seeds, workload inputs, repetitions, and placement seeds are separate fields. Simulation covers RTL cycles and architectural correctness, not board qualification or physical ILA acquisition.

Use Windows PDS 2022.2-SP6.4 with ADS, PG2L200H-6FBB676, and copied accepted board constraints. Serialize implementation. First target 153 MHz independently for A and B, with placement seeds 1, 2 and 3. Retain failed targets. If necessary test common lower targets in the predefined order 150, 144, 132, 120, 100, 75, 50, 25 MHz, subject to supported PLL settings; do not invent unsupported clock configurations. Report every attempted target/seed and choose a common target passing setup/hold and constraint audits for every included variant/seed. The highest passing tested target is not measured Fmax. Configured clock and independent measurement are separate fields.

Physical results must include complete-system CLMA+CLMS LUT (distributed RAM not double-counted), FF, BRAM, DSP, setup/hold slack, constraint coverage, PLL configuration, tool/seed, firmware, source and constraint hashes, reports and bitstream identity. The complete debug/peripheral obligation is retained even when a simulation omits the physical debug wrapper. No resource result can come from a bare-core simulation model.

## Comparator policy and stage gate

After the matched ablation stage, configure VexRiscv, PicoRV32, Ibex, SERV+MDU from their pinned sources. Plain SERV RV32I is a separate ISA configuration. Include all bus adapters and MDU resources. Freeze generator/plugin/register-file/multiplier/cache parameters and dependency hashes in a comparator protocol amendment before measurement. Do not declare an ISA-equivalent RV32IM comparison until the MDU and each core pass correctness tests.

Reuse external memory capacity/latency, peripherals, constraints and compiler policy. Prefer common benchmark binaries when the runtime permits. Document necessary startup/counter/binary differences. Preserve project caches; label native cache configurations as system comparisons rather than pretending internal caches match. Per-core ILA mapping must preserve the stated signal-width/depth obligation with documented semantics. Common-frequency comparisons and highest independently closed tested-frequency comparisons remain separate.

## Evidence and analysis

Each row contains run/protocol/variant/workload/input IDs, source and firmware hashes, measurement kind, warm-up/scaling, cycles, retired instructions, CPI or null, correctness/status, configured and measured clock or null, resources or null, setup/hold slack or null, repetition and placement seed, and evidence paths. Status vocabulary: pending, passed, verification_failed, unsupported, memory_limited, build_failed, integration_failed, timed_out, timing_failed. Missing measurements are null, never zero.

Compute cycles saved = A-B; speedup = A/B; cycle reduction = (A-B)/A. For differing independently closed configured clocks, elapsed-time ratio = (A/fA)/(B/fB), explicitly derived. Use geometric means of valid per-workload ratios with exact coverage and common-workload intersection; do not pool cycle counts. CoreMark = iterations*f/cycles only when score conditions hold; report CoreMark/MHz and CoreMark/complete-system LUT. Never use speedup/LUT overhead. Preserve neutral/negative results and all excluded cases. The historical 1.88% figure is not an expected universal effect.

Only after correctness, cycle, physical and comparator evidence is complete may paper figures/tables/manuscript claims be prepared. No automatic publication, push, deletion, upstream modification, or accepted-evidence replacement is authorized.
