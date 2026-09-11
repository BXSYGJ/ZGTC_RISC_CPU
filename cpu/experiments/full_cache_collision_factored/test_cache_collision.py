import argparse
import hashlib
import re
import itertools
import json
import subprocess
import sys
import unittest
from pathlib import Path

from candidate_sources import ROOT, BASE, PARENT, source_path

CPU = ROOT.parents[1]
sys.path.insert(0, str(CPU / "scripts"))
import test_cache_collision_forward as legacy

OUTPUT = ROOT / "build/cache-checks-complete"
RECORD = {"schema": 1, "passed": False, "scope": "current-source cycle-accurate cache differential tests and compiled rejection controls; not timing or hardware qualification", "cases": []}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def save_record():
    (OUTPUT / "manifest.json").write_text(json.dumps(RECORD, indent=2) + "\n", encoding="utf-8")


class CurrentCollisionTests(unittest.TestCase):
    def test_exact_current_source_delta(self):
        receipt = json.loads((ROOT / "change-receipt.json").read_text())
        self.assertEqual(digest(BASE / "rtl/rv32_cache.sv"), receipt["parent_cache_sha256"])
        self.assertEqual(digest(ROOT / "rv32_cache.sv"), receipt["cache_sha256"])
        self.assertEqual(digest(PARENT / "rv32_core.sv"), receipt["core_sha256"])
        self.assertEqual(digest(PARENT / "rv32_btb.sv"), receipt["btb_sha256"])
        expected = (BASE / "rtl/rv32_cache.sv").read_text()
        for before, after in receipt["substitutions"]:
            self.assertEqual(expected.count(before), 1)
            expected = expected.replace(before, after)
        self.assertEqual(expected, (ROOT / "rv32_cache.sv").read_text())
        historical = (CPU / "experiments/cache_collision_forward/rv32_cache.sv").read_text()
        for _, replacement in receipt["substitutions"]:
            self.assertIn(replacement, historical)

    def run_case(self, source, top, parameters, label, observe=True):
        directory = OUTPUT / (f"{len(RECORD['cases']):03d}-" + label)
        directory.mkdir()
        candidate = directory / "candidate.sv"
        candidate.write_text(source, encoding="utf-8")
        files = [candidate, OUTPUT / "source/reference.sv"]
        bench = (OUTPUT / "source" / (top + ".sv")).read_text()
        if top == "cache_valid_banks_pairs_tb":
            if observe:
                bench = legacy.CacheCollisionForwardTests.transform_miter(self, bench, False)
            files.append(OUTPUT / "source/cache_tb.sv")
        else:
            files.append(OUTPUT / "source/rv32_burst_ram.sv")
        active_bench = directory / "bench.sv"
        active_bench.write_text(bench, encoding="utf-8")
        files.append(active_bench)
        image = directory / "test.vvp"
        command = ["iverilog", "-g2012", "-s", top, "-o", str(image)]
        command += [f"-P{top}.{name}={value}" for name, value in parameters.items()]
        command += list(map(str, files))
        entry = {"label": label, "parameters": parameters, "source_sha256": digest(candidate), "compile_command": command, "compile_passed": False}
        RECORD["cases"].append(entry)
        save_record()
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=180)
        (directory / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        entry["compile_passed"] = True
        result = subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=120)
        (directory / "execute.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        entry.update(exit_code=result.returncode, files={path.name: digest(path) for path in directory.iterdir() if path.is_file()})
        save_record()
        return result

    def require_pass(self, result, marker):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(marker, result.stdout)

    def simulate(self, mutation=None):
        source = (OUTPUT / "source/candidate.sv").read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        parameters = dict(ADDRESS_BITS=16, CACHE_SET_BITS=1, READONLY=0, FAST_READ_HIT=1,
                          FAST_WRITE_HIT=1, READ_OVERLAP=1, CHECK_SYNC_WRITE=1, GEOMETRY_STREAM=0)
        return self.run_case(source, "cache_valid_banks_pairs_tb", parameters, "mutation" if mutation else "store-overlap")

    test_compiled_collision_mutations = legacy.CacheCollisionForwardTests.test_compiled_collision_mutations

    def test_small_geometry_store_overlap(self):
        self.require_pass(self.simulate(), "SYNC_WRITE forward0=")

    def test_writable_mode_geometry_matrix(self):
        source = (OUTPUT / "source/candidate.sv").read_text()
        for bits, sets, fast_read, fast_write, overlap in itertools.product((16, 32), (6, 9), (0, 1), (0, 1), (0, 1)):
            parameters = dict(ADDRESS_BITS=bits, CACHE_SET_BITS=sets, READONLY=0, FAST_READ_HIT=fast_read,
                              FAST_WRITE_HIT=fast_write, READ_OVERLAP=overlap, CHECK_SYNC_WRITE=1, GEOMETRY_STREAM=1)
            with self.subTest(parameters=parameters):
                result = self.run_case(source, "cache_valid_banks_pairs_tb", parameters, "writable")
                self.require_pass(result, "SYNC_WRITE forward0=")
        print("PASS 32 current-cache writable differential configurations", flush=True)

    def test_small_banked_and_readonly_geometries(self):
        source = (OUTPUT / "source/candidate.sv").read_text()
        for readonly, sets in ((0, 1), (0, 4), (0, 5), (0, 7), (0, 8), (1, 9)):
            parameters = dict(ADDRESS_BITS=16, CACHE_SET_BITS=sets, READONLY=readonly, FAST_READ_HIT=1,
                              FAST_WRITE_HIT=1-readonly, READ_OVERLAP=1, CHECK_SYNC_WRITE=1-readonly, CHECK_SYNC_READ=readonly, GEOMETRY_STREAM=1)
            with self.subTest(parameters=parameters):
                result = self.run_case(source, "cache_valid_banks_pairs_tb", parameters, "geometry")
                self.require_pass(result, "READY_PAYLOAD")
        print("PASS six small/banked/readonly geometries", flush=True)

    def test_bounds_error_pairs(self):
        for geometry, readonly, fast, overlap in itertools.product(((10, 1), (16, 6)), (0, 1), (0, 1), (0, 1)):
            bits, sets = geometry
            parameters = dict(ADDRESS_BITS=bits, SET_BITS=sets, READ_ONLY=readonly,
                              FAST_READ_HIT=fast, FAST_WRITE_HIT=fast, READ_OVERLAP=overlap)
            with self.subTest(parameters=parameters):
                outputs = []
                for filename in ("parent.sv", "candidate.sv"):
                    source = (OUTPUT / "source" / filename).read_text()
                    result = self.run_case(source, "cache_error_bounds_tb", parameters, "bounds")
                    self.require_pass(result, "PASS cache_error_bounds checks=")
                    outputs.append(result.stdout)
                self.assertEqual(outputs[0], outputs[1])
        print("PASS 16 current-cache bounds/error pairs", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", default="complete")
    arguments, tests = parser.parse_known_args()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", arguments.attempt) is None:
        raise ValueError("Invalid cache test attempt")
    OUTPUT = ROOT / "build" / ("cache-checks-" + arguments.attempt)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    (OUTPUT / "source").mkdir()
    originals = {"candidate.sv": ROOT / "rv32_cache.sv", "parent.sv": BASE / "rtl/rv32_cache.sv",
                 "rv32_burst_ram.sv": BASE / "rtl/rv32_burst_ram.sv"}
    for name in ("cache_tb.sv", "cache_valid_banks_pairs_tb.sv", "cache_error_bounds_tb.sv"):
        originals[name] = CPU / "sim" / name
    for name, path in originals.items():
        (OUTPUT / "source" / name).write_bytes(path.read_bytes())
    parent = (OUTPUT / "source/parent.sv").read_text()
    if parent.count("module rv32_cache #(") != 1:
        raise ValueError("Ambiguous current parent module")
    (OUTPUT / "source/reference.sv").write_text(parent.replace("module rv32_cache #(", "module rv32_cache_reference #("), encoding="utf-8")
    RECORD["inputs"] = {name: digest(path) for name, path in originals.items()}
    RECORD["runner_sha256"] = digest(Path(__file__))
    RECORD["helper_sha256"] = digest(Path(legacy.__file__))
    RECORD["reference_sha256"] = digest(OUTPUT / "source/reference.sv")
    save_record()
    result = unittest.main(argv=[sys.argv[0], *tests], verbosity=2, exit=False).result
    unchanged = all(digest(path) == RECORD["inputs"][name] == digest(OUTPUT / "source" / name) for name, path in originals.items())
    RECORD.update(passed=result.wasSuccessful() and unchanged, tests_run=result.testsRun, unchanged_inputs=unchanged)
    save_record()
    raise SystemExit(0 if RECORD["passed"] else 1)
