import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/early-compare-byte-stage/rtl/rv32_machine.sv'
CANDIDATE = ROOT / 'experiments/trap_vector_boundary/rv32_machine.sv'
STAGE = ROOT / 'build/trap-vector-boundary-stage'
PARENT_HASH = '2949B5177E75069BEE3597E6025D37E31FBFBDE822997254040A728BE4EB00F9'
CANDIDATE_HASH = '18C05FC7BABCC027CBA1A3F477A8D9631E83A95A7EB7E07E280E5EFAE6D5D674'


class TrapVectorBoundaryTests(unittest.TestCase):
    def run_source(self,source,bench,enable_m):
        with tempfile.TemporaryDirectory(prefix='trap-vector-boundary-') as temporary:
            directory=Path(temporary)
            candidate=directory / 'rv32_machine.sv'
            candidate.write_text(source,encoding='utf-8')
            image=directory / 'test.vvp'
            compile_result=subprocess.run(['iverilog','-g2012','-Wall','-s',bench,f'-P{bench}.ENABLE_M={enable_m}','-o',str(image),str(candidate),str(ROOT / 'sim' / (bench+'.sv'))],capture_output=True,text=True,timeout=60)
            self.assertEqual(compile_result.returncode,0,compile_result.stdout+compile_result.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=120)

    def test_exact_source_delta(self):
        parent=PARENT.read_text(encoding='utf-8')
        candidate=CANDIDATE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),PARENT_HASH)
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(),CANDIDATE_HASH)
        self.assertEqual(CANDIDATE.read_bytes(),(STAGE / 'rtl/rv32_machine.sv').read_bytes())
        original="    assign trap_target={mtvec[31:2],2'b0} + ((mtvec[1:0]==1 && trap_cause[31]) ? {25'b0,trap_cause[4:0],2'b0} : 32'b0);"
        replacement="    (* syn_keep=1 *) wire [31:0] trap_vector_sum={mtvec[31:2],2'b0} + ((mtvec[1:0]==1 && trap_cause[31]) ? {25'b0,trap_cause[4:0],2'b0} : 32'b0);\n    assign trap_target=trap_vector_sum;"
        self.assertEqual(parent.count(original),1)
        self.assertEqual(candidate.count(replacement),1)
        self.assertEqual(candidate.replace(replacement,original),parent)

    def test_paired_vector_and_original_machine(self):
        for bench in ('trap_vector_boundary_tb','machine_tb'):
            for enable_m in (0,1):
                with self.subTest(bench=bench,enable_m=enable_m):
                    outputs=[]
                    for path in (PARENT,CANDIDATE):
                        result=self.run_source(path.read_text(encoding='utf-8'),bench,enable_m)
                        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                        expected='PASS trap_vector_boundary checks=147456 direct=129024 vector=18432 overflow=' if bench=='trap_vector_boundary_tb' else ('PASS machine_m checks=' if enable_m else 'PASS machine checks=')
                        self.assertIn(expected,result.stdout)
                        outputs.append(result.stdout)
                    self.assertEqual(outputs[0],outputs[1])
                    print(f'PASS trap boundary paired bench={bench} m={enable_m}: '+outputs[1].strip())

    def test_runtime_mutations(self):
        source=CANDIDATE.read_text(encoding='utf-8')
        mutations=(
            ('drop_offset',"{25'b0,trap_cause[4:0],2'b0}","32'b0"),
            ('wrong_offset_shift',"{25'b0,trap_cause[4:0],2'b0}","{26'b0,trap_cause[4:0],1'b0}"),
            ('omit_interrupt_guard','mtvec[1:0]==1 && trap_cause[31]','mtvec[1:0]==1'),
            ('omit_vector_mode','mtvec[1:0]==1 && trap_cause[31]','trap_cause[31]'),
            ('truncate_base',"{mtvec[31:2],2'b0}","{16'b0,mtvec[15:2],2'b0}"),
            ('cause_high_bits',"{25'b0,trap_cause[4:0],2'b0}","{24'b0,trap_cause[5:0],2'b0}"),
            ('bypass_sum','assign trap_target=trap_vector_sum;',"assign trap_target={mtvec[31:2],2'b0};"),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_source(source.replace(before,after),'trap_vector_boundary_tb',1)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL trap_vector_boundary target ',result.stdout)
                self.assertNotIn('missing coverage',result.stdout)
                print('PASS trap boundary runtime mutant rejected: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
