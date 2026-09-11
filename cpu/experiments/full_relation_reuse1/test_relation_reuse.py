import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from uuid import uuid4

from test_source_delta import validate

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_id_relation_mask1"
BASE = ROOT.parent / "full_redirect_clock151200"
OUTPUT = ROOT / "build" / ("relation-tests-" + uuid4().hex[:8])
MODULES = ("rv32_core", "rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv",
           "rv32_cache", "rv32_uncached", "rv32_memory_system", "rv32_burst_ram", "rv32_burst_arbiter")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def source_path(name):
    return ROOT / (name + ".sv") if name in ("rv32_core", "rv32_btb") else BASE / "rtl" / (name + ".sv")


class RelationReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True, exist_ok=False)
        cls.case_number = 0

    def test_exact_sources_and_observers(self):
        validate((ROOT / "rv32_core.sv").read_text(), (ROOT / "rv32_btb.sv").read_text())
        observers = json.loads((ROOT / "observer-receipt.json").read_text())
        self.assertEqual(set(observers), {"core_tb.sv", "cached_core_tb.sv"})
        for filename, record in observers.items():
            original = ROOT.parent / record["parent"]
            self.assertEqual(digest(original), record["parent_sha256"])
            expected = original.read_text()
            for before, after in record["substitutions"]:
                self.assertEqual(expected.count(before), 1)
                expected = expected.replace(before, after)
            self.assertEqual((ROOT / "sim" / filename).read_text(), expected)
            self.assertEqual(digest(ROOT / "sim" / filename), record["observer_sha256"])

    def simulate(self, bubble, reference=False, mutation=None):
        RelationReuseTests.case_number += 1
        stage = OUTPUT / ("case-" + str(RelationReuseTests.case_number))
        stage.mkdir()
        inputs = []
        for name in MODULES:
            original = PARENT / "rv32_core.sv" if reference and name == "rv32_core" else source_path(name)
            content = original.read_text()
            if name == "rv32_core" and mutation:
                before, after = mutation
                self.assertEqual(content.count(before), 1)
                content = content.replace(before, after)
            destination = stage / (name + ".sv")
            destination.write_text(content)
            inputs.append(destination)
        bench = stage / "cached_core_tb.sv"
        bench.write_bytes((ROOT / "sim/cached_core_tb.sv").read_bytes())
        inputs.append(bench)
        image = stage / "test.vvp"
        parameters = {"PREDICTOR": 0, "BTB_INDEX_BITS": 8, "EARLY_D_REQUEST": 1, "ICACHE_SET_BITS": 9,
                      "CACHE_SETS": 6, "ENABLE_CACHE": 1, "LOAD_USE_BUBBLE": bubble, "FAST_ICACHE_HIT": 1,
                      "DATA_OVERLAP": 1, "FETCH_OVERLAP": 1, "FAST_DCACHE_READ": 1, "FAST_DCACHE_WRITE": 1}
        command = ["iverilog", "-g2012", "-s", "cached_core_tb", "-o", str(image)]
        command += ["-Pcached_core_tb." + name + "=" + str(value) for name, value in parameters.items()]
        command += list(map(str, inputs))
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (stage / "compile.log").write_text(compiled.stdout + compiled.stderr)
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        trace, memory = stage / "trace.txt", stage / "memory.txt"
        execute = ["vvp", str(image), "+firmware=" + str(BASE / "build/core_selftest.hex"), "+trace=" + str(trace),
                   "+memory_out=" + str(memory), "+seed=12345678"]
        result = subprocess.run(execute, capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        (stage / "execute.log").write_text(output)
        record = {"compile_command": command, "execute_command": execute, "parameters": parameters,
                  "compile_exit": compiled.returncode, "execute_exit": result.returncode, "reference": reference,
                  "mutation": mutation, "inputs": {path.name: digest(path) for path in inputs}, "executable_sha256": digest(image)}
        (stage / "invocation.json").write_text(json.dumps(record, indent=2) + "\n")
        if mutation:
            self.assertNotEqual(result.returncode, 0, output)
            self.assertRegex(output, "FAIL (raw_relation_payload live operand relation mismatch|reused relation differs from forwarded operands)")
        else:
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("PASS cached_core", output)
            self.assertIn("PASS relation reuse=", output)
        print("case " + str(RelationReuseTests.case_number) + ": " + output.strip(), flush=True)
        return stage

    def test_live_parent_and_candidate_match(self):
        for bubble in (0, 1):
            with self.subTest(bubble=bubble):
                reference = self.simulate(bubble, reference=True)
                candidate = self.simulate(bubble)
                for name in ("trace.txt", "memory.txt", "execute.log"):
                    self.assertEqual((candidate / name).read_bytes(), (reference / name).read_bytes(), name)

    def test_compiled_refresh_faults_rejected(self):
        original = "            raw_pair_relation<=LOAD_USE_BUBBLE!=0 ? early_result : operand_relation(forwarded_a,forwarded_b);"
        mutations = (
            (0, original, "            raw_pair_relation<=early_result;"),
            (1, original, "            raw_pair_relation<=LOAD_USE_BUBBLE!=0 ? (early_result ^ 3'b001) : operand_relation(forwarded_a,forwarded_b);"),
            (1, original, "            raw_pair_relation<=raw_pair_relation;"),
            (1, "                raw_pair_relation<=masked_operand_relation(mul_id_operand_a,mul_id_operand_b,id_relation_a_valid,id_relation_b_valid);",
                "                raw_pair_relation<=raw_pair_relation;"),
        )
        for bubble, before, after in mutations:
            with self.subTest(bubble=bubble, mutation=after):
                self.simulate(bubble, mutation=(before, after))


if __name__ == "__main__":
    inputs = [source_path(name) for name in MODULES]
    inputs += [PARENT / "rv32_core.sv", ROOT / "observer-receipt.json", ROOT / "change-receipt.json", Path(__file__),
               ROOT / "test_source_delta.py", ROOT / "sim/core_tb.sv", ROOT / "sim/cached_core_tb.sv",
               BASE / "build/core_selftest.hex"]
    before = {str(path): digest(path) for path in inputs}
    tests = unittest.main(verbosity=2, exit=False)
    after = {str(path): digest(path) for path in inputs}
    report = {"schema": 1, "scope": "live parent/candidate forwarding relations and compiled mutation checks; not timing or performance qualification",
              "passed": tests.result.wasSuccessful() and before == after, "tests_run": tests.result.testsRun,
              "inputs": before, "inputs_unchanged": before == after,
              "outputs": {path.relative_to(OUTPUT).as_posix(): digest(path) for path in OUTPUT.rglob("*") if path.is_file()}}
    (OUTPUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Relation evidence: " + str(OUTPUT), flush=True)
    raise SystemExit(0 if report["passed"] else 1)
