"""Reopen extraction evidence and bind it to the completed source-reference runs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from qualify_extraction import RELEASES, bound_file, digest, parse_ports, read_json, write_json


def require(condition, text):
    if not condition:
        raise ValueError(text)


def windows_path(value):
    match = re.fullmatch(r"/mnt/([a-z])/(.+)", value)
    require(match is not None, "Expected an explicit mounted Windows path")
    return Path(match[1].upper() + ":/") / match[2]


def artifact(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(path), "bytes": len(data)}


def source_reference(root, release, source, prepared):
    ila = Path(source["source_waveform_manifest"]).parents[2]
    qualification = ila / release / "qualification"
    if release == "Original_155250":
        candidates = list((qualification / "full-runs").glob("*/RESULT.json"))
        require(bool(candidates), "No completed Original full reference run")
        result_path = max(candidates, key=lambda path: path.stat().st_mtime_ns)
        result = read_json(result_path)
        require(result["complete_coremark_run"] and result["iterations"] == 6000 and result["exit_code"] == 0,
                "Original full reference execution did not pass")
        require(result["uart_byte_identical"] and result["baseline_cycles_and_retired_equal"],
                "Original full reference output comparison did not pass")
        source_path = Path(result["source_identity"])
        full_dir = Path(result["run_directory"])
        native = read_json(full_dir / "simulate.command.json")
        require(native["exit_code"] == 0, "Original actual native run did not exit zero")
        compile_path = full_dir / "compile.command.json"
        identity = read_json(source_path)
        hashes = identity["hashes"]
        cycles, retired = result["cycle_count"], result["retired_count"]
        uart_path = full_dir / "uart.log"
        reference_uart_hash = result["reference_uart_sha256"]
        run_receipt = full_dir / "simulate.command.json"
        compile_dir = full_dir
        executable = windows_path(native["arguments"][native["arguments"].index("--exec") + 1])
        stdout_path = Path(native["stdout"])
        firmware = full_dir / "firmware.hex"
    else:
        result_path = qualification / "full_reference" / "RESULT.json"
        result = read_json(result_path)
        require(result["completed_6000_iterations"] and result["native_exit_code"] == 0 and
                result["exact_reference_uart_equal"] and result["all_crc_fields_equal_by_exact_uart"],
                "H3 full reference execution or exact UART comparison did not pass")
        run_receipt = Path(result["run_receipt"])
        native = read_json(run_receipt)
        require(native["actual_exit_code"] == 0 and native["status"] == "finished",
                "H3 actual native run did not finish successfully")
        source_path = bound_file(native["source_identity"], native["source_identity_sha256"])
        executable = bound_file(native["native_simulator"], native["native_simulator_sha256"])
        identity = read_json(source_path)
        hashes = {item["file"]: item["sha256"] for item in identity["rtl"]}
        cycles, retired = result["cycles"], result["retired"]
        uart_path = Path(result["uart"])
        reference_uart_hash = result["reference_uart_sha256"]
        compile_dir = source_path.parent
        compile_path = compile_dir / "compile.command.json"
        stdout_path = Path(native["stdout"])
        firmware = Path(native["working_directory"]) / "firmware.hex"
    compile_receipt = read_json(compile_path)
    require(compile_receipt.get("exit_code", compile_receipt.get("actual_exit_code")) == 0,
            "Reference compile did not exit zero")
    bound_file(firmware, prepared["firmware_sha256"])
    require(identity["firmware_sha256"] == prepared["firmware_sha256"] == result["firmware_sha256"],
            "Full reference firmware is not the miter firmware")
    bound_file(uart_path, result["uart_sha256"])
    require(digest(uart_path) == reference_uart_hash, "Full UART bytes differ from the accepted reference")
    uart_text = uart_path.read_text(encoding="utf-8-sig")
    for expected in ("Iterations       : 6000", "seedcrc          : 0xe9f5", "[0]crclist       : 0xe714",
                     "[0]crcmatrix     : 0x1fd7", "[0]crcstate      : 0x8e3a", "[0]crcfinal      : 0xa14c",
                     "ZGTC COREMARK FINISHED"):
        require(expected in uart_text, "Missing actual full-reference UART field: " + expected)
    require("PASS RTL CoreMark smoke" in stdout_path.read_text(encoding="utf-8-sig"),
            "Actual full reference stdout lacks completion")
    expected_flags = {"CLOCK_HZ": 3200, "BAUD": 100, "ENABLE_M": 1, "ENABLE_C": 1, "ENABLE_PREDICTOR": 1,
                      "LOAD_USE_BUBBLE": 1, "FAST_ICACHE_HIT": 1, "FAST_DCACHE_READ": 1,
                      "FAST_DCACHE_WRITE": 1, "FETCH_OVERLAP": 1, "DATA_OVERLAP": 1,
                      "EARLY_D_REQUEST": 1, "BTB_INDEX_BITS": 8, "ICACHE_SET_BITS": 9,
                      "CACHE_SET_BITS": 6, "ENABLE_CACHE": 1, "MEMORY_ADDRESS_BITS": 14}
    for name, value in expected_flags.items():
        require(f"-G{name}={value}" in compile_receipt["arguments"], "Full reference configuration differs: " + name)
    parent = read_json(prepared["parent_waveform_manifest"])
    parent_inputs = {Path(item["path"]).name: item for item in parent["source_inputs"]}
    joins = []
    for item in source["rtl"]:
        name = item["name"]
        actual_full = compile_dir / "inputs" / "rtl" / name
        bound_file(actual_full, item["sha256"])
        require(hashes[name] == item["sha256"], "Full reference source identity differs: " + name)
        joins.append({"name": name, "sha256": item["sha256"], "bare": item["path"],
                      "full_reference_compiled_source": str(actual_full), "exact_source_match": True})
    environment_joins = []
    compiled_sources = []
    for argument in compile_receipt["arguments"]:
        if argument.startswith("/mnt/") and argument.endswith((".sv", ".v", ".cpp")):
            path = windows_path(argument)
            compiled_sources.append(artifact(path))
            if "/inputs/rtl/" in argument:
                require(path.name in hashes, "Full compile contains unbound RTL: " + path.name)
                bound_file(path, hashes[path.name])
                if path.name in parent_inputs:
                    require(digest(path) == parent_inputs[path.name]["sha256"],
                            "Full reference environment differs from miter service: " + path.name)
                    environment_joins.append({"name": path.name, "sha256": digest(path)})
    return {"status": "PASS", "result": artifact(result_path), "run_receipt": artifact(run_receipt),
            "source_identity": artifact(source_path), "compile_receipt": artifact(compile_path),
            "compiled_sources": compiled_sources, "simulator": artifact(executable),
            "uart": artifact(uart_path), "stdout": artifact(stdout_path), "firmware": artifact(firmware),
            "core_source_joins": joins, "environment_source_joins": environment_joins,
            "iterations": 6000, "cycles": cycles, "retired": retired, "measured_ipc": retired / cycles,
            "scope": "Completed original full SoC source simulation; source identity joined to the new bare wrapper by the finite extraction miter",
            "fresh_full_bare_wrapper_run": False, "hardware_measurement": False}


def audit_release(root, release):
    result_path = root / "analysis" / (release + "-EXTRACTION_QUALIFICATION.json")
    result = read_json(result_path)
    require(result["status"] == "PASS" and result["origin"] == "LOCAL RTL SIMULATION", "Miter did not pass")
    prepared_path = bound_file(result["preparation"], result["preparation_sha256"])
    prepared = read_json(prepared_path)
    manifest_path = bound_file(prepared["bare_source_manifest"], prepared["bare_source_manifest_sha256"])
    source = read_json(manifest_path)
    bound_file(prepared["wrapper"], prepared["wrapper_sha256"])
    bound_file(prepared["parent_waveform_manifest"], prepared["parent_waveform_manifest_sha256"])
    for item in prepared["inputs"]:
        bound_file(item["path"], item["sha256"])
    for item in source["rtl"]:
        bound_file(item["path"], item["sha256"])
        bound_file(item["source"], item["sha256"])
    ports = parse_ports(Path(prepared["wrapper"]).read_text(encoding="utf-8-sig"))
    require(ports == prepared["ports"], "Core interface receipt changed")
    require(prepared["parameters"] == source["parameters"], "Core parameters differ")
    selected = [port for port in ports if port["name"] not in ("clk", "rst_n")]
    require(prepared["mismatch_groups"][:len(selected)] == ["core." + port["name"] for port in selected],
            "Miter does not compare every core input/output")
    require(sum(port["width"] for port in selected) == prepared["frame_bits"], "Core frame width differs")
    run = prepared_path.parent
    baseline = read_json(run / "baseline.json")
    require(baseline == result["result"] == read_json(run / "rollback.json"), "Restored behavior differs")
    bound_file(run / "baseline.json", result["raw_result_sha256"])
    bound_file(run / "rollback.json", result["rollback_result_sha256"])
    bound_file(run / "uart.log", result["uart_sha256"])
    bound_file(result["simulator_executable"], result["simulator_executable_sha256"])
    require(baseline["cpu_edges"] >= 2000000 and baseline["port_frame_comparisons"] == 2 * baseline["cpu_edges"],
            "Expected preedge and settled post-edge comparisons at every CPU edge")
    require(baseline["reference_frame_fnv1a64"] == baseline["bare_frame_fnv1a64"], "Core frame digests differ")
    require(all(baseline["kernel_entry_retirements"].values()), "Miter missed a benchmark kernel")
    negative_text = Path(result["modified_negative_control"]["stderr"]).read_text(encoding="utf-8-sig")
    expected_mask = 1 << prepared["mismatch_groups"].index("core.d_rsp_data")
    require(f"EXTRACTION_MISMATCH edge=10000 phase=preedge mask=0x{expected_mask:x}" in negative_text,
            "Negative control did not detect the intended DUT-input difference")
    commands = {}
    for name, status in (("baseline", 0), ("modified_negative_control", 1), ("rollback", 0)):
        command = result[name]
        require(command["exit_code"] == status, "Wrong actual command exit status: " + name)
        commands[name] = {"executable": command["executable"], "arguments": command["arguments"],
                          "exit_code": command["exit_code"],
                          "stdout_literal": Path(command["stdout"]).read_text(encoding="utf-8-sig"),
                          "stderr_literal": Path(command["stderr"]).read_text(encoding="utf-8-sig"),
                          "logs": [artifact(command[key]) for key in ("stdout", "stderr", "stdout_raw", "stderr_raw")]}
    full = source_reference(root, release, source, prepared)
    return {"release": release, "status": "PASS", "qualification": artifact(result_path),
            "preparation": artifact(prepared_path), "source_manifest": artifact(manifest_path),
            "all_port_bits": sum(port["width"] for port in ports), "compared_port_bits": prepared["frame_bits"],
            "compared_port_groups": len(selected), "shared_identical_clock_reset": ["clk", "rst_n"],
            "complete_core_closure_hash_joins": prepared["core_closure"], "parameters": source["parameters"],
            "result": baseline, "commands": commands, "restored_behavior_equal": True,
            "source_reference_6000_join": full,
            "external_service": prepared["external_service"], "configured_core_clock_hz": prepared["configured_core_clock_hz"]}


def render_readme(root, report):
    lines = ["# Bare-core extraction qualification", "",
             "All three pure-core wrappers passed fresh local RTL extraction tests. Each baseline and restored run compared every core input/output with an independent original SoC reference over 2,000,000 CPU edges. The reference and bare DUT each used a separate copy of the same existing cached memory and peripheral services, outside the eight-file DUT.", "",
             "| Core | Compared bits | Comparisons per run | Retired | List / matrix / state entry retirements | Full-port digest |",
             "| --- | ---: | ---: | ---: | --- | --- |"]
    for release in report["releases"]:
        r = release["result"]
        kernels = r["kernel_entry_retirements"]
        lines.append(f"| {release['release']} | {release['compared_port_bits']} | {r['port_frame_comparisons']:,} | {r['retired_count']:,} | {kernels['core_bench_list']} / {kernels['core_bench_matrix']} / {kernels['core_bench_state']} | `{r['bare_frame_fnv1a64']}` |")
    lines += ["", "The shared clock and reset are identically driven. Original exposes 616 total port bits; H3 exposes 648, including its separate pair-fetch address. All remaining 614/646 bits are compared without masking invalid-cycle payloads, before every edge and after its settled high/low clock evaluation. This includes requests, responses, retirement PC/instruction/register write, trap fields, pipeline-valid bits, maintenance, timer/interrupt inputs and both full 64-bit counters. Ten additional service/MMIO/serial status groups are compared. The digest records the compared frames; direct signal equality is the pass criterion.", "",
              "For every release, the negative control changed only the bare DUT's `d_rsp_data` input at edge 10000. The comparator detected that exact first difference and the process exited 1. A separate fault-free process then ran another 2,000,000 edges with exit 0 and reproduced the complete baseline JSON byte hash. Functional RTL and original source files were unchanged.", "",
              "## Source and completed benchmark join", "",
              "Each release preserves exactly these eight RTL files: `rv32_core`, `rv32_rvc_frontend`, `rv32_rvc_expand`, `rv32_decode`, `rv32_alu`, `rv32_muldiv`, `rv32_btb`, and `rv32_machine`. Every source hash joins the bare wrapper, accepted waveform build and the actual compiled source copies of its completed 6000-iteration original SoC simulation. Parameters and complete port widths match. Both firmware identity and the external cache/peripheral RTL identity also match.", "",
              "| Completed original source simulation | 6000-iteration measured cycles | Retired | IPC |",
              "| --- | ---: | ---: | ---: |"]
    for release in report["releases"]:
        full = release["source_reference_6000_join"]
        lines.append(f"| {release['release']} | {full['cycles']:,} | {full['retired']:,} | {full['measured_ipc']:.9f} |")
    lines += ["", "The full simulation rows above are completed original SoC executions. The new bare wrapper has a fresh finite 2M-edge extraction qualification. It was not rerun for all 6000 iterations. Exact unchanged source/configuration/firmware identity and the extraction miter support the behavior-preservation join; this finite test is not an exhaustive formal proof or additional full benchmark execution.", "",
              "## Memory service and area interpretation", "",
              "The synthesized DUT excludes all caches, backing RAM, arbiters, uncached bridges and MMIO peripherals. Its unchanged RV32IMC frontend/predictor, register file/pipeline, full machine CSR/interrupt/exception logic, 64-bit counters and multiply/divide unit remain inside. Existing services are external testbench components: enabled I-cache (set bits 9), D-cache (set bits 6), 64KiB RAM, original pair-fetch metadata, ready/valid timing, UART/MMIO and timer behavior. Two independent instances avoid feeding the DUT the reference's responses.", "",
              "Any joined execution-efficiency or CoreMark-per-area metric must say **core-only area with explicitly external cached-system services**. It is conditional on this service and is not a standalone cacheless-memory CoreMark result or whole-system area efficiency. Physical resource/frequency receipts must use the same source/parameters and separate core area from the scan fixture. The physical pipeline owns those receipts.", "",
              "All results are LOCAL RTL SIMULATION. The configured FPGA targets are 155.25 / 145.125 / 145.125 MHz. Simulation UART parameters are CLOCK_HZ=3200 and BAUD=100; neither is a measured hardware clock or baud. Original retains its established Verilator 4.038 behavioral memory recipe; H3 uses Verilator 5.032 and the actual timed native memory model. No remote board or hardware measurement was used.", "",
              "## Reproduce and review", "",
              "PowerShell 7:", "", "```powershell",
              "$runner = [System.IO.Path]::Combine('D:/AAAFPGA','Bare_Core_Releases_20261101','analysis','qualification','Invoke-ExtractionMiter.ps1')",
              "& $runner -Release Original_155250,H3_Base_145125,H3_Retained_145125 -Cycles 2000000", "```", "",
              "`EXTRACTION_QUALIFICATION.json` contains the independently reopened source joins, complete commands, literal outputs and actual 0 / 1 / 0 process statuses. Per-release `*-EXTRACTION_QUALIFICATION.json` links the immutable run directory, compile receipts, source snapshots, full signal map, raw stdout/stderr, baseline/rollback JSON and simulator hash. `qualification/audit_extraction_results.py` reopens and verifies these chains without rerunning the benchmark.", ""]
    path = root / "analysis" / "EXTRACTION_QUALIFICATION.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    require(path.read_text(encoding="utf-8").startswith("# Bare-core extraction qualification"), "Readme reopening failed")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        releases = [audit_release(root, release) for release in RELEASES]
        report = {"schema": "bare-core-extraction-qualification/v1", "status": "PASS",
                  "origin": "LOCAL RTL SIMULATION", "hardware_measurement": False,
                  "scope": "Finite extraction miter plus exact source/configuration/firmware join to completed original 6000-iteration SoC simulations",
                  "fresh_full_bare_wrapper_run": False, "standalone_cacheless_service_result": False,
                  "area_metric_label": "Core-only area with explicitly external cached-system services",
                  "baseline_cpu_edges_total": sum(item["result"]["cpu_edges"] for item in releases),
                  "rollback_cpu_edges_total": sum(item["result"]["cpu_edges"] for item in releases),
                  "direct_port_frame_comparisons_total_including_rollback": 2 * sum(item["result"]["port_frame_comparisons"] for item in releases),
                  "negative_controls": 3, "releases": releases, "audit_generator_sha256": digest(__file__),
                  "audited_utc": datetime.now(timezone.utc).isoformat()}
        output = root / "analysis" / "EXTRACTION_QUALIFICATION.json"
        write_json(output, report)
        require(read_json(output) == report, "Aggregate reopening failed")
        readme = render_readme(root, report)
        print(f"EXTRACTION_AUDIT_PASS releases=3 full_source_joins=3 comparisons_with_rollback={report['direct_port_frame_comparisons_total_including_rollback']}")
        print(str(output))
        print(str(readme))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("EXTRACTION_AUDIT_FAIL " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
