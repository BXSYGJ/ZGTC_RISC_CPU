cfg_connect -ip 127.0.0.1 -port 65420
puts "== CONNECT DONE =="
cfg_set_cable_property -index 0 -freq 10Mhz
puts "== SET_PROP DONE =="
cfg_disconnect