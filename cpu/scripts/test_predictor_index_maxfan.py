from hashlib import sha256
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_btb_history_width import vectors

PROJECT=Path(__file__).resolve().parents[1]
CORE=PROJECT/'experiments/predictor_index_maxfan/rv32_btb.sv'
PARENT=PROJECT/'build/raw-pair-retime-stage/rtl/rv32_btb.sv'
BEFORE="    wire [INDEX_BITS-1:0] fetch_index=fetch_pc[INDEX_BITS+1:2] ^"
AFTER="    (* syn_maxfan=24 *) wire [INDEX_BITS-1:0] fetch_index=fetch_pc[INDEX_BITS+1:2] ^"


class PredictorIndexMaxfanTests(unittest.TestCase):
    def simulate(self, source, history_bits, counter_bits, index_bits=8, address_bits=16, hashed=1, variant="positive"):
        mutations = {
            "wrong_training_bank": ("history[update_index]==PATTERN_INDEX", "history[update_index]!=PATTERN_INDEX"),
            "train_all_banks": ("history[update_index]==PATTERN_INDEX", "1'b1"),
            "frozen_history": ("(history[update_index] << 1) | {{(HISTORY_BITS-1){1'b0}},update_taken}", "history[update_index]"),
            "reversed_history": ("history[update_index] << 1", "history[update_index] >> 1"),
            "missing_invalidate": ("end else if (invalidate) begin\n            valid<=0;", "end else if (invalidate) begin\n            valid<=valid;"),
            "out_of_range_training": ("(update_pc >> ADDRESS_BITS)==0 &&", ""),
            "out_of_range_target": ("(update_target >> ADDRESS_BITS)==0 &&", ""),
            "wrong_initial_bias": ("update_taken ? WEAK_TAKEN : WEAK_NOT_TAKEN", "update_taken ? WEAK_NOT_TAKEN : WEAK_TAKEN"),
            "unconditional_history": ("else if (update_conditional)\n", "else\n"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="btb-history-width-") as directory:
            work = Path(directory)
            rtl = work / "rv32_btb.sv"
            rtl.write_text(source, encoding="utf-8")
            rows = vectors(index_bits, address_bits, hashed, history_bits, counter_bits)
            data = work / "vectors.txt"
            data.write_text("\n".join(rows) + "\n", encoding="ascii")
            image = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "btb_history_width_tb",
                                       f"-Pbtb_history_width_tb.INDEX_BITS={index_bits}",
                                       f"-Pbtb_history_width_tb.ADDRESS_BITS={address_bits}",
                                       f"-Pbtb_history_width_tb.HASH_INDEX={hashed}",
                                       f"-Pbtb_history_width_tb.HISTORY_BITS={history_bits}",
                                       f"-Pbtb_history_width_tb.COUNTER_BITS={counter_bits}",
                                       "-o", str(image), str(rtl), str(PROJECT / "sim/btb_history_width_tb.sv")],
                                      text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(image), "+vectors=" + str(data)], text=True, capture_output=True, timeout=30)
            return result, len(rows)


    def test_only_verified_attribute_changes(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'826FE9F54C9460492FF6AE4E0A0BCF8C875E18AC4ED816203C9EEF7E2276D1C4')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),'BBB08D9A074D31CF846B26B1BCF4456C991AFA03068A09EF4B96BEC46823F2DB')
        source=CORE.read_text()
        self.assertEqual(source.count(AFTER),1)
        self.assertEqual(source.replace(AFTER,BEFORE),PARENT.read_text())
        self.assertEqual(CORE.read_bytes(),(PROJECT/'build/predictor-index-maxfan-stage/rtl/rv32_btb.sv').read_bytes())

    def test_independent_model_paired(self):
        checks=0
        cases=((8,16,1,3,2),(8,16,0,3,2),(8,32,1,3,2),(6,16,1,2,2),(4,32,0,1,1),(1,16,1,1,2))
        for index,address,hashed,history,counter in cases:
            outcomes=[]
            for source in (PARENT.read_text(),CORE.read_text()):
                result,count=self.simulate(source,history,counter,index,address,hashed)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(f'PASS local_history vectors={count}',result.stdout)
                checks+=count
                outcomes.append(result.stdout)
            self.assertEqual(outcomes[0],outcomes[1])
        print(f'PASS predictor independent model pairs=6 runs=12 vectors={checks}')

    def test_actual_predictor_four_state_pair(self):
        with tempfile.TemporaryDirectory(prefix='predictor-index-pair-') as temporary:
            directory=Path(temporary)
            design=directory/'design.sv'
            self.assertEqual(PARENT.read_text().count('module rv32_btb #('),1)
            design.write_text(PARENT.read_text().replace('module rv32_btb #(','module predictor_parent #(')+'\n'+CORE.read_text())
            image=directory/'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','predictor_index_maxfan_tb','-o',str(image),str(design),str(PROJECT/'sim/predictor_index_maxfan_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            result=subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS predictor index pair cycles=32768 resets=17',result.stdout)
            print(result.stdout.strip())

    def test_actual_runtime_mutants(self):
        for variant in ('wrong_training_bank','train_all_banks','frozen_history','reversed_history','missing_invalidate','out_of_range_training','out_of_range_target','wrong_initial_bias'):
            with self.subTest(variant=variant):
                result,_=self.simulate(CORE.read_text(),3,2,variant=variant)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL local_history',result.stdout+result.stderr)
                print('PASS predictor runtime rejection: '+variant)


if __name__=='__main__':
    unittest.main(verbosity=2)
