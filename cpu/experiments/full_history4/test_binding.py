import json
import unittest

from audit_binding import ROOT, SOURCE, hardware_parameters, validate_wrapper


class PhysicalBindingTests(unittest.TestCase):
    def setUp(self):
        self.text = (SOURCE / "pds_soc_top.v").read_text(encoding="utf-8-sig")
        self.configuration = json.loads((ROOT / "configuration.json").read_text(encoding="utf-8-sig"))
        self.parameters = hardware_parameters(self.configuration)

    def evaluate(self, text):
        return validate_wrapper(text, self.parameters, 154285714, SOURCE / "firmware.hex")

    def test_actual_wrapper(self):
        self.assertEqual(self.evaluate(self.text)["ENABLE_M"], 1)

    def test_disabled_features_rejected(self):
        for name in ("ENABLE_M", "ENABLE_PREDICTOR", "ENABLE_CACHE", "FAST_DCACHE_READ", "DATA_OVERLAP"):
            with self.subTest(parameter=name):
                changed = self.text.replace("." + name + "(1)", "." + name + "(0)")
                with self.assertRaisesRegex(ValueError, "Wrong physical parameter"):
                    self.evaluate(changed)

    def test_pll_clock_rejected(self):
        changed = self.text.replace("rv32_pll #(.CLOCK_HZ(154285714))", "rv32_pll #(.CLOCK_HZ(157500000))")
        with self.assertRaisesRegex(ValueError, "Wrong PLL"):
            self.evaluate(changed)

    def test_uart_baud_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wrong physical parameter"):
            self.evaluate(self.text.replace(".UART_BAUD(115200)", ".UART_BAUD(9600)"))

    def test_duplicate_and_unknown_parameters_rejected(self):
        for addition in (".ENABLE_M(1),", ".UNKNOWN(1),"):
            with self.subTest(addition=addition):
                with self.assertRaises(ValueError):
                    self.evaluate(self.text.replace("rv32_board_top #(", "rv32_board_top #(" + addition))

    def test_firmware_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wrong physical firmware path"):
            self.evaluate(self.text.replace("firmware.hex", "different.hex"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

