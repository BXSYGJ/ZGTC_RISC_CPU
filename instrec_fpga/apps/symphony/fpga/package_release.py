"""Package the verified native HDMI bitstream without changing prior releases."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

from collect_evidence import verify_collected_delivery

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery",type=Path,default=HERE / "evidence/DELIVERY.json")
    parser.add_argument("--label",default="symphony-hdmi-"+datetime.now().strftime("%Y%m%d-%H%M%S"))
    args=parser.parse_args()
    if not args.label or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.label):
        parser.error("Invalid release label")
    delivery_sha256=sha(args.delivery)
    data=json.loads(args.delivery.read_text(encoding="utf-8"))
    run=verify_collected_delivery(data)
    bit=Path(data["bitstream"]["path"])
    if sha(bit)!=data["bitstream"]["sha256"]: raise RuntimeError("Bitstream no longer matches delivery report")
    manifest=json.loads((run / "INPUTS.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        if sha(run / "inputs" / row["path"])!=row["sha256"]: raise RuntimeError("Frozen source changed: "+row["path"])
    for row in manifest["application_source_files"]:
        if sha(ROOT / row["path"])!=row["sha256"]: raise RuntimeError("Application changed: "+row["path"])
    runtime={Path(row["path"]).name:Path(row["path"]) for row in data["runtime_inputs"]["files"]}
    weights=runtime["weights_image.bin"]
    uploader=runtime["weight_upload.py"]
    release=ROOT / "releases" / args.label
    if release.exists(): raise FileExistsError("Prior release is preserved: "+str(release))
    release.mkdir(parents=True)
    shutil.copyfile(bit,release / "instrec_top.sbit")
    if sha(release / "instrec_top.sbit")!=data["bitstream"]["sha256"]:
        raise RuntimeError("Copied bitstream differs from accepted delivery")
    # The reproducible repository helpers remain authoritative. This archive
    # also holds the exact PDS inputs and the actual successful map/PNR records.
    files={"instrec_top.sbit":bit,"runtime/weights_image.bin":weights,"runtime/weight_upload.py":uploader}
    for path in (run / "inputs").rglob("*"):
        if path.is_file(): files["frozen_inputs/"+path.relative_to(run / "inputs").as_posix()]=path
    for name in ("INPUTS.json","APPLICATION.patch","PREPARED_RTOS_INPUTS.json","build.tcl",
                 "RESULT.json","FULL_RESULT.json","ROM_AUDIT.json"):
        files["build/"+name]=run / name
    files["build/final_timing.rtr"]=Path(data["timing_report"]["path"])
    files["build/DELIVERY.json"]=args.delivery
    for path in HERE.parent.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".vvp",".pyc"):
            files["application/"+path.relative_to(HERE.parent).as_posix()]=path
    summary={"application":"乐境：原生FPGA HDMI导赏与识别窗口检索",
             "branch":"rtos125-integration","system_clock_hz":125000000,"pixel_clock_hz":148500000,
             "model_classes":8,"history_depth":64,"key":"KEY1 C23: short select; double bookmark; long page",
             "bitstream":{"file":"instrec_top.sbit","bytes":bit.stat().st_size,"sha256":sha(bit)},
             "delivery_sha256":delivery_sha256,"pds_run":run.name,"physical_board_test":data["physical_board_test"],
             "files":[{"path":name,"bytes":path.stat().st_size,"sha256":sha(path)} for name,path in sorted(files.items())]}
    archive=release / (args.label+".zip")
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as package:
        for name,path in sorted(files.items()): package.write(path,name)
        package.writestr("MANIFEST.json",json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    # Read every decompressed member; CRC alone does not bind it to its source.
    with zipfile.ZipFile(archive) as package:
        if set(package.namelist())!=set(files)|{"MANIFEST.json"}: raise RuntimeError("Archive membership mismatch")
        for row in summary["files"]:
            actual=package.read(row["path"])
            if len(actual)!=row["bytes"] or hashlib.sha256(actual).hexdigest()!=row["sha256"]:
                raise RuntimeError("Archive readback failed: "+row["path"])
        if json.loads(package.read("MANIFEST.json"))!=summary: raise RuntimeError("Archive manifest readback failed")
    verify_collected_delivery(data)
    if sha(args.delivery)!=delivery_sha256: raise RuntimeError("Delivery report changed during packaging")
    if sha(release / "instrec_top.sbit")!=data["bitstream"]["sha256"]:
        raise RuntimeError("Released bitstream differs from accepted delivery")
    summary["archive"]={"file":archive.name,"bytes":archive.stat().st_size,"sha256":sha(archive),"all_members_reopened":True}
    (release / "RELEASE.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if json.loads((release / "RELEASE.json").read_text(encoding="utf-8"))!=summary:
        raise RuntimeError("Release metadata readback failed")
    readme="\n".join([
        "# "+summary["application"],"",
        "显示器直接连接 FPGA HDMI，KEY1 短按选择、双击标记、长按切页。",
        "启动时使用 ZIP 内 runtime/weight_upload.py 加载同目录 weights_image.bin 八类权重，上传器运行依赖 pyserial。",
        "导赏页显示八类真实概率和最近窗口；检索页按类别选择窗口并标记。",
        "识别结果到达时间按开机毫秒记录，64 槽历史与书签复位清空。","",
        "- 位流：[instrec_top.sbit](instrec_top.sbit)",
        "- 输入、应用源码和验证记录：["+archive.name+"]("+archive.name+")",
        "- 全部哈希：[RELEASE.json](RELEASE.json)",
        "- 重建与操作：[应用说明](../../apps/symphony/README.md)","",
        "位流 SHA256：`"+sha(bit)+"`。",
        "ZIP SHA256：`"+sha(archive)+"`。",
        "ZIP 内全部 "+str(len(files)+1)+" 项均已逐一重开并核对 SHA256。",
        "125 MHz / 148.5 MHz、seed2/hold8 固定，原始最终时序报告在 ZIP 的 build/final_timing.rtr。",
        "物理板卡显示与按键实测状态："+data["physical_board_test"]+"。","",
    ])
    (release / "README.md").write_text(readme,encoding="utf-8")
    for path in (release / "instrec_top.sbit",archive,release / "RELEASE.json",release / "README.md"):
        if not path.read_bytes(): raise RuntimeError("Empty release artifact")
    print("SYMPHONY_RELEASE_PASS files="+str(len(files)+1)+" bit_sha256="+sha(bit)+" archive_sha256="+sha(archive)+" path="+str(release),flush=True)
    return 0


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
