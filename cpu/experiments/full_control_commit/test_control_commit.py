import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORTS = ("invalidate", "update_valid", "write_valid", "return_from_trap")


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def predicates(source):
    result = {}
    for name in PORTS:
        matches = re.findall(r"\." + name + r"\(([^()]*)\)", source)
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous port: " + name)
        result[name] = matches[0]
    return result


def make_bench(before, after):
    declarations = []
    for name in ("mem_access", "mem_fire", "mem_fault"):
        match = re.search(r"wire " + name + r"=([^;]+);", before)
        if match is None:
            raise ValueError("Missing control definition: " + name)
        declarations.append(match.group(0))
    references, candidates = predicates(before), predicates(after)
    comparisons = []
    for name in PORTS:
        declarations.append("wire reference_" + name + "=" + references[name] + ";")
        declarations.append("wire candidate_" + name + "=" + candidates[name] + ";")
        comparisons.append('if(reference_' + name + ' !== candidate_' + name + ') $fatal(1,"predicate mismatch ' + name + ' kind=%0d controls=%0d bus=%0d",kind,controls,bus_values);')
    return "\n".join([
        "module control_commit_tb;",
        "reg mem_valid,mem_exception,mem_sent,d_rsp_valid,d_rsp_error,maintenance_ready,mem_csr_write;",
        "reg mem_branch,mem_csr,mem_mret,mem_fence_i,mem_load,mem_store;",
        "integer kind,controls,bus_values,checks=0;",
        *declarations,
        "function automatic four_state(input integer value);",
        "case(value) 0:four_state=0; 1:four_state=1; 2:four_state=1'bx; 3:four_state=1'bz; endcase",
        "endfunction",
        "initial begin",
        "for(kind=0;kind<7;kind=kind+1) begin",
        "mem_branch=kind==1; mem_csr=kind==2; mem_mret=kind==3; mem_fence_i=kind==4; mem_load=kind==5; mem_store=kind==6;",
        "for(controls=0;controls<8;controls=controls+1) begin",
        "mem_valid=controls[0]; mem_exception=controls[1]; mem_csr_write=controls[2];",
        "for(bus_values=0;bus_values<256;bus_values=bus_values+1) begin",
        "mem_sent=four_state(bus_values&3); d_rsp_valid=four_state((bus_values>>2)&3);",
        "d_rsp_error=four_state((bus_values>>4)&3); maintenance_ready=four_state((bus_values>>6)&3); #1;",
        *comparisons,
        "checks=checks+4;",
        "end end end",
        '$display("PASS control predicates checks=%0d",checks); $finish;',
        "end endmodule",
    ])


def run_iverilog(directory, name, sources):
    executable = directory / (name + ".vvp")
    compiled = subprocess.run([shutil.which("iverilog"), "-g2012", "-s", name, "-o", str(executable), *map(str, sources)], capture_output=True, text=True)
    if compiled.returncode:
        raise AssertionError(compiled.stdout + compiled.stderr)
    return subprocess.run([shutil.which("vvp"), str(executable)], capture_output=True, text=True)


class ControlCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("iverilog") or not shutil.which("vvp"):
            raise RuntimeError("Native Icarus and vvp required")
        cls.before = (ROOT.parent / "full_mul_precompute_clock154285/rtl/rv32_core.sv").read_text(encoding="utf-8")
        cls.after = (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8")

    def test_exact_physical_delta(self):
        receipt = json.loads((ROOT / "source-inputs.json").read_text(encoding="utf-8"))
        expected = self.before
        for before, after in receipt["substitutions"]:
            self.assertEqual(expected.count(before), 1)
            expected = expected.replace(before, after)
        self.assertEqual(expected, self.after)
        self.assertEqual(receipt["changed_physical_inputs"], ["rtl/rv32_core.sv"])
        for relative, expected_hash in receipt["source_hashes"].items():
            self.assertEqual(digest(ROOT / relative), expected_hash, relative)
            self.assertEqual(digest(ROOT.parent / "full_mul_precompute_clock154285" / relative), receipt["parent_hashes"][relative], relative)
            if relative != "rtl/rv32_core.sv":
                self.assertEqual(expected_hash, receipt["parent_hashes"][relative], relative)

    def evaluate_predicates(self, source):
        with tempfile.TemporaryDirectory(prefix="control-predicates-") as temporary:
            directory = Path(temporary)
            bench = directory / "control_commit_tb.sv"
            bench.write_text(make_bench(self.before, source), encoding="utf-8")
            return run_iverilog(directory, "control_commit_tb", [bench])

    def test_four_state_bus_equivalence(self):
        result = self.evaluate_predicates(self.after)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS control predicates checks=57344", result.stdout)
        print(result.stdout.strip())

    def test_actual_predicate_mutants_rejected(self):
        mutations = (
            ("mem_valid && mem_branch && !mem_exception", "mem_valid && mem_branch"),
            ("mem_valid && mem_branch && !mem_exception", "mem_branch && !mem_exception"),
            ("mem_valid && mem_fence_i && !mem_exception && maintenance_ready", "mem_valid && mem_fence_i && !mem_exception"),
            ("mem_valid && mem_csr && mem_csr_write && !mem_exception", "mem_valid && mem_csr && !mem_exception"),
            ("mem_valid && mem_mret && !mem_exception", "mem_valid && mem_mret"),
        )
        for before, after in mutations:
            with self.subTest(mutation=after):
                self.assertEqual(self.after.count(before), 1)
                result = self.evaluate_predicates(self.after.replace(before, after))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("predicate mismatch", result.stdout)

    def test_actual_decoder_control_exclusivity(self):
        with tempfile.TemporaryDirectory(prefix="control-decoder-") as temporary:
            directory = Path(temporary)
            result = run_iverilog(directory, "control_decode_tb", [ROOT / "rtl/rv32_decode.sv", ROOT / "control_decode_tb.sv"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS decoder classes", result.stdout)
            print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
