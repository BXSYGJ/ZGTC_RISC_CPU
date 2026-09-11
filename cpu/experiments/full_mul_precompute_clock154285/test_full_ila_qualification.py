import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qualify_full_ila import digest, qualify


class FullIlaQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="keep-ila-qualification-")
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        for name in ("source.adf", "netlist.v", "firmware.hex", "cpu-remapped.fic", "board.fdc", "uart_remotelab.fdc"):
            (self.stage / name).write_text(name, encoding="utf-8")
        (self.stage / "build.tcl").write_text("pnr -gplace_seed 2\n", encoding="utf-8")
        mapping = {"data_channels": 42, "trigger_channels": 33, "depth": 1024, "clock": "cpu_clk"}
        (self.stage / "mapping-audit.json").write_text(json.dumps(mapping), encoding="utf-8")
        self.inputs = {name: digest(filename) for filename in self.stage.iterdir() for name in (filename.name,)}
        self.started = time.time() - 1
        for relative in ("report_timing/pds_soc_top.rtr", "run.log", "generate_bitstream/pds_soc_top.sbit", "pds.stdout.log", "pds.stderr.log"):
            filename = self.stage / relative
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text("fixture", encoding="utf-8")
        self.invocation = {"ExitCode": 0, "WorkingDirectory": str(self.stage), "PlacementSeed": 2,
                           "StartedUtc": datetime.fromtimestamp(self.started, timezone.utc).isoformat(),
                           "FinishedUtc": datetime.now(timezone.utc).isoformat(), "Inputs": self.inputs}
        self.save_invocation()
        self.report = {"constraints_met": False, "resources": {"post_route_luts": 9300}}

    def save_invocation(self):
        (self.stage / "invocation.json").write_text(json.dumps(self.invocation), encoding="utf-8")

    def evaluate(self):
        with patch("qualify_full_ila.parse_ila_reports", return_value=dict(self.report)) as parser:
            result = qualify(self.stage, audit_mapping=False)
            parser.assert_called_once_with("fixture", "fixture", 154285714)
            return result

    def test_physical_gates_do_not_grant_hardware_score(self):
        self.assertFalse(self.evaluate()["physical_timing_passed"])
        self.report["constraints_met"] = True
        result = self.evaluate()
        self.assertTrue(result["physical_timing_passed"])
        self.assertFalse(result["full_score_qualified"])
        self.assertFalse(result["hardware_validated"])
        self.assertIsNone(result["coremark_score"])
        self.report["resources"] = {"post_route_luts": 9374}
        self.assertTrue(self.evaluate()["physical_timing_passed"])
        self.assertFalse(self.evaluate()["resource_efficiency_qualified"])

    def test_modified_input_rejected(self):
        (self.stage / "firmware.hex").write_text("wrong", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Implementation input changed"):
            self.evaluate()

    def test_stale_report_rejected(self):
        filename = self.stage / "report_timing/pds_soc_top.rtr"
        os.utime(filename, (self.started - 60, self.started - 60))
        with self.assertRaisesRegex(ValueError, "Output not from invocation"):
            self.evaluate()

    def test_missing_bitstream_rejected(self):
        (self.stage / "generate_bitstream/pds_soc_top.sbit").unlink()
        with self.assertRaisesRegex(ValueError, "Missing generated output"):
            self.evaluate()

    def test_unfinished_invocation_rejected(self):
        self.invocation["ExitCode"] = None
        self.save_invocation()
        with self.assertRaisesRegex(ValueError, "PDS did not finish"):
            self.evaluate()

    def test_omitted_hash_rejected(self):
        self.inputs.pop("firmware.hex")
        self.save_invocation()
        with self.assertRaisesRegex(ValueError, "Incomplete implementation input"):
            self.evaluate()

    def test_wrong_ila_dimensions_rejected(self):
        filename = self.stage / "mapping-audit.json"
        mapping = json.loads(filename.read_text(encoding="utf-8"))
        mapping["data_channels"] = 40
        filename.write_text(json.dumps(mapping), encoding="utf-8")
        self.inputs[filename.name] = digest(filename)
        self.save_invocation()
        with self.assertRaisesRegex(ValueError, "Wrong ILA dimensions"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
