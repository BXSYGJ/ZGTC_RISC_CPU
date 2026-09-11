import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT / 'experiments/late_branch_predicate/rv32_core.sv'
CORE=ROOT / 'experiments/irq_control_merge/rv32_core.sv'


def wrapper(source,name):
    begin=source.index('    wire mem_access=')
    end=source.index('    wire predicted_taken,',begin)
    block=source[begin:end]
    excluded=('    wire [31:0] trap_target,','    wire csr_illegal,','    wire [31:0] redirect_pc=','    wire muldiv_valid,','    wire [31:0] muldiv_result;','    reg muldiv_started;','    wire fetch_complete=')
    block=''.join(line+chr(10) for line in block.splitlines() if not line.startswith(excluded))
    for signal in ('ex_rs1','early_load_dependency','execute_local_exception','execute_common_exception','early_local_exception','early_exception'):
        marker=('    wire [4:0] ' if signal=='ex_rs1' else '    wire ')+signal+'='
        if marker in source:
            start=source.index(marker)
            block+=source[start:source.index(';',start)+1]+chr(10)
    for original,replacement in (('is_csr','ex_is_csr'),('is_mret','ex_is_mret'),('is_branch','ex_is_branch'),('is_jal','ex_is_jal'),('is_load','ex_is_load'),('uses_rs1','uses_rs1'),('uses_rs2','uses_rs2'),('illegal','ex_illegal')):
        block=block.replace('ex_decode.'+original,replacement)
    ports='input mem_load,mem_store,mem_exception,mem_valid,mem_sent,mem_fence_i,maintenance_ready,d_rsp_valid,d_rsp_error,mem_mret,mem_early_redirect,interrupt_pending,ex_is_csr,ex_is_mret,ex_is_branch,ex_is_jal,ex_is_load,uses_rs1,uses_rs2,ex_valid,mem_writes,wb_valid,muldiv_valid,id_valid,if_valid,ex_error,ex_illegal,early_taken,input [31:0] mem_next_pc,mem_prediction,ex_instruction,ex_pc,ex_prediction,early_next,early_target,input [4:0] mem_rd,input [16:0] mem_load_route,output [17:0] witness'
    outputs='mem_fire,mem_fault,mem_ready,mem_flush,ex_can_fire,ex_fire,ex_redirect,frontend_flush,ex_ready,id_fire,id_ready,if_fire,load_use_wait,frontend_barrier,execute_common_exception,early_exception,early_load_dependency,ex_serial'
    return 'module '+name+' #(parameter integer LOAD_USE_BUBBLE=1,ENABLE_M=1)('+ports+');'+chr(10)+block+'assign witness={'+outputs+'};'+chr(10)+'endmodule'+chr(10)


class IrqLateControlTests(unittest.TestCase):
    def run_variant(self,candidate,bubble):
        with tempfile.TemporaryDirectory(prefix='irq-late-control-') as temporary:
            directory=Path(temporary)
            source=directory / 'probe.sv'
            source.write_text(wrapper(PARENT.read_text(),'original_control')+wrapper(candidate,'candidate_control'))
            image=directory / 'test.vvp'
            result=subprocess.run(['iverilog','-g2012','-s','irq_late_control_tb',f'-Pirq_late_control_tb.LOAD_USE_BUBBLE={bubble}','-o',str(image),str(source),str(ROOT / 'sim/irq_late_control_tb.sv')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)

    def test_pinned_sources_and_exact_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'CE62DD68B477DCD6C752A6FB8BAC3E3397A249AC6EA59E723CB6D14D518F462A')
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(),'A0875E5CA7A364992DE7764C2A130AB7FD55B500A5721CBA4CBE50A001D3DA7F')
        parent=PARENT.read_text()
        source=CORE.read_text()
        control_parent=ROOT / 'experiments/irq_late_control/rv32_core.sv'
        self.assertEqual(hashlib.sha256(control_parent.read_bytes()).hexdigest().upper(),'35744B09CF419EBFDBD68A3F1A6756D8231546C25184EED31F701AB309E63712')
        restored=source.replace('    wire ex_redirect_without_irq=','    (* syn_keep=1 *) wire ex_redirect_without_irq=').replace('    wire id_fire_without_irq=','    (* syn_keep=1 *) wire id_fire_without_irq=')
        self.assertEqual(restored,control_parent.read_text())
        source=source.replace('    wire execute_local_exception=ex_pc[1:0]!=0 || ex_error || ex_decode.illegal;'+chr(10)+'    wire execute_common_exception=interrupt_pending || execute_local_exception;','    wire execute_common_exception=interrupt_pending || ex_pc[1:0]!=0 || ex_error || ex_decode.illegal;')
        source=source.replace('    wire early_local_exception=execute_local_exception || (early_taken && early_target[1:0]!=0);'+chr(10)+'    wire early_exception=interrupt_pending || early_local_exception;','    wire early_exception=execute_common_exception || (early_taken && early_target[1:0]!=0);')
        begin=source.index('    (* syn_keep=1 *) wire ex_fire_without_irq=')
        end=source.index('    wire id_ready=',begin)
        parent_begin=parent.index('    wire ex_fire=')
        parent_end=parent.index('    wire id_ready=',parent_begin)
        self.assertEqual(source[:begin]+parent[parent_begin:parent_end]+source[end:],parent)

    def test_actual_control_matrix(self):
        for bubble in (0,1):
            result=self.run_variant(CORE.read_text(),bubble)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn(f'PASS irq_late_control checks=1114112 bubble={bubble}',result.stdout)
            print(result.stdout.strip())

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        result=self.run_variant(source,1)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        mutations=(
            ('lost_mem_irq_drain','ex_fire_with_irq=ex_valid && !mem_valid && !wb_valid','ex_fire_with_irq=ex_valid && !wb_valid'),
            ('lost_wb_irq_drain','ex_fire_with_irq=ex_valid && !mem_valid && !wb_valid','ex_fire_with_irq=ex_valid && !mem_valid'),
            ('wrong_irq_mux','interrupt_pending ? ex_fire_with_irq : ex_fire_without_irq','interrupt_pending ? ex_fire_without_irq : ex_fire_with_irq'),
            ('redirect_during_irq','ex_redirect=!interrupt_pending && ex_redirect_without_irq','ex_redirect=ex_redirect_without_irq'),
            ('wrong_decode_mux','interrupt_pending ? id_fire_with_irq : id_fire_without_irq','interrupt_pending ? id_fire_without_irq : id_fire_with_irq'),
            ('lost_branch_flush','!mem_flush && !ex_redirect_without_irq && !frontend_barrier','!mem_flush && !frontend_barrier'),
            ('lost_muldiv_wait','(!ex_muldiv || execute_local_exception || muldiv_valid)','(!ex_muldiv || execute_local_exception || !muldiv_valid)'),
            ('lost_csr_serial','!((ex_decode.is_csr || ex_decode.is_mret) && (mem_valid || wb_valid))','!(ex_decode.is_mret && (mem_valid || wb_valid))'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_variant(source.replace(before,after),1)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL irq_late_control',result.stdout)
                print('PASS IRQ late control runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
