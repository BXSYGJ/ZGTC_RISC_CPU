"""Run two golden native inferences using exclusively frozen snapshot DUT RTL.

The full native golden/TB generators are reused; all DUT inputs and the AXI
model are resolved by module name inside the frozen snapshot and hash-checked.
This is a compute/native-chain check, not a complete production-top test.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'sim'))
import run_sim as sim


def normalized_rtl(text):
    pattern = r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/'
    clean = re.sub(pattern, lambda m: m.group(0) if m.group(0).startswith('"') else '',
                   text, flags=re.S)
    return ''.join(re.findall(r'"(?:\\.|[^"\\])*"|[^\s"]+', clean))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--manifest-only', action='store_true')
    parser.add_argument('--production', action='store_true',
                        help='Use actual ROOT/src DUT only after exact snapshot hash match')
    args = parser.parse_args()
    snapshot = args.snapshot.resolve()
    manifest = json.loads((snapshot / 'snapshot.json').read_text())
    for row in manifest['sources']:
        path = snapshot / row['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError('Frozen source mismatch: ' + str(path))
    actual_run = sim.run_case

    def frozen_case(case, verilator, options):
        rtl = []
        rows = []
        for original in list(case.rtl) + [str(HERE / 'npu_m1_owner.v')]:
            text = Path(original).read_text()
            module = re.search(r'^\s*module\s+(\w+)', text, re.M).group(1)
            matches = list((snapshot / 'src').rglob(module + '.v'))
            if module == 'ddr3_axi_model_full':
                matches = [snapshot / 'verification/ddr3_axi_model_full.sv']
            if len(matches) != 1 or not matches[0].is_file():
                raise RuntimeError('Cannot resolve frozen module: ' + module)
            frozen_path = matches[0]
            path = frozen_path
            cosmetic_evidence = None
            if args.production and module != 'ddr3_axi_model_full':
                path = ROOT / frozen_path.relative_to(snapshot)
                if not path.is_file():
                    raise RuntimeError('Missing production source: ' + str(path))
                if path.read_bytes() != frozen_path.read_bytes():
                    report = ROOT / 'reports/npu_production_promotion_20261101.json'
                    evidence = json.loads(report.read_text()) if report.is_file() else {}
                    pair = next((row for row in evidence.get('sources', [])
                                 if row['path'] == path.relative_to(ROOT).as_posix()), {})
                    frozen_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
                    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                    if (evidence.get('snapshot') != snapshot.name or
                        pair.get('snapshot_sha256') != frozen_sha or
                        pair.get('production_sha256') != actual_sha or
                        pair.get('comment_whitespace_normalized_equal') is not True or
                        normalized_rtl(path.read_text()) != normalized_rtl(frozen_path.read_text())):
                        raise RuntimeError('Unreviewed production drift: ' + str(path))
                    cosmetic_evidence = {'report': str(report),
                                         'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
                                         'snapshot_sha256': frozen_sha,
                                         'production_sha256': actual_sha,
                                         'normalized_equal': True}
            rtl.append(str(path))
            rows.append({'module': module, 'path': str(path),
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'frozen_path': str(frozen_path),
                         'matches_frozen_snapshot': path.read_bytes() == frozen_path.read_bytes(),
                         'reviewed_cosmetic_difference': cosmetic_evidence,
                         'generator_input': str(original),
                         'same_as_generator_input': path.read_bytes() == Path(original).read_bytes()})
        name = 'npu_production_native' if args.production else 'npu_snapshot_native'
        output = ROOT / 'build/sim' / name / snapshot.name
        output.mkdir(parents=True, exist_ok=True)
        inputs = output / ('manifest_only_inputs.json' if args.manifest_only else 'inputs.json')
        inputs.write_text(json.dumps(rows, indent=2), encoding='ascii')
        tb = output / 'tb_npu_full_native.sv'
        text = Path(case.tb).read_text(encoding='ascii')
        substitutions = {
            "{2'b00,n_mcmdvalid,1'b0}": "{2'b00,owner_valid,1'b0}",
            "{2'b00,n_mrdready,1'b0}": "{2'b00,owner_ready,1'b0}",
            '.m1_wready(n_wready_beat[1])': '.m1_wready(owner_n_wready)',
            '.m1_rvalid(n_rd_valid_vec[1])': '.m1_rvalid(owner_n_rvalid)',
            '.m1_done(n_done_vec[1])': '.m1_done(owner_n_done)',
            '.m1_abort(n_cmd_to_err[1] || n_addr_err[1])': '.m1_abort(owner_n_abort)',
            ".m0_cmd(37'd0),.m1_cmd(n_mcmd)": ".m0_cmd(37'd0),.m1_cmd(owner_cmd)",
            ".m0_wdata(256'd0),.m1_wdata(n_mwdata)": ".m0_wdata(256'd0),.m1_wdata(owner_wdata)",
        }
        for old, new in substitutions.items():
            if text.count(old) != 1:
                raise RuntimeError('Review native owner insertion: ' + old)
            text = text.replace(old, new)
        owner = '''
wire owner_valid,owner_ready,owner_n_wready,owner_n_rvalid,owner_n_done,owner_n_abort;
wire owner_idle,owner_error,owner_l_wready,owner_l_rvalid,owner_l_done;
wire [36:0] owner_cmd;
wire [255:0] owner_wdata;
npu_m1_owner owner(.clk(clk),.rst_n(rst_n),.loader_allowed(!busy),
 .l_valid(1'b0),.l_cmd(37'd0),.l_wdata(256'd0),.l_rd_ready(1'b1),
 .l_wready(owner_l_wready),.l_rvalid(owner_l_rvalid),.l_done(owner_l_done),
 .n_valid(n_mcmdvalid),.n_cmd(n_mcmd),.n_wdata(n_mwdata),.n_rd_ready(n_mrdready),
 .n_wready(owner_n_wready),.n_rvalid(owner_n_rvalid),.n_done(owner_n_done),.n_abort(owner_n_abort),
 .m_valid(owner_valid),.m_cmd(owner_cmd),.m_wdata(owner_wdata),.m_rd_ready(owner_ready),
 .m_wready(n_wready_beat[1]),.m_rvalid(n_rd_valid_vec[1]),.m_done(n_done_vec[1]),
 .m_abort(n_cmd_to_err[1] || n_addr_err[1]),.idle(owner_idle),.protocol_error(owner_error));
always @(posedge clk) if(rst_n && owner_error) $fatal(1,"native M1 owner error");
'''
        pos = text.rfind('endmodule')
        text = text[:pos] + owner + text[pos:]
        tb.write_text(text, encoding='ascii')
        if args.manifest_only:
            print('MANIFEST PASS: %d inputs, mode=%s; exact hashes or reviewed cosmetic SHA pairs verified' %
                  (len(rtl), 'production' if args.production else 'frozen'))
            from types import SimpleNamespace
            return SimpleNamespace(ok=True, output='Manifest only; simulation not run', log_path=inputs)
        return actual_run(replace(case, name=name + '_' + snapshot.name,
                                  tb=str(tb), rtl=rtl, timeout=480), verilator, options)

    repeat = load('snapshot_repeat_generator', HERE.parent / 'weight_read_aligner_hardened/run_repeat_native.py')
    hardened = load('snapshot_hardened_generator', HERE.parent / 'weight_read_aligner_hardened/run_full_native.py')
    repeat.real_run_case = frozen_case
    hardened.original_run_case = repeat.repeat_case
    sim.run_case = hardened.hardened_case
    baseline = load('snapshot_golden_generator', HERE.parent / 'npu_full_native/run.py')
    return baseline.main()


if __name__ == '__main__':
    raise SystemExit(main())
