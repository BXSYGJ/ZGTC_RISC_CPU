import copy
import unittest
from unittest.mock import patch

import audit_history_screens as screens


class HistoryScreenAuditTests(unittest.TestCase):
    def test_actual_pair_is_not_mislabeled_as_improved(self):
        result = screens.compare("full_history_fold2", screens.RUNS["full_history_fold2"])
        self.assertFalse(result["both_short_runs_faster"])
        self.assertFalse(result["full_score_qualified"])
        self.assertEqual([pair["extra_cycles"] for pair in result["pairs"]], [669, 120])

    def reject_mutation(self, mutate, message):
        actual_reader = screens.read_run

        def changed_reader(directory):
            manifest, result = actual_reader(directory)
            if "full_history_fold2" in directory.parts:
                manifest, result = copy.deepcopy(manifest), copy.deepcopy(result)
                mutate(manifest, result)
            return manifest, result

        with patch.object(screens, "read_run", side_effect=changed_reader):
            with self.assertRaisesRegex(ValueError, message):
                screens.compare("full_history_fold2", screens.RUNS["full_history_fold2"])

    def test_changed_firmware_metadata_rejected(self):
        self.reject_mutation(lambda manifest, result: manifest["FirmwareBuild"].update(Iterations=11), "Firmware changed")

    def test_changed_cache_configuration_rejected(self):
        self.reject_mutation(lambda manifest, result: manifest["HardwareParameters"].update(ENABLE_CACHE=0), "hardware parameters differ")

    def test_changed_retired_count_rejected(self):
        self.reject_mutation(lambda manifest, result: result.update(retired=result["retired"] + 1), "Architectural or test configuration differs")

    def test_changed_compile_options_rejected(self):
        self.reject_mutation(lambda manifest, result: manifest["CompileCommand"].append("--different-option"), "Compile commands differ")


if __name__ == "__main__":
    unittest.main(verbosity=2)

