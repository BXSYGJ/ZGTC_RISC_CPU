add_design {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/implementation/netlist.v}
add_constraint {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/constraints/board.fdc}
add_constraint {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/inputs/constraints/uart_remotelab.fdc}
add_fic {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/implementation/cpu-remapped.fic}
set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676
compile -system_verilog -top_module pds_soc_top
dev_map -input_db_file {D:/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T153315Z-881a48f1/implementation/source.adf}
pnr -gplace_seed 3 -logic_optimize_enable TRUE -logic_optimize_lut6d_combing_strategy 3 -plc_decongestion 0
report_timing
gen_bit_stream
