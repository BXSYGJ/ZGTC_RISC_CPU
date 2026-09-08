# uart_beacon PDS full-flow TCL（token 由 run_pds_full.ps1 展开）
add_design     "__PROJECT_ROOT__/src/uart_beacon.v"
add_constraint "__PROJECT_ROOT__/constraints/uart_beacon.fdc"

set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676
compile -top_module uart_beacon
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
