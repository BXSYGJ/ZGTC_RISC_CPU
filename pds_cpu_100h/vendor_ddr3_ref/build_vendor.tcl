# Vendor DDR3 demo (2_9_ddr3_test) rebuilt with this project's PDS flow.
# Reference-only: establishes whether the IP runs under our flow/constraints.
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/test_ddr.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/test_main_ctrl_v1_0.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/test_wr_ctrl_v1_0.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/test_rd_ctrl_v1_0.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/axi_bist_top_v1_0.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/prbs15_64bit_v1_0.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/prbs31_128bit_v1_0.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_rd_lock.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/adc/adc.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/adc/adc_ctrl.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_clk_gen_32bit.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_cmd_parser_32bit.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_seu_rs232_intf.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_seu_uart_rx.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_seu_uart_tx.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_uart_ctrl_32bit.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_uart_ctrl_top_32bit.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/example_design/rtl/uart_ctrl_32bit/ips2l_ver_ctrl_32bit.v"
add_design "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ipcore/ddr3_test/ddr3_test.idf"
add_constraint "D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/vendor_ddr3_ref/constraints/vendor_ddr3.fdc"
set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
compile -top_module test_ddr
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream
