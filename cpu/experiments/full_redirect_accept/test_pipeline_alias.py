from pathlib import Path
import re
import unittest

from audit_ila_mapping import normalize_pipeline_mapping, validate_config

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "build/ila/20260910-redirect-accept-seed2-remapped"


class PipelineAliasTests(unittest.TestCase):
    def setUp(self):
        self.netlist = (STAGE / "netlist.v").read_text(encoding="utf-8-sig")
        self.fic = (STAGE / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
        self.output = (STAGE / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig")

    def evaluate(self, netlist=None, fic=None, output=None):
        normalized, observed, aliases = normalize_pipeline_mapping(
            self.netlist if netlist is None else netlist,
            self.fic if fic is None else fic,
            self.output if output is None else output)
        return validate_config(normalized, observed)

    def test_actual_full_map(self):
        result = self.evaluate()
        self.assertEqual((result["data_channels"], result["trigger_channels"], result["depth"]), (42, 33, 1024))

    def test_wrong_register_drivers(self):
        for index in range(4):
            before = f".Q (pipeline_valid[{index}])"
            self.assertEqual(self.netlist.count(before), 1)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "Wrong pipeline register driver"):
                self.evaluate(netlist=self.netlist.replace(before, ".Q (other_signal)"))

    def test_missing_and_swapped_channels(self):
        for index in range(4):
            actual = "board/soc/unused_pipeline_valid[1]" if index == 1 else f"board/soc/core/pipeline_valid[{index}]"
            before = f"Project.unit<0>.dataChannel<{32 + index}>={actual}"
            self.assertEqual(self.fic.count(before), 1)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.evaluate(fic=self.fic.replace(before, before.replace(f"[{index}]", f"[{(index + 1) % 4}]")))

    def test_wrong_parent_alias_connection(self):
        before = "unused_pipeline_valid[1]"
        instances = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", self.netlist, re.S)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].count(before), 1)
        mutated = self.netlist.replace(instances[0], instances[0].replace(before, "wrong_alias[1]"))
        with self.assertRaisesRegex(ValueError, "Wrong ID-valid alias connection"):
            self.evaluate(netlist=mutated)

    def test_observed_map_required(self):
        with self.assertRaises(ValueError):
            self.evaluate(output=self.output.replace("board/soc/core/pipeline_valid[0]", "wrong_signal"))

    def test_width_and_depth_not_reduced(self):
        for before, after in (("dataDepth=1024", "dataDepth=512"), ("dataPortWidth=42", "dataPortWidth=41"),
                              ("triggerPortWidth<0>=33", "triggerPortWidth<0>=32")):
            with self.subTest(property=before), self.assertRaises(ValueError):
                self.evaluate(fic=self.fic.replace(before, after))


if __name__ == "__main__":
    unittest.main(verbosity=2)
