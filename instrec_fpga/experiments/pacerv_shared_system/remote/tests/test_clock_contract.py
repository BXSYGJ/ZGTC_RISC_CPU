from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ClockContractTests(unittest.TestCase):
    def test_vendor_domains_match_pg200_contract_and_preserve_user_self_paths(self):
        fdc=(ROOT/"constraints"/"pg200_ip_cdc.fdc").read_text()
        commands=[line for line in fdc.splitlines() if line.startswith("set_clock_groups")]
        names=("ref_clk","rst_clk","phy_dq_clk_0","phy_dq_clk_1")
        self.assertEqual(commands,[f"set_clock_groups -name {name} -asynchronous -group [get_clocks {{{name}}}]" for name in names])
        self.assertNotIn("ddrphy_sysclk", "\n".join(commands))
        self.assertNotIn("phy_dq_sysclk", "\n".join(commands))
    def test_uncertainty_is_one_explicit_user_clock_pair(self):
        fdc=(ROOT/"constraints"/"pg200_ddr3.fdc").read_text()
        commands=[line for line in fdc.splitlines() if line.startswith("set_clock_uncertainty {0.150}")]
        self.assertEqual(commands,["set_clock_uncertainty {0.150} -setup -hold -from [get_clocks {ddrphy_sysclk}] -to [get_clocks {ddrphy_sysclk}]"])
        self.assertEqual(len([line for line in fdc.splitlines() if line.startswith("set_multicycle_path 2")]),2)

if __name__=="__main__": unittest.main()
