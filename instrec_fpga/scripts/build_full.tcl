# Project: __PROJECT_NAME__
__DESIGN_FILES__

__IP_FILES__

__HEX_COPY_BLOCK__

__CONSTRAINT_FILES__

set instrec_project_root "__PROJECT_ROOT__"
set instrec_build_root "__BUILD_ROOT__"
puts "instrec build: project_root=$instrec_project_root build_root=$instrec_build_root"

set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676

compile -system_verilog -top_module __TOP_MODULE__
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
