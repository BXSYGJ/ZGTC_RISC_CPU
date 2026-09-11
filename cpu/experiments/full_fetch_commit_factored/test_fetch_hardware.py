import unittest
from audit_fetch_hardware import HARDWARE, load, validate_packets


class HardwarePacketTests(unittest.TestCase):
    def setUp(self):
        self.session = load(HARDWARE / "performance-r1-session.json")
        self.uart = (HARDWARE / "performance-r1.uart").read_text(encoding="utf-8")

    def test_actual_packets(self):
        validate_packets(self.session, self.uart)

    def test_byte_corruption_rejected(self):
        self.session["reads"][0]["body"]["hex"] = "00"
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            validate_packets(self.session, self.uart)

    def test_wrong_device_rejected(self):
        self.session["download"][0]["body"]["data"]["deviceId"] = 999
        with self.assertRaisesRegex(ValueError, "Wrong device"):
            validate_packets(self.session, self.uart)

    def test_failed_burn_rejected(self):
        self.session["download"][0]["body"]["data"]["tcpResult"]["burnResult"]["success"] = False
        with self.assertRaisesRegex(ValueError, "failed burn"):
            validate_packets(self.session, self.uart)

    def test_output_not_matching_packets_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs from packets"):
            validate_packets(self.session, self.uart + "fabricated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
