# RV control-core integration: synthesis gate (2026-11-01)

Run: `build/pds/20261101-102333-c9e3d804`, top `top_rv_core`, device
`PG2L100H-6IFBG676`. Compile and synthesis completed; synthesis success banner
is timestamped 10:47:22 local time. No place-and-route or bitstream was produced
by this gate.

| Resource | Synthesis result |
| --- | --- |
| LUT | 35804 / 66600 (53.76%) |
| Registers | 53813 / 133200 (40.40%) |
| Latches | 0 |
| DRM | 80.5 / 155 (51.94%) |
| APM | 90 / 240 (37.50%) |

The CPU is present in the synthesized netlist (`u_cpu/u_core` hierarchy and
CPU pipeline/register logic remain). The top uses `ENABLE_M=0` and
`ENABLE_PREDICTOR=0`, so the integrated instruction set is RV32I.

## Limitations of this database

The parser read RTL around 10:24:09, before the CPU subsystem MMIO width fixes
saved at 10:28:13. It must not be described as a build of the later committed
RTL. The copied firmware image matches the source image byte-for-byte:
SHA-256 `17C8F4C819C97D818112A08C822C240D896390FF34BA0216B1C98A08A1D863FF`.

The log reports `npu_rd_ready_u` undriven. This is an input of `wdma` that the
current implementation does not read; it is inherited from `top_core_only`,
not evidence that the CPU was removed. The log also reports `npu_done_st`
constant zero. Inspection found that `npu_top.layer_finished` omits the
`L_SM -> sm_done` case, preventing the existing completion branch from firing.
This requires an RTL fix and a fresh compile/synthesis before final validation.

The RV CPU shares the existing `core_clk`/`ddrphy_sysclk` domain. The build
retains the DDR hierarchy and pin-compatible core-only top ports, loading
`ddr3_100h.fdc` before `top_core_only.fdc`. Post-route setup/hold and every
clock domain remain unmeasured for this run. Synthesis resource usage alone
does not establish routability or timing closure.
