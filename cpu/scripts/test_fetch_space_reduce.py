import hashlib
from itertools import product
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_irq_late_control import wrapper as control_wrapper

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT / 'experiments/irq_control_merge/rv32_core.sv'
CORE=ROOT / 'experiments/fetch_space_reduce/rv32_core.sv'
OLD_OVERLAP="    wire fetch_overlap=FETCH_OVERLAP!=0 && fetch_complete && !frontend_flush && !frontend_barrier;"
NEW_OVERLAP="    (* syn_keep=1 *) wire fetch_accept_space=!if_valid || !id_valid || !ex_valid || ex_fire || fetch_discard;\n    wire fetch_overlap=FETCH_OVERLAP!=0 && i_rsp_valid && fetch_active && fetch_sent && fetch_accept_space && !frontend_flush && !frontend_barrier;"
OLD_READY="    assign i_rsp_ready=fetch_active && fetch_sent && (!if_valid || if_fire || fetch_discard || frontend_flush || frontend_barrier);"
NEW_READY="    assign i_rsp_ready=fetch_active && fetch_sent && (fetch_accept_space || frontend_flush || frontend_barrier);"


def wrapper(source,name):
    probe=control_wrapper(source,name)
    probe=probe.replace('LOAD_USE_BUBBLE=1,ENABLE_M=1','LOAD_USE_BUBBLE=1,ENABLE_M=1,FETCH_OVERLAP=1')
    probe=probe.replace('output [17:0] witness','input fetch_active,fetch_sent,fetch_discard,i_rsp_valid,i_req_ready,output [22:0] witness')
    extra='wire i_req_valid,i_rsp_ready;'+chr(10)
    for marker in ('    (* syn_keep=1 *) wire fetch_accept_space=','    wire fetch_complete=','    wire fetch_overlap=','    assign i_req_valid=','    assign i_rsp_ready='):
        if marker in source:
            begin=source.index(marker)
            extra+=source[begin:source.index(';',begin)+1]+chr(10)
    extra+='wire request_accepted=i_req_valid && i_req_ready;'+chr(10)
    return probe.replace('assign witness={',extra+'assign witness={request_accepted,i_req_valid,i_rsp_ready,fetch_overlap,fetch_complete,')


class FetchSpaceReductionTests(unittest.TestCase):
    def run_variant(self,candidate,bubble=1,overlap=1):
        with tempfile.TemporaryDirectory(prefix='fetch-space-reduce-') as temporary:
            directory=Path(temporary)
            source=directory / 'probe.sv'
            source.write_text(wrapper(PARENT.read_text(),'original_control')+wrapper(candidate,'candidate_control'))
            image=directory / 'test.vvp'
            result=subprocess.run(['iverilog','-g2012','-s','fetch_space_reduce_tb',f'-Pfetch_space_reduce_tb.LOAD_USE_BUBBLE={bubble}',f'-Pfetch_space_reduce_tb.FETCH_OVERLAP={overlap}','-o',str(image),str(source),str(ROOT / 'sim/fetch_space_reduce_tb.sv')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=240)

    def test_exact_source_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'A0875E5CA7A364992DE7764C2A130AB7FD55B500A5721CBA4CBE50A001D3DA7F')
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(),'9E0479973C30F7C962ACC46CCEA06C96E8750CA630C43AEBA26EA3FB06CBFB76')
        source=CORE.read_text()
        self.assertEqual(source.count(NEW_OVERLAP),1)
        self.assertEqual(source.count(NEW_READY),1)
        self.assertEqual(source.replace(NEW_OVERLAP,OLD_OVERLAP).replace(NEW_READY,OLD_READY),PARENT.read_text())

    def test_boolean_reduction_exhaustive(self):
        checks=0
        for if_valid,id_valid,ex_valid,ex_fire,discard,flush,barrier,active,sent,response,overlap,request_ready in product((False,True),repeat=12):
            ex_ready=not ex_valid or ex_fire
            id_fire=id_valid and ex_ready and not flush and not barrier
            id_ready=not id_valid or id_fire
            if_fire=if_valid and id_ready and not flush and not barrier
            old_ready=active and sent and (not if_valid or if_fire or discard or flush or barrier)
            old_complete=response and old_ready
            old_overlap=overlap and old_complete and not flush and not barrier
            old_request=active and (not sent or old_overlap)
            space=not if_valid or not id_valid or not ex_valid or ex_fire or discard
            new_ready=active and sent and (space or flush or barrier)
            new_complete=response and new_ready
            new_overlap=overlap and response and active and sent and space and not flush and not barrier
            new_request=active and (not sent or new_overlap)
            self.assertEqual((old_ready,old_complete,old_overlap,old_request,old_request and request_ready),(new_ready,new_complete,new_overlap,new_request,new_request and request_ready))
            checks+=1
        self.assertEqual(checks,4096)
        print('PASS exhaustive fetch readiness reduction cases=4096')

    def test_actual_control_matrix(self):
        for bubble in (0,1):
            for overlap in (0,1):
                result=self.run_variant(CORE.read_text(),bubble,overlap)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(f'PASS fetch_space_reduce checks=1114112 bubble={bubble} overlap={overlap}',result.stdout)
                print(result.stdout.strip())

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        good=self.run_variant(source)
        self.assertEqual(good.returncode,0,good.stdout+good.stderr)
        mutations=(
            ('ignore_empty_if','fetch_accept_space=!if_valid || !id_valid','fetch_accept_space=!id_valid'),
            ('ignore_empty_id','!if_valid || !id_valid || !ex_valid','!if_valid || !ex_valid'),
            ('ignore_empty_ex','!id_valid || !ex_valid || ex_fire','!id_valid || ex_fire'),
            ('ignore_ex_advance','!ex_valid || ex_fire || fetch_discard','!ex_valid || fetch_discard'),
            ('ignore_discard_space','|| ex_fire || fetch_discard;','|| ex_fire;'),
            ('overlap_without_pending','i_rsp_valid && fetch_active && fetch_sent && fetch_accept_space','i_rsp_valid && fetch_active && fetch_accept_space'),
            ('overlap_during_flush','fetch_accept_space && !frontend_flush && !frontend_barrier;','fetch_accept_space && !frontend_barrier;'),
            ('overlap_during_barrier','fetch_accept_space && !frontend_flush && !frontend_barrier;','fetch_accept_space && !frontend_flush;'),
            ('reject_flush_drain','(fetch_accept_space || frontend_flush || frontend_barrier)','(fetch_accept_space || frontend_barrier)'),
            ('reject_barrier_drain','(fetch_accept_space || frontend_flush || frontend_barrier)','(fetch_accept_space || frontend_flush)'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_variant(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL fetch_space_reduce',result.stdout)
                print('PASS fetch space runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
