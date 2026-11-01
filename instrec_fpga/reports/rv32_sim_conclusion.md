# RV32 control-core simulation conclusion (2026-11-01)

## Result and evidence boundary

The real RV32I core executes the checked-in firmware ROM and drives the NPU
control MMIO register. The final `rv_cpu` simulation passes nine checks: boot, MMIO identity,
firmware self-test, counter measurement, CPU-issued start, and result readback
plus DDR status decoding, sticky-event acknowledgement, and result-cycle
snapshot retention. This is a CPU/MMIO integration result, **not a complete CPU + NPU
arithmetic or physical-board result**.

`sim/tb_rv_cpu.sv` instantiates `rv32_cpu_subsys`; it does not instantiate
`top_rv_core` or `npu_top`. After observing the real `npu_soft_start` pulse, the
testbench supplies an accelerator completion with class 3, percentage 87, and
cycle count 12345. The real firmware reads those values through MMIO and prints
them through its UART FIFO. The shared top-level UART multiplexer, real NPU
memory transactions, feature readiness, DDR3 IP, and the physical UART are
outside this test's coverage.

## Commands and observed UART

Run from `instrec_fpga/`:

```text
python scripts/build_rv32_sw.py --no-m
python sim/run_sim.py rv_cpu --verbose
python sim/run_sim.py all --jobs 4 --verbose
python scripts/compare_conv1.py --self-check
```

The RV32I firmware is 2228 bytes / 557 ROM words. The final standalone RV test
(14.4 seconds, after the RTL review fixes) reported `RESULT: PASS` for `rv_cpu`:

```text
RV32 BOOT
RV32 MMIO OK
RV32 ISA OK
RV32 BENCH cycles=460012 inst=180008 acc=0xf2d8888b
DDR OK STS 0x00000001
NPU GO
NPU t=3 p=87 c=12345
CHECK PASS C1 boot banner
CHECK PASS C2 MMIO ID read-back
CHECK PASS C3 ISA self-test
CHECK PASS C4 mcycle/minstret measurement
CHECK PASS C5 NPU event surfaced through MMIO
CHECK PASS C6 CPU-triggered NPU start (CTRL[0])
CHECK PASS C7 DDR status read-back
CHECK PASS C8 firmware acknowledged and cleared NPU event
CHECK PASS C9 result cycle snapshot survives live counter change
RESULT: PASS
```

The `ISA OK` line is the firmware's small sanity test, not an architectural
compliance suite. The counter output is a workload measurement, not CoreMark
or a performance claim. The first run exposed `DDR WAIT` despite TB
`ddr_ok=1`. The RTL review corrected the status mapping, and final C7
verifies `DDR OK`. C8 observes the real firmware clear transaction and
checks the DUT sticky flags return to zero. C9 changes the live accelerator
cycle count to 99999 after completion and verifies software still prints
the result-associated captured count 12345.

## Fixes made during this session

- Firmware now writes `NPU_CTRL=1` after startup, so C6 is a real CPU-issued
  accelerator request. Previously the test timed out waiting for a command
  the software never sent.
- Firmware extracts the percentage from the MMIO result's bits `[15:8]`.
- Completion stimulus remains valid across DUT sampling edges. The DUT's
  sticky result capture was directly inspected as percentage 87 / class 3.
- `src/cpu/prog.hex` was rebuilt with `--no-m` to match `ENABLE_M=0`.

## Full regression (first run, 4 jobs)

Total 93.4 seconds: **9 PASS / 2 FAIL / 0 SKIP**. These are actual current
workspace results, and do not supersede the failures with older passing
reports.

| Case | Result | Seconds | Evidence |
|---|---|---:|---|
| self_test | PASS | 34.2 | 8 checks / 0 errors |
| conv1 | FAIL | 34.3 | 143754 mismatches / 792576 values; first index 1776 |
| mel | PASS | 52.0 | 16512 feature values, 0 mismatches |
| mel_credit | PASS | 52.7 | 16512 feature values, 0 mismatches |
| weight_loader | PASS | 25.4 | 10 checks; `WOK 42851062`, 13 terminal bytes |
| ctrl_smoke | PASS | 25.8 | 6 checks, complete BOOT / DDROK / STS output |
| npu_chain | PASS | 29.3 | GAP, FC1, FC2, softmax each 0 mismatches |
| rv_cpu | PASS | 28.9 | C1 through C6 |
| ui_render | FAIL | 2.8 | Verilator PINNOTFOUND on six overlay ports |
| ddr3_subsys | PASS | 33.3 | 15 behavioral-model scenarios |
| ddr3_aw_timeout | PASS | 25.8 | 6 behavioral-model scenarios |

Full per-case logs: `build/sim/<case>/run.log` (gitignored). Failed-run logs
are additionally preserved under `build/sim_evidence/rv32-all-20261101-first/`
as `conv1-fail.log` and `ui-render-fail.log`, alongside `rv-cpu-pass.log`.

## Final regression after corrections (4 jobs)

The final explicit non-UI case list completed in **103.2 seconds: 12 PASS /
0 FAIL / 0 SKIP**. `ui_render` was intentionally not selected; its known
pre-existing interface failure remains open, and this is not an `all` pass.

```text
python sim/run_sim.py self_test,conv1,mel,mel_credit,weight_loader,ctrl_smoke,npu_chain,rv_cpu,npu_completion,rv_top_ctrl,ddr3_subsys,ddr3_aw_timeout --jobs 4 --verbose
```

| Case | Result | Seconds |
|---|---|---:|
| self_test | PASS | 36.7 |
| conv1 | PASS | 38.7 |
| mel | PASS | 51.0 |
| mel_credit | PASS | 50.9 |
| weight_loader | PASS | 29.6 |
| ctrl_smoke | PASS | 28.9 |
| npu_chain | PASS | 26.7 |
| rv_cpu | PASS | 27.0 |
| npu_completion | PASS | 28.1 |
| rv_top_ctrl | PASS | 28.0 |
| ddr3_subsys | PASS | 25.2 |
| ddr3_aw_timeout | PASS | 25.2 |

Final logs are retained in `build/sim_evidence/rv32-final-20261101/`.

### conv1 failure qualification

First failure: row 0 / group 0 / column 111 / channel 0, expected 0, observed
17. Stream length was correct (792576), arithmetic comparison failed.

Independent checks ruled out mismatched canonical input data:

- `compare_conv1.py --self-check`: 792576 values, max absolute difference 0,
  mismatch count 0.
- `hex_conv1/conv1_feat.hex` vs golden feature tensor: 0 mismatches.
- `conv1_w32.hex` and `conv1_ctr.hex` vs the canonical image/contract table
  builder: 0 mismatches each.

The failure reproduced identically when running conv1 alone, excluding
cross-case table preparation/build races. The cause was the testbench's
ingress reuse threshold: `pix_done` counts output bytes (16 lanes per pixel)
but the row release threshold counted pixels. Consequently it released new
input rows 16 times too early and overwrote the three-bank line buffer before
the output scan finished using it. Multiplying the threshold by `LANES` fixes
the units. No conv_engine/requant_unit RTL was changed.

After this TB-only correction, standalone conv1 passed in 22.1 seconds:
792576 output values, mismatch count 0, no first mismatch, 876135 cycles.

## Additional real-source control checks

`rv_top_ctrl` extracts the UART acceptance/arbitration and NPU request gate
blocks verbatim from `src/ctrl/top_rv_core.v` into a simulation-only wrapper
under `build/sim/rv_top_ctrl/`. It instantiates the real `uart_tx` and decodes
its serial bits. It is not a second implementation of the control equations.
The bounded slice omits vendor IP, audio processing, CPU execution, and NPU
arithmetic, so it cannot prove complete top-level elaboration or operation.

The slice passed 15 checks in 17.4 seconds:

- Simultaneous weight/debug/CPU sources serialize in W/D/C priority, with
  correct data and stop bits, and each producer pops exactly once.
- A CPU request queues while the system is unready, cannot launch without a
  complete Mel window, and is blocked by weight upload, accelerator busy, or
  failed DDR self-test.
- The queued request launches at the first safe complete-window boundary,
  consumes the pending request, and does not repeat in CPU-only mode.

`npu_completion` passed in 15.0 seconds. It instantiates the real `npu_top`
and softmax, forces the sequencer past convolution/FC to the FC2 completion
transition, and runs real softmax on reset-zero logits. It verifies eight
results, busy clearing, one-cycle completion, and a second restart. This
proves the completion protocol correction, not convolution/FC arithmetic or
end-to-end inference.

### UI interface repair and revalidation

Restored all six overlay ports and the `ui_overlay` instance in
`src/ui/ui_renderer.v`. `ui_render` now passes 64 active pixels with zero
priority mismatches and zero RGB/DE alignment mismatches; standalone
`ui_overlay` passes all six checks. The complete RTL suite now passes 14/14.

## Remaining validation

1. Verify the real `top_rv_core` start/result wiring and shared UART under
   synthesis and board execution; this TB alone cannot establish those facts.
2. Verify a CPU-issued inference using prepared features and weights, then
   compare real NPU output with the golden reference. Synthetic event readback
   does not establish this end-to-end behavior.

### Final rerun (2026-11-01 13:00)

`python sim/run_sim.py`: **14 PASS / 0 FAIL / 0 SKIP**, 281.0 s. This includes
the restored UI renderer and standalone overlay cases. `python -m pytest -q`:
**429 passed / 4 skipped** in 147.42 s. `python scripts/check_rtl.py`: 53
Verilog files, 0 violations. A separate temporary dual-clock `audio_cdc_fifo`
probe also passed reset-empty, stereo ordering, cross-domain visibility,
read latency, and drained-empty checks.

An additional temporary integration probe connects `i2s_clk_gen` to `i2s_rx`
with an accelerated NCO step. It passed 769 BCK ticks, observed 24 LRCK edges,
and decoded 24 words with left/right samples `0xA53C` / `0x5AC3`. This verifies
the synchronous RTL phase/decoder contract; it does not establish the nominal
216 MHz frequency accuracy or board-level pin behavior.

Top-level audit found and repaired an undeclared `dbg_tx_ready` net in
`instrec_top.v`; the old HDMI controller's duplicate `init_over_rx` wire
declaration was also removed. Whole-tree Verilator elaboration reaches vendor
IP blockers (`pll_audio`, `pll`, `GTP_INBUFDS`, `ips2l_rst_sync_v1_3`,
`ddr3_test`), so this is not evidence of complete `instrec_top` elaboration.
