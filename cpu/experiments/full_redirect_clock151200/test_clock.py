import copy
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_clock
from audit_clock import ROOT, audit_sources, validate_firmware


class ClockTradeoffTests(unittest.TestCase):
    def firmware(self, validation=False, iterations=6000):
        delay = "_p2700000" if iterations == 6000 else ""
        filename = f"coremark_v{int(validation)}_i{iterations}{delay}_f151200000_rv32gcc_rv32im_O3_unroll_relax.build.json"
        return json.loads((ROOT.parent / "full_mul_precompute_clock154285/build" / filename).read_text(encoding="utf-8-sig"))

    def test_physical_sources_unchanged(self):
        self.assertEqual(audit_sources()["ClockHz"], 151200000)

    def test_clock_specific_firmware_pair(self):
        for validation in (False, True):
            for iterations in (10, 6000):
                self.assertTrue(validate_firmware(self.firmware(validation, iterations), validation, iterations))

    def test_reject_firmware_mismatches(self):
        original = self.firmware()
        mutations = [("ClockHz", 154285714), ("Iterations", 10), ("ValidationRun", True),
                     ("EnableM", 0), ("Isa", "rv32i"), ("UpstreamRevision", "wrong"),
                     ("ConsoleDelayCycles", 0), ("Optimization", "O2"), ("UnrollLoops", False),
                     ("LinkerRelaxation", False), ("LinkTimeOptimization", True),
                     ("Flags", original["Flags"] + ["-DCPU_CLOCK_HZ=154285714u"]),
                     ("Flags", [flag.replace("151200000", "154285714") for flag in original["Flags"]])]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(original)
                changed[field] = value
                with self.assertRaises(ValueError):
                    validate_firmware(changed, False, 6000)

    def test_reject_changed_configuration(self):
        original_read = Path.read_text
        original = json.loads((ROOT / "configuration.json").read_text(encoding="utf-8"))
        for field, value in (("ClockHz", 154285714), ("EnableM", 0), ("CacheEnabled", 0), ("HistoryBits", 4)):
            changed = dict(original, **{field: value})
            def altered_read(filename, *arguments, **keywords):
                if filename == ROOT / "configuration.json":
                    return json.dumps(changed)
                return original_read(filename, *arguments, **keywords)
            with self.subTest(field=field), patch.object(Path, "read_text", altered_read):
                with self.assertRaises(ValueError):
                    audit_sources()

    def test_reject_changed_physical_hash(self):
        original_digest = audit_clock.digest
        for relative in ("rtl/rv32_core.sv", "rtl/rv32_peripherals.sv", "fpga/rv32_pll.sv", "constraints/uart_remotelab.fdc"):
            def altered_digest(filename):
                return "0" * 64 if filename == ROOT / relative else original_digest(filename)
            with self.subTest(relative=relative), patch.object(audit_clock, "digest", altered_digest):
                with self.assertRaises(ValueError):
                    audit_sources()

    def test_pll_elaboration_and_rejected_ratio(self):
        source = (ROOT / "fpga/rv32_pll.sv").read_text(encoding="utf-8")
        primitive = source.split("    GTP_GPLL #(", 1)[1]
        parameter_text, port_text = primitive.split(") pll (", 1)
        parameters = re.findall(r"\.([A-Z0-9_]+)\(([^()]*)\)", parameter_text)
        ports = re.findall(r"\.([A-Z0-9_]+)\(([^()]*)\)", port_text)
        self.assertGreater(len(parameters), 20)
        self.assertGreater(len(ports), 20)
        stub = "module GTP_GPLL #( " + ",".join("parameter " + name + "=0" for name, value in parameters) + ") (" + ",".join(("output wire " if name in ("CLKOUT0", "LOCK") else "input wire ") + name for name, value in ports) + "); endmodule\n"
        bench = "module clock_tb; wire cpu_clk,locked; rv32_pll #(.CLOCK_HZ(151200000)) dut(.reference_clk(1'b0),.reset(1'b0),.cpu_clk(cpu_clk),.locked(locked)); initial begin #1; if(dut.pll.STATIC_RATIOI != 1 || dut.pll.STATIC_RATIOM != 2 || dut.pll.STATIC_RATIOF != 14 || dut.pll.STATIC_RATIO0 != 5 || dut.pll.CLKIN_FREQ != 27.0) $fatal(1, \"Wrong elaborated PLL ratio\"); $display(\"PASS PLL elaborated 27 MHz * 2 * 14 / 5 = 151.2 MHz configuration\"); $finish; end endmodule\n"
        with tempfile.TemporaryDirectory(prefix="clock151200-pll-") as directory:
            work = Path(directory)
            (work / "bench.sv").write_text(stub + bench, encoding="utf-8")
            for mutated in (False, True):
                candidate_source = source.replace("CLOCK_HZ==151200000", "CLOCK_HZ==151200001") if mutated else source
                (work / "pll.sv").write_text(candidate_source, encoding="utf-8")
                compiled = subprocess.run(["iverilog", "-g2012", "-s", "clock_tb", "-o", str(work / "test.vvp"), str(work / "pll.sv"), str(work / "bench.sv")], capture_output=True, text=True, timeout=60)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                executed = subprocess.run(["vvp", str(work / "test.vvp")], capture_output=True, text=True, timeout=60)
                if mutated:
                    self.assertNotEqual(executed.returncode, 0)
                    self.assertIn("Wrong elaborated PLL ratio", executed.stdout + executed.stderr)
                else:
                    self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
                    self.assertIn("PASS PLL elaborated", executed.stdout)
                    print(executed.stdout, flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
