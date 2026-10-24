# PDS batch flow for the PG2L100H CPU SoC (with DDR3).
# Tokens expanded by run_pds_full.ps1:
#   __RTL_ROOT__     mainline RTL directory (cpu/rtl)
#   __FPGA_ROOT__    mainline fpga directory (cpu/fpga: DDR3 IP wrapper)
#   __PROJECT_ROOT__ this project directory (pds_cpu_100h)
#   __BUILD_ROOT__   timestamped build directory
#   __TOP_SOURCE__   expanded top wrapper (pds_cpu_top_100h.v) in the build dir
foreach design [lsort [glob [file join "__RTL_ROOT__" *.sv]]] {
    # rv32_board_top is the 200H top (DDR3 + its own pin map); pds_cpu_top_100h
    # wraps rv32_soc directly. rv32_burst_ddr3 IS included (the DDR3 bridge).
    if {[string match "*rv32_board_top*" $design]} { continue }
    add_design $design
}
# DDR3: burst->AXI bridge is in cpu/rtl (added above); the IP wrapper + the
# 100H-generated IP idf (carries the DDR3 pin placement) come next.
add_design "__FPGA_ROOT__/rv32_ddr3_ip_wrapper.sv"
add_design "__PROJECT_ROOT__/ipcore/ddr3_test/ddr3_test.idf"
add_design "__TOP_SOURCE__"
add_constraint "__PROJECT_ROOT__/constraints/cpu_top_100h.fdc"
add_constraint "__PROJECT_ROOT__/constraints/ddr3_100h.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -system_verilog -top_module pds_cpu_top_100h
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
