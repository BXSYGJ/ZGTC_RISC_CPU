import ast
import hashlib
import inspect
import itertools
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

from candidate_sources import ROOT, BASE, PARENT
from prepare_physical import digest, require

CPU = ROOT.parents[1]
sys.path.insert(0, str(CPU / "scripts"))
import test_cache_collision_forward as legacy

OUTPUT = ROOT / "build/cache-checks-complete"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def key(parameters):
    return tuple(sorted(parameters.items()))


def validate_coverage(record):
    require(record["passed"] is True and record["unchanged_inputs"] is True and record["tests_run"] == 6, "Incomplete cache test run")
    cases = record["cases"]
    require(len(cases) == 81, "Wrong cache case count")
    grouped = {label: [case for case in cases if case["label"] == label] for label in ("writable", "geometry", "bounds", "mutation", "store-overlap")}
    require(sum(map(len, grouped.values())) == len(cases), "Unknown cache case label")
    expected = []
    for bits, sets, read, write, overlap in itertools.product((16, 32), (6, 9), (0, 1), (0, 1), (0, 1)):
        expected.append(key(dict(ADDRESS_BITS=bits, CACHE_SET_BITS=sets, READONLY=0, FAST_READ_HIT=read,
                                 FAST_WRITE_HIT=write, READ_OVERLAP=overlap, CHECK_SYNC_WRITE=1, GEOMETRY_STREAM=1)))
    require(Counter(key(case["parameters"]) for case in grouped["writable"]) == Counter(expected), "Missing or duplicate writable configuration")
    expected = []
    for readonly, sets in ((0, 1), (0, 4), (0, 5), (0, 7), (0, 8), (1, 9)):
        expected.append(key(dict(ADDRESS_BITS=16, CACHE_SET_BITS=sets, READONLY=readonly, FAST_READ_HIT=1,
                                 FAST_WRITE_HIT=1-readonly, READ_OVERLAP=1, CHECK_SYNC_WRITE=1-readonly, CHECK_SYNC_READ=readonly, GEOMETRY_STREAM=1)))
    require(Counter(key(case["parameters"]) for case in grouped["geometry"]) == Counter(expected), "Missing or duplicate cache geometry")
    expected = []
    for geometry, readonly, fast, overlap in itertools.product(((10, 1), (16, 6)), (0, 1), (0, 1), (0, 1)):
        bits, sets = geometry
        parameters = key(dict(ADDRESS_BITS=bits, SET_BITS=sets, READ_ONLY=readonly, FAST_READ_HIT=fast, FAST_WRITE_HIT=fast, READ_OVERLAP=overlap))
        expected.extend((parameters, checksum) for checksum in (record["inputs"]["parent.sv"], record["inputs"]["candidate.sv"]))
    require(Counter((key(case["parameters"]), case["source_sha256"]) for case in grouped["bounds"]) == Counter(expected), "Missing or duplicate bounds source/configuration pair")
    directed = dict(ADDRESS_BITS=16, CACHE_SET_BITS=1, READONLY=0, FAST_READ_HIT=1, FAST_WRITE_HIT=1, READ_OVERLAP=1, CHECK_SYNC_WRITE=1, GEOMETRY_STREAM=0)
    require(len(grouped["store-overlap"]) == 1 and all(case["parameters"] == directed for case in grouped["store-overlap"] + grouped["mutation"]), "Missing directed store-overlap coverage")
    require(len(grouped["mutation"]) == 10 and len({case["source_sha256"] for case in grouped["mutation"]}) == 10, "Missing or duplicate mutation")
    for case in cases:
        require(case["compile_passed"] is True, "Uncompiled cache case")
        require((case["exit_code"] != 0) if case["label"] == "mutation" else (case["exit_code"] == 0), "Wrong runtime result")
    return grouped


def audit(output=OUTPUT):
    record = read_json(output / "manifest.json")
    grouped = validate_coverage(record)
    originals = {"candidate.sv": ROOT / "rv32_cache.sv", "parent.sv": BASE / "rtl/rv32_cache.sv", "rv32_burst_ram.sv": BASE / "rtl/rv32_burst_ram.sv"}
    originals.update({name: CPU / "sim" / name for name in ("cache_tb.sv", "cache_valid_banks_pairs_tb.sv", "cache_error_bounds_tb.sv")})
    require(set(originals) == set(record["inputs"]), "Wrong cache input inventory")
    for name, path in originals.items():
        require(digest(path) == digest(output / "source" / name) == record["inputs"][name], "Cache input changed: " + name)
    require(digest(ROOT / "test_cache_collision.py") == record["runner_sha256"], "Cache runner changed")
    require(digest(Path(legacy.__file__)) == record["helper_sha256"], "Cache test helper changed")
    parent = (output / "source/parent.sv").read_text()
    require(parent.count("module rv32_cache #(") == 1, "Ambiguous reference module")
    require((output / "source/reference.sv").read_text() == parent.replace("module rv32_cache #(", "module rv32_cache_reference #("), "Reference is not the current parent")
    require(digest(output / "source/reference.sv") == record["reference_sha256"], "Reference source changed")
    receipt = read_json(ROOT / "change-receipt.json")
    require(receipt["parent_cache_sha256"] == record["inputs"]["parent.sv"] and receipt["cache_sha256"] == record["inputs"]["candidate.sv"], "Wrong cache delta chain")
    for before, after in receipt["substitutions"]:
        require(parent.count(before) == 1, "Ambiguous cache substitution")
        parent = parent.replace(before, after)
    require(parent == (ROOT / "rv32_cache.sv").read_text(), "Unexpected cache delta")
    for name, field in (("rv32_core.sv", "core_sha256"), ("rv32_btb.sv", "btb_sha256")):
        require(digest(PARENT / name) == receipt[field], "Selected CPU/predictor changed")
    tree = ast.parse(textwrap.dedent(inspect.getsource(legacy.CacheCollisionForwardTests.test_compiled_collision_mutations)))
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "mutations" for target in node.targets)]
    require(len(assignments) == 1, "Ambiguous mutation inventory")
    mutations = ast.literal_eval(assignments[0].value)
    source = (ROOT / "rv32_cache.sv").read_text()
    expected_mutants = []
    for before, after in mutations:
        require(source.count(before) == 1, "Ambiguous runtime mutation")
        expected_mutants.append(hashlib.sha256(source.replace(before, after).encode()).hexdigest().upper())
    require(Counter(expected_mutants) == Counter(case["source_sha256"] for case in grouped["mutation"]), "Wrong compiled mutation set")
    for index, case in enumerate(record["cases"]):
        directory = output / (f"{index:03d}-" + case["label"])
        require(set(case["files"]) == {"candidate.sv", "bench.sv", "test.vvp", "compile.log", "execute.log"}, "Incomplete cache case artifacts")
        for name, checksum in case["files"].items():
            require(digest(directory / name) == checksum, "Cache case artifact changed")
        require(digest(directory / "candidate.sv") == case["source_sha256"], "Wrong executed cache source")
        text = (directory / "execute.log").read_text()
        if case["label"] == "mutation":
            require("FAIL cache" in text and "watchdog" not in text.lower(), "Mutation did not fail functionally")
        else:
            require("PASS cache" in text and "FAIL" not in text, "Missing raw cache pass")
            if case["label"] != "bounds":
                require(case["source_sha256"] == record["inputs"]["candidate.sv"], "Wrong positive cache source")
    result = {"schema": 1, "passed": True, "positive_cases": 71, "compiled_rejection_cases": 10,
              "writable_configurations": 32, "other_geometries": 6, "bounds_pairs": 16,
              "manifest_sha256": digest(output / "manifest.json"), "auditor_sha256": digest(Path(__file__)),
              "scope": "source-bound current-parent cache differential and runtime rejection evidence; not formal equivalence or hardware qualification"}
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
