cfg_connect -ip 127.0.0.1 -port 65420
puts "== CONNECT DONE =="
cfg_set_cable_property -index 0 -freq 2Mhz
puts "== SET 2Mhz DONE =="
cfg_scan_chain
puts "== SCAN DONE =="
cfg_disconnect