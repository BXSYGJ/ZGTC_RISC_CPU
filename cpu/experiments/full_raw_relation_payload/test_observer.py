import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"


class ObserverTests(unittest.TestCase):
    def test_bounded_link_observation_only(self):
        record = json.loads((ROOT / "observer-receipt.json").read_text())
        self.assertEqual(set(record), {"core_tb.sv", "cached_core_tb.sv"})
        for name, entry in record.items():
            original = (BASE / "sim" / name).read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest().upper(), entry["parent_sha256"])
            expected = original.decode()
            for before, after in entry["substitutions"]:
                self.assertEqual(expected.count(before), 1)
                expected = expected.replace(before, after)
            actual = (ROOT / "sim" / name).read_bytes()
            self.assertEqual(actual, expected.encode())
            self.assertEqual(hashlib.sha256(actual).hexdigest().upper(), entry["observer_sha256"])
            self.assertIn("core.mem_result!==(core.mem_pc+32'd4)", expected)
            self.assertIn('check(link_push_observations>0,"return-stack link pushes exercised")', expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
