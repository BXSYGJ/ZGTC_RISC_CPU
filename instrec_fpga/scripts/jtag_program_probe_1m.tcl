# Program the InstRec-FPGA M1 bitstream over JTAG (USB Cable II -> J12).
# Run with jtagserver already listening on 127.0.0.1:65420:
#   cdt_js.exe -port 65420
#   cdt_cfg.exe -file jtag_program_m1.tcl
# Absolute .sbit path: adjust if the repository moves.
cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
puts "== step1: set cable property =="
cfg_set_cable_property -index 0 -freq 1Mhz
puts "== step2: scan chain =="
cfg_scan_chain
puts "== step3: assign file =="
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/instrec_fpga/build/tmp/refclk_probe/generate_bitstream/probe_top.sbit -device_index 0
puts "== step4: program =="
cfg_program -device_index 0
puts "== step5: disconnect =="
cfg_disconnect
puts "== PROGRAM FLOW DONE =="