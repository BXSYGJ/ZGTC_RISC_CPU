"""Package the modified wrapper and source diff; preserve live implementation."""
import hashlib
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parent
BASELINE = '852f067db4a4a710f5355e3ab311f035ced5b48d'


def main() -> None:
    modified = HERE / 'MODIFIED_FILE.sv'
    shutil.copy2(ROOT / 'src/cpu/rv32_cpu_subsys.sv', modified)
    tracked = ['scripts/build_sets.json', 'sim/run_sim.py', 'sim/tb_rv_cpu.sv',
               'src/cpu/rv32_cpu_subsys.sv', 'src/ctrl/instrec_top.v',
               'src/ddr3/ddr3_arbiter.v', 'src/ddr3/ddr3_ctrl_axi.v',
               'src/npu/activation_store_mux.v', 'src/npu/activation_row_store_dynamic.v',
               'src/npu/fc_engine.v', 'src/npu/weight_read_aligner_hardened.v',
               'src/npu/wdma.v', 'src/npu/gap_unit.v', 'src/ctrl/weight_loader.v',
               'ipcore/ddr3_test/ddr3_test.idf',
               'ipcore/ddr3_test/ddr3_test.v', 'ipcore/ddr3_test/ddr3_test_ddrphy_top.v',
               'constraints/ddr3_100h.fdc', 'src/ui/dashboard_renderer.v',
               'src/ui/dashboard_text.v', 'sim/tb_dashboard_ui.sv']
    added = [ROOT / 'src/ddr3/pace_cpu_ddr_bridge.v', ROOT / 'src/ddr3/ddr3_m3_share.v',
             ROOT / 'src/cpu/prog_pacerv.hex', ROOT / 'sw/rv32/main_pacerv.c',
             ROOT / 'constraints/pacerv_shared_system.fdc']
    added += sorted((ROOT / 'src/cpu/vendor/pacerv_h3').glob('*.sv'))
    added += [ROOT / 'src/cpu/vendor/pacerv_h3/PROVENANCE.json', ROOT / '.gitattributes']
    paths = ['instrec_fpga/' + p for p in tracked]
    paths += ['instrec_fpga/' + path.relative_to(ROOT).as_posix() for path in added]
    for path in added:
        relative = 'instrec_fpga/' + path.relative_to(ROOT).as_posix()
        subprocess.run(['git', 'ls-files', '--error-unmatch', '--', relative], cwd=REPO,
                       check=True, stdout=subprocess.DEVNULL)
    # Raw Git bytes preserve the original file endings, including frozen RTL.
    patch = subprocess.check_output(['git', 'diff', '--binary', BASELINE, '--', *paths], cwd=REPO)
    (HERE / 'DIFF_FILE.patch').write_bytes(patch)
    for path in (modified, HERE / 'DIFF_FILE.patch', HERE / 'ROLLBACK.ps1', HERE / 'ROLLBACK.sh'):
        data = path.read_bytes()
        if not data:
            raise RuntimeError('Empty artifact: ' + str(path))
        print(path.name + ' SHA256=' + hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
