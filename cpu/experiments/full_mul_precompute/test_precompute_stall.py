import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def run(command, timeout=60):
    return subprocess.run([str(argument) for argument in command], capture_output=True, text=True, timeout=timeout)


def linux_path(path):
    result = run(["wsl.exe", "--distribution", "Ubuntu-22.04", "--exec", "/usr/bin/wslpath", "-a", path])
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout.strip()


class StallTests(unittest.TestCase):
    def test_stalled_and_dependent_multiplies(self):
        toolchain = json.loads((ROOT / "build/riscv32-toolchain.json").read_text(encoding="utf-8-sig"))
        prefix = toolchain["ToolPrefix"]
        with tempfile.TemporaryDirectory(prefix="mul-expiry-") as temporary:
            work = Path(temporary)
            linux_work = linux_path(work)
            linux_root = linux_path(ROOT)
            for command in ([prefix + "gcc", "-march=rv32im", "-mabi=ilp32", "-nostdlib", "-nostartfiles", "-Wl,--no-relax", "-T", linux_root + "/sim/isa/link.ld", "-o", linux_work + "/test.elf", linux_root + "/precompute_stall.S"],
                            [prefix + "objcopy", "-O", "binary", linux_work + "/test.elf", linux_work + "/test.bin"]):
                result = run(["wsl.exe", "--distribution", "Ubuntu-22.04", "--exec", *command])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = (work / "test.bin").read_bytes()
            self.assertLessEqual(len(data), 65536)
            data = data.ljust(65536, b"\x00")
            firmware = work / "test.hex"
            firmware.write_text("".join(f"{int.from_bytes(data[offset:offset+4], 'little'):08x}\n" for offset in range(0, len(data), 4)))
            for delay, predictor, mutant in [(delay, predictor, False) for delay in (0, 1, 8, 31) for predictor in (0, 1)] + [(31, 1, True)]:
                with self.subTest(delay=delay, predictor=predictor, mutant=mutant):
                    core = (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
                    if mutant:
                        before = "else mul_precomputed<=mul_precompute;"
                        self.assertEqual(core.count(before), 1)
                        core = core.replace(before, "else if(mul_precompute) mul_precomputed<=1;")
                    core_path = work / "rv32_core.sv"
                    core_path.write_text(core, encoding="utf-8")
                    image = work / "test.vvp"
                    sources = [core_path] + [ROOT / "rtl" / (name + ".sv") for name in ("rv32_decode", "rv32_machine", "rv32_alu", "rv32_btb", "rv32_muldiv")]
                    result = run(["iverilog", "-g2012", "-s", "precompute_stall_tb", f"-Pprecompute_stall_tb.RESPONSE_DELAY={delay}", f"-Pprecompute_stall_tb.PREDICTOR={predictor}", "-o", image, *sources, ROOT / "precompute_stall_tb.sv"])
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = run(["vvp", image, f"+firmware={firmware.as_posix()}"])
                    if mutant:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("FAIL expired marker retained", result.stdout)
                        self.assertNotIn("watchdog", result.stdout)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn("PASS stalled precompute", result.stdout)
                        print(result.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)

