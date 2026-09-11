# Four-bit local history with two-bit counters

This isolated candidate changes only the qualified predictor's HISTORY_BITS default from 3 to 4. It retains 256 direct-mapped tagged entries, the folded address index, targets, address guards, invalidation, and two-bit saturating-counter behavior. The selector now uses sixteen counter banks rather than eight; no physical resource saving is implied. It adds 256 declared history bits and 4096 declared counter bits. Measured full-system LUTs remain necessary.

## Completed full-ILA result: rejected

The complete stage build/ila/history4-seed1 finishes with 9606 full-system LUT / 5021 FF and setup WNS -0.438 ns at 151.2 MHz. Timing fails; no long-run or resource-efficiency qualification is issued. The generated bitstream SHA256 is 0B89E5709F650C04D3E05291071F3A676E89D6D45B7AE6E0B8B7E8B5023A8FD1. The complete 42/33/1024 ILA mapping remains verified, but neither a correct mapping nor a generated bitstream establishes timing acceptance.

The ordinary worst endpoint is fetch_prediction[18].CE, whereas the full-ILA worst endpoint is raw_pair_relation[0].CE. Subsequent work in ../full_fetch_prediction_payload isolates a payload-enable change on the qualified three-bit-history CPU; it does not silently promote or combine this failed four-bit image. This completed result supersedes the pending entries below.

## Latest physical step

The ordinary implementation completes with 9121 LUT / 4291 FF and WNS -0.145 ns at 151.2 MHz: timing fails. The full-ILA stage build/ila/history4-seed1 starts as PID 51172 only after the ordinary PDS process exits. Its actual Inserter configuration passes 42 data / 33 trigger / 1024-depth checks. All thirteen source, configuration, firmware and native-map tests now pass in build/full-ila-tests.log. Full-system timing/resources are still pending, and no new qualified score is claimed. This update supersedes the pending ordinary-run and four-test descriptions below.

## Completed execution screen

| Seed | Parent cycles | Candidate cycles | Saved | Execution-efficiency ratio |
| --- | ---: | ---: | ---: | ---: |
| V0, ten iterations | 3004340 | 2998199 | 6141 | 1.0020482296205155 |
| V1, ten iterations | 3007840 | 3004096 | 3744 | 1.0012462983872685 |

Both complete results pass CRC and preserve retired counts, with unchanged full-SoC RTL outside the predictor and unchanged firmware/compiler settings. These short execution gains are not long-duration CoreMark scores or physical timing/resource qualifications. Source, firmware, binary and output hashes are retained in build/v0 and build/v1.

The independent model passes 96 history/counter/index/address/hash parameter configurations, 18 compiled fault controls, two observationally equivalent unconditional-history cases and twelve one-bit-reference compatibility comparisons across four test methods. The four-bit directed pattern exercises the newly added high history bit; masking it from the prediction selector is rejected. See build/predictor-regressions.log.

## Physical follow-up

Ordinary PDS starts as PID 86160, run build/physical-project-complete/build/pds/20260911-024019-50a14ee9, at 151200000 Hz and seed 1. Nine physical-source/metadata tests pass in build/physical-binding-tests.log, including inherited-three-bit and changed-counter-width rejection. Native net discovery in build/probe-nets.stdout.txt confirms core-local pipeline_valid[0..3]; the prepared full-ILA runner uses these actual names and waits for the verified ordinary process to finish. Timing/resources and the remaining four stage-dependent ILA tests are pending; this is not a qualification result.

prepare_physical.py checks the actual history/counter defaults and captures all twenty physical inputs from full_redirect_clock151200, changing only the BTB. The generated project is build/physical-project-complete. Its metadata explicitly records HistoryBits=4 and CounterBits=2 rather than inheriting the parent's three-bit description. A native ordinary PDS launch is serialized after the verified parallel two-way full-ILA process. Timing, full 42-data / 33-trigger / 1024-depth ILA resources, paired long runs and application qualification remain required before promotion. GPIO and UART are not removed. The accepted local and board baselines remain unchanged.
