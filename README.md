# ZGTC_RISC_CPU

## Final 153 MHz release

The repository contains the complete `cpu/experiments/full_fetch_commit_factored` implementation:

- 153 MHz configured clock.
- 511.317879224 CoreMark.
- 3.341946923 CoreMark/MHz.
- 0.05381160590 CoreMark/LUT.
- 9502 complete-system LUT, 5079 FF, and +0.021 ns setup WNS.
- GPIO, UART, caches, and 42-data/33-trigger/1024-sample ILA retained.

The release was validated with local ILA captures and remote FPGA hardware V0/V1 bring-up. Remote ILA acquisition is not required by the accepted workflow. Electrical and long-term stability caveats remain documented.

Read the [human handover](cpu/docs/PROJECT_HANDOVER_153MHZ.md), [AI handover](cpu/docs/AI_HANDOFF_153MHZ.md), and [acceptance record](cpu/docs/ACCEPTANCE.md). The [evolution record](cpu/docs/EVOLUTION_120MHZ_TO_FINAL.md) is retained as project history.

Run the portable archive check from the repository root with:

```text
python cpu/scripts/verify_153mhz_handoff.py
```

All older processor experiments, temporary board projects, and unrelated development artifacts have been removed from the release tree.
