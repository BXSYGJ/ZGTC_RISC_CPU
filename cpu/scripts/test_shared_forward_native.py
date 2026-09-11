from pathlib import Path
import re
import unittest

from shared_forward_native import inspect_forward_replication

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/shared-shift-forward-maxfan-stage/build/pds/20260909-000742-3e46f833/synthesize/pds_soc_top_syn.vm'


class ForwardMaxfanNativeTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.records=inspect_forward_replication(self.native)

    def test_actual_replication(self):
        self.assertEqual([record['consumers'] for record in self.records['a']],[7,9,24])
        self.assertEqual([record['consumers'] for record in self.records['b']],[24,15])

    def test_each_replica_rejections(self):
        for copies in self.records.values():
            for record in copies:
                output=record['signal']
                blocks=[block for block in re.findall(r'GTP_LUT6\b[^;]*;',self.native) if re.search(r'\.Z\s*\('+re.escape(output)+r'\)',block)]
                self.assertEqual(len(blocks),1)
                block=blocks[0]
                altered=block.replace(".INIT(64'b0",".INIT(64'b1")
                with self.assertRaisesRegex(ValueError,'truth table changed'):
                    inspect_forward_replication(self.native.replace(block,altered))
                with self.assertRaisesRegex(ValueError,'count or source mapping changed'):
                    inspect_forward_replication(self.native.replace(block,''))
                print('PASS maxfan missing/INIT rejection: '+output)

    def test_overload_and_missing_loads(self):
        output=self.records['a'][0]['signal']
        boundary='endmodule'
        start=self.native.index('module rv32_core')
        end=self.native.index(boundary,start)
        extra=''.join('GTP_LUT1 extra_'+str(index)+' (.I0 ('+output+'), .Z ());\n' for index in range(25))
        with self.assertRaisesRegex(ValueError,'fanout is not within target'):
            inspect_forward_replication(self.native[:end]+extra+self.native[end:])
        altered=re.sub(r'(\.I[0-5]\s*\()'+re.escape(output)+r'(\))',r"\g<1>1'b0\g<2>",self.native)
        with self.assertRaisesRegex(ValueError,'fanout is not within target'):
            inspect_forward_replication(altered)
        print('PASS maxfan overload/missing consumers rejection')

    def test_duplicate_cpu_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_forward_replication(self.native+'\nmodule rv32_core; endmodule\n')


if __name__=='__main__':
    unittest.main(verbosity=2)
