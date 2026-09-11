import unittest
from pathlib import Path
from unittest.mock import patch

import audit_fetch_long as audit


class LongBoundaryTests(unittest.TestCase):
    def test_actual_short_uart_cannot_qualify_as_long(self):
        for name in ("20260911-094801-420d3685", "20260911-094810-8ee47390"):
            text = (audit.ROOT / "build/compiled" / name / "coremark.sim.uart").read_text(encoding="ascii")
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.checker.parse_result(text, allow_short=False, expected_config=0x0e8e96fd, expected_clock_hz=153000000)

    def test_audit_requires_both_completed_long_runs(self):
        original = Path.glob
        target = audit.ROOT / "build/compiled"
        sources = [target / name / "manifest.json" for name in ("20260911-094801-420d3685", "20260911-094810-8ee47390")]
        def glob(path, pattern, *args, **kwargs):
            return iter(sources) if path.resolve() == target.resolve() else original(path, pattern, *args, **kwargs)
        with patch.object(Path, "glob", glob):
            with self.assertRaisesRegex(ValueError, "Expected exactly one completed long run per seed"):
                audit.audit_long()


if __name__ == "__main__":
    unittest.main(verbosity=2)
