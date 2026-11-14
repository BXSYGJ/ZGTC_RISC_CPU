"""Compile actual native RTL and capture four complete HDMI raster frames."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from PIL import Image

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/"rtos"/"sim"))
from output_decode import decode_mixed_output


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=PROJECT/"build"/"symphony"/"native-render")
    parser.add_argument("--simulator",choices=["verilator","iverilog"],default="verilator")
    args=parser.parse_args()
    output=args.out.resolve();output.mkdir(parents=True,exist_ok=True)
    sources=[ROOT/"symphony_renderer.v",ROOT/"tb_symphony_renderer.sv",ROOT/"gen_assets.py",ROOT/"run_render.py"]+sorted((ROOT/"assets").glob("*"))
    frozen=output/"src"/"ui";frozen.mkdir(parents=True,exist_ok=True)
    hashes={str(p.relative_to(ROOT)):digest(p) for p in sources if p.is_file()}
    for source in sources:
        if source.is_file():shutil.copy2(source,frozen/source.name)
    report={"passed":False,"fixture_only":True,"scope":"actual renderer RTL with one-clock fixture history query; actual state+KEY1 covered independently", "source_sha256":hashes,"output_decoder_sha256":digest(PROJECT/"rtos"/"sim"/"output_decode.py"),"commands":[],"screenshots":[],"simulator":args.simulator}
    started=time.monotonic()

    def execute(command):
        result=subprocess.run(command,cwd=output,capture_output=True,check=False,timeout=240)
        index=len(report["commands"])
        (output/f"command{index}.stdout.raw.log").write_bytes(result.stdout)
        (output/f"command{index}.stderr.raw.log").write_bytes(result.stderr)
        record={"command":command,"cwd":str(output),"exit_status":result.returncode,"literal_stdout":decode_mixed_output(result.stdout),"literal_stderr":decode_mixed_output(result.stderr)}
        report["commands"].append(record)
        print(record["literal_stdout"],end="",flush=True)
        if result.returncode:raise RuntimeError(record["literal_stderr"] or "Simulation command failed")
        return record["literal_stdout"]
    try:
        if args.simulator=="iverilog":
            execute(["iverilog","-g2012","-s","tb_symphony_renderer","-o","render.vvp","src/ui/symphony_renderer.v","src/ui/tb_symphony_renderer.sv"])
            literal=execute(["vvp","render.vvp"])
        else:
            windows=str(output).replace("\\","/")
            linux="/mnt/"+windows[0].lower()+windows[2:]
            prefix=["wsl.exe","-d","Ubuntu-22.04","--cd",linux,"--exec"]
            execute(prefix+["/home/bx/.local/src/verilator-5.040/bin/verilator","--binary","--timing","-Wno-fatal","--top-module","tb_symphony_renderer","--Mdir","obj","-j","2","src/ui/symphony_renderer.v","src/ui/tb_symphony_renderer.sv"])
            literal=execute(prefix+["./obj/Vtb_symphony_renderer"])
        if "NATIVE_SYMPHONY_RENDER_PASS frames=4 visible_pixels=8294400" not in literal:raise RuntimeError("Missing complete frame proof")
        for name in ["guide","library","library_empty","guide_filter"]:
            ppm=output/f"{name}.ppm";png=output/f"{name}.png"
            with Image.open(ppm) as image:
                image.load()
                if image.size!=(1920,1080):raise RuntimeError("Wrong frame dimensions")
                image.save(png)
            with Image.open(png) as image:image.load()
            report["screenshots"].append({"file":str(png),"sha256":digest(png),"ppm_sha256":digest(ppm),"size":[1920,1080]})
        report["inputs_unchanged"]=all(digest(ROOT/name)==value for name,value in hashes.items())
        if not report["inputs_unchanged"]:raise RuntimeError("Renderer input changed during capture")
        report["passed"]=True
    except Exception as error:
        report["error"]=str(error)
    report["elapsed_seconds"]=round(time.monotonic()-started,3)
    report["exit_status"]=0 if report["passed"] else 1
    filename=output/"RENDER_REPORT.json"
    filename.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if json.loads(filename.read_text(encoding="utf-8"))["passed"]!=report["passed"]:raise RuntimeError("Report reopen failed")
    print("NATIVE_RENDER_"+("PASS" if report["passed"] else "FAIL")+" report="+str(filename),flush=True)
    return report["exit_status"]


if __name__=="__main__":
    raise SystemExit(main())
