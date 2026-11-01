# CPU and native NPU joint simulation

`run.py` runs the current production RTL and production ROM through real CPU
boot/MMIO/ISA, CPU pending request held until a modeled Mel safe window,
complete native NPU golden comparisons, result UART/MMIO and CTRL[1] ACK.
Use `--run-label unique-label` to preserve existing evidence.

## Two CPU requests with distinct frames

    python sim/experiments/cpu_native_joint/run_repeat.py --run-label unique-repeat-label

The production firmware deliberately issues only one request. This experiment
builds an isolated firmware candidate from production main.c: after reporting
and acknowledging the first result, it issues exactly one more CTRL[0] request.
The candidate stays under build/, and the production ROM and RTL are unchanged.
The runner refuses an existing run directory. Its generator is tracked here so
the isolated C and ROM are reproducible.

Current production RTL, including the narrow row RAM template, passes both A/B
frames without DUT/DDR reset. B=255-A changes all 16512 feature bytes; all golden
arrays are independently recomputed and loaded before the second safe window.
Both frames complete in 31141202 accelerator cycles. The CPU reports each MMIO
snapshot as `NPU top1=0 last_class=7 last_p=0 c=31141201`, then acknowledges it.
Final counts are two CPU requests, two launches and two ACKs. Changed FC
accumulators and all intermediate comparisons distinguish the frames even though
their final top1 agrees.

Evidence: `reports/cpu_native_joint_repeat_ab_validation_20261101.json` with
source, candidate ROM/C, golden asset and log hashes. The successful log is
`build/sim/cpu_native_joint_narrow-repeat-ab-20261101-r3/run.log`; earlier
testbench failures are retained and described in the report.

DDR AXI memory, Mel safe windows and UART byte acceptance are modeled. Physical
DDR PHY, full audio/Mel frontend, board UART/JTAG, CDC and timing are excluded.
This establishes repeated control with the isolated firmware candidate; it
does not claim the current production ROM automatically requests twice.
