cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
puts "== set cable =="
cfg_set_cable_property -index 0 -freq 10Mhz
puts "== scan =="
cfg_scan_chain
puts "== assign =="
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/ref/ddr3_demo/2_9_ddr3_test/2_9_ddr3_test/ddr3_test/ipcore/ddr3_test/pnr/generate_bitstream/test_ddr.sbit -device_index 0
puts "== program =="
cfg_program -device_index 0
cfg_disconnect
