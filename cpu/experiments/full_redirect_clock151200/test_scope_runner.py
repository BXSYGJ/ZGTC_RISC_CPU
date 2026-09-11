import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from run_scope_current import run


class ScopeRunnerLoggingTests(unittest.TestCase):
    def test_success_retains_stdout_and_stderr(self):
        with tempfile.TemporaryDirectory(prefix="scope-log-") as directory:
            log = Path(directory) / "execute.log"
            text = run([sys.executable, "-c", "import sys; print('OUT',flush=True); print('ERR',file=sys.stderr,flush=True)"], log, 5)
            self.assertIn("OUT", text)
            self.assertIn("ERR", text)
            self.assertEqual(text, log.read_text(encoding="utf-8"))

    def test_failure_retains_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="scope-log-") as directory:
            log = Path(directory) / "execute.log"
            with self.assertRaisesRegex(ValueError, "Current scope command failed"):
                run([sys.executable, "-c", "print('FAIL_MARKER',flush=True); raise SystemExit(7)"], log, 5)
            self.assertIn("FAIL_MARKER", log.read_text(encoding="utf-8"))

    def test_timeout_retains_progress_and_marker(self):
        with tempfile.TemporaryDirectory(prefix="scope-log-") as directory:
            log = Path(directory) / "execute.log"
            with self.assertRaises(subprocess.TimeoutExpired):
                run([sys.executable, "-c", "import time; print('PROGRESS_MARKER',flush=True); time.sleep(10)"], log, 1)
            text = log.read_text(encoding="utf-8")
            self.assertIn("PROGRESS_MARKER", text)
            self.assertIn("HOST_TIMEOUT_SECONDS=1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
