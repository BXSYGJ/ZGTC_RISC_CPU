add_design "__PROJECT_ROOT__/src/uart_top.v"
add_design "__PROJECT_ROOT__/src/uart_rx.v"
add_design "__PROJECT_ROOT__/src/uart_tx.v"
add_design "__PROJECT_ROOT__/src/uart_data_gen.v"
add_constraint "__PROJECT_ROOT__/constraints/uart_test.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -top_module uart_top
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
