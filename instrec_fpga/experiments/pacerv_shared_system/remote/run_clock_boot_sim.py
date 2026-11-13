"""Check independent PG200 IP reset release using a pin-compatible IP stub."""
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
out = HERE / 'sim_build/clock_boot'
out.mkdir(parents=True, exist_ok=True)
ip = (HERE / 'vendor/ddr3_test/ddr3_test.v').read_text(encoding='utf-8-sig')
header = ip[:ip.index(');')+2]
stub = header + '''
reg test_lock=0;
// This contract stub withholds the user clock during startup. The wrapper
// must still expose the official, clock-independent PHY enable.
assign core_clk=test_lock ? ref_clk : 1'b0;
assign pll_lock=test_lock;
endmodule
module GTP_INBUFDS(output O,input I,IB); assign O=I; endmodule
module ips2l_rst_sync_v1_3(input clk,rst_n,sig_async,output sig_synced);
reg [1:0] sync_q;
always @(posedge clk or negedge rst_n)
 if(!rst_n) sync_q<=0; else sync_q<={sync_q[0],sig_async};
assign sig_synced=sync_q[1];
endmodule
'''
(out / 'ip_stub.sv').write_text(stub, encoding='utf-8')
tb = '''`timescale 1ns/1ps
module tb_clock_boot;
reg clk=0,resetn=0;
always #4 clk=~clk;
wire core_clk,core_resetn,lock;
ddr3_wrapper dut(.ref_clk_p(clk),.ref_clk_n(!clk),.resetn(resetn),
 .core_clk(core_clk),.core_clk_rst_n(core_resetn),.pll_lock(lock));
task edge_check; begin @(posedge clk); #1; end endtask
initial begin
 repeat(3) edge_check(); resetn=1;
 repeat(10) edge_check();
 if(dut.I_ips_ddr_top.dbg_ddrphy_rst_n!==1) $fatal(1,"PHY enable depends on stopped user clock");
 if(dut.I_ips_ddr_top.ck_dly_en!==0) $fatal(1,"PG200 CK delay must be disabled");
 dut.I_ips_ddr_top.test_lock=1;
 repeat(4) edge_check();
 if(core_resetn!==1) $fatal(1,"User reset release missing after clock starts");
 resetn=0; #1;
 if(core_resetn!==0 || dut.I_ips_ddr_top.resetn!==0) $fatal(1,"KEY reset did not assert");
 edge_check(); resetn=1; repeat(4) edge_check();
 if(core_resetn!==1) $fatal(1,"KEY reset release failed");
 $display("PG200_CLOCK_BOOT PASS independent_phy_enable=1 stopped_clock_start=1 key_reset=1 ck_delay=0");
 $finish;
end
initial begin #50000; $fatal(1,"clock boot timeout"); end
endmodule
'''
(out / 'tb_clock_boot.sv').write_text(tb, encoding='utf-8')
iv, vvp = shutil.which('iverilog'), shutil.which('vvp')
if not iv or not vvp:
    raise RuntimeError('Put Icarus on PATH')
records = []
for command in ([iv, '-g2012', '-s', 'tb_clock_boot', '-o', str(out/'test.vvp'),
                 str(out/'tb_clock_boot.sv'), str(out/'ip_stub.sv'), str(HERE/'rtl/ddr3_wrapper.v')],
                [vvp, str(out/'test.vvp')]):
    result = subprocess.run(command, capture_output=True, timeout=30)
    output = (result.stdout+result.stderr).decode('utf-8', errors='replace')
    records.append({'command': command, 'exit_status': result.returncode, 'output': output})
    if result.returncode:
        raise RuntimeError(output)
passed = 'PG200_CLOCK_BOOT PASS' in records[-1]['output']
(out/'RESULT.json').write_text(json.dumps({'passed':passed,'commands':records},indent=2)+'\n',encoding='utf-8')
print(records[-1]['output'])
raise SystemExit(0 if passed else 1)
