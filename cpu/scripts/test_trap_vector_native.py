from pathlib import Path
import unittest
from trap_vector_native import inspect_trap_vector_boundary

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT / 'build/early-compare-byte-stage/build/pds/20260908-115302-6d4916e9/synthesize/pds_soc_top_syn.vm'
CANDIDATE=ROOT / 'build/trap-vector-boundary-stage/build/pds/20260908-121344-e7d2a88a/synthesize/pds_soc_top_syn.vm'


class NativeBoundaryTests(unittest.TestCase):
    def test_actual_parent_and_candidate(self):
        with self.assertRaisesRegex(ValueError,'Trap-vector carry output boundary is not complete'):
            inspect_trap_vector_boundary(PARENT.read_text())
        report=inspect_trap_vector_boundary(CANDIDATE.read_text())
        self.assertEqual(report['sum_bits'],30)
        self.assertEqual(report['constant_low_bits'],2)
        self.assertTrue(report['redirect_selection_excluded'])
        print('PASS native trap boundary: actual parent rejected, candidate isolated')

    def test_native_mutations(self):
        source=CANDIDATE.read_text()
        mutations=(
            ('lost_sum_bit','.Z (trap_target[17])','.Z (lost_sum_bit)','Trap-vector carry output boundary is not complete'),
            ('redirect_recoupled','.I0 (mtvec[6])','.I0 (early_taken)','Trap-vector carry depends on redirect selection'),
            ('carry_disconnected','.CIN (_N1002)','.CIN (1\'b0)','Trap-vector carry chain is broken'),
            ('low_bit_disconnected','.Z (trap_target[0])','.Z (lost_low_bit)','Trap-vector low alignment boundary is incomplete'),
        )
        for name,before,after,reason in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                with self.assertRaisesRegex(ValueError,reason):
                    inspect_trap_vector_boundary(source.replace(before,after))
                print('PASS native boundary rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
