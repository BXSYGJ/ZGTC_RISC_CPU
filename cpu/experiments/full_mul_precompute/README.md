# Independent multiply precompute

Experimental only. Preserve accepted DC90363D pipeline, GPIO, UART, and full ILA requirements. No score, timing, or resource qualification yet.

When an independent MUL enters EX, use the existing idle partial-product registers to compute its operands one cycle earlier. Qualification excludes dependencies on all valid EX/MEM writers and any occupied multiplier. WB forwarding already exists at ID operand read. The one-cycle validity marker expires on a stall, falling back to normal execution; cancellation and exceptions retain existing priorities. Other M operations keep the original state machine. This is not the previously rejected combinational low-multiply implementation.

Only the CPU and multiplier RTL change. Before promotion, require arithmetic/backpressure/cancellation tests, CPU dependency and exception checks, actual identical-firmware V0/V1 simulations, full-ILA routed timing and resource efficiency, and hardware qualification.

## Verified short-run progress (September 10, 2026)

| Ten-iteration seed | Accepted DC baseline cycles | Candidate cycles | Cycles saved | Cycle reduction |
| --- | ---: | ---: | ---: | ---: |
| Performance | 3151519 | 3060873 | 90646 | 2.876264% |
| Validation | 3156276 | 3065630 | 90646 | 2.871929% |

Both CRCs pass. Retired counts, complete reported cache statistics, firmware bytes, simulator driver, compile flags, and hardware parameters match the corresponding accepted-baseline short run. Only CPU and multiplier RTL differ among simulation inputs. `audit_short.py` rechecks source snapshots, executable, firmware, UART, and result hashes. This is approximately 2.96% more modeled throughput, not a new hardware CoreMark score. Both measured windows are below 0.02 seconds.

Validation completed:

- Four `test_precompute.py` methods: exact source delta, 12544 original arithmetic/protocol checks with precompute enabled but marker absent, 8950 precompute arithmetic/holding/cancellation checks across 2048 trials, and four rejected runtime mutants.
- Six randomized-bus CPU/reference runs and two I9/D6 cached CPU/reference runs pass; these general core regressions are not specific proof of the new M path.
- Fourteen precise M interrupt/cancellation/restart runs pass. The local interrupt adapter handles immediate precomputed low MUL before acceptance; DIV and high MUL keep their original injection points.
- Pinned RV32UM: eight tests, 32 configurations/runs, and four expected rejection controls pass under `build/isa/20260910-182943-c2f787ee`. This is not full ISA certification.
- Read-only arithmetic observation of actual CPU execution covers 122 precomputed and 82 fallback low multiplies across four ISA MUL runs. Retirement traces and final memory match their uninstrumented runs after OS newline normalization only. These runs observe zero expired markers, so they do not prove stall-expiry coverage.
- Artifact tampering controls reject changes to firmware, UART, result, executable, source, and passed status.

Initial test harness failures were not RTL arithmetic failures: the wildcard unit instance needed the new marker tied low; the exact-delta receipt needed to describe the removed trailing blank line. Observer reporting was made one-shot, and Windows/WSL newline differences are normalized explicitly.

## Physical gate still required

Fresh ordinary PDS run: `build/pds/20260910-182838-6e4c465e`, seed 2, 157.5 MHz, exact accepted 6000-iteration V0 firmware. This ordinary build is preliminary, not the full-ILA comparison against 9374 LUT. No promotion or GitHub upload is authorized by short-run improvement. Full 42-data/33-trigger/1024-depth ILA insertion, full-system routing, paired long tests, and hardware qualification remain required. GPIO/UART source and all other baseline RTL remain unchanged.

## Physical status at handoff

The ordinary run terminated with **8996 post-route LUT, 4267 FF, and setup WNS -0.193 ns**. It fails the 157.5 MHz timing requirement. The matching ordinary accepted-core run has 8996 LUT and WNS -0.157 ns; neither ordinary result substitutes for the accepted full-ILA hardware qualification.

A new full-ILA implementation is running in `build/ila/20260910-mul-precompute-seed2`. Actual Inserter verification and source-bound audit confirm 42 data channels, 33 trigger channels, depth 1024, and `cpu_clk`. Two optimized pipeline probes use aliases proved by the current synthesized CPU output connections. Failed initial path/canonical-name attempts are preserved, not treated as successful verification. The invocation records exact input hashes, process identity, and completion status; `qualify_full_ila.py` checks fresh outputs, timing, and channel dimensions after termination.

Timing qualification explicitly does not grant a resource-efficiency or hardware score. A higher LUT count is not automatically disqualifying if measured long-run throughput compensates, but no such compensation is claimed from short tests. Marker-expiry stress coverage, broader SoC regression, paired long runs, and hardware closure remain outstanding even if this physical run passes.

## September 10 follow-up

The first full-ILA implementation completed with 9373 post-route LUT, 5002 FF, and **WNS -0.251 ns** at 157.5 MHz. It is not qualified for hardware. Its timing estimate, 151.5152 MHz, is below the roughly 153 MHz provisional score-preserving floor from the short-run ratios; an unconstrained clock reduction would not satisfy the revised goal. A timing-directed child is isolated in `../full_mul_precompute_compare`.

New CPU bus-level expiry tests pass eight predictor/delay combinations (delays 0, 1, 8, 31), with four correct retired multiplies and two stores each. Six combinations observe two expired precompute markers. A real sticky-marker RTL mutation is rejected by the next-cycle expiry assertion. No internal pipeline signal is forced; the test delays data-bus responses.

GPIO diagnostics pass both configurations with 2976 checks each and three interrupts each. The M-enabled fast configuration is included. Four M-enabled SoC tests pass: two normal cases with 74 checks, 23 UART bytes and software/timer/external interrupts, plus two fault cases with 41 checks. The local SoC bench enables M explicitly; the RV32I firmware remains a peripheral integration test rather than an M arithmetic test.

The revised metric policy permits lower clock only when exact CoreMark, execution efficiency, and resource efficiency do not fall below the accepted baseline. Source-only policy helper: `../../scripts/frequency_target500.py`, `compare_execution_clock_tradeoff`. Six new boundary/type tests and all seven historical-policy tests pass; the old policy remains available for historical evidence. Numeric-policy approval never grants timing, firmware, ILA, or hardware qualification.

