from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class DividerZeroPayloadTests(unittest.TestCase):
    def simulate(self, variant="positive", monitor=1):
        source = (PROJECT / "rtl/rv32_muldiv.sv").read_text(encoding="utf-8")
        payload = "response_data<=req_operation[1] ? req_operand_a : 32'hffffffff;"
        mutations = {
            "qualified": (payload, "if(req_valid) " + payload),
            "wrong_remainder": (payload, "response_data<=32'hffffffff;"),
            "overwrite_held": ("            case(state)", "            " + payload + "\n            case(state)"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="divider-zero-payload-") as directory:
            work = Path(directory)
            rtl = work / "rv32_muldiv.sv"
            rtl.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "muldiv_tb",
                       f"-Pmuldiv_tb.CHECK_IDLE_RESPONSE={monitor}", "-o", str(image),
                       str(rtl), str(PROJECT / "sim/muldiv_tb.sv")]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=30)

    def test_all_operations_latency_cancel_backpressure_and_capture(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IDLE_RESPONSE samples=", result.stdout)
        self.assertIn("PASS muldiv checks=12544", result.stdout)

    def test_qualification_data_and_hold_failures(self):
        for variant, monitor, expected in (
            ("qualified", 1, "Idle exceptional response payload must not depend on request qualification"),
            ("wrong_remainder", 0, "Muldiv op="),
            ("overwrite_held", 0, "Muldiv"),
        ):
            with self.subTest(variant=variant):
                result = self.simulate(variant, monitor)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout + result.stderr)
                self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
