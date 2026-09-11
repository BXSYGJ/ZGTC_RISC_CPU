import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/late-branch-predicate-stage/rtl/rv32_peripherals.sv'
CANDIDATE = ROOT / 'experiments/timer_byte_compare/rv32_peripherals.sv'
OLD = "    (* syn_keep=1 *) wire timer_upper_equal=timer_value[63:32]==timer_compare[63:32];\n    (* syn_keep=1 *) wire timer_upper_greater=timer_value[63:32]>timer_compare[63:32];\n    (* syn_keep=1 *) wire timer_lower_at_least=timer_value[31:0]>=timer_compare[31:0];\n    assign irq_timer=timer_upper_greater || (timer_upper_equal && timer_lower_at_least);"
NEW = "    (* syn_keep=1 *) wire [7:0] timer_byte_equal,timer_byte_greater;\n    genvar timer_byte;\n    generate for(timer_byte=0;timer_byte<8;timer_byte=timer_byte+1) begin: timer_byte_compare\n        assign timer_byte_equal[timer_byte]=timer_value[timer_byte*8+:8]==timer_compare[timer_byte*8+:8];\n        assign timer_byte_greater[timer_byte]=timer_value[timer_byte*8+:8]>timer_compare[timer_byte*8+:8];\n    end endgenerate\n    (* syn_keep=1 *) wire timer_upper_equal=&timer_byte_equal[7:4];\n    (* syn_keep=1 *) wire timer_upper_greater=timer_byte_greater[7] ||\n        (timer_byte_equal[7] && timer_byte_greater[6]) ||\n        (&timer_byte_equal[7:6] && timer_byte_greater[5]) ||\n        (&timer_byte_equal[7:5] && timer_byte_greater[4]);\n    (* syn_keep=1 *) wire timer_lower_at_least=timer_byte_greater[3] ||\n        (timer_byte_equal[3] && timer_byte_greater[2]) ||\n        (&timer_byte_equal[3:2] && timer_byte_greater[1]) ||\n        (&timer_byte_equal[3:1] && timer_byte_greater[0]) || (&timer_byte_equal[3:0]);\n    assign irq_timer=timer_upper_greater || (timer_upper_equal && timer_lower_at_least);"


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
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), '8C46872D243E7AA61B379FED21D85893C45F5466B1E8CC04C8870D239AA83F75')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(), 'D0FD9F51FD4A068A19E7C360CAFE9FA1F838A1864CD76D4188C007DD0761571E')
        self.assertEqual(before.count(OLD),1)
        self.assertEqual(after,before.replace(OLD,NEW))
        for relative in ('rtl/rv32_uart.sv','rtl/rv32_fifo.sv','sim/peripherals_tb.sv'):
            self.assertEqual((ROOT / relative).read_bytes(),(ROOT / 'build/late-branch-predicate-stage' / relative).read_bytes())

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
            ("lost_equality"," || (&timer_byte_equal[3:0])",""),
            ("reverse_byte","timer_value[timer_byte*8+:8]>timer_compare[timer_byte*8+:8]","timer_value[timer_byte*8+:8]<timer_compare[timer_byte*8+:8]"),
            ("signed_byte","timer_value[timer_byte*8+:8]>timer_compare[timer_byte*8+:8]","$signed(timer_value[timer_byte*8+:8])>$signed(timer_compare[timer_byte*8+:8])"),
            ("lost_upper_guard","timer_upper_equal && timer_lower_at_least","timer_lower_at_least"),
            ("wrong_upper_equal","&timer_byte_equal[7:4]","&timer_byte_equal[7:5]"),
            ("lost_byte4_prefix","&timer_byte_equal[7:5] && timer_byte_greater[4]","timer_byte_greater[4]"),
            ("wrong_low_byte","&timer_byte_equal[3:1] && timer_byte_greater[0]","&timer_byte_equal[3:1] && timer_byte_greater[1]"),
            ("wrong_low_equal","(&timer_byte_equal[3:0])","(&timer_byte_equal[3:1])"),
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
