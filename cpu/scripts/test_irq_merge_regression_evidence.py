import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import irq_merge_regression_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build/irq-control-merge-stage'


class RegressionEvidenceTests(unittest.TestCase):
    def test_actual_raw_evidence(self):
        result=evidence.audit(ROOT)
        self.assertEqual((result['isa_pairs'],result['isa_executions'],result['soc_pairs'],result['soc_executions']),(98,196,4,8))

    def test_metadata_changes_are_rejected(self):
        cases=(
            ('isa_cycles','isa',lambda report:report['records'][0]['result'].__setitem__('cycles',1)),
            ('isa_retired','isa',lambda report:report['records'][0]['result'].__setitem__('retired',1)),
            ('isa_trace','isa',lambda report:report['records'][0]['trace'].__setitem__('trace_sha256','0'*64)),
            ('isa_inventory','isa',lambda report:report['records'].pop()),
            ('isa_source','isa',lambda report:report['source_snapshots']['candidate'].__setitem__('rtl/rv32_core.sv','0'*64)),
            ('isa_parameters','isa',lambda report:report['parameters'].__setitem__('LOAD_USE_BUBBLE',0)),
            ('isa_firmware','isa',lambda report:report['records'][0]['result'].__setitem__('hex_sha256','0'*64)),
            ('isa_rejection','isa',lambda report:report['negative_controls'][0].__setitem__('log_sha256','0'*64)),
            ('soc_inventory','soc',lambda report:report['records'].pop()),
            ('soc_stdout','soc',lambda report:report['records'][0]['candidate'].__setitem__('stdout','PASS fake')),
            ('soc_trace','soc',lambda report:report['records'][0]['candidate'].__setitem__('trace_sha256','0'*64)),
            ('soc_uart_mode','soc',lambda report:report['records'][0].__setitem__('external_uart',1)),
            ('soc_firmware','soc',lambda report:report['records'][0].__setitem__('elf_sha256','0'*64)),
            ('soc_duplicate','soc',lambda report:report['records'].__setitem__(1,copy.deepcopy(report['records'][0]))),
        )
        original=evidence.load_json
        for name,kind,mutate in cases:
            target=STAGE / ('build/isa-target-paired-qualified/results.json' if kind=='isa' else 'build/soc-paired-replay-qualified/results.json')
            observations=[]
            def changed(path):
                report=original(path)
                if Path(path).resolve()==target.resolve():
                    report=copy.deepcopy(report)
                    mutate(report)
                    observations.append(name)
                return report
            with self.subTest(name=name),patch.object(evidence,'load_json',changed):
                with self.assertRaises(ValueError):
                    evidence.audit(ROOT)
            self.assertEqual(observations,[name])
            print('PASS paired evidence metadata rejection: '+name)

    def test_raw_evidence_changes_are_rejected(self):
        isa=evidence.load_json(STAGE / 'build/isa-target-paired-qualified/results.json')
        first=isa['records'][0]['result']
        stem=first['name']+'_'+first['configuration']
        files=(
            STAGE / 'build/isa-target-paired-qualified/candidate' / (stem+'.log'),
            STAGE / 'build/isa-target-paired-qualified/candidate' / (stem+'.memory'),
            STAGE / 'build/soc-paired-replay-qualified/historical_candidate_fault0.trace',
        )
        original=Path.read_bytes
        for target in files:
            observations=[]
            def changed(path):
                content=original(path)
                if path.resolve()==target.resolve():
                    observations.append(target.name)
                    return content+b'corrupted'
                return content
            with self.subTest(name=target.name),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(ValueError):
                    evidence.audit(ROOT)
            self.assertTrue(observations)
            print('PASS paired evidence raw rejection: '+target.name)

    def test_actual_elaboration_marker_is_required(self):
        target=STAGE / 'build/isa-target-paired-qualified/candidate/p0_c1_s6.vvp'
        original=Path.read_text
        observations=[]
        def changed(path,*args,**kwargs):
            content=original(path,*args,**kwargs)
            if path.resolve()==target.resolve():
                self.assertIn('ex_fire_without_irq',content)
                observations.append(True)
                return content.replace('ex_fire_without_irq','removed_predicate')
            return content
        with patch.object(Path,'read_text',changed):
            with self.assertRaisesRegex(ValueError,'Actual ISA elaboration changed'):
                evidence.audit(ROOT)
        self.assertEqual(observations,[True])
        print('PASS paired evidence actual elaboration rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
