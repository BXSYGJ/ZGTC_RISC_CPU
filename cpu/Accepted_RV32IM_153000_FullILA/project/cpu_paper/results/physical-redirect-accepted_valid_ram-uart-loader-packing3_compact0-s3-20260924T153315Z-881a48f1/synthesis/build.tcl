add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_alu.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_board_top.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_btb.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_burst_arbiter.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_burst_ram.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_cache.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_core.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_decode.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_fifo.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_machine.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_memory_system.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_muldiv.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_peripherals.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_soc.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_uart.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/rtl/rv32_uncached.sv}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/pds_soc_top.v}
add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/fpga/rv32_pll.sv}
add_constraint {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/constraints/board.fdc}
add_constraint {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/constraints/uart_remotelab.fdc}
set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676
compile -system_verilog -top_module pds_soc_top
synthesize -ads -selected_syn_tool_opt 2
