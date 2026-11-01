add_design {D:/AAAFPGA/ILA_Core_Releases_20261101/H3_Retained_145125/builds/20261101-013613-bbd7e86b/implementation/netlist.v}
add_constraint {D:/AAAFPGA/ILA_Core_Releases_20261101/H3_Retained_145125/builds/20261101-013613-bbd7e86b/inputs/constraints/board.fdc}
add_constraint {D:/AAAFPGA/ILA_Core_Releases_20261101/H3_Retained_145125/builds/20261101-013613-bbd7e86b/inputs/constraints/uart_remotelab.fdc}
add_fic {D:/AAAFPGA/ILA_Core_Releases_20261101/H3_Retained_145125/builds/20261101-013613-bbd7e86b/implementation/cpu.fic}
set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676
compile -system_verilog -top_module pds_soc_top
dev_map -input_db_file {D:/AAAFPGA/ILA_Core_Releases_20261101/H3_Retained_145125/builds/20261101-013613-bbd7e86b/implementation/source.adf}
pnr -dc_duplication false -plc_decongestion 0 -gplace_seed 1 -logic_optimize_lut6d_combing_strategy 3
report_timing
gen_bit_stream
