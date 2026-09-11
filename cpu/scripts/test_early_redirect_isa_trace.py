from pathlib import Path
import tempfile
import unittest

from early_redirect_isa_trace import verify_pair


class EarlyRedirectIsaTraceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='early-redirect-terminal-trace-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.current = self.root / 'current'
        self.previous = self.root / 'previous'
        self.current.mkdir()
        self.previous.mkdir()
        self.work = ['R 00000000 00500093 1 1 00000005','R 00000004 10000f37 1 30 10000000','R 00000008 00100f93 1 31 00000001','R 0000000c 01ff2023 0 0 10000000']
        self.loop = 'R 00000010 0000006f 0 0 00000014'
        self.entry = dict(name='case',configuration='p0_c1_s1',retired=7)
        self.reference = dict(self.entry,retired=5)
        for folder,repeats in ((self.current,3),(self.previous,1)):
            (folder / 'case_p0_c1_s1.trace').write_text('\n'.join(self.work+[self.loop]*repeats)+'\n',encoding='utf-8')
            (folder / 'case_p0_c1_s1.memory').write_text('@00000000 00000000\n',encoding='utf-8')

    def test_only_verified_terminal_iterations_may_differ(self):
        record = verify_pair(self.current,self.previous,self.entry,self.reference)
        self.assertEqual(record['work_retired'],4)
        self.assertEqual(record['parent_terminal_iterations'],1)
        self.assertEqual(record['candidate_terminal_iterations'],3)

    def test_architectural_work_difference_is_rejected(self):
        path = self.current / 'case_p0_c1_s1.trace'
        path.write_text(path.read_text().replace('00000005','00000006'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'architectural work'):
            verify_pair(self.current,self.previous,self.entry,self.reference)

    def test_different_terminal_pc_is_rejected(self):
        path = self.current / 'case_p0_c1_s1.trace'
        path.write_text(path.read_text().replace('R 00000010 0000006f','R 00000020 0000006f'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'same success self-loop'):
            verify_pair(self.current,self.previous,self.entry,self.reference)

    def test_mailbox_address_and_data_are_required(self):
        path = self.current / 'case_p0_c1_s1.trace'
        path.write_text(path.read_text().replace('1 31 00000001','1 31 00000002'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'mailbox address/data'):
            verify_pair(self.current,self.previous,self.entry,self.reference)

    def test_success_store_is_required(self):
        path = self.current / 'case_p0_c1_s1.trace'
        path.write_text(path.read_text().replace('01ff2023','00000013'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'mailbox store'):
            verify_pair(self.current,self.previous,self.entry,self.reference)

    def test_reported_retirement_is_bound_to_trace(self):
        with self.assertRaisesRegex(ValueError,'raw trace length'):
            verify_pair(self.current,self.previous,dict(self.entry,retired=8),self.reference)

    def test_final_memory_difference_is_rejected(self):
        (self.current / 'case_p0_c1_s1.memory').write_text('@00000000 00000001\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'final memory'):
            verify_pair(self.current,self.previous,self.entry,self.reference)


if __name__ == '__main__':
    unittest.main(verbosity=2)
