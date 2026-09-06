import unittest
from check_coremark import parse_result


def fixture(cycles=324000000, clock_hz=27000000):
    seconds = cycles // clock_hz
    validation = "Correct operation validated." if seconds >= 10 else "ERROR! Must execute for at least 10 secs for a valid result!\nErrors detected"
    return "\n".join((
        "ZGTC COREMARK START iterations=120 validation=0",
        "CoreMark Size    : 666",
        f"Total ticks      : {cycles // (clock_hz // 1000)}",
        f"Total time (secs): {seconds}",
        "Iterations       : 120",
        "Compiler flags   : -DTOTAL_DATA_SIZE=2000",
        "seedcrc          : 0xe9f5",
        "[0]crclist       : 0xe714",
        "[0]crcmatrix     : 0x1fd7",
        "[0]crcstate      : 0x8e3a",
        "[0]crcfinal      : 0x1234",
        validation,
        f"ZGTC cycles_hex={cycles:016x} retired_hex=0000000005000000 clock_hz={clock_hz}",
        "ZGTC COREMARK FINISHED",
    ))


class CoreMarkCheckerTests(unittest.TestCase):
    def test_supported_clock_scores(self):
        for clock_hz in (27000000, 54000000, 60000000, 67500000, 72000000, 75600000, 81000000, 90000000, 99000000, 102600000, 108000000, 135000000, 162000000, 180000000, 194400000, 216000000, 270000000):
            with self.subTest(clock_hz=clock_hz):
                text = fixture(clock_hz * 12, clock_hz)
                result = parse_result(text, expected_clock_hz=clock_hz)
                self.assertEqual(result["seconds"], 12)
                self.assertEqual(result["iterations_per_second"], 10)
                self.assertAlmostEqual(result["iterations_per_second_per_mhz"], 10000000 / clock_hz)
                with self.assertRaises(ValueError):
                    parse_result(text, expected_clock_hz=clock_hz + 1)
        with self.assertRaises(ValueError):
            parse_result(fixture(360000000, 30000000), expected_clock_hz=30000000)

    def test_explicit_frequency_required(self):
        text = fixture(648000000).replace("clock_hz=27000000", "clock_hz=54000000").replace("Total ticks      : 24000", "Total ticks      : 12000").replace("Total time (secs): 24", "Total time (secs): 12")
        with self.assertRaises(ValueError):
            parse_result(text)
        result = parse_result(text, expected_clock_hz=54000000)
        self.assertEqual(result["seconds"], 12)
        self.assertEqual(result["iterations_per_second"], 10)
        self.assertAlmostEqual(result["iterations_per_second_per_mhz"], 10 / 54)
        with self.assertRaises(ValueError):
            parse_result(text.replace("12000", "24000"), expected_clock_hz=54000000)

    def test_valid_score(self):
        result = parse_result(fixture(), lut_count=1000)
        self.assertTrue(result["reportable_duration"])
        self.assertEqual(result["iterations_per_second"], 10)
        self.assertEqual(result["iterations_per_second_per_lut"], 0.01)

    def test_short_never_scored(self):
        text = fixture(27000000)
        with self.assertRaises(ValueError):
            parse_result(text)
        result = parse_result(text, allow_short=True)
        self.assertFalse(result["reportable_duration"])
        self.assertNotIn("iterations_per_second", result)

    def test_mutations_rejected(self):
        mutations = (("0xe714", "0xe715"), ("0xe9f5", "0x18f2"),
                     ("Total ticks      : 12000", "Total ticks      : 11000"),
                     ("ZGTC COREMARK FINISHED", "missing"),
                     ("Correct operation validated.", "Errors detected"),
                     ("Iterations       : 120", "Iterations       : 121"),
                     ("clock_hz=27000000", "clock_hz=54000000"),
                     ("CoreMark Size    : 666", "CoreMark Size    : 2000"))
        for original, replacement in mutations:
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                parse_result(fixture().replace(original, replacement))

    def test_duplicate_runs_rejected(self):
        with self.assertRaises(ValueError):
            parse_result(fixture() + "\n" + fixture())

    def test_trap_rejected(self):
        with self.assertRaises(ValueError):
            parse_result(fixture() + "\nZGTC TRAP cause=2")

    def test_validation_seed(self):
        text = fixture().replace("validation=0", "validation=1").replace("0xe9f5", "0x18f2").replace("0xe714", "0xe3c1").replace("0x1fd7", "0x0747").replace("0x8e3a", "0x8d84")
        self.assertTrue(parse_result(text)["validation_run"])

    def test_uncached_profile(self):
        text = fixture() + "\nZGTC config=0e020403 ihit=0 imiss=0 dhit=0 dmiss=0 writebacks=0"
        result = parse_result(text, expected_config=0x0E020403)
        self.assertFalse(result["profile"]["cache_enabled"])
        self.assertTrue(result["profile"]["predictor_enabled"])
        for field in ("ihit", "imiss", "dhit", "dmiss", "writebacks"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_result(text.replace(f"{field}=0", f"{field}=1"))

    def test_profile_configuration(self):
        fast_text = fixture() + "\nZGTC config=0e020409 ihit=100 imiss=20 dhit=90 dmiss=10 writebacks=4"
        self.assertTrue(parse_result(fast_text, expected_config=0x0E020409)["profile"]["fast_icache_hit"])
        with self.assertRaises(ValueError):
            parse_result(fast_text, expected_config=0x0E020401)
        invalid = fixture() + "\nZGTC config=0e02040b ihit=0 imiss=0 dhit=0 dmiss=0 writebacks=0"
        with self.assertRaises(ValueError):
            parse_result(invalid)
        text = fixture() + "\nZGTC config=0e020401 ihit=100 imiss=20 dhit=90 dmiss=10 writebacks=4"
        result = parse_result(text, expected_config=0x0E020401)
        self.assertEqual(result["profile"]["i_hits"], 100)
        self.assertFalse(result["profile"]["load_use_bubble"])
        bubble_text = text.replace("config=0e020401", "config=0e020405")
        self.assertTrue(parse_result(bubble_text, expected_config=0x0E020405)["profile"]["load_use_bubble"])
        with self.assertRaises(ValueError):
            parse_result(bubble_text, expected_config=0x0E020401)
        self.assertTrue(result["profile"]["interval_includes_counter_read_overhead"])
        with self.assertRaises(ValueError):
            parse_result(text, expected_config=0x0E020400)
        with self.assertRaises(ValueError):
            parse_result(fixture(), expected_config=0x0E020401)
        with self.assertRaises(ValueError):
            parse_result(text.replace("ihit=100", "ihit=4294967296"))


if __name__ == "__main__":
    unittest.main()
