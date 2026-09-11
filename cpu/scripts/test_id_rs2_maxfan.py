import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'experiments/wb_byte_retime/rv32_core.sv'
CANDIDATE = ROOT / 'experiments/id_rs2_maxfan/rv32_core.sv'


class IdRs2FanoutTests(unittest.TestCase):
    def test_attribute_only_source_change(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3')
        self.assertEqual(sha256(CANDIDATE.read_bytes()).hexdigest().upper(),'C4EFEFCC737AF6A74D23EF60D8970689804F9241BC8D1B17111AA5B5B37D8D49')
        source = CANDIDATE.read_text()
        before = '    wire [4:0] id_rs1,id_rs2,id_rd;'
        after = '    wire [4:0] id_rs1,id_rd;'+chr(10)+'    (* syn_maxfan=32 *) wire [4:0] id_rs2;'
        self.assertEqual(source.count(after),1)
        self.assertEqual(source.replace(after,before),PARENT.read_text())
        self.assertEqual(source.count('syn_maxfan'),1)

    def test_core_elaboration_both_load_modes(self):
        rtl = ROOT / 'build/wb-byte-retime-stage/rtl'
        sources = [path for path in sorted(rtl.glob('*.sv')) if path.name != 'rv32_core.sv']+[CANDIDATE]
        with tempfile.TemporaryDirectory(prefix='id-rs2-fanout-') as temporary:
            for bubble in (0,1):
                image = Path(temporary) / ('core'+str(bubble)+'.vvp')
                result = subprocess.run(['iverilog','-g2012','-Wall','-s','rv32_core','-Prv32_core.ENABLE_M=1','-Prv32_core.BTB_INDEX_BITS=8',f'-Prv32_core.LOAD_USE_BUBBLE={bubble}','-o',str(image),*map(str,sources)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(str(CANDIDATE),image.read_text())
                print('PASS ID rs2 fanout core elaboration bubble='+str(bubble))


if __name__ == '__main__':
    unittest.main(verbosity=2)
