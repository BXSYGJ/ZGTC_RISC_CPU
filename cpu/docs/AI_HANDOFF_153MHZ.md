# AI handoff: qualified complete 153 MHz CPU

## Read first — binding continuation instructions

This is the authoritative continuation note as of **September 11, 2026**, Asia/Shanghai. Read `PROJECT_HANDOVER_153MHZ.md` for the human narrative and `evidence/153mhz-20260911/` for portable evidence. Older READMEs and ACCEPTANCE entries contain historical present-tense statements. Do not treat those as live jobs or newer results.

The user stopped further optimization at the 153 MHz / 511.318 CoreMark version and requested local ILA validation, remote bring-up, two documents and a GitHub snapshot. **The user explicitly says local ILA checking is sufficient; remote ILA is NOT an acceptance gate.** The validation gates now pass. After the authorized publication, provisionally conclude the work; do not resume the previous open-ended optimization goal automatically. AI acceleration remains deferred. Do not claim electrical or exhaustive certification.

Use English. Work in PowerShell 7, not Bash. Follow the current user/AGENTS instructions for UTF-8, path construction and error handling. Do not infer permission to use unavailable subagent models. The proposed new full_local_history4 candidate was not created after this iteration; older full_history4 experiments are historical and are not the qualified 153 MHz build. Do not start a new H4 experiment without a new request.

## Authoritative implementation and measurements

Repository: `D:/AAAFPGA/ZGTC_RISC_CPU`. Git branch: `DYH`. GitHub repository: `BXSYGJ/ZGTC_RISC_CPU`. The selected implementation is **`cpu/experiments/full_fetch_commit_factored`**. Top-level `cpu/rtl` and the open clock157500/clock141750 PLL tabs are not this accepted implementation.

| Field | Accepted value |
| --- | --- |
| Configured clock | 153000000 Hz |
| Performance CoreMark | 511.3178792238763 |
| Execution efficiency | 3.341946923031871 CoreMark/MHz |
| Resource efficiency | 0.05381160589600887 CoreMark/LUT |
| Complete post-route denominator | 9502 LUT, 5079 FF |
| Complete setup WNS | +0.021 ns |
| V0 timed cycles / retired / final CRC | 1795360650 / 1649428424 / a14c |
| V1 timed cycles / retired / final CRC | 1795883504 / 1649775523 / 18e1 |
| Iterations per seed | 6000 |
| Runtime configuration | 0e8e96fd |
| Physical FPGA | PG2L200H-6FBB676 |

Preserve GPIO, UART and **42 data / 33 trigger / 1024-sample ILA**. Denominator = complete post-route CLMA LUT + CLMS LUT; do not count distributed RAM twice or use ordinary 9075-LUT area. Both seed images have 9502 LUT. Scope also has the complete ILA.

Critical source SHA-256 values:

- CPU: EC22FD905CF50FCEC84981EED57835615CC3C62E2B046F41E5052A026A623DB8
- BTB: 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E
- Peripherals: AB2D42B769C2493630325E3DB9CB2D5447608F20EF57D884D64A9D2F1B7E2D3E
- PLL: EDD8A3A04C0CE1A72944CA4D01E37F7FBA38F924CF04A1136F9583BAF1EECFD1

All twenty physical source hashes are in the portable hardware qualification. Source/input JSON files intentionally retain their original historical purpose text (including 'not qualified'); changing them would break provenance. New acceptance is expressed in new qualification evidence, not by mutating historical receipts.

## Hardware result versus local result

Remote verification on September 11 used Experiment box 1, device ID 12, PG2L200H. Both full CoreMark images reported successful download/burn and complete UART results. Per-packet hex, byte counts and text were checked; hardware cycles, retired instructions, cache profiles and CRCs match each seed's local long simulation exactly. This is now hardware evidence, not merely the previous 511.318 projection.

The clock is **configured**, not independently measured. Neither 153.5155 MHz PDS estimate nor older 157.5 MHz timing applies to the reported result. Hardware V0 score is not the mean of V0 and V1.

**Never report 545 CoreMark from the legacy UART 'Iterations/Sec' line.** The old integer-print path also shows whole seconds. Use the final 64-bit ZGTC counters and configured frequency: 6000 * 153000000 / 1795360650. Do not change firmware or compiler flags and keep calling it the same validated artifact. GCC 10.2.0, RV32IM, O3, unroll, relaxation and the complete compiler flags are preserved in the raw UART documentation.

The old accepted DC90363D hardware baseline remains a historical comparator: 157.5 MHz, 501.0657302224314 CoreMark, 3.181369715697977/MHz, 9374 LUT and 0.053452712846429634/LUT. New throughput and resource efficiency exceed its required floors. The immediately preceding local 151.2 MHz candidate has slightly better resource efficiency than this final candidate (difference -0.0885%); do not claim a Pareto win over every intermediate experiment.

## ILA acceptance boundary

The user accepts local detection. Current captures reside at `build/ila-pipeline-rtl/fetch-commit153000` inside the selected experiment. Their exact short-run source is `build/compiled/20260911-094801-420d3685`; ten-iteration V0 diagnostic firmware is distinct from the 6000-iteration scoring firmware.

Each ELF-resolved list/matrix/state entry has 1024 samples of all 42 logical channels and 1023 temporal checks. These pass source/firmware binding, unchanged full short-result comparison, width/index/count checks, MEM-fire validity and preceding-MEM-to-WB checks. Four capture tests pass. CSVs and 16-cycle SVGs are published; the matrix SVG was visually reviewed.

These are RTL observer-port captures, **not physical DebugCore RAM acquisition**. Actual native FabricInserter mapping separately preserves all 42/33/1024 channels in the programmed images. Native WB alias proof uses the real SoC pipeline-valid alias and its DFF driver, not an invented net.

The remote FIC import displays only 33 channels and ex_pc/ex_fire/cpu_clk. No physical acquisition was started. This limitation is informational, not a remaining user gate. Do not alter FIC widths or claim remote capture to work around it.

An initial capture run failed because importing audit_fetch_long before run_coremark_compiled polluted the module cache with an older frequency checker. Both generator and auditor now load the current source-bound runner first. The failed original remains in `build/ila-pipeline-rtl/fetch-commit153000-rejected-checker-import`; the accepted fresh capture passes. Preserve rejected evidence; do not overwrite the fixed accepted output directory.

## Exact local build identities

All entries below are relative to the selected experiment unless noted.

| Purpose | Directory / identity |
| --- | --- |
| Long V0 | build/compiled/20260911-102437-50412c5f |
| Long V1 | build/compiled/20260911-105001-2a7db72e |
| Ordinary V0 | build/pds/20260911-095312-74f93c4b |
| Ordinary V1 | build/pds/20260911-101436-c57addf3 |
| Ordinary scope | build/pds/20260911-105255-fc9be582 |
| Complete V0 | build/ila/fetch-commit-seed1-native-wb |
| Complete V1 | build/ila/fetch-commit-v1-seed1 |
| Complete scope | build/ila/fetch-commit-scope-seed1 |
| Local scope simulation | build/scope-current/20260911-105053-71d3ebca |
| Raw hardware evidence (relative to cpu) | build/hardware/fetch-commit153000-20260911-box1 |

Complete bitstreams use `generate_bitstream/pds_soc_top.sbit`:

- V0: 5BBBEA849F5E3E51576927641FC7DC00393862D6BD9CB3638C3769E7FF757DB1
- V1: 441DA777607E2C16FF7FA19671A1618473B24783F05EC44B1C70974F3BAF3018
- Scope: D2D91235C09FF5C5D7E9639AA6887AF8642FFEA82B4AA441D580711C7CEEFF6F

Local-only joint receipt SHA-256: 909D8E616A1F57D6D6EC4EE9E847D3EE67D67B48842BDF9F8DBB4342A19C200E. Its hardware_validated=false is correct for its historical scope; do not rewrite it. The new `hardware-qualification.json` records hardware acceptance and local ILA acceptance separately, with electrical_review_closed=false and physical_ila_acquisition_passed=false.

## Scope application and remaining caveats

The scope firmware samples at 1224 cycles per record (nominal 125 kHz), 256 records, with a 4590000000-cycle timeout. Firmware SHA-256: 4D6AF10D6117FEC061273512E0AABF36B7916B357BFE66E152C89C6E3A388B06.

Local application checks cover UART 0x55, expected GPIO pulse sequence, two checksummed captures, EMPTY, TIMEOUT, late=0 and ready state. The local timeout is accelerated with explicit 64-bit counter jumps, not thirty continuously simulated seconds. Hardware scope smoke covers EMPTY, ARMED and an approximately thirty-second real timeout. Hardware help text was truncated by the platform receive path. No hardware scope waveform/checksum or GPIO-key pulse capture is claimed for this version. Do not conflate scope and ILA.

PDS SCBV remains unset. Full electrical/CDC review, actual configuration-power evidence, independent clock measurement, voltage/temperature margin and long-duration stability are open engineering caveats. The bounded UART/GPIO/reset synchronizer check is not whole-design CDC or MTBF proof. Successful board bring-up does not close them. The user authorized a provisional endpoint, not a universal signoff.

## Reproduction, publication and continuation

For a **fresh clone**, from repository root:

`python cpu/scripts/verify_153mhz_handoff.py`

This verifies published evidence hashes, the twenty current implementation source hashes, exact UART-derived results, area/bitstream consistency and three local ILA windows. It does not recreate native PDS results or rerun hardware. The evidence manifest is an integrity inventory, not a cryptographic third-party attestation.

On the original workstation, from the selected experiment directory:

- `python audit_fetch_hardware.py` — native artifact/source/packet binding and provisional validation receipt.
- `python test_fetch_hardware.py` — five transport-integrity negative-control methods.
- `python audit_fetch_pipeline.py` and `python test_fetch_pipeline.py` — original full local ILA evidence and four tests.
- `python audit_fetch_long.py` and `python audit_fetch_joint.py` — original local paired scoring and complete-resource binding.
- `python audit_fetch_application.py build/scope-current/20260911-105053-71d3ebca` — original full application evidence.
- `python audit_fetch_async.py --include-application` — bounded structure checks, not electrical certification.

These historical audits depend on ignored original parent-build artifacts. The Git snapshot is source/tests/scripts/docs plus compact text evidence, **not a hermetic all-history rebuild bundle**. Do not launch fixed-output preparation scripts on top of accepted directories or mistake missing receipts in a fresh clone for a failing CPU. Before a genuine rebuild, inspect the selected README, source-inputs.json, parent dependencies and runner parameters, and create an isolated output location.

The original environment uses WSL Ubuntu-22.04 for simulation and Windows PDS 2022.2-SP6.4 for formal implementation. Serialize native PDS; do not run multiple instances. Long simulation total watchdog is six billion cycles because startup/output delays are outside the timed benchmark. An earlier 2.1-billion watchdog failure is preserved, not a valid score. The RV32 toolchain prefix was /home/bx/.local/zgtc-riscv32-10.2.0/bin/riscv32-unknown-elf-. Do not download or overwrite tools without checking the actual environment.

Browser bring-up used the already-authorized Chrome debugging port 19476 after new-browser launch was blocked by the execution tool. No policy workaround was used. The authenticated session is private; never put login credentials, authorization headers or tokens in Git or handoff documents. The UART was closed and device 12 released. Recheck future live device identity and exact bitstream before programming; do not assume an old reservation or port remains valid.

Windows Git was absent from PATH, so publication uses WSL git without Bash on existing DYH. Inspect staged files before committing. Experiment build trees and generated PDS artifacts are ignored; byte-preserving attributes protect hashed experiment inputs and evidence. Preserve unrelated user edits. The user authorizes this snapshot only; **do not auto-push subsequent updates** or repeatedly check Git/BRAM/DDR unless needed for a new task.

No further optimization is pending under the provisional stopping criterion. If the user later reopens work, first ask which goal changes: evidence strengthening, electrical/stability review, a portable rebuild workflow or renewed performance work. Never silently restart the old unlimited goal.
