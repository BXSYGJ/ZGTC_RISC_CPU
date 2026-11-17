"""Validate selected proposal provenance using only archived source and receipts."""
from __future__ import annotations
import hashlib
import json
import re

CORE_PROPOSALS = ("load_selective_xor", "load_simple_native_add", "load_simple_relaxed_keep", "load_simple")
CACHE_PROPOSALS = ("timing_cache_counters_v2", "timing_cache_valid_v2")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_timing_report(data):
    text = data.decode("utf-8-sig")
    require("Design Summary : All Constraints Met." in text and "clock uncertainty" in text and "-0.150" in text, "Actualtimingreportclosureanduncertainty")
    require("CLKOUT0_Inferred  6.8900" in text and "145.1379 MHz" in text, "Actualgeneratedclockperiod")
    checks = {}
    for corner in ("Slow", "Fast"):
        for kind in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"):
            section = re.search(re.escape(kind + " Summary(" + corner + " Corner):") + r"(.*?)(?=\r?\n=+)", text, re.S)
            require(section is not None, "Actualtimingsection:" + kind + "/" + corner)
            rows = re.findall(r"^\s*(.*?)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+(\d+)\s+(\d+)\s*$", section[1], re.M)
            require(bool(rows), "Actualtimingendpointrows:" + kind + "/" + corner)
            checks[kind + "_" + corner] = [dict(Clocks=clocks.strip(), WorstSlackNs=float(slack), TotalNegativeSlackNs=float(total), FailingEndpoints=int(failing), TotalEndpoints=int(endpoints)) for clocks, slack, total, failing, endpoints in rows]
    return checks


def sat(receipt):
    require(receipt["exit_status"] == 0 and "SAT proof finished - no model found: SUCCESS!" in receipt["literal_output"], "SelectedproposalSATmustpass")


def verify_proposal(read, proposal, module, actual_hash):
    if proposal == "load_simple_loop16_h4":
        from h4_proof import verify_h4
        return verify_h4(read, actual_hash)
    require(proposal in CORE_PROPOSALS + CACHE_PROPOSALS, "Unknownselectedproposal")
    prefix = "evidence/rtl/" + proposal + "/"
    load = lambda name: json.loads(read(prefix + name).decode("utf-8-sig"))
    change, evidence = load("CHANGE.json"), load("VERIFICATION.txt")
    before, after = read(prefix + "BASELINE_FILE.sv"), read(prefix + module)
    baseline = change["baseline_sha256"].lower()
    modified = change.get("modified_sha256", change.get("candidate_sha256")).lower()
    require(digest(before) == baseline and digest(after) == modified == actual_hash, "Proposalproductionsourcebinding:" + proposal)
    require(evidence["baseline_sha256"].lower() == baseline and evidence["modified_sha256"].lower() == modified, "Proposalverificationhashbinding")
    directed = load("DIRECTED_VERIFICATION.json" if proposal in ("load_simple", "load_selective_xor") else "DIRECTED_EQUIVALENCE.json")
    tests = evidence["core_tests"]
    require(len(tests) == 3 and {t["name"] for t in tests} == {"BASELINE", "MODIFIED", "ROLLBACK"}, "Threeprovenancecorevariants")
    for test in tests:
        require(test["compile"]["exit_status"] == test["run"]["exit_status"] == 0 and "CORE_TOKEN_PASS early=1 mode=1 scenarios=23" in test["run"]["literal_output"], "Proposalcore23result")
        if module == "rv32_core.sv":
            require(test["source_sha256"].lower() == (modified if test["name"] == "MODIFIED" else baseline), "Proposalcoretestsourcehash")
        else:
            expected_source = module if test["name"] == "MODIFIED" else ("BASELINE_FILE.sv" if test["name"] == "BASELINE" else "rollback_test.sv")
            require(test["source"] == expected_source and expected_source in test["compile"]["command"], "Proposalcachecoretestsource")
    if proposal == "load_selective_xor":
        require(directed["status"] == "PASS" and directed["core_scenarios"] == 23 and directed["decoder_all2power32"] and directed["xor_result_all2power64"] and directed["negative_controls_rejected"] == 2, "XORdirectedproof")
        text = after.decode("utf-8-sig")
        require(text.count(change["class_after"]) == text.count(change["xor_after"]) == 1, "XORtransformunique")
        inverse = text.replace(change["class_after"], change["class_before"]).replace(change["xor_after"], change["adder_before"])
        inverse = inverse.replace("// Only XOR/XORI consume a load response in this path.", "// Only ADD/ADDI and XOR/XORI consume a load response in this path.")
        require(inverse == before.decode("utf-8-sig"), "XORexactinverse")
        sat(evidence["decoder_classification"]["formal"])
        sat(evidence["xor_result_proof"]["formal"])
        require(digest(read("physical_inputs/rtl/rv32_decode.sv")) == evidence["decoder_classification"]["actual_decoder_sha256"], "XORactualdecoderbinding")
        require(len(evidence["negative_controls"]) == 2 and all(t["expected_failure"] and t["run"]["exit_status"] != 0 for t in evidence["negative_controls"]), "XORnegativecontrols")
    elif proposal == "load_simple_native_add":
        require(directed["status"] == "PASS" and directed["scenarios"] == 23 and directed["actual_production_cones"] and directed["all65_binary_inputs_sat"] and directed["complete_cycle_output_identical"], "NativeADDdirectedproof")
        sat(evidence["formal"])
        require(evidence["negative_control"]["exit_status"] != 0 and evidence["unchanged_prefix_and_suffix"], "NativeADDsourceandnegativeproof")
        full = load("INTERFACE_EQUIVALENCE.json")
        require(full["only_different_input"] == ["rv32_core.sv"] and full["modified_build"]["input_sha256"][module] == modified, "NativeADDfull100source")
        for key in ("timed_cycles", "retired", "trace_sha256", "interface_sha256", "uart_sha256"):
            require(full["cached_baseline"][key] == full["modified"][key], "NativeADDfull100equality")
    elif proposal == "load_simple_relaxed_keep":
        require(directed["status"] == "PASS" and directed["scenarios"] == 23 and directed["exact_inverse_attribute_proof"] and directed["expression_mutation_rejected"], "RelaxedKeepdirectedproof")
        inverse = after.decode("utf-8-sig").replace("\r\n", "\n")
        require(len(change["removed_keep_wires"]) == 6, "RelaxedKeepsixattributes")
        for name in change["removed_keep_wires"]:
            inverse, count = re.subn(r"(wire \[[78]:0\] " + re.escape(name) + "=)", r"(* syn_keep=1 *) \1", inverse)
            require(count == 1, "RelaxedKeepexactdeclaration")
        require(inverse == before.decode("utf-8-sig").replace("\r\n", "\n"), "RelaxedKeepexactinverse")
    elif proposal == "load_simple":
        require(directed["architectural_match"] and directed["all_exit_zero"] and directed["formal_add_xor_all_inputs"] and directed["scenarios"] == 23, "OriginalSelectivedirectedproof")
        sat(evidence["formal"])
        decoder = load("DECODER_CLASSIFICATION.json")
        sat(decoder)
        require(decoder["core_sha256"].lower() == modified, "OriginalSelectivedecoderbinding")
    elif proposal == "timing_cache_counters_v2":
        require(directed["status"] == "PASS" and directed["formal_all_binary_inputs"] and directed["core_scenarios"] == 23 and directed["baseline_modified_rollback_equal"] and directed["all_cache_outputs_compared_each_cycle"], "Counterdirectedproof")
        sat(evidence["formal_transition"])
        full = load("INTERFACE_EQUIVALENCE.json")
        require(full["modified_build"]["input_sha256"][module] == modified, "Counterfull100sourcebinding")
        for key in ("timed_cycles", "retired", "trace_sha256", "interface_sha256", "uart_sha256"):
            require(full["cached_baseline"][key] == full["modified"][key], "Counterfull100equality")
    else:
        require(directed["status"] == "PASS" and directed["formal_geometries"] == 11 and directed["core_scenarios"] == 23 and directed["baseline_modified_rollback_equal"] and directed["cache_configs_per_variant"] == 9, "Validbankdirectedproof")
        text = after.decode("utf-8-sig")
        require(text.count(change["after"]) == 1 and text.replace(change["after"], change["before"]) == before.decode("utf-8-sig"), "Validbankexactinverse")
        require(len(evidence["formal"]) == 11, "Validbankformalgeometries")
        for item in evidence["formal"]:
            sat(item)
    rollback = load("ROLLBACK_SH_RESULT.json") if proposal == "load_simple" else load("ROLLBACK_RESULT.json")
    require(rollback.get("exit_status", rollback.get("ExitStatus")) == 0, "Proposalrollbackexit")
    restored = next((rollback[k] for k in ("restored_sha256", "RestoredHash", "RestoredSHA256", "restored_hash") if k in rollback), None)
    require(restored is not None and restored.lower() == baseline, "Proposalrestoredsourcehash")
    return dict(proposal=proposal, module=module, baseline_sha256=baseline, modified_sha256=modified, core_scenarios=23,
                change_sha256=digest(read(prefix + "CHANGE.json")), verification_sha256=digest(read(prefix + "VERIFICATION.txt")))


def collect_proofs(root, actual):
    def read(name):
        if name.startswith("evidence/rtl/"):
            return (root / "rtl_proposals" / name[len("evidence/rtl/"):]).read_bytes()
        if name.startswith("physical_inputs/rtl/"):
            return (actual / name[len("physical_inputs/rtl/"):]).read_bytes()
        raise ValueError("Unexpectedproofpath")
    proofs = []
    for module, proposals, required in (("rv32_core.sv", CORE_PROPOSALS, True), ("rv32_cache.sv", CACHE_PROPOSALS, False)):
        actual_hash = digest((actual / module).read_bytes())
        matches = []
        for proposal in proposals:
            area = root / "rtl_proposals" / proposal
            if (area / module).is_file() and digest((area / module).read_bytes()) == actual_hash:
                matches.append(proposal)
        require(len(matches) <= 1 and (bool(matches) or not required), "Selectedmoduleprovenancemustmatch:" + module)
        if matches:
            proofs.append(verify_proposal(read, matches[0], module, actual_hash))
        else:
            require(actual_hash == digest((root / "candidates/load_simple/rtl" / module).read_bytes()), "Unknowncachevariant")
    btb_hash = digest((actual / "rv32_btb.sv").read_bytes())
    if btb_hash == "b362dea594ba68f5eba4274ee054a5ec4d09e57b2695c695f1b2bdf849e8eca0":
        original_read = read
        def read(name):
            if name == "evidence/rtl/H4_BINDING.json":
                return (root / "scripts/closure-packaging-loop16-h4/H4_BINDING.json").read_bytes()
            return original_read(name)
        proofs.append(verify_proposal(read, "load_simple_loop16_h4", "rv32_btb.sv", btb_hash))
    else:
        require(btb_hash == "47573ae5b351a71c6bc453901822ca8910e7696c170bca71ecd77fb8eb5b0993", "UnknownBTBvariant")
    return proofs
