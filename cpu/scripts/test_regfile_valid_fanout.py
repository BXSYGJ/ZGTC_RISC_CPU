import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from load_use_profile import file_hash
from regfile_valid_fanout_changes import CHANGES
from test_regfile_valid_storage import PARENT as RESET_PARENT, wrapper as storage_wrapper

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "experiments/regfile_valid_storage/rv32_core.sv"
CORE = ROOT / "experiments/regfile_valid_fanout/rv32_core.sv"


def wrapper(source, name):
    result = storage_wrapper(source, name)
    aliases = re.findall(r"\(\* syn_maxfan=16 \*\) wire (id_register_[ab]_valid)=([^;]+);", source)
    if name == "candidate_regfile" and len(aliases) != 2:
        raise ValueError("Actual constrained validity aliases missing")
    if aliases:
        declarations = "\n".join("wire "+signal+"="+expression+";" for signal,expression in aliases)
        if result.count("reg [31:0] register_valid;") != 1:
            raise ValueError("Validity state capture missing")
        result = result.replace("reg [31:0] register_valid;", "reg [31:0] register_valid;\n"+declarations)
    return result


class ValidityFanoutTests(unittest.TestCase):
    def simulate(self, source):
        with tempfile.TemporaryDirectory(prefix="validity-fanout-") as directory:
            work = Path(directory)
            design = work / "design.sv"
            image = work / "test.vvp"
            design.write_text(wrapper(RESET_PARENT.read_text(),"parent_regfile")+"\n"+wrapper(source,"candidate_regfile"))
            compiled = subprocess.run(["iverilog","-g2012","-s","regfile_valid_tb","-o",str(image),str(design),str(ROOT / "sim/regfile_valid_storage_tb.sv")],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(["vvp",str(image)],capture_output=True,text=True,timeout=60)

    def test_exact_two_read_port_delta(self):
        self.assertEqual(file_hash(RESET_PARENT),"732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3")
        self.assertEqual(file_hash(PARENT),"ABD2D7A8C5B7C81239F14A90E5BB802308F53E74387097D88A8A20F3531EB59D")
        self.assertEqual(file_hash(CORE),"DC90363D426754F032EC04DB6F4BE76DA439CCA149E372853EE2D64536D20FCE")
        source = CORE.read_text()
        for before,after in reversed(CHANGES):
            self.assertEqual(source.count(after),1)
            source = source.replace(after,before)
        self.assertEqual(source,PARENT.read_text())
        self.assertEqual(CORE.read_text().count("(* syn_maxfan=16 *)"),2)

    def test_actual_read_write_reset_and_bypass(self):
        result = self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("checks=75891 resets=73",result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutations_rejected(self):
        source = CORE.read_text()
        positive = self.simulate(source)
        self.assertEqual(positive.returncode,0,positive.stdout+positive.stderr)
        changes = (
            ("wrong_reset","register_valid<=0;","register_valid<=32'hffffffff;"),
            ("missing_valid_mark","register_valid[wb_rd]<=1'b1;","register_valid[wb_rd]<=1'b0;"),
            ("wrong_write_data","registers[wb_rd]<=wb_data;","registers[wb_rd]<=~wb_data;"),
            ("raw_uninitialized_read","(id_register_a_valid ? registers[id_rs1] : 32'd0)","registers[id_rs1]"),
            ("wrong_valid_address","id_register_b_valid=register_valid[id_rs2]","id_register_b_valid=register_valid[id_rs1]"),
            ("lost_read_bypass","(trace_write && wb_rd==id_rs1)","(1'b0 && wb_rd==id_rs1)"),
            ("masked_wb_data","? wb_data : (id_register_a_valid","? 32'd0 : (id_register_a_valid"),
        )
        for name,before,after in changes:
            with self.subTest(mutation=name):
                self.assertEqual(source.count(before),1)
                result = self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn("FAIL regfile_valid",result.stdout+result.stderr)
                print("PASS validity fanout runtime rejection: "+name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
