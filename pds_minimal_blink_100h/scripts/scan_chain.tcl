# Pango 100Pro+ (PG2L100H) JTAG scan - full sequence
cfg_connect -ip 127.0.0.1 -port 65420
cfg_set_cable_property -index 0 -freq 10MHz
cfg_scan_chain
cfg_disconnect