# One-entry return stack with prediction-payload capture factoring

## Measured motivation and exact scope

The parent full_return_stack1 full-ILA run fails at -0.161 ns on wb_data[19] -> early forwarded branch comparison -> frontend control -> fetch_prediction[4].CE. This isolated candidate applies the three exact substitutions from full_fetch_prediction_payload to that one-entry parent. The earlier payload-only experiment failed in a different core context; it is not treated as a passing implementation or rerun unchanged. CPU SHA256: 6A889FFD1E4E435A8AC44A0635F87B79CC331135C8DFC668CA9C1F2CF4CF6843. BTB remains 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E.

Only prediction payload capture is separated from late frontend-flush/barrier guards. Request acceptance, redirects, valid/discard state and architectural instruction flow remain unchanged. Extra dead-slot payload writes are allowed only where later live consumption retains the correct capture. GPIO, UART, cache geometry, RV32IM/machine-mode logic and the required 42-data / 33-trigger / 1024-depth ILA are retained. The full qualified-parent source reconstruction remains in change-receipt.json. candidate_sources.py uses the raw-relation parent only for its unchanged link/raw-pair observation benches; the immediate RTL parent is full_return_stack1.

## Completed local functional evidence

Five exact-delta tests pass. Four predictor/overlap combinations pass 6000-cycle dual-core differential checks and the 35-case / 444-check directed redirect suite. All four compiled capture faults are rejected. Extra dead-slot writes are observed while live metadata stays equal. Five return-stack depths each pass 4123 vectors; eight predictor faults are rejected. The source-extracted 32768-combination commit/hint check rejects four faulty conditions. These bounded tests use randomized frontend controls and NOP response streams for the differential portion; they do not constitute exhaustive equivalence.

The 14-method safety suite binds current tests, benches, parent/qualified sources and all complete logs in build/safety/manifest.json (SHA256 798784FAB144F4FAF0B173FB712A4B82C5C861AA41D41B9DCFD3949F08719197). Eight real core/cache executions independently match instruction traces and final memory, including the existing committed-link and live raw-pair assertions. Regression manifest SHA256: 1CFD3BCC379CA7B1683BFA8452D96523B8139E6AEE4042858674BBCCEF74E08B.

Both ten-iteration CoreMark logs match full_return_stack1 byte-for-byte: V0 3000565 cycles / CRC fcaf, V1 3001255 / c64e. The payload transformation adds no execution-efficiency gain; it attempts to make the existing return-stack gain physically usable. No long-run or resource-efficiency score is inferred from these short runs.

## Implementation status

Twenty physical inputs are staged, with only core/predictor RTL differing from the qualified source inventory. Ordinary 151.2 MHz PDS run 20260911-052657-0130a856 completes with 9115 LUT / 4331 FF and WNS -0.035 ns (one failing setup endpoint). Its worst path is instruction-cache request_address[5] -> banked_valid.banks[0].valid0_2.I5. This is a timing rejection, not a resource-efficiency result. It uses unchanged 6000-iteration V0 firmware SHA256 3A82C84E665E212C8BC8CF492CD169D7A579BF20146F810FA104F51EAE61287B.

Independent current-source RV32UI/RV32UM validation completes with 196 positive executions and eight expected rejection controls. The source/raw-log/coverage audit and its four tests pass. Invocation SHA256: B8911CBB00C9E090CB36CD3A6D2E10FA2B90C3C486B7DA4ACFADD231927CED86. These use four predictor/cache configurations and the documented precise-misalignment-trap exclusion, not full ISA certification. Six safety-auditor tests also reject changed inputs, missing/altered logs and incomplete/raw-missing completion.

Fresh native net discovery and actual Inserter verification confirm core-local IF/ID/EX valid nets and parent MEM alias board/soc/unused_pipeline_valid[3]. All 42 data / 33 trigger channels and depth 1024 pass. Twenty-two full-ILA source/mapping/evidence tests pass. Netlist SHA256: D4958D7CB45A8D2F3A0C05D488EBF6F81322EAE6012E65F8D4FFE1CF4AD2405D. Ordinary and full-ILA sessions are both terminal; their failed timing evidence is retained.

The full-ILA return-payload1-seed1 run is terminal: 9550 complete-system LUT / 5045 FF, WNS -0.375 ns, 108 failing slow-setup endpoints and TNS -13.662 ns. Bitstream SHA256: C74639C5FCC7C1D18A035D7680CC5347EE23C8D172DD601EBAF27B8119E6F4A1. This candidate is rejected; functional equivalence and successful bitstream generation do not qualify its timing or score.

The worst routed path now runs from register_valid[22] through the register-valid read mux, id_register_b_valid_1 and id_operand_b[19] into multiply_divide.unit/N98/gopapm/Y[3]. It has four logic levels, 1.033 ns logic and 4.286 ns routing; the final route to the APM input alone is 1.845 ns. The shared validity node has native fanout 24 in this report despite the RTL synthesis fanout hint of 16. This is observed implementation evidence, not proof that a tighter attribute will fix it. Follow-up should review the already accumulated register-valid/multiplier-prefetch experiments before proposing a structurally different change; no blind seed retry or long-run simulation is launched here.

The payload transformation still preserves only the measured short-run execution behavior; it has not made the return-stack benefit physically acceptable. Keep full_redirect_clock151200 as the locally paired version and DC90363D as the hardware baseline. All five non-AI tasks, complete-system scoring, electrical/configuration-power evidence and the user's remote-validation gate remain active.

No score, application promotion or board test follows this rejected implementation. Neither baseline is replaced. Remote Chrome 19476 and GitHub remain untouched.
