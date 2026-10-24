add_design "__PROJECT_ROOT__/src/blink_top.v"
add_constraint "__PROJECT_ROOT__/constraints/blink_top.fdc"
add_simulation "__PROJECT_ROOT__/sim/blink_top_tb.v"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -top_module blink_top
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream