"""Verify an extracted PaceRV package or its ZIP using archived evidence only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from closure_proofs_h4 import verify_proposal, parse_timing_report


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(data):
    return json.loads(data.decode("utf-8-sig"))


def safe_name(value):
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and ".." not in path.parts and "\\" not in value
            and ":" not in value and path.as_posix() == value, "Invalid archive member name: " + value)
    return value


def canonical_core(data):
    text = data.decode("utf-8-sig").replace("\r\n", "\n")
    text = text.replace("    wire [4:0] id_rs1,id_rd;\n    (* syn_maxfan=8 *) wire [4:0] id_rs2;", "    wire [4:0] id_rs1,id_rs2,id_rd;")
    text = text.replace("(* syn_maxfan=8 *) wire id_zero_taken", "wire id_zero_taken")
    for name in ("frontend_redirect_address_select", "ex_transfer_capacity", "fetch_accept_space"):
        text = text.replace(f"(* syn_keep=1, syn_maxfan=8 *) wire {name}", f"(* syn_keep=1 *) wire {name}")
    group = ("    (* syn_keep=1 *) wire [7:0] id_operand_equal_nibbles;\n"
             "    generate for(genvar id_equal_nibble=0;id_equal_nibble<8;id_equal_nibble=id_equal_nibble+1) begin: id_equal_lut4\n"
             "        assign id_operand_equal_nibbles[id_equal_nibble]=\n"
             "            id_operand_a[id_equal_nibble*4+:4]==id_operand_b[id_equal_nibble*4+:4];\n"
             "    end endgenerate\n"
             "    wire id_operand_pair_equal=&id_operand_equal_nibbles;\n")
    if group in text:
        require(text.count(group) == 1, "Repeated core equality cone")
        text = text.replace(group, "").replace("id_operand_pair_equal;", "id_operand_a==id_operand_b;")
    return text


def verify_content(read, names):
    require(len(names) == len(set(names)), "Duplicate package member")
    for name in names:
        safe_name(name)
    manifest = json_bytes(read("MANIFEST.json"))
    require(manifest.get("closure_minimum_coremark_per_mhz_exclusive") == 3.5 and manifest["schema"] == "pacerv-optimized-release/v3-closure", "Closurepackagecontract")
    entries = manifest["files"]
    require(len(entries) == len({row["path"] for row in entries}), "Duplicate manifest path")
    require(set(names) == {row["path"] for row in entries} | {"MANIFEST.json"}, "Package inventory mismatch")
    for row in entries:
        data = read(safe_name(row["path"]))
        require(len(data) == row["bytes"] and digest(data) == row["sha256"].lower(), "Package hash or size mismatch: " + row["path"])
        require(not row["path"].endswith((".vvp", ".fst", ".vcd")), "Unexpected simulation binary or trace")
    require(manifest["frequency_hz"] == 145125000 and manifest["clock_uncertainty_ns"] == 0.15, "Clock binding")
    for role in ("V0", "V1"):
        prefix = "firmware/" + role + "/"
        run, build = json_bytes(read(prefix + "RUN.json")), json_bytes(read(prefix + "BUILD.json"))
        uart = read(prefix + "uart.log").decode("utf-8-sig")
        stdout = read(prefix + "simulation.log").decode("utf-8-sig")
        require(run["exit_status"] == 0 and all(run["checks"].values()) and run["formal_ten_seconds"], role + " run status")
        require(run["firmware"] == build and run["stdout"] == stdout, role + " run receipt binding")
        require(build["role"] == role and build["iterations"] == 6000, role + " role/iterations")
        image_hash = digest(read(prefix + "firmware.hex"))
        require(image_hash == build["firmware_hex_sha256"].lower() == manifest[role]["firmware_sha256"].lower(), role + " firmware binding")
        require(run["timed_cycles"] >= 1451250000 and "Correct operation validated." in uart and "ERROR" not in uart, role + " duration/validation")
        counters = re.search(r"cycles_hex=([0-9a-fA-F]{16}) retired_hex=([0-9a-fA-F]{16})", uart)
        require(counters is not None and int(counters[1], 16) == run["timed_cycles"]
                and int(counters[2], 16) == run["retired"], role + " UART counters")
        observer = re.search(r"OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)", stdout)
        require(observer is not None and int(observer[1]) == run["timed_cycles"] and int(observer[2]) == run["retired"]
                and int(observer[3]) == run["minimum_sp"] and 49152 <= int(observer[3]) <= 65536, role + " independentrawobservercounters")
        expected = {"V0": ["0xe714", "0x1fd7", "0x8e3a", "0xa14c"], "V1": ["0xe3c1", "0x0747", "0x8d84", "0x18e1"]}[role]
        crcs = re.findall(r"\[0\](?:crc(?:list|matrix|state)|crcfinal)\s*:\s*(0x[0-9a-fA-F]+)", uart)
        require(crcs == expected == run["crc_fields"], role + " CRCs")
        require(abs(run["coremark_per_mhz"] - 6000000000 / run["timed_cycles"]) < 1e-12
                and abs(manifest[role]["coremark_per_mhz"] - run["coremark_per_mhz"]) < 1e-12, role + " score")
        require(6000000000 / run["timed_cycles"] > 3.5, role + " scoremustexceed3.5")
        for relative, expected_hash in build["source_hashes"].items():
            require(digest(read(prefix + "inputs/" + safe_name(relative))) == expected_hash.lower(), role + " source hash: " + relative)
    physical = json_bytes(read("evidence/physical/BUILD_RESULT.json"))
    require(physical["ConfiguredCpuClockHz"] == 145125000 and physical["SetupUncertaintyNs"] == 0.15, "Physical clock")
    require(digest(read("physical_inputs/firmware.hex")) == physical["FirmwareSHA256"].lower()
            == manifest["V0"]["firmware_sha256"], "Physical V0 firmware")
    require(digest(read("bitstreams/V0.sbit")) == physical["Bitstream"]["SHA256"].lower()
            == manifest["physical"]["bitstream_sha256"], "Bitstream binding")
    report = read("evidence/physical/report_timing/pds_soc_top.rtr")
    require(digest(report) == physical["Timing"]["ReportSHA256"].lower(), "Timing report binding")
    require(b"Design Summary : All Constraints Met." in report and b"clock uncertainty" in report and b"-0.150" in report, "Actualtimingreportclosureanduncertainty")
    timing_checks = manifest.get("timing_checks", physical["Timing"]["Checks"])
    require(physical["Timing"]["Checks"] == timing_checks and len(timing_checks) == 10, "Ten timing categories")
    require(set(timing_checks) == {kind + "_" + corner for kind in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width") for corner in ("Slow", "Fast")}, "Exact10timingcategorynames")
    require(parse_timing_report(report) == timing_checks, "Actual10timingrowsmustmatchreceipt")
    passed = all(row["WorstSlackNs"] >= 0 and row["TotalNegativeSlackNs"] == 0 and row["FailingEndpoints"] == 0
                 for rows in timing_checks.values() for row in rows)
    require(passed == physical["Timing"]["AllReportedChecksPass"] == manifest["physical"]["all_ten_timing_checks_pass"], "Timing pass receipt")
    require(passed, "All10timingchecksmustpass")
    qualification = manifest.get("qualification_status", "timing_passed" if passed and manifest["schema"].endswith("/v1") else "experimental_timing_failed")
    require((qualification == "timing_passed") == passed
            and (physical["Status"] == "completed_timing_pass") == passed, "Qualification status")
    for row in json_bytes(read("evidence/physical/INPUT_HASHES.json")):
        require(digest(read("physical_inputs/" + safe_name(row["RelativePath"].replace("\\", "/")))) == row["SHA256"].lower(), "Physical input binding")
    binding = json_bytes(read("evidence/RTL_BINDING.json"))
    require(binding == manifest["rtl_binding"], "RTL binding receipt")
    checks = [row for row in binding["checks"] if isinstance(row, dict)]
    rtl_names = {PurePosixPath(name).name for name in names if name.startswith("simulation/rtl/") and name.endswith(".sv")}
    require(len(checks) == len(rtl_names) == len({row["name"] for row in checks}) == 17 and {row["name"] for row in checks} == rtl_names, "Exact17distinctRTLinputs")
    recipe = json_bytes(read("evidence/SIMULATION_RECIPE.json"))
    identity = hashlib.sha256()
    recipe_paths = ["simulation/rtl/" + PurePosixPath(item).name for item in recipe["simulation"]["argv"] if "/simulation/inputs/rtl/" in item]
    recipe_paths += ["simulation/sim/" + PurePosixPath(item).name for item in recipe["simulation"]["argv"] if "/simulation/inputs/sim/" in item]
    require({PurePosixPath(path).name for path in recipe_paths if path.startswith("simulation/rtl/")} == rtl_names, "Simulationrecipe17sourcebinding")
    for path in recipe_paths:
        identity.update(PurePosixPath(path).name.encode())
        identity.update(read(path))
    identity.update(str(binding["load_use_bubble"]).encode())
    require(identity.hexdigest() == binding["simulation_identity"], "Savedactualsimulationidentity")
    for role in ("V0", "V1"):
        run = json_bytes(read("firmware/" + role + "/RUN.json"))
        require(run["rtl_sha256"] == identity.hexdigest() and run["load_use_bubble"] == binding["load_use_bubble"], role + " actualsimulationinputbinding")
    for proof in binding.get("proofs", []):
        prefix = "evidence/rtl/" + proof["proposal"] + "/"
        if proof["proposal"] == "load_simple":
            change = json_bytes(read(prefix + "CHANGE.json"))
            require(digest(read("physical_inputs/rtl/rv32_core.sv")) == change["candidate_sha256"] == proof["modified_sha256"], "Selective source binding")
            directed = json_bytes(read(prefix + "DIRECTED_VERIFICATION.json"))
            require(directed["all_exit_zero"] and directed["architectural_match"] and directed["formal_add_xor_all_inputs"] and directed["scenarios"] == 23, "Selective directed proof")
            decoder = json_bytes(read(prefix + "DECODER_CLASSIFICATION.json"))
            require(decoder["exit_status"] == 0 and decoder["core_sha256"] == proof["modified_sha256"]
                    and "SAT proof finished - no model found: SUCCESS!" in decoder["literal_output"], "Selective decoder proof")
            require(all(item["expected_failure_observed"] and item["exit_status"] != 0
                        for item in json_bytes(read(prefix + "NEGATIVE_CONTROLS.json"))), "Selective negative controls")
            require(json_bytes(read(prefix + "ROLLBACK_SH_RESULT.json"))["exit_status"] == 0, "Selective rollback proof")
        elif proof["proposal"] == "timing_cache_hit_fanout":
            directed = json_bytes(read(prefix + "DIRECTED_EQUIVALENCE.json"))
            require(directed["baseline_modified_rollback_equal"] and directed["four_state_cases"] == 140000
                    and directed["core_scenarios"] == 23 and directed["cache_configs_per_variant"] == 4, "Cache directed proof")
            evidence = json_bytes(read(prefix + "VERIFICATION.txt"))
            require(len(evidence["formal_tests"]) == len(evidence["four_state_tests"]) == 7, "Cache proof widths")
            require(all(test["exit_status"] == 0 and "SAT proof finished - no model found: SUCCESS!" in test["literal_output"]
                        for test in evidence["formal_tests"]), "Cache formal proof")
            require(all(test["exit_status"] == 0 for test in evidence["four_state_tests"]), "Cache four-state proof")
            require(json_bytes(read(prefix + "ROLLBACK_RESULT.json"))["ExitStatus"] == 0, "Cache rollback proof")
    known = {"load_simple", "load_selective_xor", "load_simple_native_add", "load_simple_relaxed_keep", "timing_cache_counters_v2", "timing_cache_valid_v2", "load_simple_loop16_h4"}
    require(sum(proof.get("module") == "rv32_core.sv" for proof in binding.get("proofs", [])) == 1, "Exactlyoneselectedcoreprovenance")
    require(len({proof["module"] for proof in binding["proofs"]}) == len(binding["proofs"]), "Distinctprovenancemodules")
    for proof in binding["proofs"]:
        require(proof["proposal"] in known, "Unknownclosureproposal")
        require(verify_proposal(read, proof["proposal"], proof["module"], digest(read("physical_inputs/rtl/" + proof["module"]))) == proof, "Selectedprovenancereceiptbinding")
    if not any(proof["module"] == "rv32_cache.sv" for proof in binding["proofs"]):
        require(digest(read("physical_inputs/rtl/rv32_cache.sv")) == "c9d73d59e80a70399df214dfbbe3316083e6df0d33974e1564795a4ae875d6c1", "OriginalSelectivecachebinding")
    btb_hash = digest(read("physical_inputs/rtl/rv32_btb.sv"))
    btb_proofs = [proof for proof in binding["proofs"] if proof["module"] == "rv32_btb.sv"]
    if btb_hash == "b362dea594ba68f5eba4274ee054a5ec4d09e57b2695c695f1b2bdf849e8eca0":
        require(len(btb_proofs) == 1 and btb_proofs[0]["proposal"] == "load_simple_loop16_h4", "ExactlyoneH4BTBprovenance")
    else:
        require(btb_hash == "47573ae5b351a71c6bc453901822ca8910e7696c170bca71ecd77fb8eb5b0993" and not btb_proofs, "UnknownBTBvariant")
    for row in checks:
        sim = read("simulation/rtl/" + row["name"])
        phy = read("physical_inputs/rtl/" + row["name"])
        require(digest(sim) == row["simulation_sha256"] and digest(phy) == row["physical_sha256"], "RTL source inventory")
        require(sim == phy, "Exact17RTLbindingrequired")
        if sim == phy:
            continue
        if row["name"] == "rv32_core.sv":
            require(canonical_core(sim) == canonical_core(phy), "Unproved core source mismatch")
            proof = json_bytes(read("evidence/rtl/timing_id_equal_lut4/FORMAL_EQUIVALENCE.json"))
            require(proof["exit_status"] == 0, "Core SAT proof status")
            for proposal, filename in (("timing_id_fanout8", "BENCHMARK_EQUIVALENCE.json"), ("timing_id_equal_lut4", "INTERFACE_EQUIVALENCE.json")):
                evidence = json_bytes(read("evidence/rtl/" + proposal + "/" + filename))
                require(evidence["trace_comparison"]["exit_status"] == evidence["uart_comparison"]["exit_status"] == 0, "Core equivalence status")
                for field in ("timed_cycles", "retired", "trace_sha256", "uart_sha256"):
                    require(evidence["records"][0][field] == evidence["records"][1][field], "Core equivalence data")
        elif row["name"] == "rv32_cache.sv":
            prefix = "evidence/rtl/timing_cache_hit_fanout/"
            change = json_bytes(read(prefix + "CHANGE.json"))
            require({digest(sim), digest(phy)} == {change["baseline_sha256"], change["modified_sha256"]}, "Cache source pair")
            a, b = read(prefix + "BASELINE_FILE.sv"), read(prefix + "rv32_cache.sv")
            require(b.decode("utf-8-sig").replace(change["after"], change["before"]) == a.decode("utf-8-sig"), "Cache exact transform")
            evidence = json_bytes(read(prefix + "VERIFICATION.txt"))
            require(len(evidence["formal_tests"]) == 7 and all(test["exit_status"] == 0
                    and "SAT proof finished - no model found: SUCCESS!" in test["literal_output"] for test in evidence["formal_tests"]), "Cache SAT proof")
            interface = json_bytes(read(prefix + "INTERFACE_EQUIVALENCE.json"))
            require(interface["cached_baseline"]["exit_status"] == interface["modified"]["exit_status"] == 0, "Cache interface exits")
            for field in ("timed_cycles", "retired", "trace_sha256", "interface_sha256", "uart_sha256"):
                require(interface["cached_baseline"][field] == interface["modified"][field], "Cache interface equality")
        else:
            raise ValueError("Unproved RTL difference: " + row["name"])
    return {"files": len(entries), "common_rtl": 17, "timing_pass": passed, "v0_coremark_per_mhz": manifest["V0"]["coremark_per_mhz"],
            "v1_coremark_per_mhz": manifest["V1"]["coremark_per_mhz"], "bitstream_sha256": digest(read("bitstreams/V0.sbit"))}


def verify_folder(folder):
    folder = Path(folder).resolve()
    paths = sorted(p for p in folder.rglob("*") if p.is_file())
    require(not any(p.is_symlink() for p in paths), "Symlink package member")
    result = verify_content(lambda name: (folder / name).read_bytes(), [p.relative_to(folder).as_posix() for p in paths])
    return result


def verify_zip(path):
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "ZIP CRC failure")
        names = archive.namelist()
        require(names and all(not n.endswith("/") for n in names), "ZIP file entries expected")
        roots = {PurePosixPath(safe_name(name)).parts[0] for name in names}
        require(len(roots) == 1, "ZIP root folder")
        prefix = next(iter(roots)) + "/"
        return verify_content(lambda name: archive.read(prefix + name), [name[len(prefix):] for name in names])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder", type=Path)
    group.add_argument("--zip", type=Path)
    args = parser.parse_args()
    result = verify_zip(args.zip) if args.zip else verify_folder(args.folder)
    print("PACKAGE_VERIFY_PASS " + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
