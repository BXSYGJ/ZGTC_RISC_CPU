import json
import re
import subprocess
import tempfile
from pathlib import Path
import unittest

from load_use_profile import file_hash
from loop_pending_address_native import carry_truth

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/loop-predictor-pending-address-slice-stage/build/pds/20260909-082255-aa21f3d9/synthesize/pds_soc_top_syn.vm'
LIBRARY = Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')


class VendorCarryTests(unittest.TestCase):
    def simulate(self,flip=None):
        self.assertEqual(file_hash(NATIVE),'D23B9910343E3984E4428E8FD0666E361A818C477CCF9EE9F3B3DC0221AF3254')
        module = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',NATIVE.read_text())[0]
        blocks = re.findall(r'GTP_LUT6CARRY\b[^;]*;',module)
        source_blocks = [block for block in blocks if any(name in block for name in (chr(92)+'N81.eq_',chr(92)+'N79.lt_','/* N37_39 */'))]
        initializers = sorted(set(re.findall(r"\.INIT\(64'b([01]{64})\)",chr(10).join(source_blocks))))
        cases = [f'GTP_LUT6CARRY #(.INIT(64{chr(39)}b{initial}),.I5_TO_CARRY("{carry}"),.I5_TO_LUT("{lut}"))' for initial in initializers for carry in ('FALSE','TRUE') for lut in ('FALSE','TRUE')]
        width = len(cases)
        self.assertGreaterEqual(width,20)
        lines = ['module carry_vendor_tb;', 'reg [6:0] inputs;',f'wire [{width-1}:0] actual_carry,actual_lut;']
        for index,block in enumerate(cases):
            lines.append(block+f' dut_{index} (.COUT(actual_carry[{index}]),.Z(actual_lut[{index}]),.CIN(inputs[6]),'+','.join(f'.I{bit}(inputs[{bit}])' for bit in range(6))+');')
        lines.append('initial begin')
        for inputs in range(128):
            expected = [carry_truth(block,inputs) for block in cases]
            if flip is not None:
                expected[0][flip] ^= 1
            carry_value = sum(entry['COUT'] << index for index,entry in enumerate(expected))
            lut_value = sum(entry['Z'] << index for index,entry in enumerate(expected))
            lines.append(f'inputs=7{chr(39)}d{inputs}; #1; if(actual_carry!=={width}{chr(39)}h{carry_value:x} || actual_lut!=={width}{chr(39)}h{lut_value:x}) $fatal(1,"FAIL carry vendor input={inputs}");')
        lines.append(f'$display("PASS carry vendor cases={width} inputs=128 output_checks={width*256}"); $finish; end endmodule')
        with tempfile.TemporaryDirectory(prefix='pending-carry-vendor-') as temporary:
            directory = Path(temporary)
            bench = directory / 'bench.sv'
            image = directory / 'test.vvp'
            bench.write_text(chr(10).join(lines)+chr(10))
            compiled = subprocess.run(['iverilog','-g2012','-s','carry_vendor_tb','-y',str(LIBRARY),'-o',str(image),str(bench)],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=30)

    def test_installed_vendor_model(self):
        result = self.simulate()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS carry vendor',result.stdout)
        hashes = {name:file_hash(LIBRARY / name) for name in ('GTP_LUT6CARRY.v','GTP_LUT5.v','INT_LUTMUX2_UDP.v','INT_LUTMUX4_UDP.v')}
        print('BOUND vendor files='+json.dumps(hashes,sort_keys=True))
        print(result.stdout.strip())

    def test_wrong_output_models_rejected(self):
        positive = self.simulate()
        self.assertEqual(positive.returncode,0,positive.stdout+positive.stderr)
        for output in ('COUT','Z'):
            with self.subTest(output=output):
                result = self.simulate(output)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL carry vendor',result.stdout)
                print('PASS vendor rejection: wrong '+output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
