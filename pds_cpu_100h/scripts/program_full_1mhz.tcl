# Low-speed (1 MHz) JTAG programming variant - use when the default 10 MHz
# link is marginal (silent data corruption shows as "program ok" but the FPGA
# never runs the new design).
cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
puts "== step1: set cable property =="
cfg_set_cable_property -index 0 -freq 1Mhz
puts "== step2: scan chain =="
cfg_scan_chain
puts "== step3: assign file =="
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/build/pds-latest.sbit -device_index 0
puts "== step4: program =="
cfg_program -device_index 0
cfg_disconnect
