import json
import subprocess
import unittest
from pathlib import Path
from uuid import uuid4

from prepare_fetch import ROOT, PARENT, digest, require, validate_delta

OUTPUT = ROOT / "build" / ("fetch-tests-" + uuid4().hex[:8])
RUNS = []


class FetchCommitTests(unittest.TestCase):
    def simulate(self, bench, overlap, predictor=1, mutation=None):
        stage = OUTPUT / ("case-" + str(len(RUNS) + 1))
        stage.mkdir(parents=True, exist_ok=False)
        source = (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        (stage / "candidate.sv").write_text(source, encoding="utf-8")
        original = (PARENT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        self.assertEqual(original.count("module rv32_core #("), 1)
        (stage / "reference.sv").write_text(original.replace("module rv32_core #(", "module rv32_core_reference #("), encoding="utf-8")
        image = stage / "test.vvp"
        command = ["iverilog", "-g2012", "-s", bench, f"-P{bench}.FETCH_OVERLAP={overlap}"]
        if bench != "fetch_enable_tb":
            command.append(f"-P{bench}.PREDICTOR={predictor}")
        command += ["-o", str(image), str(stage / "candidate.sv"), str(stage / "reference.sv")]
        command += [str(ROOT / "rtl" / (name + ".sv")) for name in
                    ("rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv")]
        command.append(str(ROOT / (bench + ".sv")))
        record = {"bench": bench, "overlap": overlap, "predictor": predictor, "mutation": mutation,
                  "compile_command": command, "execute_command": ["vvp", str(image)], "passed": False}
        RUNS.append(record)
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (stage / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
        record["compile_exit"] = compiled.returncode
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        self.assertNotIn("not found", compiled.stderr)
        executed = subprocess.run(record["execute_command"], capture_output=True, text=True, timeout=90)
        output = executed.stdout + executed.stderr
        (stage / "execute.log").write_text(output, encoding="utf-8")
        record["execute_exit"] = executed.returncode
        marker = bench.removesuffix("_tb")
        if mutation:
            self.assertNotEqual(executed.returncode, 0, output)
            self.assertIn("FAIL " + marker, output)
        else:
            self.assertEqual(executed.returncode, 0, output)
            self.assertIn("PASS " + marker, output)
        record["passed"] = True
        record["outputs"] = {path.name: digest(path) for path in stage.iterdir() if path.is_file()}
        (stage / "invocation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(output.strip(), flush=True)

    def test_exact_source_delta(self):
        validate_delta()

    def test_exhaustive_boolean_equivalence(self):
        for overlap in (0, 1):
            with self.subTest(overlap=overlap):
                self.simulate("fetch_enable_tb", overlap)

    def test_randomized_exact_state_equivalence(self):
        for overlap in (0, 1):
            for predictor in (0, 1):
                with self.subTest(overlap=overlap, predictor=predictor):
                    self.simulate("fetch_commit_tb", overlap, predictor)

    def test_directed_redirect_cases(self):
        for overlap in (0, 1):
            for predictor in (0, 1):
                with self.subTest(overlap=overlap, predictor=predictor):
                    self.simulate("redirect_prime_tb", overlap, predictor)

    def test_capture_faults_rejected(self):
        mutations = (
            ("fetch_redirect_pending && fetch_active && !fetch_sent && i_req_ready", "1'b0"),
            ("(!frontend_barrier && fetch_redirect_pending", "(fetch_redirect_pending"),
            ("if(fetch_prediction_update && !frontend_flush)", "if(fetch_prediction_update)"),
            ("(i_rsp_valid && fetch_sent && fetch_accept_space));", "1'b0);"),
            ("next_pc_write=frontend_flush || fetch_prediction_update", "next_pc_write=fetch_prediction_update"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                self.simulate("fetch_commit_tb", 1, 1, mutation)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / name for name in ("test_fetch_commit.py", "fetch_commit_tb.sv", "fetch_enable_tb.sv", "redirect_prime_tb.sv", "change-receipt.json")]
    paths += [ROOT / "rtl" / (name + ".sv") for name in ("rv32_core", "rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv")]
    paths.append(PARENT / "rtl/rv32_core.sv")
    sources = {str(path): digest(path) for path in paths}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FetchCommitTests))
    unchanged = sources == {str(path): digest(path) for path in paths}
    passed = result.wasSuccessful() and unchanged and len(RUNS) == 15 and all(run["passed"] for run in RUNS)
    record = {"schema": 1, "scope": "exhaustive Boolean enables and bounded exact fetch-state equivalence; not full ISA or physical validation",
              "passed": passed, "tests_run": result.testsRun, "sources_unchanged": unchanged, "sources": sources, "runs": RUNS,
              "outputs": {str(path.relative_to(OUTPUT)): digest(path) for path in OUTPUT.rglob("*") if path.is_file()}}
    (OUTPUT / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Fetch functional evidence: " + str(OUTPUT), flush=True)
    raise SystemExit(0 if passed else 1)
