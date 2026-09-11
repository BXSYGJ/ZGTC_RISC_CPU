import unittest
from replay import replay, stack_action


def jal(destination=1):
    return 111 | destination << 7


def jalr(destination=0, source=1, immediate=0, function=0):
    return 103 | destination << 7 | function << 12 | source << 15 | (immediate & 4095) << 20


def events(instructions):
    return [(index + 1, address, instruction) for index, (address, instruction) in enumerate(instructions)]


class ReplayTests(unittest.TestCase):
    def test_all_jalr_register_hints(self):
        for destination in range(32):
            for source in range(32):
                if destination in (1, 5):
                    expected = (source in (1, 5) and source != destination, True)
                else:
                    expected = (source in (1, 5), False)
                with self.subTest(destination=destination, source=source):
                    self.assertEqual(stack_action(jalr(destination, source)), expected)
                    self.assertEqual(stack_action(jalr(destination, source, -4)), expected)
        for destination in range(32):
            self.assertEqual(stack_action(jal(destination)), (False, destination in (1, 5)))
        for function in range(1, 8):
            self.assertEqual(stack_action(jalr(function=function)), (False, False))
        self.assertEqual(stack_action(19), (False, False))

    def test_nested_calls_and_changing_return_target(self):
        trace = events([(0x100, jal()), (0x200, jal()), (0x300, jalr()),
                        (0x204, jalr()), (0x104, jal()), (0x300, jalr()), (0x108, 19)])
        result = replay(trace, (1, 2, 4))
        self.assertEqual(result["counts"]["resolved_pops"], 3)
        self.assertEqual(result["counts"]["pc_last_target_changes"], 1)
        self.assertEqual(result["depths"]["1"]["correct_targets"], 2)
        self.assertEqual(result["depths"]["1"]["overflows"], 1)
        self.assertEqual(result["depths"]["1"]["underflows"], 1)
        self.assertEqual(result["depths"]["2"]["correct_targets"], 3)
        self.assertEqual(result["depths"]["4"]["wrong_targets"], 0)

    def test_cold_entry_and_last_target_hit(self):
        result = replay(events([(0x300, jalr()), (0x104, 19), (0x300, jalr()), (0x104, 19)]), (2,))
        self.assertEqual(result["counts"]["pc_last_target_cold"], 1)
        self.assertEqual(result["counts"]["pc_last_target_hits"], 1)
        self.assertEqual(result["depths"]["2"]["underflows"], 2)
        self.assertEqual(result["depths"]["2"]["resolved_without_prediction"], 2)

    def test_coroutine_pop_then_push(self):
        result = replay(events([(0x100, jal(5)), (0x200, jalr(1, 5)), (0x104, jalr()), (0x204, 19)]), (2,))
        self.assertEqual(result["counts"]["pop_then_push_hints"], 1)
        self.assertEqual(result["depths"]["2"]["correct_targets"], 2)
        self.assertEqual(result["depths"]["2"]["maximum_occupancy"], 1)

    def test_same_link_push_and_wrong_return(self):
        result = replay(events([(0x100, jalr(1, 1)), (0x200, jalr()), (0x108, 19)]), (2,))
        self.assertEqual(result["counts"]["pop_hints"], 1)
        self.assertEqual(result["depths"]["2"]["wrong_targets"], 1)

    def test_final_return_is_not_assigned_a_target(self):
        result = replay(events([(0x100, jal()), (0x200, jalr())]), (2,))
        self.assertEqual(result["counts"]["unresolved_final_pop"], 1)
        self.assertEqual(result["depths"]["2"]["resolved_predictions"], 0)
        self.assertEqual(result["counts"]["resolved_pops"], 0)

    def test_invalid_trace_and_configuration(self):
        for trace in ([], [(0, 2, 19)], [(2, 0, 19), (2, 4, 19)], [(-1, 0, 19)]):
            with self.subTest(trace=trace), self.assertRaises((AssertionError, ValueError, RuntimeError)):
                replay(trace)
        for depths in ((), (0,), (65,), (2, 2)):
            with self.subTest(depths=depths), self.assertRaises((AssertionError, ValueError, RuntimeError)):
                replay(events([(0, 19)]), depths)


if __name__ == "__main__":
    unittest.main(verbosity=2)

