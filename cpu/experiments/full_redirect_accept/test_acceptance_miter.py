from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_redirect_prime"


def run(command, timeout=90):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr


class AcceptanceMiterTests(unittest.TestCase):
    def test_cycle_equivalence(self):
        reference_source = (PARENT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        metadata = json.loads((ROOT / "source-inputs.json").read_text(encoding="utf-8"))
        actual_hash = hashlib.sha256(reference_source.encode()).hexdigest().upper()
        self.assertEqual(actual_hash, metadata["parent_hashes"]["rtl/rv32_core.sv"])
        reference_source = reference_source.replace("module rv32_core #(", "module rv32_core_reference #(")
        bench = (ROOT / "sim/core_tb.sv").read_text(encoding="utf-8")
        bench = bench.replace("module core_tb;", "module core_tb;\n    parameter integer FETCH_OVERLAP=0;")
        instance = re.findall(r"    rv32_core #\((.*?)\) core\(\.\*\);", bench)
        self.assertEqual(len(instance), 1)
        parameters = ".FETCH_OVERLAP(FETCH_OVERLAP)," + instance[0]
        ports = re.findall(r"^    (input|output) wire (\[[^]]+\] )?(\w+)[,\n]", reference_source.split(");", 1)[0], re.M)
        self.assertEqual(len(ports), 38)
        outputs = [(width, name) for direction, width, name in ports if direction == "output"]
        connections = [f".{name}({'reference_' if direction == 'output' else ''}{name})" for direction, width, name in ports]
        declarations = [f"    wire {width}reference_{name};" for width, name in outputs]
        declarations += [f"    rv32_core #({parameters}) core(.*);",
                         f"    rv32_core_reference #({parameters}) reference_core(" + ",".join(connections) + ");"]
        bench = bench.replace("    rv32_core #(" + instance[0] + ") core(.*);", "\n".join(declarations))
        observed = ",".join(name for width, name in outputs)
        expected = ",".join("reference_" + name for width, name in outputs)
        assertions = ("            if(core.fetch_redirect_pending) check(core.fetch_active && !core.fetch_sent && !core.fetch_discard,\"pending fetch invariant\");\n"
                      "            check(core.redirect_prediction_commit === (core.fetch_redirect_pending && i_req_valid && i_req_ready && !core.frontend_flush && !core.frontend_barrier),\"original commit predicate\");\n"
                      + "            check({" + observed + "} === {" + expected + "},\"all reference outputs cycle equivalent\");\n")
        bench = bench.replace("            cycles=cycles+1;", assertions + "            cycles=cycles+1;")
        with tempfile.TemporaryDirectory(prefix="redirect-accept-miter-") as directory:
            work = Path(directory)
            reference = work / "reference.sv"
            reference.write_text(reference_source, encoding="utf-8")
            testbench = work / "miter.sv"
            testbench.write_text(bench, encoding="utf-8")
            dependencies = [ROOT / "rtl" / name for name in
                            ("rv32_core.sv", "rv32_machine.sv", "rv32_decode.sv", "rv32_alu.sv", "rv32_btb.sv", "rv32_muldiv.sv")]
            for predictor in (0, 1):
                for overlap in (0, 1):
                    for bubble in (0, 1):
                        image = work / "test.vvp"
                        run(["iverilog", "-g2012", "-s", "core_tb", f"-Pcore_tb.PREDICTOR={predictor}",
                             f"-Pcore_tb.FETCH_OVERLAP={overlap}", f"-Pcore_tb.LOAD_USE_BUBBLE={bubble}",
                             "-Pcore_tb.EARLY_D_REQUEST=1", "-Pcore_tb.BTB_INDEX_BITS=8", "-o", image,
                             *dependencies, reference, testbench])
                        for seed in ("12345678", "a5a5c3c3", "deadbeef"):
                            with self.subTest(predictor=predictor, overlap=overlap, bubble=bubble, seed=seed):
                                trace = work / "run.trace"
                                memory = work / "run.memory"
                                output = run(["vvp", image, "+firmware=" + str(PARENT / "build/core_selftest.hex"),
                                              "+trace=" + str(trace), "+memory_out=" + str(memory), "+seed=" + seed])
                                self.assertIn("PASS core checks=", output)
                                checked = run(["python3", ROOT / "scripts/check_trace.py", PARENT / "build/core_selftest.bin",
                                               trace, "--memory", memory])
                                self.assertIn("PASS reference", checked)
                                print(f"PASS miter predictor={predictor} overlap={overlap} bubble={bubble} seed={seed}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

