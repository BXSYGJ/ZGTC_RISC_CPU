import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = 'c4f0ef80e634f153f5bf1cb2b0f9bb314432333bf9dc93e1a8e9f6e1c2cc2346'


class AddressPartitionTests(unittest.TestCase):
    def simulate(self, split_bits, variant='positive'):
        baseline = (PROJECT / 'rtl/rv32_core.sv').read_bytes()
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), BASELINE_SHA256)
        original = '    wire [31:0] effective_address=forwarded_a+ex_decode.immediate;'
        self.assertEqual(baseline.decode().count(original), 1)
        source = (PROJECT / f'experiments/address_partition/rv32_core_{split_bits}.sv').read_text()
        start = source.index('    wire [')
        candidate_start = source.index(f'    wire [{split_bits}:0] address_low=')
        candidate_end = source.index(';', source.index('    wire [31:0] effective_address=', candidate_start)) + 1
        self.assertGreater(candidate_start, start)
        self.assertEqual(source[:candidate_start] + original + source[candidate_end:], baseline.decode())
        if variant == 'baseline':
            source = baseline.decode()
        high_bits = 32 - split_bits
        mutations = {
            'lost_carry': (f'address_low[{split_bits}] ? address_high_one : address_high_zero', 'address_high_zero'),
            'wrong_carry_bit': (f'address_low[{split_bits}] ?', f'address_low[{split_bits-1}] ?'),
            'wrong_high_carry': (f"ex_decode.immediate[31:{split_bits}]+{high_bits}'d1", f"ex_decode.immediate[31:{split_bits}]-{high_bits}'d1"),
            'cleared_address_low': (f'address_high_zero,address_low[{split_bits-1}:0]', f"address_high_zero,address_low[{split_bits-1}:2],2'b0"),
            'lost_immediate_high': (f'address_high_zero=forwarded_a[31:{split_bits}]+ex_decode.immediate[31:{split_bits}]', f'address_high_zero=forwarded_a[31:{split_bits}]'),
        }
        if variant not in ('positive', 'baseline'):
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='address-partition-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            image = work / 'test.vvp'
            dependencies = [PROJECT / 'rtl' / name for name in (
                'rv32_machine.sv', 'rv32_decode.sv', 'rv32_alu.sv', 'rv32_btb.sv', 'rv32_muldiv.sv')]
            command = ['iverilog', '-g2012', '-s', 'address_partition_tb', '-o', str(image),
                       f'-Paddress_partition_tb.SPLIT_BITS={split_bits}', str(core),
                       *map(str, dependencies), str(PROJECT / 'sim/address_partition_tb.sv')]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=30)

    def test_baseline_and_partitions(self):
        for split_bits in (8, 12):
            for variant in ('positive', 'baseline'):
                with self.subTest(split_bits=split_bits, variant=variant):
                    result = self.simulate(split_bits, variant)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('PASS address_partition checks=30384', result.stdout)
                    print(f'PASS address partition boundary={split_bits} variant={variant} cases=30384')

    def test_functional_mutations(self):
        for split_bits in (8, 12):
            for variant in ('lost_carry', 'wrong_carry_bit', 'wrong_high_carry', 'cleared_address_low', 'lost_immediate_high'):
                with self.subTest(split_bits=split_bits, variant=variant):
                    result = self.simulate(split_bits, variant)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('FAIL address_partition', result.stdout + result.stderr)
                    print(f'PASS address partition boundary={split_bits} rejects={variant}')


if __name__ == '__main__':
    unittest.main()
