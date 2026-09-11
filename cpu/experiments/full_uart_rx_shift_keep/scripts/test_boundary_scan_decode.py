import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from boundary_scan_decode import DEVICE, PACKING, decode_snapshot, reject_duplicate_keys


def snapshot():
    return {"device": DEVICE, "packing": PACKING, "origin": "synthetic", "rawFrame": [0] * 150}


class BoundaryDecodeTests(unittest.TestCase):
    def test_zero_and_one(self):
        for value in (0, 255):
            data = snapshot()
            data["rawFrame"] = [value] * 150
            result = decode_snapshot(data)
            self.assertEqual({entry["level"] for entry in result["signals"].values()}, {int(value != 0)})
            self.assertEqual(result["status"], "offline_decoded_not_board_acceptance")
            for key in ("scan_instruction_verified", "capture_device_verified", "configuration_voltage_verified", "mechanical_key_actuation_verified"):
                self.assertFalse(result[key])

    def test_independent_pin_positions(self):
        for name, byte_index, mask in (("SCBV", 134, 2), ("KEY1", 29, 128), ("UART_RX", 133, 128), ("UART_TX", 133, 32)):
            data = snapshot()
            data["rawFrame"][byte_index] = mask
            result = decode_snapshot(data)
            self.assertEqual([signal for signal, entry in result["signals"].items() if entry["level"]], [name])

    def test_neighbor_bits_not_selected(self):
        data = snapshot()
        data["rawFrame"][134] = 5
        self.assertEqual(decode_snapshot(data)["signals"]["SCBV"]["level"], 0)

    def test_tail_is_not_used_but_is_hashed(self):
        data = snapshot()
        first = decode_snapshot(data)
        data["rawFrame"][134] = 1
        data["rawFrame"][135:] = [255] * 15
        second = decode_snapshot(data)
        self.assertEqual(first["signals"], second["signals"])
        self.assertNotEqual(first["raw_sha256"], second["raw_sha256"])

    def test_bad_lengths(self):
        for length in (0, 100, 134, 135, 149, 151):
            data = snapshot()
            data["rawFrame"] = [0] * length
            with self.assertRaises(ValueError):
                decode_snapshot(data)

    def test_bad_bytes(self):
        for value in (-1, 256, True, False, 1.0, "1", None, [], {}):
            data = snapshot()
            data["rawFrame"][0] = value
            with self.assertRaises(ValueError):
                decode_snapshot(data)

    def test_explicit_profile_and_origin(self):
        for key, value in (("device", "PG2L100H"), ("packing", "tdo-lsb-first"), ("origin", "hardware_verified")):
            data = snapshot()
            data[key] = value
            with self.assertRaises(ValueError):
                decode_snapshot(data)
        data = snapshot()
        data["origin"] = "unverified_capture"
        self.assertFalse(decode_snapshot(data)["capture_device_verified"])

    def test_shape_and_no_mutation(self):
        data = snapshot()
        before = copy.deepcopy(data)
        decode_snapshot(data)
        self.assertEqual(before, data)
        for invalid in (None, [], {}, {**data, "extra": 1}, {**data, "rawFrame": "00"}):
            with self.assertRaises(ValueError):
                decode_snapshot(invalid)

    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            json.loads("{\"device\": 1, \"device\": 2}", object_pairs_hook=reject_duplicate_keys)

    def test_cli(self):
        script = Path(__file__).with_name("boundary_scan_decode.py")
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "snapshot.json"
            input_path.write_text(json.dumps(snapshot()), encoding="utf-8-sig")
            result = subprocess.run([sys.executable, str(script), str(input_path)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["origin"], "synthetic")
            input_path.write_text("x" * 16385, encoding="utf-8")
            result = subprocess.run([sys.executable, str(script), str(input_path)], capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("16 KiB", result.stderr)


if __name__ == "__main__":
    unittest.main()
