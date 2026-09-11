import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def native_arguments(initialization):
    command = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; try { " + initialization + "; & python -c 'import json,sys; print(json.dumps(sys.argv[1:]))' @validationArguments; if ($LASTEXITCODE) { throw 'Native argument receiver failed.' } } catch { Write-Error $_; exit 1 }"
    completed = subprocess.run(["pwsh", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    return json.loads(completed.stdout.strip())


class RunnerArgumentTests(unittest.TestCase):
    def test_actual_runner_passes_one_validation_argument(self):
        text = (ROOT / "run_full_ila.ps1").read_text(encoding="utf-8-sig")
        matches = re.findall(r"    \[string\[\]\]\$validationArguments = @\(\)\n    if \(\$ValidationRun\) \{ \$validationArguments = @\('--validation'\) \}", text)
        self.assertEqual(len(matches), 1, "Typed native argument initialization missing")
        for enabled in (False, True):
            initialization = "$ValidationRun = " + ("$true" if enabled else "$false") + "; " + matches[0]
            with self.subTest(validation=enabled):
                self.assertEqual(native_arguments(initialization), ["--validation"] if enabled else [])

    def test_original_scalar_splat_is_reproduced(self):
        initialization = "$ValidationRun=$true; $validationArguments = if ($ValidationRun) { @('--validation') } else { @() }"
        self.assertEqual(native_arguments(initialization), list("--validation"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
