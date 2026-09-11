# Forwarded-relation reuse with complete peripherals and ILA

## Scope and source identity

This candidate descends from `full_id_relation_mask1`. Only the CPU changes; GPIO, UART, cache geometry, predictor, interrupts, exceptions, firmware, PLL and constraints remain unchanged. The ILA retains all 42 data channels, 33 trigger channels and 1024 samples. No hardware score or accepted-baseline replacement is claimed.

CPU SHA256: `707941FBAF4B5E73EDF3380022C4EA32D109446BA78D3B8CA6608DCAF131065B`. BTB SHA256: `74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E`. `change-receipt.json` reconstructs both the one-line immediate-parent change and the complete qualified-ancestor delta.

The EX relation refresh reuses `early_result` only when `LOAD_USE_BUBBLE != 0`. In that configuration the existing parallel relation/forwarding selection matches `operand_relation(forwarded_a, forwarded_b)`. The original comparator remains for bubble-disabled configurations because their forwarded operands can include the current MEM load value, which the early comparison path excludes. Reset, ID-capture priority and operand-register updates are unchanged. This is not the previously rejected late comparator-input-multiplexer experiment.

## Functional evidence

- Five source-delta tests reconstruct the exact change.
- `build/core-regressions-coverage-groups/manifest.json` records sixteen core/cache tests: predictors off/on, load-bubble off/on, three uncached seeds and one production-geometry cached run per configuration. Independent instruction traces and final memory match in all sixteen runs.
- Both cached/uncached load modes cover MEM forwarding, WB forwarding, stalls and loads across each mode group. Every bubble-enabled run exercises the live relation-reuse equality invariant; bubble-disabled runs retain the original path.
- `build/relation-tests-186e1eff/manifest.json` records three methods and eight compiled cases: live parent/candidate cached comparisons in both load modes and four rejected faulty CPUs. Positive pairs have byte-identical traces, final memory and execution logs. Mutations remove the bubble guard, corrupt signed comparison, freeze refresh or drop ID capture; all fail the active-EX invariant.
- `build/v0` and `build/v1` retain byte-identical parent UART output, with 3000565 / 3001255 cycles and CRC fcaf / c64e. Short runs are not long-run scores.
- `build/external-isa/audit.json` passes pinned RV32UI/RV32UM: 164 + 32 positive executions across four configurations, plus eight rejection controls. Four coverage/negative-result audit tests pass. This is not complete ISA certification; misaligned accesses are expected to trap.

The first local regression attempts exposed testbench assumptions, not qualified CPU failures: the original cached bench assumed load bubbles, and per-seed forwarding coverage was too strict for some predictor-enabled seeds. The revised bench explicitly checks direct MEM-load forwarding in bubble-disabled mode and requires coverage across each complete mode group. Failed attempts remain in `build/core-regressions` and `build/core-regressions-load-modes`; only the sixteen-pass coverage-groups manifest is staged.

## Physical evidence

Ordinary PDS `20260911-082214-6a099604` is terminal: configured 151.2 MHz, 9191 post-route LUT, 4339 FF, setup WNS +0.235 ns, all timing constraints met. Bitstream SHA256: `DB2C2F02CE9C24BB4B6B7BCC8118DFBF84A235B3594F3A515DDC0BEDCF30BA8E`. This ordinary build excludes the required inserted ILA, so 9191 is not the score denominator.

`build/synthesis-comparison.json` binds the raw parent/candidate reports and staged sources: total synthesized LUT 8753 -> 8727, carry cells 1611 -> 1567, LUT7 multiplexers 451 -> 493; total FF stays 4305. Inclusive core LUT 4073 -> 4059. Do not add nested hierarchy counts or interpret these synthesis changes as complete post-route savings.

The first ILA staging attempt, `relation-reuse1-seed1`, stops before native implementation because Inserter drops the unavailable core-local MEM-valid alias. A native `ins_list_nets` probe proves the exposed net is `board/soc/unused_pipeline_valid[3]`. The revised audit proves its SoC port connection back to core `pipeline_valid[3]` and checks the actual `mem_valid` register Q driver. It does not fabricate or silently omit a data channel.

The corrected stage is `build/ila/relation-reuse1-seed1-native-alias`. Actual Inserter output validates 42 data channels, 33 trigger channels and depth 1024. Twelve binding/mapping tests pass, including wrong register drivers, wrong MEM alias connection, missing channels, changed source inventory and firmware. The initial mutation-test anchor was corrected to the exact CPU-instance port connection; production connectivity checks remain strict.

Complete ILA PDS is terminal: **151.2 MHz, 9653 total LUT, 5055 FF, setup WNS +0.108 ns**, all timing constraints met. Bitstream SHA256: `FBD3D625F5A928BCF88EFD4616FBE9F97101BC8FEDC634E7E40B928F8BD8E52E`. The full-system area is 21 LUT above the immediate parent despite the synthesis reduction. It is not promoted.

The limiting path now runs from timer_value[1] through the 64-bit increment, timer-value write selection and timer comparator to irq_timer (16 logic levels, 2.439 ns logic, 3.583 ns routing). The next two setup paths end at mem_result with +0.131 / +0.132 ns slack. Timer optimization alone therefore does not prove a higher usable clock.

At 9653 LUT the resource floor requires at least 515.9790371065852 CoreMark. If the parent long-run execution efficiency were preserved, that would require at least 154.39474324100883 MHz; this is a conditional planning calculation, not a candidate score or validated clock. At the unchanged parent score, 200 LUT would need to be removed to reach the 9453-LUT ceiling. No paired long-run score, resource-efficiency gate, application-image acceptance or hardware qualification exists for this candidate.

A separate `full_timer_prefix16` child investigates the measured timer carry path using parallel 16-bit increments without adding timer latency or removing peripherals. SCBV and remaining electrical evidence remain open. No remote-board access or GitHub publication was performed.
