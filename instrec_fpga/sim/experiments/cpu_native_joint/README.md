# Real CPU and native NPU joint simulation

This experiment executes the real RV32 CPU and firmware ROM, requests inference
through CTRL[0], holds the request pending, and releases it at a modeled Mel safe
window. It then runs the complete native NPU, compares every conv/pool/GAP/FC and
softmax output with the integer golden pipeline, delivers the actual result to CPU
MMIO, checks the UART report, and checks the firmware CTRL[1] acknowledgement.

The test uses the production `npu_top`, controller, M1 bridge/owner and hardened
aligner with a behavioral AXI DDR model. The launch logic is extracted from
`top_rv_core.v`. The CPU boots and passes its MMIO/ISA self checks. DDR PHY,
physical audio capture and the full Mel pipeline are outside this experiment;
DDR-ready and the Mel safe window are modeled. This is one inference per run.

## Commands

```powershell
python sim/experiments/cpu_native_joint/run.py
python sim/experiments/cpu_native_joint/build_firmware.py
python sim/experiments/cpu_native_joint/run_firmware_cpu.py
python sim/experiments/cpu_native_joint/run.py --top1-firmware
```

`build_firmware.py` builds an isolated candidate under
`build/sim/cpu_native_joint_top1/firmware/`; it never replaces `sw/rv32/main.c`
or `src/cpu/prog.hex`.

## Result semantics

The original firmware reports `NPU t=7 p=0 c=31141201` for this fixture. Its `t`
and `p` come from SYS_PROBS, which latches the final probability lane. They do
not report the winning class. STATUS[11:8] contains the actual hardware top1.

The isolated firmware reports
`NPU top1=0 last_class=7 last_p=0 c=31141201`. The joint runner independently
checks top1 against the golden probability argmax. A separate CPU-only test
injects top1=5 and last_class=3, checks
`NPU top1=5 last_class=3 last_p=87 c=12345`, and passes C1-C9. This makes the
two fields observably distinct even if a different fixture has top1=7.

## Evidence

- Original firmware joint PASS:
  `build/sim/cpu_native_joint/original_firmware_legacy_report.log`
  (SHA-256 `0d8621b189dbb269e014235eb597e9b805dd587e0d60357e3b99448955a10161`).
- Current production firmware joint rerun: `build/sim/cpu_native_joint/run.log`.
- Isolated firmware CPU C1-C9 PASS: `build/sim/cpu_top1_firmware/run.log`.
- Isolated firmware full joint PASS: `build/sim/cpu_native_joint_top1/run.log`.
- Generated testbench and fixture files are retained in each run directory.
- `inputs.json` records SHA-256 of RTL and ROM inputs for the joint runs.
- Full native inference takes 31,141,202 observed cycles; the actual MMIO
  completion-cycle payload is 31,141,201, matching the UART report.

Earlier top1 runs mistakenly used case name `pool4`, because fixture generation
reused the case-name variable. Their successful logs remain at
`build/sim/pool4/run.log` as historical evidence; they are superseded by the
correctly named rerun. Both fixture loops now use separate variable names.

## Production promotion

After the isolated checks, the same formatting fix was promoted to
`sw/rv32/main.c` and `src/cpu/prog.hex` was rebuilt with
`python scripts/build_rv32_sw.py --no-m`. The raw binary has 2313 bytes;
the word-padded ROM has 2316 bytes / 579 words. Two consecutive production
builds and the fully joint-tested isolated ROM are byte identical:

`24d0b7fd4cb3e37f08cdfe4e3ab361321ba43f21ea6ec5367c3b2703b2dec294`

Evidence: `build/sim/cpu_native_joint_top1/production_rom_rebuild.json`.
The production CPU regression now deliberately uses hardware top1=5 with
last_class=3, and checks both fields in C5/C9. Its log is
`build/sim/rv_cpu/run.log`. The default joint command also expects the new
production UART format. Previously frozen PDS build inputs are unchanged.

Correctly named isolated joint log SHA-256:
`dc9ecf54a9e90009ed4f444d6411698d57b42d49717aed1c882236f95a2c3532`.
These results establish digital simulation behavior, not physical DDR/audio or
board-level validation. The production ROM change needs a new frozen PDS build
before it can appear on the board.
