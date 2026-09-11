import itertools
import unittest

from check_coremark import parse_result
from run_coremark_compiled import configuration_word, hardware_parameters, check_simulation_result
from test_coremark_checker import fixture
from test_coremark_compiled import configuration


class InstructionCacheParameterTests(unittest.TestCase):
    def test_reference_memory_geometry_preserves_fault_boundary(self):
        from check_trace import Reference, Trap
        self.assertEqual(len(Reference(b"\x13\x00\x00\x00").memory), 16384)
        for memory_bytes in (16384, 32768):
            reference = Reference(b"\x13\x00\x00\x00", memory_bytes=memory_bytes)
            self.assertEqual(len(reference.memory), memory_bytes)
            reference.memory[-4:] = (0x13).to_bytes(4, "little")
            reference.pc = memory_bytes - 4
            self.assertEqual(reference.fetch(), 0x13)
            reference.pc = 0x8000
            with self.assertRaises(Trap) as fetched:
                reference.fetch()
            self.assertEqual((fetched.exception.cause, fetched.exception.value), (1, 0x8000))
            reference.registers[1] = 0x8000
            for instruction, cause in ((0x0000a103, 5), (0x0020a023, 7)):
                with self.assertRaises(Trap) as trapped:
                    reference.decode(instruction)
                self.assertEqual((trapped.exception.cause, trapped.exception.value), (cause, 0x8000))
        for memory_bytes in (True, "32768", 8192, 65536):
            with self.subTest(memory_bytes=memory_bytes), self.assertRaises(ValueError):
                Reference(b"", memory_bytes=memory_bytes)
        with self.assertRaises(ValueError):
            Reference(bytes(32769), memory_bytes=32768)

    def test_reference_expanded_upper_half_is_real_memory(self):
        from check_trace import Reference, Trap
        small = Reference(b"")
        expanded = Reference(b"", memory_bytes=32768)
        small.registers[1] = expanded.registers[1] = 0x4000
        with self.assertRaises(Trap) as trapped:
            small.decode(0x0000a103)
        self.assertEqual(trapped.exception.cause, 5)
        expanded.decode(0x0000a103)

    def test_instruction_data_predictor_round_trip(self):
        cases = 0
        for instruction_bits, data_bits, predictor_bits in itertools.product(range(1, 11), range(1, 9), range(1, 9)):
            with self.subTest(instruction_bits=instruction_bits, data_bits=data_bits, predictor_bits=predictor_bits):
                values = {**configuration(), 'ICacheSetBits': instruction_bits, 'CacheSetBits': data_bits,
                          'BtbIndexBits': predictor_bits}
                parameters = hardware_parameters(values)
                encoded = configuration_word(parameters)
                self.assertEqual((encoded >> 12) & 15, instruction_bits if instruction_bits != data_bits else 0)
                self.assertEqual((encoded >> 8) & 15, data_bits)
                text = fixture() + f'\nZGTC config={encoded:08x} ihit=1 imiss=2 dhit=3 dmiss=4 writebacks=5\n'
                result = check_simulation_result(text, {'Iterations': 120, 'ValidationRun': False, 'ClockHz': 27000000}, parameters, False)
                self.assertEqual(result['profile']['icache_set_bits'], instruction_bits)
                self.assertEqual(result['profile']['dcache_set_bits'], data_bits)
                self.assertEqual(result['profile']['btb_index_bits'], predictor_bits)
                self.assertEqual(result['measurement_kind'], 'rtl_simulation_not_hardware')
                cases += 1
        print(f'PASS cache parameter round trips={cases}')

    def test_new_instruction_width_does_not_widen_data_or_predictor(self):
        values = {**configuration(), 'ICacheSetBits': 10}
        for name, rejected in [('CacheSetBits', 9), ('CacheSetBits', 10), ('BtbIndexBits', 9),
                               ('ICacheSetBits', 11), ('ICacheSetBits', 16), ('ICacheSetBits', 0),
                               ('ICacheSetBits', True), ('ICacheSetBits', '10')]:
            with self.subTest(name=name, rejected=rejected), self.assertRaisesRegex(ValueError, 'width hardware'):
                hardware_parameters({**values, name: rejected})
        for encoded in ('0e8eb6f9', '0e8ef6f9', '0e8ea9f9', '0e9ea6f9'):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                parse_result(fixture()+f'\nZGTC config={encoded} ihit=1 imiss=2 dhit=3 dmiss=4 writebacks=5\n')

    def test_expanded_runtime_must_match_requested_geometry(self):
        parameters = hardware_parameters({**configuration(), 'ICacheSetBits': 10})
        text = fixture()+'\nZGTC config=0e8e96f9 ihit=1 imiss=2 dhit=3 dmiss=4 writebacks=5\n'
        with self.assertRaisesRegex(ValueError, 'configuration differs'):
            check_simulation_result(text, {'Iterations': 120, 'ValidationRun': False, 'ClockHz': 27000000}, parameters, False)


if __name__ == '__main__':
    unittest.main()
