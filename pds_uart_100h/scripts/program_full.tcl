cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
puts "== step1: set cable property =="
cfg_set_cable_property -index 0 -freq 10Mhz
puts "== step2: scan chain =="
cfg_scan_chain
puts "== step3: assign file =="
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_uart_100h/generate_bitstream/uart_top.sbit -device_index 0
puts "== step4: program =="
cfg_program -device_index 0
cfg_disconnect
