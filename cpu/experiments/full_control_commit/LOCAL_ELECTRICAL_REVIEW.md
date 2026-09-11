# Local asynchronous-I/O and electrical review

Reviewed September 10, 2026 against the full_control_commit candidate. This is a bounded evidence update, not electrical signoff or permission to program a board.

## What the actual synthesized netlist proves

The source-bound V0 full-ILA netlist at build/ila/20260910-control-commit-seed2/netlist.v has SHA-256 AE3965B3BB76118F1CCAB226AE3A005C8B5DC87E7B7A12297BBDAB99DC3C43F9. audit_async_structure.py checks these four chains in the native synthesized cells:

| Module | First register | Second register | First-stage input | Native cell |
| --- | --- | --- | --- | --- |
| rv32_uart | rx_meta | rx_sync | serial_rx | GTP_DFF_P |
| rv32_peripherals | gpio_meta[0] | gpio_sync[0] | gpio_input[0] | GTP_DFF_C |
| rv32_peripherals | gpio_meta[1] | gpio_sync[1] | serial_rx | GTP_DFF_C |
| rv32_board_top | reset_pipe[0] | reset_pipe[1] | constant one | GTP_DFF_C |

Each pair uses clk and matching reset/preset connections. The second register receives the first register directly; the first-stage net has only its Q driver and the next D named-port connection, with no assign fanout. Six tests cover the real netlist and mutations for all four bypasses, extra first-stage logic/assign fanout, a wrong clock and a missing UART module. This is not a general Verilog elaborator or whole-design CDC proof.

Manual netlist inspection additionally shows GPIO bit zero driven by the inverted KEY path; UART_RX is shared by the UART receiver and GPIO bit-one synchronizer. The other six board GPIO inputs are constants in the RTL and optimized away, not removed software registers. The board reset clear combines the external reset and PLL lock; the reset synchronizer then supplies the SoC reset. UART and GPIO software interfaces remain unchanged.

## What the timing report covers

The same full-ILA implementation reports All Constraints Met under the supplied constraints. The CPU setup WNS is 0.000 ns; slow-corner hold WHS is 0.144 ns. Its slow-corner recovery summary includes 3972 endpoints, zero failures and WNS 2.123 ns. These are reported constrained internal paths, not proof of every asynchronous reset release or external interface.

The existing board.fdc false-path exception starts at rst_n, key and uart_rx. The UART_TX and LED outputs have no external source-synchronous timing contract. Current PDS output still reports these external ports as unconstrained. No zero-delay constraints, guessed endpoint exceptions, SCBV values or I/O voltage edits were introduced merely to suppress warnings.

The structural checker deliberately leaves post-route placement, metastability MTBF, complete reset recovery/removal and electrical qualification false. Neither two registers in a netlist nor successful UART simulation closes those items.

## Missing electrical evidence

The reference 3_Hardware subtree contains the customer baseboard schematic/PCB, connector PDF and core/baseboard component-position PDFs. It does not provide the complete core configuration-power schematic identified as missing in ../../docs/CONFIGURATION_ASSURANCE.md. That existing review distinguishes the MES reference board from the actual remote laboratory board.

Before electrical signoff, obtain the remote board's exact model/revision and authoritative configuration-power information: configuration mode, VCCIOCFG, VCCIOL4, VCCIOL5 and the physical SCBV connection. Check any setting against the documented PDS interface only after that board evidence is available. The browser at port 19476 remains untouched under the user's pre-qualification gate.

