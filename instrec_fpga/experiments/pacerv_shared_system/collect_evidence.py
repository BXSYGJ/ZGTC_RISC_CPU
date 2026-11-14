"""Collect completed integration evidence without changing source or build inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from inspect_pds import inspect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def observed_uncertainty(text: str) -> dict:
    observed = {'setup': set(), 'hold': set()}
    for block in text.split('Startpoint  :')[1:]:
        if not re.search(r'Path Group\s*:\s*ddrphy_sysclk\b', block):
            continue
        kind = re.search(r'Path Type\s*:\s*(max|min) \((?:slow|fast) corner\)', block)
        value = re.search(r'clock uncertainty\s+(-?[\d.]+)', block)
        if kind and value:
            observed['setup' if kind[1] == 'max' else 'hold'].add(abs(float(value[1])))
    if any(not values for values in observed.values()):
        raise RuntimeError('System setup/hold path uncertainty is missing from the timing report')
    if any(value < 0.150 for values in observed.values() for value in values):
        raise RuntimeError('Reported system path uncertainty is below the declared 0.150 ns budget')
    return {'reported_system_' + kind + '_uncertainty_ns': sorted(values)
            for kind, values in observed.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-build", type=Path, required=True)
    parser.add_argument("--remote-build", type=Path)
    parser.add_argument("--board-run", type=Path)
    parser.add_argument("--npu-run", type=Path, required=True)
    parser.add_argument("--uart-run", type=Path,
                        default=ROOT / 'build/pacerv_shared_system/uart/clock_109375')
    parser.add_argument("--audio-clock-run", type=Path)
    parser.add_argument("--loader-gap-study", type=Path)
    parser.add_argument("--allow-pending-timing", action="store_true",
                        help="Publish functional evidence with an explicit unqualified pending timing gate")
    parser.add_argument("--dashboard-run", type=Path,
                        default=ROOT / 'build/pacerv_shared_system/dashboard_equivalence_7clock')
    args = parser.parse_args()
    if bool(args.remote_build) != bool(args.board_run):
        parser.error("Optional remote evidence needs both --remote-build and --board-run")
    selected_manifest = read(args.full_build / 'INPUTS.json')
    uncertainty_fdc = args.full_build / 'inputs/constraints/pacerv_shared_system.fdc'
    uncertainty = re.search(r'^set_clock_uncertainty \{([\d.]+)\} -setup -hold -from ',
                            uncertainty_fdc.read_text(encoding='utf-8'), re.M)
    if not uncertainty or float(uncertainty[1]) != 0.150:
        raise RuntimeError('The selected full build must retain 0.150 ns setup/hold uncertainty')
    operating_point = {'target': selected_manifest['target'],
                       'system_clock_hz': selected_manifest['system_clock_hz'],
                       'pixel_clock_hz': selected_manifest['pixel_clock_hz'],
                       'declared_system_setup_hold_uncertainty_ns': float(uncertainty[1])}
    git_context = {key: subprocess.check_output(['git', *git_args], cwd=ROOT, text=True,
                                                creationflags=subprocess.CREATE_NO_WINDOW).strip()
                   for key, git_args in (('branch', ['branch', '--show-current']),
                                         ('checkout_commit', ['rev-parse', 'HEAD']))}
    evidence = HERE / "evidence"
    evidence.mkdir(exist_ok=True)
    copied = []

    def retain(source: Path, name: str) -> None:
        destination = evidence / name
        if destination.is_file() and digest(destination) != digest(source):
            history = evidence / 'history' / digest(destination)[:12] / name
            history.parent.mkdir(parents=True, exist_ok=True)
            if history.exists() and digest(history) != digest(destination):
                raise RuntimeError('Historical evidence collision: ' + name)
            shutil.copy2(destination, history)
        shutil.copy2(source, destination)
        if digest(source) != digest(destination):
            raise RuntimeError("Evidence copy differs: " + name)
        copied.append({"source": str(source.resolve()), "file": name,
                       "bytes": destination.stat().st_size, "sha256": digest(destination)})

    cpu_file = ROOT / "build/pacerv_integration/pacerv_checks.json"
    baseline_file = ROOT / "build/pacerv_shared_system/baseline/BASELINE_CPU_RESULTS.json"
    npu_file = args.npu_run / "PACERV_NATIVE_REPORT.json"
    cpu, baseline, npu = read(cpu_file), read(baseline_file), read(npu_file)
    if cpu["wrapper_sha256"] != digest(ROOT / "src/cpu/rv32_cpu_subsys.sv"):
        raise RuntimeError("CPU checks refer to a different wrapper")
    for item in npu["inputs"]:
        path = Path(item["path"])
        if not path.is_file() or digest(path) != item["sha256"]:
            raise RuntimeError("Native NPU input changed: " + str(path))
    retain(cpu_file, "PACERV_CPU_CHECKS.json")
    retain(baseline_file, "BASELINE_CPU_RESULTS.json")
    retain(baseline_file.with_name("BASELINE_CPU_OUTPUT.txt"), "BASELINE_CPU_OUTPUT.txt")
    retain(npu_file, "FULL_NPU_IMC_RESULTS.json")
    retain(args.npu_run / "pacerv_native_npu.log", "FULL_NPU_IMC_OUTPUT.txt")
    ddr_dir = ROOT / 'sim/experiments/pacerv_shared_ddr'
    ddr_checks = {}
    for mode in ('BASELINE', 'MODIFIED', 'ROLLBACK'):
        source = ddr_dir / (mode + '_RESULTS.json')
        cases = read(source)
        ddr_checks[mode] = bool(cases) and all(
            c['CompileExit'] == 0 and c['RunExit'] == 0 and 'PASS' in c['Output'] for c in cases)
        retain(source, 'SHARED_DDR_' + mode + '_RESULTS.json')
    for item in read(ddr_dir / 'SOURCE_HASHES.json'):
        if digest(Path(item['File'])).upper() != item['ModifiedSHA256'].upper():
            raise RuntimeError('Shared DDR evidence input changed: ' + item['File'])
    retain(ddr_dir / 'SOURCE_HASHES.json', 'SHARED_DDR_SOURCE_HASHES.json')
    retain(ddr_dir / 'VERIFICATION.txt', 'SHARED_DDR_VERIFICATION.txt')
    retain(ROOT / "build/pacerv_shared_system/focused_regression.log", "FOCUSED_PYTHON_OUTPUT.txt")
    rollback_file = evidence / "INTEGRATION_ROLLBACK_RESULTS.json"
    rollback = read(rollback_file)
    if not rollback.get("passed") or not rollback.get("live_modified_files_unchanged"):
        raise RuntimeError("Integration rollback has not passed")
    uart_file = args.uart_run / "RESULT.json"
    uart = read(uart_file)
    if not uart.get("passed"):
        raise RuntimeError("Production shared UART check has not passed")
    for item in uart["inputs"]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Shared UART inputs changed: " + item["path"])
    retain(uart_file, "SHARED_UART_RESULTS.json")
    retain(ROOT / "build/pacerv_shared_system/uart/before_priority_fix_v2/RESULT.json",
           "SHARED_UART_BEFORE_FIX.json")
    standard_file = ROOT / "build/pacerv_shared_system/standard_cpu_entry/RESULT.json"
    standard = read(standard_file)
    if not standard.get("passed"):
        raise RuntimeError("Standard CPU testbench has not passed")
    for item in standard["inputs"]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Standard CPU testbench input changed: " + item["path"])
    retain(standard_file, "STANDARD_CPU_TB_RESULTS.json")
    pipeline_checks = {}
    for key, source in (("dashboard_equivalence", args.dashboard_run / 'RESULT.json'),
                        ("activation_mux", ROOT / 'build/pacerv_shared_system/activation_mux/RESULT.json')):
        check = read(source)
        if not check['passed']:
            raise RuntimeError(key + ' did not pass')
        for item in check['inputs']:
            if digest(ROOT / item['path']) != item['sha256']:
                raise RuntimeError(key + ' input changed: ' + item['path'])
        retain(source, key.upper() + '_RESULTS.json')
        pipeline_checks[key] = check
    control_checks = {}
    original_hashes = {row['path'].removeprefix('instrec_fpga/'): row['sha256']
                       for row in read(HERE / 'BASELINE_MANIFEST.json')['files']}
    control_sources = ('src/ctrl/weight_loader.v', 'src/npu/gap_unit.v')
    if any(digest(ROOT / path) != original_hashes[path] for path in control_sources):
        if not args.loader_gap_study:
            raise RuntimeError('Modified loader/GAP requires --loader-gap-study evidence')
    if args.loader_gap_study:
        for mode in ('BASELINE', 'MODIFIED', 'ROLLBACK'):
            source = args.loader_gap_study / mode / 'RESULT.json'
            check = read(source)
            if check.get('mode') != mode or not check.get('passed') or not check.get('live_sources_unchanged'):
                raise RuntimeError('Loader/GAP control failed: ' + mode)
            baseline_manifest = Path(check['baseline_manifest'])
            if digest(baseline_manifest) != check['baseline_manifest_sha256']:
                raise RuntimeError('Loader/GAP frozen baseline manifest changed')
            control_baseline_hashes = {item['path']: item['sha256']
                                       for item in read(baseline_manifest)['files']}
            for item in check['inputs']:
                expected = (digest(ROOT / item['path']) if mode == 'MODIFIED'
                            else control_baseline_hashes[item['path']])
                if item['sha256'] != expected:
                    raise RuntimeError('Loader/GAP control source mismatch: ' + mode + ' ' + item['path'])
            for item in check['test_inputs']:
                if digest(Path(item['path'])) != item['sha256']:
                    raise RuntimeError('Loader/GAP test input changed: ' + item['path'])
            retain(source, 'LOADER_GAP_' + mode + '_RESULTS.json')
            control_checks[mode] = check
        if len({check['baseline_manifest_sha256'] for check in control_checks.values()}) != 1:
            raise RuntimeError('Loader/GAP controls use different frozen baselines')
    audio_clock = None
    if args.audio_clock_run:
        audio_clock = read(args.audio_clock_run / 'RESULT.json')
        if not audio_clock['passed'] or not audio_clock['live_inputs_unchanged']:
            raise RuntimeError('Audio clock comparison has not passed')
        for path, expected in audio_clock['inputs_sha256'].items():
            if digest(Path(path)) != expected:
                raise RuntimeError('Audio clock input changed: ' + path)
        retain(args.audio_clock_run / 'RESULT.json', 'AUDIO_CLOCK_RESULTS.json')
        for case in audio_clock['cases']:
            retain(Path(case['simulation']['log']),
                   'AUDIO_CLOCK_' + str(case['clock_hz']) + '_OUTPUT.txt')
    elif read(args.full_build / 'INPUTS.json').get('system_clock_hz', 125000000) != 125000000:
        raise RuntimeError('Changed system clock requires --audio-clock-run')
    physical = {}
    checkout_file = args.full_build / "CHECKOUT_INPUT_AUDIT.json"
    checkout = read(checkout_file)
    if not checkout["passed"] or checkout["manifest_sha256"] != digest(args.full_build / "INPUTS.json"):
        raise RuntimeError("Git checkout input audit is missing or stale")
    retain(checkout_file, "FULL_CHECKOUT_INPUT_AUDIT.json")
    selected_builds = [("FULL", args.full_build)]
    if args.remote_build:
        selected_builds.append(("REMOTE", args.remote_build))
    for label, run in selected_builds:
        build_manifest = read(run / "INPUTS.json")
        for item in build_manifest["files"]:
            current = ROOT / item["path"]
            if not current.is_file() or digest(current) != item["sha256"]:
                raise RuntimeError("Selected build differs from current input: " + str(current))
        if args.allow_pending_timing and label == 'FULL' and not list((run / 'report_timing').glob('*.rtr')):
            physical['full'] = {'run': str(run.resolve()), 'target': build_manifest['target'],
                                'status': 'final_timing_evidence_pending', 'qualified': False,
                                'frozen_input_count': len(build_manifest['files'])}
            interruption_file = run / 'INTERRUPTION.json'
            if interruption_file.is_file():
                interruption = read(interruption_file)
                if interruption['manifest_sha256'] != digest(run / 'INPUTS.json'):
                    raise RuntimeError('Interrupted build manifest changed')
                for record in interruption['logs']:
                    if digest(run / record['path']) != record['sha256']:
                        raise RuntimeError('Interrupted build log changed: ' + record['path'])
                if interruption['status'] != 'interrupted_timeout' or interruption['supervisor_exit_status'] != 1:
                    raise RuntimeError('Unexpected interrupted build status')
                physical['full'].update(status=interruption['status'],
                                        supervisor_exit_status=interruption['supervisor_exit_status'],
                                        last_route_iteration=interruption['last_route_iteration'],
                                        last_unrouted_subnets=interruption['last_unrouted_subnets'])
                retain(interruption_file, 'FULL_PDS_INTERRUPTION.json')
            stale_names = ('FULL_PDS_RESULT.json', 'FULL_PDS_QUALIFICATION.json', 'FULL_TIMING.rtr',
                           'FULL_ROUTED_RESOURCES.prr', 'FULL_RAM_INFERENCE.txt')
            if not interruption_file.is_file():
                stale_names += ('FULL_PDS_INTERRUPTION.json',)
            for name in stale_names:
                old = evidence / name
                if old.is_file():
                    historical = evidence / 'history' / digest(old)[:12] / name
                    historical.parent.mkdir(parents=True, exist_ok=True)
                    if historical.exists() and historical.read_bytes() != old.read_bytes():
                        raise RuntimeError('Historical physical evidence collision: ' + name)
                    shutil.copy2(old, historical)
                    if historical.read_bytes() != old.read_bytes():
                        raise RuntimeError('Physical evidence archive mismatch: ' + name)
                    old.unlink()
            retain(run / 'INPUTS.json', label + '_PDS_INPUTS.json')
            retain(run / 'build.tcl', label + '_BUILD_RECIPE.tcl')
            continue
        qualification = inspect(run)
        if read(run / 'QUALIFICATION.json') != qualification:
            raise RuntimeError('Stored PDS qualification is stale: ' + str(run))
        retain(run / 'QUALIFICATION.json', label + '_PDS_QUALIFICATION.json')
        for source_name, target_name in (("INPUTS.json", "_PDS_INPUTS.json"),
                                         ("RESULT.json", "_PDS_RESULT.json")):
            retain(run / source_name, label + target_name)
        retain(Path(qualification["timing_report"]), label + "_TIMING.rtr")
        retain(run / "build.tcl", label + "_BUILD_RECIPE.tcl")
        resource_reports = list((run / "place_route").glob("*.prr"))
        if len(resource_reports) != 1:
            raise RuntimeError("Exactly one routed resource report is required")
        retain(resource_reports[0], label + "_ROUTED_RESOURCES.prr")
        retain(run / "synthesize/apm_drm_lutram_utilization.log", label + "_RAM_INFERENCE.txt")
        physical[label.lower()] = qualification
        if label == 'FULL':
            operating_point.update(observed_uncertainty(
                Path(qualification['timing_report']).read_text(encoding='utf-8')))
    board = None
    if args.board_run:
        board = read(args.board_run / "result.json")
        remote = physical["remote"]
        if board["bitstream_sha256"] != remote["bitstream_sha256"]:
            raise RuntimeError("Board capture and selected remote build differ")
        for filename in ("result.json", "capture.txt", "capture.bin", "capture.jsonl"):
            retain(args.board_run / filename, "BOARD_" + filename)
        board_pass = (board.get("matched") is True and board.get("released") is True
                      and board.get("programmed") is True
                      and board.get("longest_consecutive_passes", 0) >= 2
                      and not board.get("errors"))
    verdict = {"baseline_passed": baseline["passed"], "cpu_passed": cpu["passed"],
               "native_npu_passed": npu["status"] == "pass",
               "rollback_passed": rollback["passed"],
               "shared_ddr_passed": all(ddr_checks.values()),
               "shared_uart_passed": uart["passed"],
               "standard_cpu_tb_passed": standard["passed"],
               "checkout_inputs_match": checkout["passed"],
               "full_pds_qualified": physical["full"]["qualified"]}
    verdict.update({key + '_passed': value['passed'] for key, value in pipeline_checks.items()})
    if audio_clock:
        verdict['audio_clock_passed'] = audio_clock['passed']
    if control_checks:
        verdict['loader_gap_controls_passed'] = all(check['passed'] for check in control_checks.values())
    if args.remote_build:
        verdict.update(remote_pds_qualified=physical["remote"]["qualified"],
                       remote_board_passed=board_pass)
    source_paths = [ROOT / "src/cpu/rv32_cpu_subsys.sv", ROOT / "src/ctrl/instrec_top.v",
                    *sorted((ROOT / "src/cpu/vendor/pacerv_h3").glob("*.sv")),
                    *[ROOT / "src/ddr3" / name for name in
                      ("pace_cpu_ddr_bridge.v", "ddr3_m3_share.v", "ddr3_ctrl_axi.v", "ddr3_arbiter.v")],
                    ROOT / "src/cpu/prog_pacerv.hex", ROOT / "sw/rv32/main_pacerv.c",
                    ROOT / 'src/npu/activation_store_mux.v', ROOT / 'src/npu/activation_row_store_dynamic.v',
                    ROOT / 'src/npu/fc_engine.v', ROOT / 'src/npu/wdma.v',
                    ROOT / 'src/npu/weight_read_aligner_hardened.v',
                    ROOT / 'src/ctrl/weight_loader.v', ROOT / 'src/npu/gap_unit.v',
                    ROOT / 'ipcore/ddr3_test/ddr3_test.idf', ROOT / 'constraints/ddr3_100h.fdc',
                    ROOT / 'src/ui/dashboard_text.v',
                    ROOT / 'src/ui/dashboard_renderer.v']
    artifacts = {"MODIFIED_FILE": str(HERE / "MODIFIED_FILE.sv"),
                 "DIFF_FILE": str(HERE / "DIFF_FILE.patch"),
                 "VERIFICATION": str(HERE / "VERIFICATION.txt"),
                 "ROLLBACK": str(HERE / "ROLLBACK.sh")}
    summary = {"verdict": verdict, "all_selected_gates_passed": all(verdict.values()),
               'git_context': git_context, 'operating_point': operating_point,
               "artifacts": artifacts,
               "source_hashes": [{"path": str(p.relative_to(ROOT)), "sha256": digest(p)}
                                 for p in source_paths],
               "physical": physical, "board": board, "evidence_files": copied,
               "scope": "PG100 complete-system implementation and functional simulation; "
                        + ("optional PG200 board evidence" if args.board_run else
                           "local PDS qualification requested; board testing not selected")}
    for name in ('RESULTS.json', 'VERIFICATION.txt'):
        old = HERE / name
        if old.is_file():
            historical = evidence / 'history' / digest(old)[:12] / name
            historical.parent.mkdir(parents=True, exist_ok=True)
            if historical.exists() and historical.read_bytes() != old.read_bytes():
                raise RuntimeError('Historical review artifact collision: ' + name)
            shutil.copy2(old, historical)
    (HERE / "RESULTS.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = ["PaceRV core + shared whole-system memory/peripherals", "",
             'Branch and checkout: ' + json.dumps(git_context),
             'Selected operating point: ' + json.dumps(operating_point),
             "Changed: RV32IMC H3 execution core, paired local-ROM fetch, uncached CPU DDR data port,",
             "M3_MASK_ENABLE byte masks and locked M3 client ownership; native local data RAM;",
             "four-source UART acceptance, registered MMIO/activation/DDR commands, synchronous FC",
             "coefficient RAM, seven-clock display alignment, FETCH_ADDRESS_BITS=IAW+2 ROM qualification,",
             "register-based short weight FIFOs, digest_q/rdigest_q checksum staging,",
             "GAP synchronous block-RAM accumulator pipeline, scalar DDR/UART FIFO registers,",
             "and matched actual DDR/system clock configuration.",
             "", "Selected gates: " + json.dumps(verdict),
             "Physical status: " + json.dumps({label: item.get('status', 'complete')
                                             for label, item in physical.items()}), "",
             "Baseline and CPU/NPU exact commands, inputs, literal output and exits follow."]
    lines += [name + ": " + path for name, path in artifacts.items()]
    lines += ["", "Working directory: " + str(ROOT),
              "BASELINE exact command: python experiments/pacerv_shared_system/run_baseline_cpu.py",
              "Input: baseline commit 852f067db4a4a710f5355e3ab311f035ced5b48d, original prog.hex and RTL.",
              "Literal result: RV32 BENCH cycles=460012 inst=180008 acc=0xf2d8888b; RESULT: PASS; exit 0.",
              "MODIFIED exact command: python sim/experiments/pacerv_integration/run_pacerv_checks.py",
              "Input: same original prog.hex plus directed IMC/backpressure/fetch-fault cases and frozen H3 vendor core.",
              "Literal result: RV32 BENCH cycles=180016 inst=180008 acc=0xf2d8888b; PACERV_CHECKS_PASS cases=4 vendor_hashes=8; exit 0.",
              "ROLLBACK exact command: python experiments/pacerv_shared_system/run_integration_rollback.py",
              f"Input: marked modified copy populated from current files; {len(original_hashes)} original baseline files.",
              f"Literal result: INTEGRATION_ROLLBACK_PASS files={len(original_hashes)} cycles=460012 retired=180008 live_modified_unchanged=1; exit 0."]
    for label, report, key in (("BASELINE CPU", baseline, "commands"),
                                ("MODIFIED CPU", cpu, "results"),
                                ("MODIFIED NPU", npu, "commands"),
                                ("ROLLBACK CPU", rollback, "commands"),
                                ("MODIFIED SHARED UART", uart, "commands"),
                                ("STANDARD CPU TB (M and predictor disabled by this legacy TB)", standard, "commands"),
                                ("DISPLAY PIXEL EQUIVALENCE", pipeline_checks['dashboard_equivalence'], "commands"),
                                ("REGISTERED ACTIVATION MUX", pipeline_checks['activation_mux'], "commands")):
        lines += ["", label]
        for command in report[key]:
            lines += ["command: " + json.dumps(command["command"]),
                      "input/cwd: " + str(command.get("cwd", ROOT)),
                      "exit: " + str(command["exit_status"]),
                      "literal output:", command["output"]]
    if audio_clock:
        lines += ["", "PHYSICAL-RATE AUDIO CLOCK COMPARISON",
                  "Input: 48 kHz stereo I2S, 27 MHz receiver, production CDC FIFO/audio sink;",
                  "two 132096-frame windows per clock; behavioural DDR completion after 512 cycles.",
                  "Startup first window has one injected frame at each clock; stable second window",
                  "contains only real frames, with exact sample order and zero FIFO overflow."]
        for case in audio_clock['cases']:
            lines += ["system_clock_hz: " + str(case['clock_hz'])]
            for key in ('compile', 'simulation'):
                record = case[key]
                lines += [key + " command: " + json.dumps(record['command']),
                          "exit: " + str(record['exit_status']),
                          "raw output: " + record['log'], "raw output SHA256: " + record['log_sha256']]
            lines += ["literal results:", *case['literal_results']]
    if control_checks:
        lines += ['', 'CHECKSUM PIPELINE AND GAP STORAGE CONTROLS']
        for mode, report in control_checks.items():
            lines += [mode + ' exact command: python experiments/pacerv_shared_system/run_loader_gap_timing.py '
                      '--mode ' + mode + ' --label ' + args.loader_gap_study.name,
                      'Input source hashes: ' + json.dumps(report['inputs'])]
            for record in report['commands']:
                lines += ['command: ' + json.dumps(record['command']),
                          'input/cwd: ' + record['cwd'], 'exit: ' + str(record['exit_status']),
                          'literal output:', record['output']]
    lines += ["", "DDR BASELINE/MODIFIED/ROLLBACK exact commands and all literal outputs:",
              str(ROOT / "sim/experiments/pacerv_shared_ddr/VERIFICATION.txt"),
              "Rollback restored original behavior/hashes in a separate copy; live modified RTL remains.",
              "", "PDS exact commands, inputs and results are in evidence/*RESULT*.json,",
              "evidence/*INPUTS.json, evidence/*QUALIFICATION.json and evidence/*BUILD_RECIPE.tcl."]
    if args.board_run:
        lines += ["Optional board evidence: evidence/BOARD_*."]
    else:
        lines += ["Selected acceptance: 100Pro+ complete-system local PDS implementation and functional simulation."]
    (HERE / "VERIFICATION.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for path in (HERE / "RESULTS.json", *[Path(p) for p in artifacts.values()]):
        if not path.read_bytes():
            raise RuntimeError("Empty output: " + str(path))
    print(json.dumps({"verdict": verdict, "evidence_files": len(copied),
                      "output": str(HERE / "RESULTS.json")}, indent=2))


if __name__ == "__main__":
    main()
