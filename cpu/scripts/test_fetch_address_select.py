import hashlib
import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / 'build/cache-valid-reuse-stage'
BASE_HASH = 'F02A7F259598E85E5F2B8344ACC21FB1F347E714310B9F3DDADA6C4D70D7183C'


class FetchAddressSelectTests(unittest.TestCase):
    def simulate(self, candidate=True, predictor=1, overlap=1, mutation=None):
        baseline = (BASE / 'rtl/rv32_core.sv').read_bytes()
        self.assertEqual(hashlib.sha256(baseline).hexdigest().upper(), BASE_HASH)
        source = (PROJECT / 'experiments/fetch_address_select/rv32_core.sv').read_text()
        changed = 'assign i_req_address=fetch_sent ? next_pc : fetch_address;'
        original = 'assign i_req_address=fetch_overlap ? next_pc : fetch_address;'
        self.assertEqual(source.count(changed), 1)
        self.assertEqual(source.replace(changed, original), baseline.decode())
        if not candidate:
            source = baseline.decode()
        if mutation is not None:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='fetch-address-select-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            image = work / 'test.vvp'
            dependencies = [BASE / 'rtl' / name for name in (
                'rv32_machine.sv', 'rv32_decode.sv', 'rv32_alu.sv', 'rv32_btb.sv', 'rv32_muldiv.sv')]
            command = ['iverilog', '-g2012', '-s', 'fetch_address_select_tb', '-o', str(image),
                       f'-Pfetch_address_select_tb.PREDICTOR={predictor}',
                       f'-Pfetch_address_select_tb.OVERLAP={overlap}',
                       f'-Pfetch_address_select_tb.RETIMED={int(candidate)}', str(core),
                       *map(str, dependencies), str(PROJECT / 'sim/fetch_address_select_tb.sv')]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=60)

    def test_original_and_candidate_control_space(self):
        for candidate, predictor, overlap in itertools.product((False, True), (0, 1), (0, 1)):
            with self.subTest(candidate=candidate, predictor=predictor, overlap=overlap):
                result = self.simulate(candidate=candidate, predictor=predictor, overlap=overlap)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS fetch_address_select checks=43008', result.stdout)
                print(result.stdout.strip())
        print('PASS eight real-core compilations and 344064 control/address cases')

    def test_compiled_control_and_payload_mutations(self):
        mutations = (
            ('i_req_address=fetch_sent ?', 'i_req_address=!fetch_sent ?'),
            ('i_req_address=fetch_sent ? next_pc : fetch_address;', 'i_req_address=fetch_address;'),
            ('i_req_address=fetch_sent ? next_pc : fetch_address;', 'i_req_address=next_pc;'),
            ('i_req_address=fetch_sent ? next_pc : fetch_address;', "i_req_address=(fetch_sent ? next_pc : fetch_address) & 32'hfffffffc;"),
            ('i_req_address=fetch_sent ?', 'i_req_address=(fetch_sent && i_req_ready) ?'),
            ('assign i_req_valid=fetch_active && (!fetch_sent || fetch_overlap);', 'assign i_req_valid=fetch_active && !fetch_sent;'),
            ('assign i_rsp_ready=fetch_active && fetch_sent &&', 'assign i_rsp_ready=fetch_active &&'),
            ('wire fetch_overlap=FETCH_OVERLAP!=0 && fetch_complete && !mem_flush && !frontend_barrier;',
             'wire fetch_overlap=FETCH_OVERLAP!=0 && fetch_complete;'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL fetch_address_select', result.stdout + result.stderr)
                self.assertNotIn('missing coverage', result.stdout + result.stderr)
                self.assertNotIn('idle payload boundary', result.stdout + result.stderr)
        print('PASS eight compiled control and valid-payload mutations rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
