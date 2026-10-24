# PDS batch flow for the PG2L100H CPU SoC bring-up (BRAM only, no DDR3).
# Tokens expanded by run_pds_full.ps1:
#   __RTL_ROOT__     mainline RTL directory (cpu/rtl)
#   __PROJECT_ROOT__ this project directory (pds_cpu_100h)
#   __BUILD_ROOT__   timestamped build directory
#   __TOP_SOURCE__   expanded top wrapper (pds_cpu_top_100h.v) in the build dir
foreach design [lsort [glob [file join "__RTL_ROOT__" *.sv]]] {
    # DDR3-dependent files are excluded: the 100Pro+ bring-up build has no
    # DDR3 backend and no board_top (pds_cpu_top_100h wraps rv32_soc directly).
    if {[string match "*rv32_board_top*" $design]} { continue }
    if {[string match "*rv32_burst_ddr3*" $design]} { continue }
    add_design $design
}
add_design "__TOP_SOURCE__"
add_constraint "__PROJECT_ROOT__/constraints/cpu_top_100h.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -system_verilog -top_module pds_cpu_top_100h
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
