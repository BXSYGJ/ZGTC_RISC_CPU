# Qualified CPU release collection

The current board-ready releases each have a separate folder under [cpu/](cpu/README.md): H3 Base 145.125 MHz, H3 Retained 145.125 MHz, Original 153 MHz, Original 155.25 MHz, and the selected full-ILA RV32IM 153 MHz build. See that index for performance, resources, firmware, captures and rebuild instructions.

The following 153 MHz section documents the older full-fetch experiment.

---

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

Read the [final experiment README](cpu/experiments/full_fetch_commit_factored/README.md) for the implementation and acceptance context.

All older processor experiments, temporary board projects, and unrelated development artifacts have been removed from the release tree.

## Additional qualified releases

The [155.25 MHz and best archived 153 MHz cores](cpu/releases/qualified-cores-20261012/README.md) include complete build snapshots, firmware, bitstreams, routed reports and board references.
