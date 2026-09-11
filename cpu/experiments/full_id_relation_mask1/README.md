# ID relation validity factoring

## Status

Isolated candidate `full_id_relation_mask1` starts from `full_decode_payload1`. Ordinary PDS `20260911-063921-2a052d9e` completes at 151.2 MHz with 9211 LUT / 4317 FF and setup WNS +0.023 ns. Complete V0 ILA implementation `build/ila/id-relation-mask1-seed1` also passes: **9632 total LUT / 5029 FF / WNS +0.052 ns**. Native mapping and all 21 full-ILA audit tests retain 42 data channels, 33 trigger channels and 1024 samples. V0 bitstream SHA256 `97E7FA282A6DE2CC6838292502117ECCE4F05A24F1CAAACE1336CEC1759BFC3F`.

The full-system worst path is now MEM result bit 4 through control to fetch_prediction[27].CE, ten logic levels with 1.951 ns logic and 4.177 ns routing; it meets timing. Passing timing does not establish resource efficiency or a new score. At 9632 LUT, the exact baseline resource floor requires at least **514.8565301368102 CoreMark** (3.40513578132811 CoreMark/MHz at 151.2 MHz). This is a requirement calculation, not a predicted result.

Pinned independent ISA execution and its four auditor tests pass: 164 RV32UI and 32 RV32UM runs plus eight rejection controls. Invocation SHA256 `6C76168627F6D8BDDFB18D809F8A3BBCCDA52CA041221A65A0059200595672A0`. This is not complete ISA certification.

Both source-bound 6000-iteration simulations have completed successfully in `build/long-v0` and `build/long-v1`. Seven long-run gate tests pass before launch. `run_long.py` preserves the verified reference compiler command, simulation/UART model clocks, exact long firmware and current physical RTL; allows 6000000000 cycles with a 7200-second execution timeout; rejects short durations and changed physical inputs. The V0 physical gate is only an RTL/timing prerequisite for the V1 simulation, not a V1 image or joint-score qualification.

Separate V1 ordinary implementation `20260911-065629-53494b7b` completes at 9211 LUT / 4317 FF / WNS +0.023 ns. Fresh native discovery and actual 42/33/1024 V1 mapping pass all 21 V1 audit tests. V1 full-ILA run `id-relation-mask1-v1-seed1` also completes at **9632 LUT / 5029 FF / WNS +0.052 ns**. V1 bitstream SHA256 `C8521F5826DC1D10BB02A12020645D29BFC1911594CD2ACFC03D010AD4EB8709`. Both benchmark images and both long simulations now pass their individual checks. The joint audit rejects resource efficiency; board scores and baseline replacement remain unqualified.

## Measured motivation

The immediate parent fails complete-system timing at -0.041 ns with 9566 LUT and 5048 FF. Its worst path runs from register_valid[2] through the ID operand mask and comparison to raw_pair_relation[0], with ten levels, 2.052 ns logic and 3.984 ns routing. The other setup violation is -0.016 ns into MEM result bit 22. This candidate targets the first path; it does not assume the second path or area requirement is solved.

## Exact change

Three source substitutions add a masked relation function, two validity selectors and replace only the ID-to-EX raw-pair relation calculation. The unmasked register/WB muxes already used by guarded multiplier prefetch are reused. Raw comparison runs before the late validity selection; equality, unsigned less-than and signed less-than against a forced zero are selected afterward. Both unavailable operands produce the relation for zero versus zero.

Ordinary ID operand masks, register initialization contract, x0 handling, forwarding order, EX refresh, ID capture priority, all interfaces and pipeline control remain unchanged. GPIO, UART and the complete 42-data / 33-trigger / 1024-sample ILA are required in eventual physical qualification. No datapath or application feature is removed.

CPU SHA256: `D37866F5E7EBB3D64D581C4C73B663EC742038C597B29953ABF1BF2AA53BE86B`. BTB SHA256: `74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E`. Exact substitutions and qualified-baseline ancestry are recorded in `change-receipt.json`.

## Completed checks

- Five exact source-delta tests pass.
- The new relation test passes 32768 combinations covering all source-index pairs, validity combinations, four WB routing cases, signed boundaries, zeros, equal operands and random words. Unavailable register payloads contain X/Z, while available architectural values and control are known. This is not equivalence for arbitrary unknown valid controls or valid-but-unknown operands.
- Six compiled faults are rejected by the relation result check, including incorrect zero relations, signed comparison, WB validity and WB routing. An independent direct signed/unsigned comparator checks the same results in addition to the original relation function.
- Twenty-one source-bound safety methods pass in `build/safety-final`; manifest SHA256 CE25BB3278A239BAD49B9C6085DF95AE34DDDEA8D7CE6F6F251282F25A15F4BF. These include inherited decode differential/redirect, multiplier fallback/dependency, return-stack and commit checks. Six safety-auditor tests pass.
- Eight current core/cache runs agree with the independent reference. All eight retirement traces, eight final memory dumps and both short CoreMark UART logs are byte-identical to the immediate parent: eighteen files recorded in `build/parent-behavior-comparison.json`.
- Short V0 remains 3000565 cycles / 2748941 retired / CRC fcaf; V1 remains 3001255 / 2749614 / c64e. No long-run throughput or efficiency is extrapolated.

## Failed test attempts retained

The initial relation test rejected the two known Icarus discarded-synthesis-attribute warnings before simulation. The harness now permits exactly those two diagnostics and rejects other compiler messages; the initial log remains. An inherited multiplier negative-control anchor then matched both the new relation validity expression and the original prefetch expression. Its anchors now name the complete prefetch declarations, preserving the same six real compiled faults. The failed `build/safety-complete` remains untouched; the complete rerun passes separately in `build/safety-final`.

## Next acceptance gates

The completed paired audit in `audit_long_pair.py` rechecks both native ILA mappings, raw PDS reports, captured and current RTL, each image's own firmware, the unchanged long runner, compile commands, model clocks, output hashes and raw UART. Ten paired-auditor methods plus the existing long/physical auditors pass (59 methods total), recorded in `build/long-pair-audit-tests.log`. The audit exits 2 because the exact resource floor fails, not because evidence is missing.

V0: 6000 iterations, 1795360650 cycles, 1649428424 retired, CRC a14c, 11.874078373015873 modeled seconds. V1: 1795883504 cycles, 1649775523 retired, CRC 18e1, 11.877536402116402 modeled seconds. The respective cycle savings versus the qualified local reference are 2279975 and 3962965. These are RTL measurements, not board runs.

`build/local-joint-score-resource-qualification.json` binds the V0 public projection to its 9632-LUT complete image: **505.3023747624189 CoreMark**, **3.341946923031871 CoreMark/MHz**, **0.05246079472201193 CoreMark/LUT** at 151.2 MHz. The score floor passes; the 0.053452712846429634 resource floor fails. V1 is validation, not an average or a substitute score.

At unchanged execution and frequency, at most **9453 full-system LUTs** are allowed, requiring **179 fewer LUTs**; 9454 already fails the exact rational comparison. Alternatively, unchanged area requires the previously stated 514.8565301368102 CoreMark. This is the next structural area/performance target, not achieved work. No baseline is replaced. Application/electrical acceptance remains open, and no remote-board access or GitHub upload occurs.
