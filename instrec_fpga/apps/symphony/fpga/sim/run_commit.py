"""Verify the actual inference event extension and restore an independent copy.

The historical source is read-only. No simulator results are manufactured: each
variant is compiled and executed, including the PowerShell-restored copy.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
FPGA = HERE.parent
ROOT = FPGA.parents[2]
ORIGINAL = ROOT / "rtos/baseline125/src/ui/bars_data.v"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = (args.out or ROOT / "build/symphony/commit" / datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
    if out.exists():
        raise FileExistsError("Preserve previous evidence; choose a new output directory")
    out.mkdir(parents=True)
    iv, vvp, pwsh = (shutil.which(name) for name in ("iverilog", "vvp", "pwsh"))
    if not all((iv,vvp,pwsh)):
        raise RuntimeError("Native Icarus and PowerShell 7 are required")
    spec = importlib.util.spec_from_file_location("symphony_builder", FPGA / "build_system.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original_bytes = ORIGINAL.read_bytes()
    original_hash = sha(ORIGINAL)
    baseline = out / "BASELINE.v"
    modified = out / "MODIFIED_FILE.v"
    rollback_copy = out / "rollback_copy.v"
    baseline.write_bytes(original_bytes)
    changed = builder.patch_bars_data(original_bytes.decode("utf-8"))
    modified.write_text(changed, encoding="utf-8", newline="\n")
    rollback_copy.write_bytes(modified.read_bytes())
    diff_file = out / "DIFF_FILE.patch"
    diff_file.write_text("".join(difflib.unified_diff(
        original_bytes.decode("utf-8").splitlines(True), changed.splitlines(True),
        fromfile="baseline125/src/ui/bars_data.v", tofile="symphony/src/ui/bars_data.v")),encoding="utf-8")
    ps_quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    rollback_script = "\n".join([
        "[CmdletBinding()]",
        "param([Parameter(Mandatory=$true)][string]$Target, [string]$FixtureRoot = $PSScriptRoot)",
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
        "$ErrorActionPreference = 'Stop'",
        "try {",
        "    $expectedTarget = [System.IO.Path]::Combine($FixtureRoot, 'rollback_copy.v')",
        "    $resolvedTarget = [System.IO.Path]::GetFullPath($Target)",
        "    if ($resolvedTarget -ne [System.IO.Path]::GetFullPath($expectedTarget)) { throw 'Only the isolated rollback fixture is permitted' }",
        "    $source = [System.IO.Path]::Combine($FixtureRoot, 'BASELINE.v')",
        "    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne " + ps_quote(original_hash) + ") { throw 'Baseline hash mismatch' }",
        "    Copy-Item -LiteralPath $source -Destination $resolvedTarget -Force -ErrorAction Stop",
        "    if ((Get-FileHash -LiteralPath $resolvedTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne " + ps_quote(original_hash) + ") { throw 'Restored hash mismatch' }",
        "    Write-Output 'ROLLBACK_RESTORED original_sha256=" + original_hash + "'",
        "    exit 0",
        "} catch { Write-Error $_; exit 1 }",
        "",
    ])
    # The requested .sh artifact contains PowerShell 7 source; no Bash is used.
    for name in ("ROLLBACK.ps1", "ROLLBACK.sh"):
        (out / name).write_text(rollback_script, encoding="utf-8-sig",newline="\n")
    (out / "ROLLBACK.sh").chmod(0o755)
    bench = out / "tb_symphony_commit.sv"
    shutil.copy2(HERE / bench.name,bench)
    report = {"passed":False,"changed_field":"bars_data.frame_update", "branch":"rtos125-integration",
              "original_path":str(ORIGINAL),"original_sha256":original_hash,"modified_sha256":sha(modified),
              "artifacts":{name:str(out / name) for name in ("MODIFIED_FILE.v","DIFF_FILE.patch","VERIFICATION.txt","ROLLBACK.sh")},
              "commands":[]}

    def run(label: str, command: list[str]) -> str:
        proc = subprocess.run(command,cwd=out,capture_output=True,text=True,
                              encoding="utf-8",errors="strict",timeout=60)
        output = proc.stdout + proc.stderr
        report["commands"].append({"label":label,"command":command,"cwd":str(out),
                                    "input":str(bench) if label != "ROLLBACK_SCRIPT" else str(rollback_copy),
                                    "output":output,"exit_status":proc.returncode})
        if proc.returncode:
            raise RuntimeError(label + ": " + output)
        return output

    def simulate(label: str, source: Path, event: bool) -> str:
        binary = out / (label.lower()+".vvp")
        command = [iv,"-g2012","-s","tb_symphony_commit","-o",str(binary)]
        if event: command += ["-DHAS_FRAME_UPDATE"]
        run(label+"_COMPILE",command+[str(bench),str(source)])
        output = run(label,[vvp,"-i",str(binary)])
        expected = "MODIFIED_PASS" if event else "BASELINE_PASS"
        if expected not in output: raise RuntimeError("Missing success token: " + label)
        print(label + ": " + output.splitlines()[0],flush=True)
        return output

    try:
        simulate("BASELINE",baseline,False)
        simulate("MODIFIED",modified,True)
        # PowerShell reserves -File for .ps1. Execute the requested .sh source
        # through its native scriptblock API and pass paths as separate values.
        command = "& ([scriptblock]::Create([System.IO.File]::ReadAllText($args[0]))) -Target $args[1] -FixtureRoot $args[2]"
        restored = run("ROLLBACK_SCRIPT",[pwsh,"-NoProfile","-CommandWithArgs",command,
                                           str(out / "ROLLBACK.sh"),str(rollback_copy),str(out)])
        print(restored,end="",flush=True)
        simulate("ROLLBACK",rollback_copy,False)
        report["restored_behavior"]="Original coherent snapshots and sticky frame_ready; no frame_update extension"
        report["restored_sha256"]=sha(rollback_copy)
        report["baseline_unchanged"]=sha(ORIGINAL)==original_hash
        report["modified_left_changed"]=sha(modified)==report["modified_sha256"] and sha(modified)!=original_hash
        if not all((report["baseline_unchanged"],report["modified_left_changed"],sha(rollback_copy)==original_hash)):
            raise RuntimeError("Source preservation or rollback hash check failed")
        report["passed"]=True
    finally:
        (out / "RESULT.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        lines=["branch="+report["branch"],"changed_field="+report["changed_field"],
               "original_sha256="+original_hash,"modified_sha256="+report["modified_sha256"]]
        lines += [key+"="+value for key,value in report["artifacts"].items()]
        for command in report["commands"]:
            lines += ["",command["label"],"command="+subprocess.list2cmdline(command["command"]),
                      "cwd="+command["cwd"],"input="+command["input"],"literal_output:",
                      command["output"].rstrip(),"exit_status="+str(command["exit_status"])]
        lines += ["","restored_behavior="+report.get("restored_behavior","not completed"),"passed="+str(report["passed"])]
        (out / "VERIFICATION.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Reopen every claimed artifact and prove the patched copy remains changed.
    for path in (modified,diff_file,out / "VERIFICATION.txt",out / "ROLLBACK.sh"):
        if not path.read_bytes(): raise RuntimeError("Empty evidence artifact: " + str(path))
    print("SYMPHONY_COMMIT_TRANSACTION_PASS path="+str(out),flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
