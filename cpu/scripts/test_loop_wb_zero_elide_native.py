import re
from pathlib import Path
import unittest

from load_use_profile import file_hash
from loop_wb_zero_elide_native import inspect_forwarding

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/loop-pending-wb-zero-elide-stage/build/pds/20260909-074450-e8457dd7/synthesize/pds_soc_top_syn.vm'


class NativeForwardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        print('BOUND native_sha256='+file_hash(NATIVE)+' test_sha256='+file_hash(Path(__file__)))

    def test_actual_cones(self):
        self.assertEqual(file_hash(NATIVE),'C7382C4184ACC890BC187374FB85ECE51AC19CD6C30CD5D022481ABB9BCE79E6')
        result = inspect_forwarding(self.native)
        self.assertEqual((result['match_checks'],result['zero_checks'],result['mux_checks'],result['trace_checks'],result['split_cut_checks']),(8192,128,16000,128,2120))
        print('PASS native forwarding '+str(result))

    def test_actual_netlist_changes_are_rejected(self):
        inspect_forwarding(self.native)
        core = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',self.native)[0]
        blocks = re.findall(r'GTP_LUT[1-6](?:D|CARRY)?\b[^;]*;',core)
        def driver(signal):
            matches = [block for block in blocks if re.search(r'\.Z\s*\('+re.escape(signal)+r'\)',block)]
            self.assertEqual(len(matches),1)
            return matches[0]
        changes = []
        for operand in ('a','b'):
            mux = driver(f'forwarded_{operand}[0]')
            selector = re.findall(r'\.I2\s*\(([^)]+)\)',mux)[0]
            match = driver(selector)
            changes.append(('match_truth_'+operand,match,re.sub(r"(\.INIT\(\d+'b)([01]+)",lambda found:found[1]+('1' if found[2][0]=='0' else '0')+found[2][1:],match)))
            for bit in (0,31):
                block = driver(f'forwarded_{operand}[{bit}]')
                changes.append((f'mux_data_{operand}{bit}',block,block.replace(f'trace_data[{bit}]',f'trace_data[{1 if bit==0 else 30}]')))
            changes.append(('zero_override_'+operand,mux,mux.replace(f'early_source_{operand}[0]',"1'b0")))
        for signal in ('forwarded_a[8]','forwarded_a[9]','forwarded_a[12]','_N36522','_N38929','_N20611'):
            block = driver(signal)
            changes.append(('split_truth_'+signal,block,re.sub(r"(\.INIT\(\d+'b)([01]+)",lambda found:found[1]+''.join('1' if bit=='0' else '0' for bit in found[2]),block)))
        carry = driver('forwarded_a[9]')
        changes.append(('split_carry_mode',carry,carry.replace('.I5_TO_LUT("FALSE")','.I5_TO_LUT("TRUE")')))
        trace = driver('trace_write')
        changes.append(('trace_truth',trace,re.sub(r"(\.INIT\(64'b)([01]+)",lambda found:found[1]+'1'*64,trace)))
        for name,before,after in changes:
            self.assertNotEqual(before,after)
            self.assertEqual(self.native.count(before),1)
            with self.subTest(name=name),self.assertRaises(ValueError):
                inspect_forwarding(self.native.replace(before,after))
            print('PASS native forwarding rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
