import hashlib
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'experiments/next_pc_enable_reduce/rv32_core.sv'
PARENT = ROOT / 'experiments/fetch_space_reduce/rv32_core.sv'
BENCH = ROOT / 'sim/next_pc_enable_reduce_tb.sv'
CORE_HASH = "79D70BDD0E9DAD5AC894799D30B9A5164D989C29B64D1D5B759992749D692B95"
PARENT_HASH = '9E0479973C30F7C962ACC46CCEA06C96E8750CA630C43AEBA26EA3FB06CBFB76'
OLD_ENABLE = "    wire fetch_complete=i_rsp_valid && i_rsp_ready;"
NEW_ENABLE = "    (* syn_keep=1 *) wire next_pc_sequential_write=!frontend_barrier && (!fetch_active || (i_rsp_valid && fetch_sent && fetch_accept_space));\n    wire next_pc_write=frontend_flush || next_pc_sequential_write;\n    wire fetch_complete=i_rsp_valid && i_rsp_ready;"
OLD_STEP = "                next_pc<=(ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken) ? predicted_target : next_pc+32'd4;\n"
OLD_REDIRECT = "                next_pc<=redirect_pc; if_valid<=0; id_valid<=0; ex_valid<=0;"
NEW_REDIRECT = "                if_valid<=0; id_valid<=0; ex_valid<=0;"
OLD_END = "            if(frontend_barrier) begin"
NEW_END = "            if(next_pc_write)\n                next_pc<=frontend_flush ? redirect_pc : ((ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken) ? predicted_target : next_pc+32'd4);\n            if(frontend_barrier) begin"

def wrapper(source, name):
    declarations=[]
    for marker in ('wire fetch_accept_space=', 'wire fetch_complete=', 'assign i_rsp_ready='):
        matches=[line.strip() for line in source.splitlines() if marker in line]
        if len(matches)!=1:
            raise ValueError('Ambiguous actual fetch control: '+marker)
        declarations.extend(matches)
    if 'wire next_pc_write=' in source:
        declarations.extend(line.strip() for line in source.splitlines() if 'wire next_pc_sequential_write=' in line or 'wire next_pc_write=' in line)
        update=re.findall(r'            if\(next_pc_write\)\n                next_pc<=[^\n]+;',source)
        if len(update)!=1:
            raise ValueError('Missing actual unified PC write')
        transition=update[0]
    else:
        launch=re.findall(r'            if\(\(!fetch_active \|\| fetch_complete\)[^\n]+ begin',source)
        sequential=re.findall(r"                next_pc<=\(ENABLE_PREDICTOR[^\n]+;",source)
        redirect=re.findall(r'                next_pc<=redirect_pc;',source)
        if len(launch)!=1 or len(sequential)!=1 or len(redirect)!=1:
            raise ValueError('Missing actual original PC writes')
        transition=launch[0]+'\n'+sequential[0]+'\n            end\n            if(frontend_flush) begin\n'+redirect[0]+'\n            end'
    return '\n'.join([
        'module '+name+' #(parameter integer ENABLE_PREDICTOR=1)(input wire clk,rst_n,',
        'input wire fetch_active,fetch_sent,fetch_discard,if_valid,id_valid,ex_valid,ex_fire,i_rsp_valid,',
        'input wire frontend_flush,frontend_barrier,prediction_hit,predicted_taken,',
        'input wire [31:0] predicted_target,redirect_pc,output reg [31:0] next_pc);',
        'wire i_rsp_ready;',*declarations,
        "always @(posedge clk or negedge rst_n) begin if(!rst_n) next_pc<=32'hfffffffc; else begin",
        transition,'end end','endmodule',''])


class NextPcEnableTests(unittest.TestCase):
    def run_variant(self, source, predictor, accepted):
        with tempfile.TemporaryDirectory(prefix='next-pc-enable-') as temporary:
            directory=Path(temporary)
            control=directory / 'control.sv'
            image=directory / 'test.vvp'
            control.write_text(wrapper(PARENT.read_text(),'original_control')+wrapper(source,'candidate_control'),encoding='utf-8')
            compilation=subprocess.run(['iverilog','-g2012','-Wall','-s','next_pc_enable_reduce_tb',f'-Pnext_pc_enable_reduce_tb.ENABLE_PREDICTOR={predictor}','-o',str(image),str(control),str(BENCH)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compilation.returncode,0,compilation.stdout+compilation.stderr)
            result=subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=60)
            if accepted:
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(f'PASS next_pc_enable_reduce checks=69632 resets=65 predictor={predictor}',result.stdout)
            else:
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL next_pc_enable_reduce',result.stdout)
            return result.stdout

    def test_exact_source_delta(self):
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(),CORE_HASH)
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),PARENT_HASH)
        original=CORE.read_text()
        self.assertEqual(original.count(NEW_ENABLE),1)
        self.assertEqual(original.count(NEW_END),1)
        original=original.replace(NEW_ENABLE,OLD_ENABLE).replace(NEW_END,OLD_END)
        redirect_anchor='            if(frontend_flush) begin\n'+NEW_REDIRECT
        self.assertEqual(original.count(redirect_anchor),1)
        original=original.replace(redirect_anchor,'            if(frontend_flush) begin\n'+OLD_REDIRECT)
        anchor="                fetch_prediction<=(ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken) ? predicted_target : next_pc+32'd4;\n"
        self.assertEqual(original.count(anchor),1)
        original=original.replace(anchor,anchor+OLD_STEP)
        self.assertEqual(original,PARENT.read_text())

    def test_actual_sequential_control(self):
        for predictor in (0,1):
            with self.subTest(predictor=predictor):
                print(self.run_variant(CORE.read_text(),predictor,True).strip())

    def test_runtime_mutants(self):
        original=CORE.read_text()
        for predictor in (0,1):
            self.run_variant(original,predictor,True)
        mutations=(
            ('lose_redirect_write','wire next_pc_write=frontend_flush || next_pc_sequential_write;','wire next_pc_write=next_pc_sequential_write;',1),
            ('invert_redirect_priority','next_pc<=frontend_flush ? redirect_pc :','next_pc<=!frontend_flush ? redirect_pc :',1),
            ('ignore_barrier','wire next_pc_sequential_write=!frontend_barrier &&','wire next_pc_sequential_write=',1),
            ('ignore_idle','(!fetch_active || (i_rsp_valid','(fetch_active || (i_rsp_valid',1),
            ('accept_unsolicited_response','i_rsp_valid && fetch_sent && fetch_accept_space','i_rsp_valid && fetch_accept_space',1),
            ('ignore_capacity','i_rsp_valid && fetch_sent && fetch_accept_space','i_rsp_valid && fetch_sent',1),
            ('wrong_increment'," : next_pc+32'd4);"," : next_pc+32'd8);",1),
            ('ignore_prediction_hit','ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken','ENABLE_PREDICTOR!=0 && predicted_taken',1),
            ('ignore_prediction_taken','ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken','ENABLE_PREDICTOR!=0 && prediction_hit',1),
            ('ignore_predictor_disable','ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken','prediction_hit && predicted_taken',0),
        )
        for name,before,after,predictor in mutations:
            with self.subTest(name=name):
                self.assertIn(before,original)
                self.run_variant(original.replace(before,after),predictor,False)
                print('PASS next PC enable runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
