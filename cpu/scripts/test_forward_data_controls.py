import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class ForwardDataControls(unittest.TestCase):
    def project_path(self):
        return PROJECT

    def candidate_path(self):
        return PROJECT / "rtl/rv32_core.sv"

    def simulate(self, variant="positive", bubble=0, predictor=1):
        project = self.project_path()
        source = self.candidate_path().read_text(encoding="utf-8")
        mutations = {
            "response_gated_mux": (
                "(!mem_load || LOAD_USE_BUBBLE==0)",
                "(!mem_load || (LOAD_USE_BUBBLE==0 && mem_fire && !d_rsp_error))"),
            "execute_before_response": (
                "wire ex_can_fire=ex_valid && mem_ready",
                "wire ex_can_fire=ex_valid && (mem_ready || (mem_valid && mem_load))"),
            "execute_on_fault": (
                "ex_valid && mem_ready && !mem_flush && !load_use_wait",
                "ex_valid && mem_ready && (!mem_flush || (mem_valid && mem_load && mem_fire && d_rsp_error)) && !load_use_wait"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        firmware = project / "build/core_selftest.hex"
        self.assertTrue(firmware.is_file(), "Run build_selftest.ps1 before this test")
        with tempfile.TemporaryDirectory(prefix="forward-data-") as directory:
            work = Path(directory)
            core = work / "rv32_core.sv"
            core.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            trace = work / "test.trace"
            memory = work / "test.memory"
            command = ["iverilog", "-g2012", "-s", "core_tb", "-o", str(output),
                       "-Pcore_tb.POISON_INVALID_DATA=1", "-Pcore_tb.EARLY_D_REQUEST=1",
                       "-Pcore_tb.BTB_INDEX_BITS=8", f"-Pcore_tb.LOAD_USE_BUBBLE={bubble}",
                       f"-Pcore_tb.PREDICTOR={predictor}", str(core)]
            command += [str(project / "rtl" / (name + ".sv")) for name in
                        ("rv32_decode", "rv32_alu", "rv32_machine", "rv32_btb", "rv32_muldiv")]
            command.append(str(project / "sim/core_tb.sv"))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(output), f"+firmware={firmware}",
                                     f"+trace={trace}", f"+memory_out={memory}", "+seed=deadbeef"],
                                    capture_output=True, text=True, timeout=30)
            if variant == "positive" and result.returncode == 0:
                reference = subprocess.run(["python3", str(project / "scripts/check_trace.py"),
                                            str(project / "build/core_selftest.bin"), str(trace),
                                            "--memory", str(memory)], capture_output=True, text=True, timeout=30)
                self.assertEqual(reference.returncode, 0, reference.stdout + reference.stderr)
                self.assertIn("PASS reference", reference.stdout)
            return result

    def test_poisoned_responses_with_both_predictor_and_bubble_modes(self):
        for bubble in (0, 1):
            for predictor in (0, 1):
                with self.subTest(bubble=bubble, predictor=predictor):
                    result = self.simulate(bubble=bubble, predictor=predictor)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("PASS core checks=", result.stdout)
                    if bubble == 0:
                        self.assertIn("POISONED_LOAD_WAITS=", result.stdout)

    def test_negative_controls(self):
        expected = {
            "response_gated_mux": "selection independent of response qualification",
            "execute_before_response": "invalid load response cannot execute or issue a younger request",
            "execute_on_fault": "faulted load cannot execute a younger instruction",
        }
        for variant, message in expected.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
