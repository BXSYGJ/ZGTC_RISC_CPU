import unittest
from scope_decode import checksum, decode_triggered_uart, parse_captures, waveform_svg


def fixture(clock_hz=27000000):
    records = []
    for index in range(256):
        timestamp = 100 + (clock_hz // 125000) * index
        bit_index = timestamp // ((clock_hz + 4800) // 9600)
        level = 0 if bit_index == 0 else ((0x55 >> (bit_index-1)) & 1 if bit_index <= 8 else 1)
        records.append((timestamp, level * 2))
    lines = [f"SCOPE1 count=00000100 period={clock_hz // 125000:08x} clock={clock_hz:08x} trigger=02"]
    lines.extend(f"{timestamp:08x}:{pins:02x}" for timestamp, pins in records)
    lines.append(f"END checksum={checksum(records):08x} late=00000000")
    return "\n".join(lines)


class ScopeDecoderTests(unittest.TestCase):
    def test_uart_waveform(self):
        capture = parse_captures(fixture())[0]
        self.assertEqual(decode_triggered_uart(capture, 9600), 0x55)
        self.assertIn("polyline", waveform_svg(capture))

    def test_current_clock_and_time_axis(self):
        capture = parse_captures(fixture(157500000), expected_clock_hz=157500000)[0]
        self.assertEqual(capture["period_cycles"], 1260)
        self.assertEqual(decode_triggered_uart(capture, 9600), 0x55)
        self.assertIn("2040.0 us", waveform_svg(capture))
        for actual, expected in ((157500000, 27000000), (27000000, 157500000)):
            with self.assertRaisesRegex(ValueError, "expected firmware clock"):
                parse_captures(fixture(actual), expected_clock_hz=expected)
        with self.assertRaises(ValueError):
            parse_captures(fixture(157500000).replace("clock=09634260", "clock=00000000"))

    def test_corruption_rejected(self):
        for changed in (fixture().replace("00000064:00", "00000064:01"),
                        fixture().replace("count=00000100", "count=00000101"),
                        fixture().replace("0000013c:00", "00000064:00"),
                        fixture().replace("trigger=02", "trigger=04"),
                        fixture().rsplit("\n", 1)[0]):
            with self.subTest(changed=changed[:80]), self.assertRaises(ValueError):
                parse_captures(changed)

    def test_sparse_sampling_rejected(self):
        capture = parse_captures(fixture())[0]
        capture["records"] = capture["records"][::16]
        with self.assertRaises(ValueError):
            decode_triggered_uart(capture, 9600)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            parse_captures("EMPTY\n")

    def test_multiple_packets(self):
        self.assertEqual(len(parse_captures(fixture()+"\nDONE\n"+fixture())), 2)


if __name__ == "__main__":
    unittest.main()
