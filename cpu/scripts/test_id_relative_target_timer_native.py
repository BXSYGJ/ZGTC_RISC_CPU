import re
import unittest

import test_timer_increment_native as parent
from timer_next_native import inspect_timer_next

NATIVE=parent.ROOT/'build/id-relative-target-stage/build/pds/20260909-022522-f1351b42/synthesize/pds_soc_top_syn.vm'


class CurrentTargetTimerNativeTests(parent.TimerIncrementNativeTests):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.result=inspect_timer_next(self.native,retained_increment=True)
        module=re.findall(r'\bmodule\s+rv32_peripherals\b[\s\S]*?\bendmodule\b',self.native)[0]
        self.blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',module)

    def test_control_resolution_requires_actual_truth_and_wiring(self):
        self.assertEqual(self.result['increment_write_control_truth_inputs'],64)
        renamed=inspect_timer_next(self.native.replace('_N22596_inv','verified_timer_write'),retained_increment=True)
        self.assertIn('verified_timer_write',renamed['decoded_control_cutpoints'])
        block=self.block('Z','_N22596_inv')
        truth=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
        for bit in range(64):
            changed=truth[:bit]+str(1-int(truth[bit]))+truth[bit+1:]
            self.reject('write_control_truth_'+str(bit),block,truth,changed)
        self.reject('write_control_input',block,'.I4 (N36)','.I4 (req_valid)')
        print('PASS current timer control function survives net rename; truth=64')


if __name__=='__main__':
    unittest.main(verbosity=2)
