# Local asynchronous-I/O review of the 151.2 MHz candidate

## Application image follow-up

The completed local application pair is recorded in build/local-application-qualification.json. The actual scope netlist E7168581BC5CA2502E73AF56651F3CC8A6844E9956CE20E87217A69277F7D5F9 passes the same four-chain structural checker after matching its physical invocation. Runtime and full-ILA timing both pass; this adds no board-specific voltage, SCBV, MTBF or complete CDC evidence. The open electrical items below remain open.

This is a bounded review of the actual paired full-ILA netlists, not electrical signoff or permission to program a board.

## Source-bound structural evidence

Both netlists match the SHA256 recorded in their physical invocation before the structural checker runs:

| Image | Netlist SHA256 |
| --- | --- |
| Performance, 20260910-redirect-clock151200-seed1 | C177AD14106D2BB4D917EE5B9A90BF5932C3A58BC17558D44D57D4D2AC647BB1 |
| Validation, 20260911-redirect-clock151200-v1-seed1 | 61C3E4D3E75B13601A3338BA1FE422331073A7E75440AEFBDC49B9D4C9A2990F |

Each passes audit_async_structure.py for these four native two-register chains:

- UART rx_meta -> rx_sync, sourced from serial_rx, using GTP_DFF_P cells.
- GPIO gpio_meta[0] -> gpio_sync[0], sourced from gpio_input[0], using GTP_DFF_C cells.
- GPIO gpio_meta[1] -> gpio_sync[1], sourced from serial_rx, using GTP_DFF_C cells.
- Board reset_pipe[0] -> reset_pipe[1], with first-stage data tied high, using GTP_DFF_C cells.

The checker verifies the expected clock, matching reset/preset connections, direct stage-to-stage data connection and no additional first-stage named-port or assign fanout in these modules. Six test methods pass, including bypass, extra logic/assign fanout, wrong clock and missing-module mutations. Per-image receipts are stored as async-structure.json inside the respective full-ILA directories.

## Limits and remaining evidence

The separate build/async-input-paths.json now binds all three benchmark/application input netlists to their actual implementation invocations and checks UART/KEY raw-signal consumer lists plus seven typed hierarchy links. No unexpected consumer is found outside the specified input-buffer, KEY inversion and synchronizer paths. Eight positive/negative regression methods pass. This is an additional bounded check of the synthesized inputs; it does not expand reset coverage, prove routed placement or determine board voltages/SCBV.

Both physical images separately pass the supplied PDS timing constraints with +0.017 ns setup slack, but that does not prove every asynchronous interface is constrained appropriately. This structural checker does not inspect post-route synchronizer placement, derive metastability MTBF, prove whole-design CDC, or establish complete reset recovery/removal safety.

The current physical qualifiers still record the unset-SCBV warning. The earlier reference review in ../full_control_commit/LOCAL_ELECTRICAL_REVIEW.md and ../../docs/CONFIGURATION_ASSURANCE.md identifies missing actual remote-board configuration-power evidence. Exact board model/revision, configuration mode, VCCIOCFG, VCCIOL4/VCCIOL5 and physical SCBV connection must be established before electrical signoff. No voltage value, configuration strap, pin assignment or timing exception is guessed to make a checker pass.

The candidate remains subject to its own long-run/application acceptance and the user's remote-board gate. Structural evidence is not hardware validation.
