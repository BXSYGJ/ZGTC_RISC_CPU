# History compression screening

Date: September 10, 2026. Parent: the unchanged complete full_control_commit candidate at configured 154285714 Hz. These experiments investigate the execution bottleneck measured in EXECUTION_PROFILE.md; none replaces the qualified candidate or accepted hardware baseline.

## Two storage hypotheses

The earlier full_history4 experiment used four local-history bits and sixteen independent two-bit counters per BTB entry. Its short execution improvement was small, while its full-ILA implementation used 9663 LUT and failed timing. This screen tries to retain some history benefit without that complete counter expansion.

The three full_history_fold0/1/2 variants keep four history bits but only eight two-bit counter banks. They XOR the oldest history bit into bit zero, one or two of the three-bit pattern index, respectively. Fetch prediction and update training use the same folded index; the history shift register still retains all four outcomes.

full_history_shared_confidence keeps all sixteen direction bits but shares confidence among a branch entry's patterns. With the default COUNTER_BITS=2, a correct prediction makes the shared bit strong, and an incorrect prediction makes it weak. A weak entry permits the selected pattern's direction to change to the observed outcome. Allocation initializes all directions to that outcome and confidence to weak. Confidence is per BTB entry, not global across the entire predictor. Sharing it introduces interference between patterns.

Ignoring tags, targets, valid and conditional bits, the parent uses 19 history/prediction state bits per entry; folded history uses 20; shared confidence uses 21; independent full four-bit history uses 36. These are logical state counts, not PDS LUT/FF results or measured resource-efficiency gains.

## Matched ten-iteration results

All eight candidate runs use byte-identical parent firmware and matching compiler flags, clocks and other CPU parameters. Only the BTB RTL differs among the simulation sources and twenty physical source inputs. Retired counts remain 2748941 for V0 and 2749614 for V1, with final CRCs fcaf and c64e. audit_history_screens.py validates source snapshots, current sources, executable/UART/result hashes, parsed counters, firmware metadata and normalized compile commands; build/history-screen-comparison.json holds the paired receipts.

| Candidate | V0 cycles | Extra vs parent | V1 cycles | Extra vs parent |
| --- | ---: | ---: | ---: | ---: |
| Parent | 3060873 | 0 | 3065630 | 0 |
| Fold into bit 0 | 3065812 | 4939 | 3069160 | 3530 |
| Fold into bit 1 | 3065311 | 4438 | 3067998 | 2368 |
| Fold into bit 2 | 3061542 | 669 | 3065750 | 120 |
| Shared confidence | 3082587 | 21714 | 3087435 | 21805 |

All four are slower in both short tests. None is selected as an execution-efficiency improvement. No PDS implementation or long-run metric qualification was performed for these four screens, so this does not establish their physical area/frequency tradeoffs or global Pareto inferiority. In particular, no claim is made that they failed the user's numerical resource-efficiency floor: that metric was not measured for them.

## Verification and preserved failures

Each folded variant passes eight geometry/address/hash cases and three compatibility cases with one-, two- and three-bit histories. A fixed sixteen-entry reference mapping is independent of the RTL fold function. A repeated four-bit sequence covers all sixteen history values; runtime mutations removing the oldest-bit contribution, training the wrong bank and reversing allocation bias are rejected. Total: 33 positive simulator runs and nine rejected mutants across the three positions.

Shared confidence passes 17 parameterized simulator runs across history widths 1/3/4, counter widths 1/2/3, address widths 16/32, index widths 2/8 and hashed/unhashed cases. Three runtime mutants are rejected. An initial test failed to reject strong allocation because its initial repeated outcomes erased the confidence difference; a directed opposing outcome followed by return to the affected history now distinguishes it. Six randomized-bus core/reference runs also pass, each with thirteen traps. The benchmark runs additionally pass the existing compiled warning policy without new exemptions.

The folded-reference test initially used an unfolded write index, then an incorrectly indented correction. Both failed logs are retained; the final reference model and actual RTL comparisons pass. No failed run was relabeled successful. No physical CPU, GPIO, UART, clock or constraint source in the parent was modified.

## Next hypothesis: reduce recovery delay rather than predictor state

Inspection of the current core shows fetch allocation is blocked whenever frontend_flush is asserted. Even when no fetch is outstanding, or the old response completes on that edge, the current logic updates next_pc but waits until a later edge to allocate the target fetch. This is a source-level scheduling opportunity, not yet a measured removable cycle.

A potential isolated experiment can prime a free fetch slot with the redirect address while preserving outstanding-request draining. Prediction metadata must then be generated from the redirect target, not the stale pre-flush next_pc. Repeated redirects, backpressure before request acceptance, zero-latency/held responses, interrupts and FENCE.I barriers all need directed tests. In particular, an old pending prediction update must not advance a newer redirect's next_pc. No shortcut that cancels an accepted bus request or uses stale prediction metadata is acceptable.

Any such change must still preserve GPIO/UART and actual 42-data/33-trigger/1024-depth ILA, pass full source-bound implementation and paired long tests, and meet the unchanged CoreMark/resource-efficiency floors before promotion. The remote-board pre-qualification gate remains in force; Chrome 19476 was not contacted and no GitHub upload occurred.

