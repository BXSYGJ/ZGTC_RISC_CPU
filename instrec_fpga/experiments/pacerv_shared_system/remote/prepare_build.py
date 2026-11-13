"""Stage PG200 vendor IP and emit a PDS build recipe; never launches PDS."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
REPO=PROJECT.parent

def copy_ip(source: Path) -> Path:
    target=HERE/"vendor"/"ddr3_test"
    idf=source/"ddr3_test.idf"
    tree=ET.parse(idf)
    header=tree.getroot().find("header")
    if header.findtext("device")!="PG2L200H" or header.findtext("package")!="FBB676":
        raise RuntimeError("Expected generated PG2L200H/FBB676 DDR IP.")
    records=[]
    names=["ddr3_test.idf"]+[n.attrib["pathname"] for n in tree.findall("./file_list/source/file")]
    for name in dict.fromkeys(names):
        src=source/name; dst=target/name
        if not src.is_file(): raise FileNotFoundError(src)
        dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists() or dst.read_bytes()!=src.read_bytes(): shutil.copy2(src,dst)
        records.append({"path":name,"bytes":dst.stat().st_size,"sha256":hashlib.sha256(dst.read_bytes()).hexdigest()})
    manifest={"source":str(source),"device":"PG2L200H","package":"FBB676","files":records}
    (HERE/"vendor"/"MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return target/"ddr3_test.idf"

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendor-ip",type=Path)
    ap.add_argument("--output",type=Path,default=HERE/"build")
    args=ap.parse_args()
    local=HERE/"vendor"/"ddr3_test"/"ddr3_test.idf"
    if args.vendor_ip: local=copy_ip(args.vendor_ip.resolve(strict=True))
    if not local.is_file(): ap.error("First preparation requires --vendor-ip pointing at the PG200 generated IP.")
    constraints=HERE/"constraints"
    constraints.mkdir(exist_ok=True)
    if not (constraints/"pg200_ddr3.fdc").exists():
        original=REPO/"cpu"/"constraints"/"ddr3.fdc"
        fdc=original.read_text(encoding="utf-8-sig").replace("board.ddr3_wrapper.","ddr3_wrapper.")
        fdc="\n".join(line for line in fdc.splitlines() if not line.startswith("set_clock_groups"))
        (constraints/"pg200_ddr3.fdc").write_text(fdc,encoding="utf-8")
    fdc=(constraints/"pg200_ddr3.fdc").read_text(encoding="utf-8-sig")
    lines=[line for line in fdc.splitlines() if not line.startswith("set_clock_uncertainty {0.150}")
           and not line.startswith("# One 0.150 ns budget")]
    lines=[line for line in lines if "CPU clock (clk, board.fdc) is asynchronous" not in line]
    lines += ["# One 0.150 ns budget for user-clock self paths (explicit clock pair).",
              "set_clock_uncertainty {0.150} -setup -hold -from [get_clocks {ddrphy_sysclk}] -to [get_clocks {ddrphy_sysclk}]"]
    (constraints/"pg200_ddr3.fdc").write_text("\n".join(lines)+"\n",encoding="utf-8")
    io=["# PG200 remote lab pins; 125 MHz CPU and DDR user logic share a clock.",
        "# The 27 MHz domain supplies startup reset only; release is IP-synchronized.",
        "create_clock -name {board_clk27} [get_ports {board_clk27}] -period {37.037} -waveform {0.000 18.519}",
        "set_clock_groups -name board_boot -asynchronous -group [get_clocks {board_clk27}]"]
    pins={"board_clk27":"D18","resetn":"C22","uart_tx":"AB26","led[0]":"A20","led[1]":"C18","led[2]":"C19","led[3]":"E18","led[4]":"A17","led[5]":"A18","led[6]":"C17","led[7]":"B17"}
    for port,pin in pins.items():
        direction="INPUT" if port in ("resetn","board_clk27") else "OUTPUT"
        io.extend([f"define_attribute {{p:{port}}} {{PAP_IO_DIRECTION}} {{{direction}}}",
                   f"define_attribute {{p:{port}}} {{PAP_IO_LOC}} {{{pin}}}",
                   f"define_attribute {{p:{port}}} {{PAP_IO_VCCIO}} {{3.3}}",
                   f"define_attribute {{p:{port}}} {{PAP_IO_STANDARD}} {{LVCMOS33}}",
                   f"define_attribute {{p:{port}}} {{PAP_IO_NONE}} {{TRUE}}"])
        if direction=="OUTPUT":
            io.extend([f"define_attribute {{p:{port}}} {{PAP_IO_DRIVE}} {{8}}",
                       f"define_attribute {{p:{port}}} {{PAP_IO_SLEW}} {{SLOW}}"])
    (constraints/"pg200_remote.fdc").write_text("\n".join(io)+"\n",encoding="ascii")
    sources=[PROJECT/"src"/"cpu"/"rv32_cpu_subsys.sv"]
    sources+=sorted((PROJECT/"src"/"cpu"/"vendor"/"pacerv_h3").glob("*.sv"))
    sources += [PROJECT/"src"/"ddr3"/name for name in ("pace_cpu_ddr_bridge.v","ddr3_m3_share.v","ddr3_ctrl_axi.v","ddr3_arbiter.v")]
    sources += [HERE/"rtl/ddr3_wrapper.v"]
    sources += [PROJECT/"src"/"ctrl"/"self_test.v",PROJECT/"src"/"ctrl"/"uart_tx.v",HERE/"remote_pg200_top.v"]
    for p in sources:
        if not p.is_file(): raise FileNotFoundError(p)
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    firmware=HERE/"firmware"/"remote_prog.hex"
    shutil.copy2(firmware,output/"remote_prog.hex")
    lines=[f'add_design "{p.as_posix()}"' for p in sources]
    lines += [f'add_design "{local.as_posix()}"']
    constraint_names=("pg200_ddr3.fdc","pg200_ip_cdc.fdc","pg200_remote.fdc")
    lines += [f'add_constraint "{(constraints/n).as_posix()}"' for n in constraint_names]
    lines += ["set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676",
              "compile -system_verilog -top_module remote_pg200_top",
              "synthesize -ads -selected_syn_tool_opt 2","dev_map","pnr -gplace_seed 1",
              "report_timing","gen_bit_stream","exit"]
    (output/"build.tcl").write_text("\n".join(lines)+"\n",encoding="utf-8")
    manifest={"top":"remote_pg200_top","target":"PG2L200H-6FBB676","clock_hz":125000000,
        "sources":[{"path":str(p.relative_to(PROJECT)),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
        "ip":str(local.relative_to(PROJECT)),"recipe":str(output/"build.tcl"),
        "pds_started":False,"physical_ddr":True,"competing_master":"synthetic pattern generator"}
    inputs=sources+[local,firmware]+[constraints/n for n in constraint_names]
    inputs+=sorted((HERE/"vendor"/"ddr3_test").glob("rtl/**/*"))
    inputs+=[HERE/"vendor"/"ddr3_test"/n for n in ("ddr3_test.v","ddr3_test_ddrphy_top.v")]
    manifest["inputs"]=[{"path":str(p.relative_to(PROJECT)),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in dict.fromkeys(inputs) if p.is_file()]
    (output/"BUILD_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"recipe":str(output/"build.tcl"),"source_count":len(sources),"pds_started":False}))

if __name__=="__main__": main()
