cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
cfg_set_cable_property -index 0 -freq 10Mhz
cfg_scan_chain
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/vendor_ddr3_ref/generate_bitstream/test_ddr.sbit -device_index 0
cfg_program -device_index 0
cfg_disconnect
