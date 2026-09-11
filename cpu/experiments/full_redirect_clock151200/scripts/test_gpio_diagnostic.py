import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class GpioDiagnosticControls(unittest.TestCase):
    def simulate(self, mutation):
        manifest = json.loads((PROJECT / "build/gpio-latest.json").read_text(encoding="utf-8-sig"))
        firmware = subprocess.run(["wslpath", "-a", manifest["Hex"]], capture_output=True, text=True, check=True).stdout.strip()
        with tempfile.TemporaryDirectory(prefix="gpio-control-") as directory:
            work = Path(directory)
            relative, old, new = mutation
            original = PROJECT / relative
            text = original.read_text(encoding="utf-8-sig")
            self.assertEqual(text.count(old), 1, "Mutation must match exactly once")
            replacement = work / original.name
            replacement.write_text(text.replace(old, new), encoding="utf-8")
            if relative.startswith("sw/"):
                prefix = manifest["Toolchain"]["Prefix"]
                self.assertRegex(prefix, r"^/home/[A-Za-z0-9/._-]+/bin/riscv32-unknown-elf-$")
                self.assertNotIn("..", prefix.split("/"))
                compiled = subprocess.run([
                    prefix + "gcc", "-march=rv32i", "-mabi=ilp32", "-msmall-data-limit=0", "-std=c11", "-O2",
                    "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-nostdlib", "-nostartfiles",
                    "-Wl,--no-relax", "-I", str(PROJECT / "sw"), "-T", str(PROJECT / "sw/link_soc.ld"),
                    "-o", str(work / "firmware.elf"), str(PROJECT / "sw/start.S"), str(replacement), "-lgcc",
                ], capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                subprocess.run([prefix + "objcopy", "-O", "binary", str(work / "firmware.elf"), str(work / "firmware.bin")], check=True, capture_output=True, timeout=30)
                subprocess.run(["python3", str(PROJECT / "scripts/bin_to_hex.py"), str(work / "firmware.bin"), str(work / "firmware.hex"), "--bytes", "65536"], check=True, capture_output=True, timeout=30)
                firmware = str(work / "firmware.hex")
            sources = [replacement if path == original else path for path in sorted((PROJECT / "rtl").glob("*.sv"))]
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "gpio_diagnostic_tb", "-Pgpio_diagnostic_tb.FAST_CONFIGURATION=1",
                "-o", str(work / "test.vvp"), *map(str, sources), str(PROJECT / "sim/gpio_diagnostic_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(work / "test.vvp"), "+firmware=" + firmware], capture_output=True, text=True, timeout=90)

    def test_wrong_input_irq_and_pending_are_rejected(self):
        mutations = [
            ("rtl/rv32_board_top.sv", ".gpio_input({6'b0,uart_rx,~key})", ".gpio_input({6'b0,uart_rx,uart_rx})"),
            ("rtl/rv32_board_top.sv", ".gpio_input({6'b0,uart_rx,~key})", ".gpio_input({6'b0,uart_rx,key})"),
            ("sw/gpio_diagnostic.c", "GPIO_ENABLE = 1;", "GPIO_ENABLE = 3;"),
            ("sw/gpio_diagnostic.c", "GPIO_PENDING = 1;", "GPIO_PENDING = 0;"),
            ("sw/gpio_diagnostic.c", "interrupt_count++;", "interrupt_count += 2;"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertRegex(result.stdout, r"FAIL GPIO UART|GPIO firmware failed|FAIL GPIO interrupt storm")
                self.assertNotIn("watchdog", result.stdout.lower())
                self.assertNotIn("PASS gpio_diagnostic", result.stdout)


if __name__ == "__main__":
    unittest.main()
