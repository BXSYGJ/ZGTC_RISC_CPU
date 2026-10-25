# Protocol v27: iterative redirect recovery optimization

Frozen 2026-09-20. Origin: academic-research-suite experiment workflow, execution mode. New candidate benefits are UNVERIFIED until their stated gates pass.

## Objective and comparisons

Iteratively improve redirect recovery at configured 153 MHz. Express every performance gain relative to a matched priming-off design. Also report incremental changes against current priming and the best fully qualified incumbent. Promotion requires no degradation in overall CoreMark score or complete-system resource efficiency against current priming and the incumbent. CoreMark V0 and V1 are distinct configurations, not seeds. Report measured cycles, retired instructions, CPI, correctness, and workload-level regressions. Do not infer hardware performance or timing closure from simulation.

Keep the accepted full_fetch_commit_factored tree, upstream sources, and all prior evidence unchanged. New sources and runs belong in versioned variants/results directories. Priming-off disables only the original priming allocation gate. Preserve the original fetch-commit enable factoring, nominal 256-entry BTB, existing cache geometry, single-issue in-order pipeline, GPIO, UART, and 42-data/33-trigger/1024-sample ILA. Additional instruction buffering is an explicitly separate factor.

## Frozen firmware and staged experiments

Use the v26 relocated Embench firmware from embench-loader-firmware-20260918T075837Z-7e6f9c1f, verifying its source and binary hashes. Execute the actual loader and UART RAM upload in RTL and on hardware, with identical application bytes, heat=1, scale=1, 16 KiB stack, and cold initial state. Do not substitute earlier v3/v25 cycle counts for these matched controls. Retain the dummy without subtracting its counters.

Start with off, current priming, and an earlier-target-request candidate. The latter issues only with no outstanding fetch or while completing the old response. It must preserve a stalled request, discard stale responses, maintain MEM redirect priority, and associate fresh prediction metadata with the correct target and successor. The existing next-PC enable factoring equations remain fixed. Any new predictor-to-request path must be timed; apparent request-latency savings are not assumed to reduce execution cycles.

Profile redirect categories, slot eligibility, request stalls, outstanding-response waits, cache states, target reuse, and target-delivery latency. Assess a single pending-target queue against existing overlap; reject a queue-only hypothesis if no removable bubble exists. Then evaluate directly indexed 4/8/16-entry buffers of tagged target instruction words. Invalidate on reset and FENCE.I; never bypass access-error checks or cancel accepted external transactions. Compare buffering separately and in combination with early issue. Follow evidence to additional candidates rather than declaring the first passing candidate optimal.

Run short smoke workloads first, then all 19 Embench workloads plus dummy, CoreMark V0/V1, and independent architectural/interrupt/transaction regressions. Extend tests for simultaneous redirect/response, request backpressure, repeated redirects, fresh BTB metadata, traps, errors, reset, instruction/data coherence and FENCE.I. Screening runs may precede complete regressions, but must be labeled unqualified and cannot support promotion.

Use three cold repetitions for final matched simulation and hardware results. CoreMark screening uses identical short-run binaries; hardware qualification uses identical loader-compatible 6000-iteration binaries, existing compiler flags and console pacing, with duration and CRC checks. Any new port has its own hashes and must pass independent counter-boundary checks. Counter differences caused by timer polling must be explained from traces, not forcibly equalized.

## Physical qualification and selection

Use native Windows PDS 2022.2-SP6.4 ADS, PG2L200H-6FBB676, matching constraints and full ILA. Independently implement each candidate and matched controls at 153 MHz, seeds 1, 2, 3 in that order. Preserve all timing failures. Select the first passing seed for hardware; report all seeds rather than selecting a favorable resource result after measurement. Do not lower the clock to qualify a candidate for the 153 MHz objective.

One qualified loader bitstream per RTL variant supports all applications. Cold-program before every observation to reset RAM/caches/predictor/counters; repeated programming does not require repeated synthesis. Record board identity, programming receipt, image hash, upload CRC32, UART bytes, counters, complete-system LUT/FF/BRAM/DSP, setup/hold slack, and configured versus measured clock separately.

Promotion requires all correctness gates, independent timing closure, nondecreasing CoreMark V0 score and score/LUT, nonincreasing V1 cycles, and improved Embench geometric-mean throughput and throughput/LUT versus current priming and the incumbent. Compare at identical firmware and clock. Report each workload's changes. Rank qualifying candidates by Embench throughput/LUT; ties prefer fewer LUT, then fewer FF. Unsupported, memory-limited, integration-failed and timing-failed configurations remain explicit results.

## Evidence and stopping

Each immutable run records source hashes, tool identity, exact commands, exit status, firmware hashes, raw logs and CSV/JSON. Scripts must refuse to overwrite runs and must bind each model to its variant manifest. Historical evidence is context only. Record rejected ideas and why, including timing/area costs, prediction bubbles, blocking misses and interaction effects.

The goal remains active while plausible untested candidates or required qualification remain. A finite search cannot prove universal architectural optimality: any final exhaustion claim must state the explored transformations and measured limits, and cannot silently replace the user's broader objective with one successful prototype.
