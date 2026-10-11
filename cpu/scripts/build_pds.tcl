foreach design [lsort [glob [file join "__PROJECT_ROOT__" rtl *.sv]]] {
    add_design $design
}
add_design "__BUILD_ROOT__/pds_soc_top.v"
__DDR3_DESIGN__
__CLOCK_DESIGN__
add_constraint "__PROJECT_ROOT__/constraints/board.fdc"
add_constraint "__PROJECT_ROOT__/constraints/__UART_CONSTRAINT__"
__DDR3_CONSTRAINT__
__FLASH_CONSTRAINT_LINE__
set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676
compile -system_verilog -top_module pds_soc_top
synthesize -ads -selected_syn_tool_opt 2
dev_map
__PNR_COMMAND__
report_timing
gen_bit_stream
