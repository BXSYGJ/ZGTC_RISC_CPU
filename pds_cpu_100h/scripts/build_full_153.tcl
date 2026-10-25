# PDS batch flow: accepted 153 MHz configuration on PG2L100H (BRAM-only).
# RTL = cpu/experiments/full_fetch_commit_factored/rtl (the qualified sources)
# + the experiment's fpga/rv32_pll.sv (153 MHz GPLL table).
# Tokens expanded by run_pds_153.ps1:
#   __RTL_ROOT__     accepted-experiment rtl directory
#   __FPGA_ROOT__    accepted-experiment fpga directory (rv32_pll.sv)
#   __PROJECT_ROOT__ this project directory (pds_cpu_100h)
#   __TOP_SOURCE__   expanded 153 MHz top (pds_cpu_top_100h_153.v) in build dir
foreach design [lsort [glob [file join "__RTL_ROOT__" *.sv]]] {
    add_design $design
}
add_design "__FPGA_ROOT__/rv32_pll.sv"
add_design "__TOP_SOURCE__"
add_constraint "__PROJECT_ROOT__/constraints/cpu_top_100h.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -system_verilog -top_module pds_cpu_top_100h
synthesize -ads -selected_syn_tool_opt 2
dev_map
__PNR_COMMAND__
report_timing
gen_bit_stream
