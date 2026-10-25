# Evaluation protocol v3 — stack partition and observer amendment

## Material Passport

- Date: 2026-09-18, Asia/Shanghai.
- Basis: the v2 full-suite smoke run stopped huffbench at the 4096-byte stack monitor; its algorithm verification did not execute.
- Status: prospective for subsequent runs. Retain v1 and v2 and all their run evidence.

The original 4096-byte reservation was a minimum linker gap, not a measured upper bound for Embench. Pinned huffbench has local frequency, heap, link and code arrays exceeding that budget on RV32. Adopt one uniform 16384-byte stack partition for every subsequent Embench workload and both priming variants. The physical memory remains 65536 bytes at address zero. Do not vary this partition by workload or variant. A linker assertion requires static sections/heap start below address 49152; newlib _sbrk cannot grow beyond 49152. Runtime stack monitoring requires the committed stack pointer to remain in [49152,65536] from platform initialization through verification. Record the minimum observed SP; static-fit and runtime-limit failures are memory_limited, not a failed algorithm verifier. Retain the original v2 failure log and identify its earlier generic status classification in analysis.

The simulation-only observer instantiates unchanged SoC RTL. It verifies every cycle increment and retirement increment against pre-edge retire events, and each snapshot against the simultaneous pre-edge raw counters. Reported UART deltas must exactly match independently observed snapshot deltas. This observer does not change processor RTL and does not substitute for the required physical ILA. First crc32 smoke preceded this observer; use later observer-equipped runs for counter and stack validation.

Measure the upstream support/dummy-benchmark separately as instrumentation context. It is not a twentieth Embench workload, is excluded from suite aggregates, and its cost is not universally subtracted. Keep raw timing boundaries defined by v1/v2.

All other v1/v2 requirements remain in effect, including pristine sources, common compiler, matched firmware, independent timing closure, full-system resources, transparent failures and separate RV32I SERV reporting.
