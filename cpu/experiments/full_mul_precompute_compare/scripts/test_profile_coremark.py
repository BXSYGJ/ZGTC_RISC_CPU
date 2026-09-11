import unittest

from profile_coremark import EVENT_NAMES, analyze


HISTOGRAM = "WINDOW start=00000000 stop=00000010 cycles=20 retired=10\n00000000 1\n00000004 3\n00000008 6\n"
SYMBOLS = "00000000 00000008 T iterate\n00000008 00000008 T helper\n00000010 00000004 T stop_time\n"


class ProfileTests(unittest.TestCase):
    def test_conservation_and_percentages(self):
        result = analyze(HISTOGRAM, SYMBOLS)
        self.assertEqual(result["ambiguous_or_unmapped_retired"], 0)
        self.assertEqual(result["functions"][0], {"name": "helper", "retired": 6, "retired_percent": 60})

    def test_event_counts_and_legacy_profiles(self):
        values = dict.fromkeys(EVENT_NAMES, 0)
        values.update(branch_resolutions=4, branch_redirects=1, jalr_resolutions=2, jalr_redirects=1,
                      retiring_cycles=10, nonretiring_cycles=10, memory_wait_cycles=15, fetch_wait_cycles=15)
        row = "EVENTS " + " ".join(f"{name}={values[name]}" for name in EVENT_NAMES)
        header, body = HISTOGRAM.split("\n", 1)
        result = analyze(header + "\n" + row + "\n" + body, SYMBOLS)
        self.assertEqual(result["pipeline_events"]["conditional_branch_redirect_percent"], 25)
        self.assertEqual(result["pipeline_events"]["indirect_jump_redirect_percent"], 50)
        self.assertIsNone(analyze(HISTOGRAM, SYMBOLS)["pipeline_events"])
        for invalid in (row.replace("branch_redirects=1", "branch_redirects=5"),
                        row.replace("memory_wait_cycles=15", "memory_wait_cycles=21"),
                        row.replace("branch_resolutions=4", "branch_resolutions=20"),
                        row.replace("nonretiring_cycles=10", "nonretiring_cycles=9"),
                        row.replace("retiring_cycles=10", "retiring_cycles=9"),
                        row.replace("jalr_redirects=1", "jalr_redirects=-1"),
                        row + " unknown=1", row + "\n" + row, row.replace("fetch_wait_cycles=15", "fetch_wait_cycles=x")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                analyze(header + "\n" + invalid + "\n" + body, SYMBOLS)

    def test_ambiguous_symbols_not_guessed(self):
        result = analyze(HISTOGRAM, SYMBOLS + "00000008 00000008 T alias\n")
        self.assertEqual(result["ambiguous_or_unmapped_retired"], 6)

    def test_malformed_duplicates_and_nonconservation(self):
        for text in ("", HISTOGRAM + "00000008 6\n", HISTOGRAM.replace("retired=10", "retired=11"),
                     HISTOGRAM.replace("cycles=20", "cycles=2"), HISTOGRAM.replace("00000004 3", "00000005 3"),
                     HISTOGRAM.replace("00000008 6", "00010000 6"), HISTOGRAM.replace("00000008 6", "00000010 6"),
                     HISTOGRAM.replace("00000000 1", "00000000 2")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                analyze(text, SYMBOLS)

    def test_empty_symbols_rejected(self):
        with self.assertRaises(ValueError):
            analyze(HISTOGRAM, "")


if __name__ == "__main__":
    unittest.main()
