import tempfile
import unittest
from pathlib import Path

from analyze_control import BITS, classify_ex_block, records, summarize
from profile_control import FLAGS, ROOT, observe_soc, observe_driver, replace_once


def flags(*names):
    return sum(BITS[name] for name in names)


class ControlEventTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {"start_cycle": 100, "stop_cycle": 104, "cycles": 4, "records": 3}
        self.image = bytes.fromhex("63000000")
        self.events = [
            (100, 0, 0, flags("wb_valid")),
            (101, 0, 0, flags("mem_valid", "mem_fire", "mem_ready", "ex_valid", "ex_fire", "ex_decode.is_branch", "mem_branch", "mem_conditional")),
            (102, 0, 0, flags("wb_valid", "mem_valid", "ex_valid")),
            (103, 0, 0, flags("ex_valid", "mem_ready", "load_use_wait")),
        ]

    def test_exact_cycle_and_retirement_conservation(self):
        result = summarize(self.events, self.metadata, self.image)
        self.assertEqual(result["counts"]["wb_empty_cycles"], 2)
        self.assertEqual(result["counts"]["wb_events"], 2)
        self.assertEqual(result["ex_blocked_priority_partition"], {"memory_stage_not_ready": 1, "load_use_wait": 1})
        self.assertEqual(result["control_pcs"][0]["mem_events"], 1)

    def test_missing_duplicate_and_outside_cycles_rejected(self):
        mutations = [self.events[:-1], [self.events[0], *self.events], [(99, *self.events[0][1:]), *self.events[1:]]]
        for changed in mutations:
            with self.subTest(length=len(changed)), self.assertRaises(ValueError):
                summarize(changed, self.metadata, self.image)

    def test_fire_valid_flush_and_wb_invariants_rejected(self):
        mutations = [(1, BITS["ex_valid"]), (1, BITS["mem_valid"]), (2, BITS["frontend_flush"]), (0, BITS["mem_fire"])]
        for index, mask in mutations:
            changed = list(self.events)
            row = changed[index]
            changed[index] = (*row[:3], row[3] ^ mask)
            with self.subTest(index=index, mask=mask), self.assertRaises(ValueError):
                summarize(changed, self.metadata, self.image)
        changed = list(self.events)
        changed[0] = (*changed[0][:3], flags("wb_valid", "mem_valid", "mem_fire"))
        changed[1] = (*changed[1][:3], changed[1][3] | BITS["wb_valid"])
        with self.assertRaisesRegex(ValueError, "retirement interval"):
            summarize(changed, self.metadata, self.image)

    def test_wb_without_previous_mem_fire_rejected(self):
        changed = list(self.events)
        changed[1] = (*changed[1][:3], changed[1][3] & ~BITS["mem_fire"])
        with self.assertRaisesRegex(ValueError, "prior MEM fire"):
            summarize(changed, self.metadata, self.image)

    def test_wrong_firmware_control_opcode_rejected(self):
        with self.assertRaisesRegex(ValueError, "actual firmware"):
            summarize(self.events, self.metadata, bytes.fromhex("13000000"))

    def test_truncated_record_rejected(self):
        with tempfile.TemporaryDirectory(prefix="control-record-") as directory:
            path = Path(directory) / "truncated.bin"
            path.write_bytes(bytes(19))
            with self.assertRaisesRegex(ValueError, "Truncated"):
                list(records(path))

    def test_stall_priority_is_explicit(self):
        blocked = flags("ex_valid", "mem_ready", "load_use_wait", "ex_muldiv")
        self.assertEqual(classify_ex_block(blocked), "load_use_wait")
        self.assertEqual(classify_ex_block(blocked | BITS["mem_flush"]), "older_flush")
        self.assertEqual(classify_ex_block(blocked | BITS["interrupt_pending"]), "interrupt_drain")
        self.assertEqual(classify_ex_block(flags("ex_valid", "mem_ready", "ex_muldiv")), "muldiv_result_wait")
        self.assertIsNone(classify_ex_block(blocked | BITS["ex_fire"]))

    def test_observation_flag_width_and_source_anchors(self):
        self.assertEqual(len(FLAGS), 32)
        self.assertEqual(len(set(FLAGS)), 32)
        original = (ROOT / "rtl/rv32_soc.sv").read_text()
        observed = observe_soc(original)
        self.assertIn("output wire [31:0] control_flags,control_ex_pc,control_mem_pc", observed)
        self.assertIn("assign control_flags={core.interrupt_pending", observed)
        with self.assertRaises(ValueError):
            observe_soc(original + "\nendmodule\n")
        with self.assertRaises(ValueError):
            observe_driver("int main() {}")
        with self.assertRaises(ValueError):
            replace_once("anchor anchor", "anchor", "replacement")


if __name__ == "__main__":
    unittest.main(verbosity=2)
