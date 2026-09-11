import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT / 'build/trap-vector-boundary-stage/rtl/rv32_core.sv'
CANDIDATE=ROOT / 'experiments/word_load_address/rv32_core.sv'
STAGE=ROOT / 'build/word-load-address-stage'
CORE_HASH='734B1D48A89D4A60A32A24154593BBA0AC6D33F226959AA1BD50CCD158C93CFF'


class WordLoadAddressTests(unittest.TestCase):
    def run_bench(self,source,bench,parameters):
        with tempfile.TemporaryDirectory(prefix='word-load-address-') as temporary:
            folder=Path(temporary)
            candidate=folder / 'rv32_core.sv'
            candidate.write_text(source,encoding='utf-8')
            image=folder / 'test.vvp'
            top=bench.stem
            dependencies=[STAGE / 'rtl' / (name+'.sv') for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            compiled=subprocess.run(['iverilog','-g2012','-s',top,*[f'-P{top}.{name}={value}' for name,value in parameters.items()],'-o',str(image),str(candidate),*map(str,dependencies),str(bench)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=300)

    def test_exact_source_and_fixture_delta(self):
        parent=PARENT.read_text(encoding='utf-8')
        candidate=CANDIDATE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'3E431AA8FA2B91A933C2B51163366EA372CCF0B2DD95B1B9F6C0CC3D5D9599AC')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(),CORE_HASH)
        self.assertEqual(CANDIDATE.read_bytes(),(STAGE / 'rtl/rv32_core.sv').read_bytes())
        restored=candidate.replace('    wire load_address_bypass=ex_decode.is_load && mem_load_route[9];','    wire load_address_bypass=ex_decode.is_load;').replace('    wire word_address_forward=load_address_bypass && branch_load_forward && ex_decode.uses_rs1 && ex_rs1==mem_rd;\n    wire [31:0] address_operand=word_address_forward ? d_rsp_data : forwarded_a;','    wire [31:0] address_operand=load_address_bypass ? branch_operand_a : forwarded_a;')
        self.assertEqual(restored,parent)
        original=(ROOT / 'experiments/load_route_predecode/load_use_address_bypass_tb.sv').read_text(encoding='utf-8')
        expected=original.replace('                    expected_address=(access_mode==1 ? branch_a : expected_a)+decode_value.immediate;',"                    expected_address=(LOAD_USE_BUBBLE!=0 && access_mode==1 && memory_valid && memory_load && memory_writes && memory_rd!=0 && !memory_exception && decode_value.uses_rs1 && instruction[19:15]==memory_rd && memory_funct3==2 && memory_address[1:0]==0 ? response_data : expected_a)+decode_value.immediate;").replace('expected_wait=LOAD_USE_BUBBLE!=0 && !(access_mode==1) &&',"expected_wait=LOAD_USE_BUBBLE!=0 && !(access_mode==1 && memory_funct3==2 && memory_address[1:0]==0) &&")
        self.assertEqual((ROOT / 'experiments/word_load_address/load_use_address_bypass_tb.sv').read_text(encoding='utf-8'),expected)

    def test_full_operand_matrix(self):
        for label,path,bench in (
            ('parent',PARENT,ROOT / 'experiments/load_route_predecode/load_use_address_bypass_tb.sv'),
            ('candidate',CANDIDATE,ROOT / 'experiments/word_load_address/load_use_address_bypass_tb.sv'),
        ):
            for bubble in (0,1):
                with self.subTest(label=label,bubble=bubble):
                    result=self.run_bench(path.read_text(encoding='utf-8'),bench,dict(LOAD_USE_BUBBLE=bubble))
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertIn(f'PASS load_use_address_bypass checks=2631680 bubble={bubble}',result.stdout)
                    print(f'PASS word address operand matrix source={label} bubble={bubble}: '+result.stdout.strip())

    def test_sequential_handover(self):
        for bubble in (0,1):
            for early in (0,1):
                with self.subTest(bubble=bubble,early=early):
                    result=self.run_bench(CANDIDATE.read_text(encoding='utf-8'),ROOT / 'sim/word_load_address_tb.sv',dict(LOAD_USE_BUBBLE=bubble,EARLY_D_REQUEST=early))
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertIn(f'PASS word_load_address cases=832 faults=416 bubbles={384 if bubble else 0} bubble={bubble} early={early}',result.stdout)
                    print(result.stdout.strip())

    def test_runtime_mutants(self):
        source=CANDIDATE.read_text(encoding='utf-8')
        control=self.run_bench(source,ROOT / 'sim/word_load_address_tb.sv',dict(LOAD_USE_BUBBLE=1,EARLY_D_REQUEST=1))
        self.assertEqual(control.returncode,0,control.stdout+control.stderr)
        mutations=(
            ('missing_subword_wait','load_address_bypass=ex_decode.is_load && mem_load_route[9]','load_address_bypass=ex_decode.is_load'),
            ('block_word_bypass','load_address_bypass=ex_decode.is_load && mem_load_route[9]',"load_address_bypass=1'b0"),
            ('stale_word_operand','word_address_forward ? d_rsp_data : forwarded_a','word_address_forward ? forwarded_a : forwarded_a'),
            ('subword_reads_new_response','word_address_forward ? d_rsp_data : forwarded_a','ex_decode.is_load ? d_rsp_data : forwarded_a'),
            ('lost_load_route','mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0]);',"mem_load_route<=decode_load_route(3'd0,2'd0);"),
            ('lost_held_execute','if(ex_valid) begin ex_operand_a<=forwarded_a;','if(ex_valid) begin ex_valid<=0; ex_operand_a<=forwarded_a;'),
            ('ignore_old_fault','mem_exception || (mem_access && mem_sent && d_rsp_valid && d_rsp_error)','mem_exception'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_bench(source.replace(before,after),ROOT / 'sim/word_load_address_tb.sv',dict(LOAD_USE_BUBBLE=1,EARLY_D_REQUEST=1))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL word_load_address ',result.stdout)
                self.assertNotIn('coverage',result.stdout)
                print('PASS word address runtime mutant rejected: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
