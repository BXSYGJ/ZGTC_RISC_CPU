import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from load_use_profile import file_hash
from regfile_storage_native import extract, wrapper, pins
from test_regfile_valid_storage import wrapper as rtl_wrapper

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/regfile-valid-storage-stage/build/pds/20260909-111626-8819e58d/synthesize/pds_soc_top_syn.vm'
VENDOR = Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')


class RegisterStorageNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.cells = extract(cls.native)
        print('BOUND native_sha256='+file_hash(NATIVE)+' test_sha256='+file_hash(Path(__file__))+' checker_sha256='+file_hash(ROOT / 'scripts/regfile_storage_native.py'))

    def simulate(self, cells):
        with tempfile.TemporaryDirectory(prefix='native-regfile-') as directory:
            work = Path(directory)
            source, bench, image = work / 'native.sv', work / 'bench.sv', work / 'native.vvp'
            parent = ROOT / 'experiments/wb_byte_retime/rv32_core.sv'
            source.write_text(rtl_wrapper(parent.read_text(), 'parent_regfile')+chr(10)+wrapper(cells))
            bench_text = (ROOT / 'sim/regfile_valid_storage_tb.sv').read_text()
            binary_substitutions = (("32'hxxxxxxxx", "32'h13371337"), ("32'hzzzzzzzz", "32'ha5a55a5a"), ("32'h12xz34xz", "32'h12345678"), ("32'hzx01xz10", "32'h55aa55aa"), ('data_includes_XZ=1', 'data_includes_XZ=0'))
            for before, after in binary_substitutions:
                self.assertEqual(bench_text.count(before), 1)
                bench_text = bench_text.replace(before, after)
            self.assertEqual(bench_text.count('module regfile_valid_tb;'), 1)
            bench.write_text(bench_text.replace('module regfile_valid_tb;', 'module regfile_valid_tb;'+chr(10)+"    GTP_GRS GRS_INST(.GRS_N(1'b1));"))
            compiled = subprocess.run(['iverilog','-g2012','-s','regfile_valid_tb','-y',str(VENDOR),'-o',str(image),str(source),str(bench)],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            dependencies = sorted(set(Path(name) for name in re.findall(r'"([^"\n]+\.v)"',image.read_text()) if name.startswith(str(VENDOR)+'/')))
            self.assertTrue(dependencies)
            hashes = {name.name:file_hash(name) for name in dependencies}
            result = subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=60)
            return result, hashes

    def test_actual_vendor_cone(self):
        self.assertEqual(file_hash(NATIVE),'2D0013AC01666FE186F26CAC7FF1FC8382CD519BE12B1E0AED4A27FEA7AA2D8B')
        result, hashes = self.simulate(self.cells)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS regfile_valid cycles=25269 checks=75891 resets=73',result.stdout)
        self.assertIn('data_includes_XZ=0',result.stdout)
        self.assertTrue({'GTP_RAM32X2DP.v','GTP_DFF_CE.v','GTP_GRS.v','GTP_LUT5.v','GTP_LUT6D.v','GTP_MUX2LUT7.v','GTP_MUX2LUT8.v'}.issubset(hashes))
        print(result.stdout.strip())
        print('PASS native register cone cells=190 RAM32X2DP=32 validity_DFF=31 feedback_truths=1984')
        for name, digest in hashes.items():
            print('VENDOR '+name+' '+digest)

    def test_runtime_mutations(self):
        positive, hashes = self.simulate(self.cells)
        self.assertEqual(positive.returncode,0,positive.stdout+positive.stderr)
        cases = (
            ('RAM_write_disable', lambda cell:cell.startswith('GTP_RAM32X2DP '), '.WE (trace_write)', ".WE (1'b0)"),
            ('RAM_read_address', lambda cell:cell.startswith('GTP_RAM32X2DP ') and '.RADDR (id_rs1)' in cell, '.RADDR (id_rs1)', '.RADDR (id_rs2)'),
            ('RAM_data_bit', lambda cell:cell.startswith('GTP_RAM32X2DP ') and 'trace_data[0]' in cell, 'trace_data[0]', 'trace_data[1]'),
            ('valid_clear', lambda cell:cell.startswith('GTP_DFF_CE '), '.C ('+chr(92)+'board/soc/N62_0 )', ".C (1'b0)"),
            ('valid_enable', lambda cell:cell.startswith('GTP_DFF_CE '), '.CE (trace_write)', ".CE (1'b0)"),
            ('feedback_truth', lambda cell:pins(cell).get('Z') == 'N1283[1]', None, None),
            ('read_mux_truth', lambda cell:pins(cell).get('Z') == 'id_operand_a[0]', None, None),
        )
        for name, select, before, after in cases:
            cells = list(self.cells)
            index = next(index for index,cell in enumerate(cells) if select(cell))
            if before is None:
                cells[index] = re.sub(r"(\.INIT\((?:32|64)'b)([01]+)",lambda match:match[1]+''.join('0' if bit=='1' else '1' for bit in match[2]),cells[index])
            else:
                self.assertIn(before,cells[index])
                cells[index] = cells[index].replace(before,after)
            self.assertNotEqual(cells[index],self.cells[index])
            with self.subTest(name=name):
                result, hashes = self.simulate(cells)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL regfile_valid',result.stdout+result.stderr)
                print('PASS native register runtime rejection: '+name)

    def test_structural_mutations(self):
        changes = (
            ('missing_write_port','.WADDR (trace_rd)','.WADDR (id_rs1)'),
            ('wrong_read_bank','.RADDR (id_rs1)','.RADDR (id_rs2)'),
            ('clock_change','.WCLK (clk)',".WCLK (1'b0)"),
            ('validity_reset',".INIT(1'b0)",".INIT(1'b1)"),
        )
        for name,before,after in changes:
            selected = next(cell for cell in self.cells if before in cell and (cell.startswith('GTP_DFF_CE ') if name=='validity_reset' else cell.startswith('GTP_RAM32X2DP ')))
            self.assertEqual(self.native.count(selected),1)
            with self.subTest(name=name), self.assertRaises(ValueError):
                extract(self.native.replace(selected,selected.replace(before,after)))
            print('PASS native register structural rejection: '+name)
        ram = next(cell for cell in self.cells if cell.startswith('GTP_RAM32X2DP '))
        with self.assertRaises(ValueError):
            extract(self.native.replace(ram,ram+chr(10)+ram))
        print('PASS native register structural rejection: duplicate_RAM')


if __name__ == '__main__':
    unittest.main(verbosity=2)
