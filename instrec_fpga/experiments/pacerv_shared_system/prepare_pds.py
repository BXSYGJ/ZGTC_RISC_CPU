"""Freeze inputs and build a separate PG100 PaceRV audio-system project."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(stage: str, seed: int = 1, hold_iterations: int = 4,
            pnr_mode: str = 'performance', router_threads: int = 1,
            hold_margin_ps: int = 100, hold_clock_margin_ps: int = 200,
            hold_cross_srb_margin_ps: int = 400) -> Path:
    if router_threads != 1:
        raise ValueError('PG2L100H uses the vendor single-thread router')
    if not all(0 <= value <= 2000 for value in
               (hold_margin_ps, hold_clock_margin_ps, hold_cross_srb_margin_ps)):
        raise ValueError('Hold optimization margins must be within 0..2000 ps')
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "build/pacerv_shared_system/pds" / ("full-" + stamp + "-" + stage)
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / "inputs"
    config = json.loads((ROOT / "scripts/build_sets.json").read_text(encoding="utf-8"))["sets"]["full"]
    files: list[Path] = []
    for pattern in config["sources"]:
        matches = sorted(ROOT.glob(pattern)) if "*" in pattern else [ROOT / pattern]
        if not matches and "*" not in pattern:
            raise FileNotFoundError(pattern)
        files.extend(matches)
    files = list(dict.fromkeys(files))
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)
        target = inputs / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for relative in config["ip_cores"]:
        source = (ROOT / relative).parent
        shutil.copytree(source, inputs / source.relative_to(ROOT), dirs_exist_ok=True)
    for relative in config["constraints"]:
        source = ROOT / relative
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in config["hex_dirs"]:
        for path in (ROOT / relative).glob("*.hex"):
            target = inputs / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    all_inputs = sorted(p for p in inputs.rglob("*") if p.is_file())
    records = [{"path": str(p.relative_to(inputs)).replace(os.sep, "/"),
                "bytes": p.stat().st_size, "sha256": digest(p)} for p in all_inputs]
    lines = [f'add_design "{(inputs / p.relative_to(ROOT)).as_posix()}"' for p in files]
    lines += [f'add_design "{(inputs / p).as_posix()}"' for p in config["ip_cores"]]
    lines += [f'add_constraint "{(inputs / p).as_posix()}"' for p in config["constraints"]]
    for relative in config["hex_dirs"]:
        target_dir = out / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for p in (inputs / relative).glob("*.hex"):
            shutil.copy2(p, target_dir / p.name)
    lines += ["set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676",
              "compile -system_verilog -top_module instrec_top"]
    if stage in ("map", "full"):
        lines += ["synthesize -ads -selected_syn_tool_opt 2", "dev_map"]
    if stage == "full":
        lines += [f"pnr -mode {pnr_mode} -gplace_seed {seed} "
                  "-optimize_multi_corner_timing -fix_hold_violation "
                  f"-fix_hold_violation_in_route TRUE -fix_hold_violation_iterations {hold_iterations} "
                  f"-fix_hold_violation_threshold {hold_margin_ps} "
                  f"-fix_hold_violation_threshold_for_clock_path_cross_srb {hold_cross_srb_margin_ps} "
                  f"-fix_hold_violation_threshold_for_clk_tree {hold_clock_margin_ps} "
                  "-max_hold_violated_paths_num 50000",
                  "report_timing", "gen_bit_stream"]
    lines.append("exit")
    (out / "build.tcl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ddr_parameters = {p.findtext('name'): p.findtext('value') for p in ET.parse(
        inputs / 'ipcore/ddr3_test/ddr3_test.idf').findall('./param_list/param')}
    manifest = {"scope": "complete PG100 audio/NPU/display/PaceRV system", "stage": stage,
                "target": "PG2L100H-6IFBG676", "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "design_files": len(files), "files": records,
                "placement_seed": seed, "hold_fix_iterations": hold_iterations,
                "pnr_mode": pnr_mode, "router_threads": router_threads,
                "system_clock_hz": round(float(ddr_parameters['ACTUAL_RATE']) * 1e6 / 8),
                "pixel_clock_hz": 148500000,
                "hold_margin_ps": {"post_route": hold_margin_ps,
                                   "cross_srb": hold_cross_srb_margin_ps,
                                   "clock_tree": hold_clock_margin_ps}}
    (out / "INPUTS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("PDS_PREPARED " + str(out), flush=True)
    return out


def prepare_remote(stage: str) -> Path:
    remote = ROOT / "experiments/pacerv_shared_system/remote"
    subprocess.run([os.sys.executable, str(remote / "prepare_build.py")], check=True, cwd=ROOT)
    source_manifest = json.loads((remote / "build/BUILD_MANIFEST.json").read_text(encoding="utf-8"))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "build/pacerv_shared_system/pds" / ("remote-" + stamp + "-" + stage)
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for item in source_manifest["inputs"]:
        source = ROOT / item["path"]
        if digest(source) != item["sha256"]:
            raise RuntimeError("Remote manifest changed: " + str(source))
        target = out / "inputs" / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append({"path": str(target.relative_to(out / "inputs")).replace(os.sep, "/"),
                        "bytes": target.stat().st_size, "sha256": digest(target)})
    shutil.copy2(remote / "firmware/remote_prog.hex", out / "remote_prog.hex")
    recipe = (remote / "build/build.tcl").read_text(encoding="utf-8")
    recipe = recipe.replace(ROOT.as_posix() + "/", (out / "inputs").as_posix() + "/")
    commands = recipe.splitlines()
    if stage == "compile":
        commands = commands[:next(i for i, s in enumerate(commands) if s.startswith("synthesize"))] + ["exit"]
    elif stage == "map":
        commands = commands[:next(i for i, s in enumerate(commands) if s.startswith("pnr"))] + ["exit"]
    (out / "build.tcl").write_text("\n".join(commands) + "\n", encoding="utf-8")
    manifest = {"scope": "PG200 CPU/physical DDR/UART with synthetic competing master",
                "target": source_manifest["target"], "project_name": "pacerv_shared_200h",
                "stage": stage, "files": records, "clock_hz": 125000000}
    (out / "INPUTS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("PDS_PREPARED " + str(out), flush=True)
    return out


def run(out: Path, minutes: int, restart: bool = False) -> None:
    out = out.resolve(strict=True)
    manifest = json.loads((out / "INPUTS.json").read_text(encoding="utf-8"))
    def verify() -> None:
        for item in manifest["files"]:
            if digest(out / "inputs" / item["path"]) != item["sha256"]:
                raise RuntimeError("Frozen input changed: " + item["path"])
    verify()
    check = subprocess.run(["pwsh", "-NoProfile", "-Command",
        "if (Get-Process -Name pds_shell -ErrorAction SilentlyContinue) { exit 2 }"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    if check.returncode:
        raise RuntimeError("A PDS process is already running")
    pds = Path(os.environ.get("PDS_ROOT", "D:/PDS_2022.2-SP6.4")) / "bin/pds_shell.exe"
    if not pds.is_file():
        raise FileNotFoundError(pds)
    if not Path(os.environ.get("PANGO_LICENSE_FILE", "")).is_file():
        raise RuntimeError("PANGO_LICENSE_FILE must identify an existing license file")
    prior = None
    prior_record = None
    recipe = out / 'build.tcl'
    if restart:
        prior = json.loads((out / 'RESULT.json').read_text(encoding='utf-8'))
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        attempt = out / 'attempts' / stamp
        attempt.mkdir(parents=True, exist_ok=False)
        for name in ('RESULT.json', 'build.tcl', 'pds.stdout.log', 'pds.stderr.log'):
            shutil.copy2(out / name, attempt / name)
        full = (out / 'build.tcl').read_text(encoding='utf-8')
        full = re.sub(r' -number_of_router_thread \d+', '', full)
        (out / 'build.tcl').write_text(full, encoding='utf-8')
        prior_record = {'directory': str(attempt), 'result_sha256': digest(attempt / 'RESULT.json'),
                        'recipe_sha256': digest(attempt / 'build.tcl')}
    command = [str(pds), "-file", str(recipe), "-work_dir", str(out),
               "-project_name", manifest.get("project_name", "pacerv_shared_100h")]
    started = time.monotonic()
    with (out / "pds.stdout.log").open("wb") as stdout, (out / "pds.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=out, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        print("PDS_PID " + str(process.pid), flush=True)
        try:
            code = process.wait(timeout=minutes * 60)
        except subprocess.TimeoutExpired:
            # Only this runner's PDS process tree; never the JTAG service.
            subprocess.run(["pwsh", "-NoProfile", "-Command",
                f"Stop-Process -Id {process.pid} -Force -ErrorAction SilentlyContinue"],
                creationflags=subprocess.CREATE_NO_WINDOW)
            raise RuntimeError("PDS time budget exhausted: " + str(out))
    verify()
    output = (out / "pds.stdout.log").read_text(encoding="utf-8", errors="replace")
    output += (out / "pds.stderr.log").read_text(encoding="utf-8", errors="replace")
    errors = [s for s in output.splitlines() if re.match(r"^E:", s)
              and "SCBV has not been set" not in s and "Bitstream-2001" not in s]
    stages = {s: bool(re.search(r"Executing\s*:\s*" + s + r"\b[^\r\n]*successfully\.", output))
              for s in ("compile", "synthesize", "dev_map", "pnr", "report_timing", "gen_bit_stream")}
    result = {"command": command, "exit_code": code, "seconds": time.monotonic()-started,
              "frozen_inputs_unchanged": True, "stages": stages, "errors": errors}
    if prior:
        result.update(restarted_from_frozen_inputs=True, prior_attempt=prior_record)
    if manifest["stage"] == "full" and stages["report_timing"]:
        from inspect_pds import inspect
        qualification = inspect(out)
        (out / "QUALIFICATION.json").write_text(json.dumps(qualification, indent=2) + "\n", encoding="utf-8")
        result["all_constraints_met"] = qualification["timing"]["all_constraints_met"]
        result["qualified"] = qualification["qualified"]
        result["routed_resources"] = qualification["routed_resources"]
    (out / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    required = ["compile"] + (["synthesize", "dev_map"] if manifest["stage"] in ("map", "full") else [])
    if manifest["stage"] == "full":
        required += ["pnr", "report_timing", "gen_bit_stream"]
    if code or errors or not all(stages[s] for s in required):
        raise RuntimeError("PDS stage failed; inspect " + str(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("compile", "map", "full"), default="compile")
    ap.add_argument("--scope", choices=("full", "remote"), default="full")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--restart", type=Path, help="Replay an existing frozen build; preserve the prior attempt")
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--hold-iterations", type=int, default=4)
    ap.add_argument('--hold-margin-ps', type=int, default=100)
    ap.add_argument('--hold-clock-margin-ps', type=int, default=200)
    ap.add_argument('--hold-cross-srb-margin-ps', type=int, default=400)
    ap.add_argument("--mode", choices=('normal', 'performance', 'fast'), default='performance')
    ap.add_argument("--router-threads", type=int, choices=(1,), default=1,
                    help="Routing workers; vendor documents PG2L100H as a single-thread routing device")
    args = ap.parse_args()
    if args.seed < 1 or args.hold_iterations < 1:
        ap.error('Seed and hold iterations must be positive')
    if not 1 <= args.router_threads <= (os.cpu_count() or 1):
        ap.error('Router threads must be between one and the host logical CPU count')
    output = args.restart if args.restart else (prepare_remote(args.stage) if args.scope == "remote" else prepare(
        args.stage, args.seed, args.hold_iterations, args.mode, args.router_threads,
        args.hold_margin_ps, args.hold_clock_margin_ps, args.hold_cross_srb_margin_ps))
    if args.run:
        run(output, args.minutes, restart=bool(args.restart))
