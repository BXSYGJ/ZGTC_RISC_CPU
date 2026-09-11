import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT_STAGE = ROOT / 'build/cache-error-retime-stage'
PARENT = PARENT_STAGE / 'rtl/rv32_memory_system.sv'
CANDIDATE = ROOT / 'experiments/mmio_shadow_accept/rv32_memory_system.sv'


class ShadowAcceptTests(unittest.TestCase):
    def simulate(self, source, top, parameters):
        with tempfile.TemporaryDirectory(prefix='mmio-shadow-') as temporary:
            directory = Path(temporary)
            candidate = directory / 'rv32_memory_system.sv'
            reference = directory / 'rv32_memory_system_reference.sv'
            candidate.write_text(source, encoding='utf-8')
            reference.write_text(PARENT.read_text().replace('module rv32_memory_system #(', 'module rv32_memory_system_reference #(', 1), encoding='utf-8')
            dependencies = [PARENT_STAGE / 'rtl' / name for name in ('rv32_cache.sv','rv32_uncached.sv','rv32_burst_arbiter.sv','rv32_burst_ram.sv')]
            image = directory / 'test.vvp'
            command = ['iverilog','-g2012','-s',top,'-o',str(image)]
            command += [f'-P{top}.{name}={value}' for name,value in parameters.items()]
            command += [str(candidate),str(reference),*map(str,dependencies),str(ROOT / 'sim' / (top+'.sv'))]
            compiled = subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=90)

    def test_source_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'2080990BFB20C6D6660EF63235E6C1716ED1DF1D1C4FD626A9B042E1CE86F2DD')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(),'16F7124CD1FDE2D1825827D0A0CB186A7925002B0A135AB83253355AD70119D7')
        self.assertEqual(hashlib.sha256((PARENT_STAGE / 'rtl/rv32_cache.sv').read_bytes()).hexdigest().upper(),'984B45FECD7D5AFF9410638DD0234649F2BCB99198EC2933C761B7D6FD5C4343')
        source = PARENT.read_text()
        source = source.replace('    reg data_active,data_mmio;','    localparam [0:0] SHADOW_MMIO=ENABLE_CACHE!=0 && DATA_OVERLAP!=0 && MEMORY_ADDRESS_BITS<=26;\n    reg data_active,data_mmio;')
        source = source.replace('    assign cache_req_valid[1]=d_req_valid && data_issue && !request_mmio;','    assign cache_req_valid[1]=d_req_valid && data_issue && (SHADOW_MMIO!=0 || !request_mmio);')
        source = source.replace('    assign cache_rsp_ready[1]=data_active && !data_mmio && d_rsp_ready;','    assign cache_rsp_ready[1]=(SHADOW_MMIO!=0 && data_mmio) || (data_active && !data_mmio && d_rsp_ready);')
        self.assertTrue(source.endswith('\n\n'))
        self.assertEqual(source[:-1],CANDIDATE.read_text())

    def test_protocol_matrix(self):
        matrix = []
        for memory,sets,instructions in ((8,2,3),(14,6,9)):
            for cache in (0,1):
                for overlap in (0,1):
                    for latency in (0,1,3):
                        for wait in (0,3):
                            matrix.append(dict(MEMORY_BITS=memory,DATA_SETS=sets,INSTRUCTION_SETS=instructions,ENABLE_CACHE=cache,DATA_OVERLAP=overlap,MMIO_LATENCY=latency,MMIO_WAIT=wait))
        for read,write in ((0,0),(0,1),(1,0)):
            for latency in (0,1):
                for wait in (0,3):
                    matrix.append(dict(MEMORY_BITS=14,DATA_SETS=6,INSTRUCTION_SETS=9,ENABLE_CACHE=1,DATA_OVERLAP=1,FAST_READ=read,FAST_WRITE=write,MMIO_LATENCY=latency,MMIO_WAIT=wait))
        for parameters in matrix:
            with self.subTest(parameters=parameters):
                result = self.simulate(CANDIDATE.read_text(),'mmio_shadow_tb',parameters)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('PASS mmio_shadow checks=',result.stdout)
                self.assertIn('requests=240 mmio=120 writes=60',result.stdout)
                print('PASS shadow matrix '+str(parameters)+' '+result.stdout.strip(),flush=True)

    def test_existing_overlap_pairs(self):
        for read in (0,1):
            for write in (0,1):
                for instruction_sets in (0,3):
                    for stall in (0,3,7):
                        parameters = dict(DATA_OVERLAP=1,FAST_DCACHE_READ=read,FAST_DCACHE_WRITE=write,ICACHE_SET_BITS=instruction_sets,MMIO_STALL_CYCLES=stall)
                        with self.subTest(parameters=parameters):
                            outputs = []
                            for path in (PARENT,CANDIDATE):
                                result = self.simulate(path.read_text(),'memory_overlap_tb',parameters)
                                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                                self.assertIn('handovers=4',result.stdout)
                                outputs.append(result.stdout)
                            self.assertEqual(outputs[0],outputs[1])
                            print('PASS shadow existing overlap pair '+str(parameters),flush=True)

    def test_runtime_mutants(self):
        source = CANDIDATE.read_text()
        mutations = (
            ('truncate_shadow_address','cache_req_address[1]=d_req_address;',"cache_req_address[1]={4'b0,d_req_address[27:0]};"),
            ('drain_real_response','(SHADOW_MMIO!=0 && data_mmio)','(SHADOW_MMIO!=0)'),
            ('leak_shadow_response','data_mmio ? mmio_rsp_valid : cache_rsp_valid[1]','data_mmio ? cache_rsp_valid[1] : cache_rsp_valid[1]'),
            ('lose_owner','data_mmio<=request_mmio;',"data_mmio<=1'b0;"),
            ('truncate_mmio_payload','mmio_request_address<=d_req_address;',"mmio_request_address<={4'b0,d_req_address[27:0]};"),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result = self.simulate(source.replace(before,after),'mmio_shadow_tb',dict(MMIO_LATENCY=0,MMIO_WAIT=0))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL mmio_shadow',result.stdout+result.stderr)
                self.assertNotIn('watchdog',result.stdout.lower()+result.stderr.lower())
                print('PASS shadow runtime mutant rejected: '+name,flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
