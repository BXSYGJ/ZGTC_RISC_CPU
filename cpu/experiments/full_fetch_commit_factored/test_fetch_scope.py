import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_fetch_scope_firmware as firmware
import run_fetch_scope as runner


class ScopePreparationTests(unittest.TestCase):
    def test_actual_firmware_and_support(self):
        result = firmware.audit_firmware()
        self.assertTrue(result["passed"])
        self.assertEqual(result["sample_cycles"], 1224)
        self.assertEqual(result["timeout_cycles"], 30 * result["clock_hz"])
        self.assertEqual(set(runner.validate_support()), {"sim/scope_tb.sv", "scripts/scope_decode.py"})

    def test_firmware_rejects_wrong_clock_flags_and_commands(self):
        original = firmware.load
        for target, field, value in ((".build.json", "ClockHz", 151200000), (".build.json", "Flags", []), ("invocation.json", "commands", [])):
            with self.subTest(field=field):
                def altered(path):
                    record = copy.deepcopy(original(path))
                    if str(path).endswith(target):
                        record[field] = value
                    return record
                with patch.object(firmware, "load", side_effect=altered):
                    with self.assertRaises(ValueError):
                        firmware.audit_firmware()

    def test_captured_wrong_firmware_rejected(self):
        with tempfile.TemporaryDirectory(prefix="scope-bad-image-") as directory:
            image = Path(directory) / "firmware.hex"
            image.write_text("00000000\n")
            with self.assertRaisesRegex(ValueError, "Captured scope firmware differs"):
                firmware.audit_firmware(image)

    def test_bench_timebase_and_full_parameters(self):
        parameters = runner.physical.binding()["hardware_parameters"]
        bench = runner.generate_bench(parameters)
        self.assertIn("send_byte(8'h55,15938);", bench)
        self.assertEqual(bench.count("repeat(45333)"), 3)
        for name, value in parameters.items():
            self.assertIn(f".{name}({value})", bench)
        self.assertEqual(sum(runner.OVERRIDES["timeout_counter_jumps"]), 4590000000)
        self.assertIn("Scope timeout before full 30-second interval", bench)
        self.assertIn("Scope watchdog", bench)
        self.assertIn("Scope fault", bench)
        self.assertIn("Wrong ready LED state", bench)

    def test_bench_rejects_missing_and_duplicate_anchors(self):
        original = (runner.ROOT / "sim/scope_tb.sv").read_text(encoding="utf-8")
        for before in ("send_byte(8'h55,2813);", "repeat(8000)", "        wait(timeout_count==1);", "rv32_soc #(.CLOCK_HZ(3200),.BAUD(100)) soc(.*);"):
            for mutation in (original.replace(before, ""), original + before):
                with self.subTest(anchor=before):
                    with self.assertRaisesRegex(ValueError, "Scope bench anchor changed"):
                        runner.generate_bench({}, mutation)

    def test_decoder_accepts_only_matching_timebase(self):
        records = [(index * 1224, 2) for index in range(256)]
        capture = "\n".join(["SCOPE1 count=00000100 period=000004c8 clock=091e9840 trigger=01",
                                *[f"{timestamp:08x}:{pins:02x}" for timestamp, pins in records],
                                f"END checksum={runner.decoder.checksum(records):08x} late=00000000"])
        self.assertEqual(runner.decoder.parse_captures(capture, expected_clock_hz=153000000)[0]["clock_hz"], 153000000)
        with self.assertRaisesRegex(ValueError, "Capture clock differs"):
            runner.decoder.parse_captures(capture, expected_clock_hz=151200000)
        with self.assertRaisesRegex(ValueError, "Unsupported capture metadata"):
            runner.decoder.parse_captures(capture.replace("091e9840", "00000001"))

    def test_runner_preserves_failure_and_timeout_logs(self):
        with tempfile.TemporaryDirectory(prefix="scope-runner-") as directory:
            log = Path(directory) / "execute.log"
            with self.assertRaises(ValueError):
                runner.run([sys.executable, "-c", "print('FAILED_COMMAND',flush=True); raise SystemExit(7)"], log, 5)
            self.assertIn("FAILED_COMMAND", log.read_text())
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run([sys.executable, "-c", "import time; print('PROGRESS',flush=True); time.sleep(10)"], log, 1)
            self.assertIn("PROGRESS", log.read_text())
            self.assertIn("HOST_TIMEOUT_SECONDS=1", log.read_text())

    def test_failed_terminal_rejected(self):
        for log in ("", "PASS scope cycles=1 dumps=2 timeout=1 empty=1\nFATAL: fault", "PASS scope cycles=1 dumps=2 timeout=1 empty=1\n" * 2):
            with self.subTest(log=log), self.assertRaises(ValueError):
                runner.validate_output(log, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
