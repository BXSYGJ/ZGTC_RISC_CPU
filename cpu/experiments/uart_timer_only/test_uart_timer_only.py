import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
BASELINE = ROOT / 'build/regfile-valid-fanout-stage/rtl'


class UartTimerOnlyTests(unittest.TestCase):
    def simulate(self, replacement=None):
        baseline = BASELINE / 'rv32_peripherals.sv'
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest().upper(),
                         'B61ED1BC98CA4B6375AA27337FB6C68091FBFEBA156495424D71431A6F4630E6')
        reference = baseline.read_text().replace('module rv32_peripherals #(', 'module reference_peripherals #(', 1)
        candidate = (EXPERIMENT / 'rv32_peripherals.sv').read_text()
        if replacement:
            original, modified = replacement
            self.assertEqual(candidate.count(original), 1)
            candidate = candidate.replace(original, modified)
        with tempfile.TemporaryDirectory(prefix='uart-timer-only-') as temporary:
            work = Path(temporary)
            (work / 'reference.sv').write_text(reference)
            (work / 'candidate.sv').write_text(candidate)
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'uart_timer_only_tb', '-o', str(work / 'test.vvp'),
                                       str(work / 'reference.sv'), str(work / 'candidate.sv'),
                                       str(BASELINE / 'rv32_fifo.sv'), str(BASELINE / 'rv32_uart.sv'),
                                       str(EXPERIMENT / 'uart_timer_only_tb.sv')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(work / 'test.vvp')], capture_output=True, text=True, timeout=30)

    def test_preserved_services_and_removed_gpio(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS uart_timer_only checks=39', result.stdout)

    def test_invalid_implementations_are_rejected(self):
        mutations = (
            ("assign gpio_output=8'b0;", "assign gpio_output=8'b1;"),
            ('assign irq_external=', 'assign irq_external=gpio_input[0] || '),
            ("VERSION: rsp_data<=32'h00010000;", "VERSION: rsp_data<=32'h00010000; 32'h10000204: rsp_data<=0;"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('watchdog', result.stdout.lower())


if __name__ == '__main__':
    unittest.main()
