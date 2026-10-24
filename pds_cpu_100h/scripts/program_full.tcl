# Program the PG2L100H CPU SoC bitstream over JTAG (USB Cable II -> J12).
# Requires jtagserver on 127.0.0.1:65420:
#   H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_js.exe -port 65420 -work_dir <this scripts dir>
# then:
#   H:/GG/pango/PDS_2022.2-SP6.4/bin/cdt_cfg.exe -file program_full.tcl
# NOTE: the .sbit path below is absolute; adjust if the repository moves.
cfg_set_tcl_break -flag false
cfg_connect -ip 127.0.0.1 -port 65420
puts "== step1: set cable property =="
cfg_set_cable_property -index 0 -freq 10Mhz
puts "== step2: scan chain =="
cfg_scan_chain
puts "== step3: assign file =="
cfg_assign_file -file D:/0000/111/001/Pango/ZGTC_RISC_CPU/pds_cpu_100h/build/pds-latest.sbit -device_index 0
puts "== step4: program =="
cfg_program -device_index 0
cfg_disconnect
