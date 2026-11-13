"""Execute the exact RV32IMC firmware with a simulation-only DDR user-port model."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware",type=Path,default=HERE/"firmware"/"remote_prog.hex")
    parser.add_argument("--audio",action="store_true",help="validate the main audio-control firmware through its first synthetic NPU result")
    parser.add_argument("--no-key-reset",action="store_true",help="start with physical KEY0 already released, as after remote programming")
    args=parser.parse_args()
    out=HERE/"sim_build"/("audio" if args.audio else "shared")
    out.mkdir(parents=True,exist_ok=True)
    shutil.copy2(args.firmware,out/"remote_prog.hex")
    production=(PROJECT/"src"/"ddr3"/"ddr3_wrapper.v").read_text(encoding="utf-8-sig")
    header=production[:production.index("    // Single-ended reference clock")]
    model=header+'''    assign core_clk=ref_clk_p;
    assign core_clk_rst_n=resetn;
    assign pll_lock=resetn;
    assign ddrphy_cpd_lock=resetn;
    reg [4:0] delay_count=0;
    always @(posedge ref_clk_p or negedge resetn) begin
        if(!resetn) delay_count<=0;
        else if(delay_count!=31) delay_count<=delay_count+1'b1;
    end
    assign ddr_init_done=delay_count==31;
    assign axi_wusero_id=0;
    ddr3_axi_model #(.AW_DELAY(2),.W_DELAY(1),.AR_DELAY(3),.R_STALL_CYCLES(5)) memory_model (
        .clk(core_clk),.rst_n(core_clk_rst_n),
        .s_awaddr(axi_awaddr),.s_awvalid(axi_awvalid),.s_awlen(axi_awlen),.s_awuser_id(axi_awuser_id),.s_awready(axi_awready),
        .s_wdata(axi_wdata),.s_wstrb(axi_wstrb),.s_wready(axi_wready),.s_wusero_last(axi_wusero_last),
        .s_araddr(axi_araddr),.s_arvalid(axi_arvalid),.s_arlen(axi_arlen),.s_aruser_id(axi_aruser_id),.s_arready(axi_arready),
        .s_rdata(axi_rdata),.s_rid(axi_rid),.s_rlast(axi_rlast),.s_rvalid(axi_rvalid)
    );
endmodule
'''
    (out/"ddr3_wrapper_model.sv").write_text(model,encoding="utf-8")
    manifest=json.loads((HERE/"build"/"BUILD_MANIFEST.json").read_text(encoding="utf-8"))
    sources=[PROJECT/r["path"] for r in manifest["sources"] if not r["path"].endswith("ddr3_wrapper.v")]
    sources += [PROJECT/"sim"/"ddr3_axi_model.sv",out/"ddr3_wrapper_model.sv",HERE/"tests"/"tb_remote_pg200.v"]
    iverilog=shutil.which("iverilog") or "D:/AAAPP/iverilog/bin/iverilog.exe"
    vvp=shutil.which("vvp") or "D:/AAAPP/iverilog/bin/vvp.exe"
    switches=["-Ptb_remote_pg200.AUDIO=1"] if args.audio else []
    if args.no_key_reset:
        switches += ["-Ptb_remote_pg200.NO_KEY_RESET=1"]
    subprocess.run([iverilog,"-g2012","-s","tb_remote_pg200"]+switches+["-o",str(out/"sim.vvp")]+[str(p) for p in sources],cwd=out,check=True)
    with (out/"simulation.log").open("w",encoding="utf-8") as log:
        run=subprocess.run([vvp,str(out/"sim.vvp")],cwd=out,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=360 if args.audio else 180)
    output=(out/"simulation.log").read_text(encoding="utf-8")
    print(output)
    marker="REMOTE_AUDIO_PROTOCOL_SIM PASS" if args.audio else "REMOTE_PROTOCOL_SIM PASS"
    if run.returncode or marker not in output:
        raise RuntimeError("Protocol simulation failed; inspect simulation.log.")

if __name__=="__main__": main()
