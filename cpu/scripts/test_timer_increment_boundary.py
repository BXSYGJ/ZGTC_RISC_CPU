import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/forward-match-retime-stage/rtl/rv32_peripherals.sv'
CORE=ROOT/'experiments/timer_increment_boundary/rv32_peripherals.sv'
CHANGES=[
  [
    "    output wire irq_timer,",
    "    output reg irq_timer,"
  ],
  [
    "    (* syn_keep=1 *) wire timer_upper_equal=timer_value[63:32]==timer_compare[63:32];\n    (* syn_keep=1 *) wire timer_upper_greater=timer_value[63:32]>timer_compare[63:32];\n    (* syn_keep=1 *) wire timer_lower_at_least=timer_value[31:0]>=timer_compare[31:0];\n    assign irq_timer=timer_upper_greater || (timer_upper_equal && timer_lower_at_least);\n",
    "    reg [63:0] timer_value_next,timer_compare_next;\n    always @* begin\n        timer_value_next=timer_value+1'b1;\n        timer_compare_next=timer_compare;\n        if(request_fire && req_write) begin\n            case(req_address)\n                TIME_LOW: timer_value_next={timer_value[63:32],(timer_value[31:0] & ~write_mask) | (req_data & write_mask)};\n                TIME_HIGH: timer_value_next={(timer_value[63:32] & ~write_mask) | (req_data & write_mask),timer_value[31:0]};\n                COMPARE_LOW: timer_compare_next[31:0]=(timer_compare[31:0] & ~write_mask) | (req_data & write_mask);\n                COMPARE_HIGH: timer_compare_next[63:32]=(timer_compare[63:32] & ~write_mask) | (req_data & write_mask);\n                default: begin end\n            endcase\n        end\n    end\n    (* syn_keep=1 *) wire timer_upper_equal=timer_value_next[63:32]==timer_compare_next[63:32];\n    (* syn_keep=1 *) wire timer_upper_greater=timer_value_next[63:32]>timer_compare_next[63:32];\n    (* syn_keep=1 *) wire timer_lower_at_least=timer_value_next[31:0]>=timer_compare_next[31:0];\n    wire timer_interrupt_next=timer_upper_greater || (timer_upper_equal && timer_lower_at_least);\n"
  ],
  [
    "            uart_control<=0; uart_errors<=0; timer_value<=0; timer_compare<=64'hffffffffffffffff; irq_software<=0;",
    "            uart_control<=0; uart_errors<=0; timer_value<=0; timer_compare<=64'hffffffffffffffff; irq_software<=0; irq_timer<=0;"
  ],
  [
    "            timer_value<=timer_value+1'b1;",
    "            timer_value<=timer_value_next; timer_compare<=timer_compare_next; irq_timer<=timer_interrupt_next;"
  ],
  [
    "                        TIME_LOW: timer_value<={timer_value[63:32],(timer_value[31:0] & ~write_mask) | (req_data & write_mask)};\n                        TIME_HIGH: timer_value<={(timer_value[63:32] & ~write_mask) | (req_data & write_mask),timer_value[31:0]};\n                        COMPARE_LOW: timer_compare[31:0]<=(timer_compare[31:0] & ~write_mask) | (req_data & write_mask);\n                        COMPARE_HIGH: timer_compare[63:32]<=(timer_compare[63:32] & ~write_mask) | (req_data & write_mask);",
    "                        TIME_LOW,TIME_HIGH,COMPARE_LOW,COMPARE_HIGH: begin end"
  ],
  [
    "    reg [63:0] timer_value_next,timer_compare_next;",
    "    (* syn_keep=1 *) wire [63:0] timer_incremented=timer_value+1'b1;\n    reg [63:0] timer_value_next,timer_compare_next;"
  ],
  [
    "        timer_value_next=timer_value+1'b1;",
    "        timer_value_next=timer_incremented;"
  ]
]


class TimerIncrementBoundaryTests(unittest.TestCase):
    def run_bench(self,source,paired=True):
        with tempfile.TemporaryDirectory(prefix='timer-irq-next-') as temporary:
            folder=Path(temporary)
            candidate=folder/'candidate.sv'
            candidate.write_text(source)
            inputs=[str(candidate)]
            if paired:
                parent=folder/'parent.sv'
                parent.write_text(PARENT.read_text().replace('module rv32_peripherals #(','module rv32_peripherals_parent #('))
                inputs.append(str(parent))
            for name in ('rv32_uart','rv32_fifo'):
                dependency=ROOT/'build/forward-match-retime-stage/rtl'/(name+'.sv')
                self.assertEqual(dependency.read_bytes(),(ROOT/'rtl'/(name+'.sv')).read_bytes())
                inputs.append(str(dependency))
            top='timer_irq_next_tb' if paired else 'peripherals_tb'
            image=folder/'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s',top,'-o',str(image),*inputs,str(ROOT/'sim'/(top+'.sv'))],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)

    def test_only_preserves_increment_boundary(self):
        parent=ROOT/'experiments/timer_irq_next/rv32_peripherals.sv'
        self.assertEqual(hashlib.sha256(parent.read_bytes()).hexdigest().upper(),'555426210B1380AB8D20EAEF3FB8EE893CA6031356420DAB261C678CC57ADEF6')
        source=CORE.read_text()
        for before,after in reversed(CHANGES[-2:]):
            self.assertEqual(source.count(after),1)
            source=source.replace(after,before)
        self.assertEqual(source,parent.read_text())

    def test_exact_registered_next_state_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'8C46872D243E7AA61B379FED21D85893C45F5466B1E8CC04C8870D239AA83F75')
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(),'B61ED1BC98CA4B6375AA27337FB6C68091FBFEBA156495424D71431A6F4630E6')
        restored=CORE.read_text()
        for before,after in reversed(CHANGES):
            self.assertEqual(restored.count(after),1)
            restored=restored.replace(after,before)
        self.assertEqual(restored,PARENT.read_text())

    def test_actual_cycle_by_cycle_peripheral_equivalence(self):
        result=self.run_bench(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS timer_irq_next cycles=9088 resets=65',result.stdout)
        print(result.stdout.strip())

    def test_unchanged_peripheral_transaction_suite(self):
        outputs=[]
        for source in (PARENT,CORE):
            result=self.run_bench(source.read_text(),False)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS peripherals checks=',result.stdout)
            outputs.append(result.stdout)
            print(result.stdout.strip())
        self.assertEqual(outputs[0],outputs[1])

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        mutations=(
            ('late_irq','irq_timer<=timer_interrupt_next;','irq_timer<=(timer_value[63:32]>timer_compare[63:32]) || ((timer_value[63:32]==timer_compare[63:32]) && timer_value[31:0]>=timer_compare[31:0]);'),
            ('zero_strobe_increments','if(request_fire && req_write) begin','if(request_fire && req_write && |req_strobe) begin'),
            ('accept_without_ready','if(request_fire && req_write) begin','if(req_valid && req_write) begin'),
            ('lost_compare_high','COMPARE_HIGH: timer_compare_next[63:32]=(timer_compare[63:32] & ~write_mask) | (req_data & write_mask);','COMPARE_HIGH: begin end'),
            ('wrong_reset','irq_software<=0; irq_timer<=0;','irq_software<=0; irq_timer<=1;'),
            ('strict_threshold','timer_value_next[31:0]>=timer_compare_next[31:0]','timer_value_next[31:0]>timer_compare_next[31:0]'),
            ('signed_high','timer_value_next[63:32]>timer_compare_next[63:32]','$signed(timer_value_next[63:32])>$signed(timer_compare_next[63:32])'),
            ('lost_wrap',"timer_incremented=timer_value+1'b1;","timer_incremented=timer_value==64'hffffffffffffffff ? timer_value : timer_value+1'b1;"),
            ('high_write_increments_low','TIME_HIGH: timer_value_next={(timer_value[63:32] & ~write_mask) | (req_data & write_mask),timer_value[31:0]};','TIME_HIGH: timer_value_next={(timer_value[63:32] & ~write_mask) | (req_data & write_mask),timer_value_next[31:0]};'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_bench(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL timer_irq_next',result.stdout)
                print('PASS timer IRQ next runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
