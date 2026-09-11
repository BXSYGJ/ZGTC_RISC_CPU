import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/word-load-address-151200-stage/rtl/rv32_peripherals.sv'
CANDIDATE = ROOT / 'experiments/timer_compare_split/rv32_peripherals.sv'
OLD = "    assign irq_timer=timer_value>=timer_compare;"
NEW = "    (* syn_keep=1 *) wire timer_upper_equal=timer_value[63:32]==timer_compare[63:32];\n    (* syn_keep=1 *) wire timer_upper_greater=timer_value[63:32]>timer_compare[63:32];\n    (* syn_keep=1 *) wire timer_lower_at_least=timer_value[31:0]>=timer_compare[31:0];\n    assign irq_timer=timer_upper_greater || (timer_upper_equal && timer_lower_at_least);"


def run_bench(source, bench, top):
    with tempfile.TemporaryDirectory(prefix='timer-compare-split-') as temporary:
        directory = Path(temporary)
        rtl = directory / 'rv32_peripherals.sv'
        rtl.write_text(source, encoding='utf-8')
        image = directory / 'test.vvp'
        compiled = subprocess.run(['iverilog','-g2012','-s',top,'-o',str(image),str(rtl),str(ROOT / 'rtl/rv32_uart.sv'),str(ROOT / 'rtl/rv32_fifo.sv'),str(bench)], capture_output=True, text=True, timeout=60)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)
        return subprocess.run(['vvp',str(image)], capture_output=True, text=True, timeout=180)


class TimerCompareSplitTests(unittest.TestCase):
    def test_exact_source_delta(self):
        before = PARENT.read_text(encoding='utf-8')
        after = CANDIDATE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), '412D393DD1FB9B5706AC7927F79CF8686C0115CA9754178BD75220A65E133F6E')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(), '8C46872D243E7AA61B379FED21D85893C45F5466B1E8CC04C8870D239AA83F75')
        self.assertEqual(before.count(OLD),1)
        self.assertEqual(after,before.replace(OLD,NEW))
        for relative in ('rtl/rv32_uart.sv','rtl/rv32_fifo.sv','sim/peripherals_tb.sv'):
            self.assertEqual((ROOT / relative).read_bytes(),(ROOT / 'build/word-load-address-151200-stage' / relative).read_bytes())

    def test_original_and_split_comparison_matrix(self):
        for source in (PARENT,CANDIDATE):
            with self.subTest(source=source.name, parent=source==PARENT):
                result = run_bench(source.read_text(encoding='utf-8'),ROOT / 'sim/timer_compare_split_tb.sv','timer_compare_split_tb')
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('PASS timer_compare_split checks=800256',result.stdout)
                print(('PASS original ' if source==PARENT else 'PASS candidate ') + result.stdout.strip())

    def test_unchanged_full_peripheral_transactions(self):
        outputs=[]
        for source in (PARENT,CANDIDATE):
            result=run_bench(source.read_text(encoding='utf-8'),ROOT / 'sim/peripherals_tb.sv','peripherals_tb')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertRegex(result.stdout,r'PASS peripherals checks=[0-9]+ request_waits=[0-9]+')
            outputs.append(result.stdout)
            print(('PASS original ' if source==PARENT else 'PASS candidate ') + result.stdout.strip())
        self.assertEqual(outputs[0],outputs[1])

    def test_actual_runtime_mutants(self):
        text=CANDIDATE.read_text(encoding='utf-8')
        good=run_bench(text,ROOT / 'sim/timer_compare_split_tb.sv','timer_compare_split_tb')
        self.assertEqual(good.returncode,0,good.stdout+good.stderr)
        mutations=(
            ('strict_low','timer_value[31:0]>=timer_compare[31:0]','timer_value[31:0]>timer_compare[31:0]'),
            ('reversed_high','timer_value[63:32]>timer_compare[63:32]','timer_value[63:32]<timer_compare[63:32]'),
            ('reversed_low','timer_value[31:0]>=timer_compare[31:0]','timer_value[31:0]<=timer_compare[31:0]'),
            ('lost_equal_guard','timer_upper_equal && timer_lower_at_least','timer_lower_at_least'),
            ('signed_high','timer_value[63:32]>timer_compare[63:32]','$signed(timer_value[63:32])>$signed(timer_compare[63:32])'),
            ('strict_equal_guard','timer_value[63:32]==timer_compare[63:32]','timer_value[63:32]!=timer_compare[63:32]'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(text.count(before),1)
                result=run_bench(text.replace(before,after),ROOT / 'sim/timer_compare_split_tb.sv','timer_compare_split_tb')
                self.assertNotEqual(result.returncode,0)
                self.assertIn('timer comparison differs',result.stdout+result.stderr)
                print('PASS timer runtime mutant rejected: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
