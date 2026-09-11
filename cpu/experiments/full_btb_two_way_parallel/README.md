# Two-way BTB with parallel prediction reads

This timing-focused experiment preserves the two-way predictor's replacement, tags, local history, counters and update behavior. Both ways' targets and direction predictions are read independently before the hit result selects the output. It removes the late tag-hit bit from the counter/history memory read address. Storage duplication or LUT savings are not inferred from RTL declarations; native implementation is required.

## Completed physical result: not promoted

Ordinary PDS 20260911-022751-c70713a8 finishes with 9596 LUT / 4433 FF and WNS -0.523 ns. The complete 42-data / 33-trigger / 1024-depth ILA stage build/ila/parallel-seed1 finishes with 10093 LUT / 5114 FF and WNS -0.482 ns at 151.2 MHz. Both fail timing. Against the serial two-way full-ILA build, slack improves by 0.049 ns but total LUTs increase by 424, with identical short execution cycles. This is not an acceptable replacement.

Eleven candidate-specific source/firmware/native-mapping tests pass in build/full-ila-tests.log. The physical-qualification.json receipt keeps timing, resource-efficiency, complete-score and hardware qualification false. A bitstream was generated, but its existence is not a timing pass. This completed result supersedes the historical pending-launch description below. The next isolated experiment is ../full_btb_history4, not another promotion of the failed two-way image.

## Measured motivation

The serial-read predecessor's ordinary PDS run full_btb_two_way/build/physical-project-complete/build/pds/20260911-020416-a810df1b fails at 151.2 MHz: setup WNS -0.705 ns and 9231 ordinary-system LUT. Its worst path runs from next_pc[4] through the folded address, tag read/comparison, fetch_hit_second (fanout 105), counter read and direction selection to next_pc[16]. The reported path has seven logic levels, 1.986 ns logic and 5.011 ns routing delay. Those ordinary LUTs are not the required full-ILA denominator.

## Completed matched execution checks

| Seed | Qualified direct-mapped parent | Serial two-way | Parallel two-way |
| --- | ---: | ---: | ---: |
| V0, ten iterations | 3004340 cycles | 3001251 cycles | 3001251 cycles |
| V1, ten iterations | 3007840 cycles | 2999526 cycles | 2999526 cycles |

Both complete short runs preserve CRC and retired instructions. They save 3089 / 8314 cycles versus the qualified direct-mapped parent, and exactly preserve the serial two-way cycle counts. These are execution screens, not long-run scores.

The independent predictor model passes 72 parameter configurations, 28 compiled fault controls and two observationally equivalent unconditional-history cases, reported by three test methods. Added mutations swap the first and second counter-read banks, proving that both independent direction reads are exercised. See build/predictor-regressions.log.

## Physical implementation

prepare_physical.py captures all twenty physical source inputs from the qualified full system, changing only rtl/rv32_btb.sv. It binds both screen manifests and their outputs and captures the existing native PDS scripts. The immutable generated project is build/physical-project-complete.

After the verified serial two-way full-ILA process exits, ordinary PDS starts as PID 90716, run build/physical-project-complete/build/pds/20260911-022751-c70713a8, at 151200000 Hz and placement seed 1. The final reports are pending; a live process must not be restarted. Full 42-data / 33-trigger / 1024-depth ILA, total-resource/timing checks and paired long runs are still required before promotion. GPIO and UART remain in the physical source set. No accepted score, board baseline, electrical signoff or GitHub state is changed.
