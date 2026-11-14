"""Audit a complete PG100 implementation against its actual inputs and evidence."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from collect_evidence import observed_uncertainty
from inspect_pds import inspect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-build', type=Path, required=True)
    args = parser.parse_args()
    run = args.full_build.resolve(strict=True)
    checks: dict[str, dict] = {}

    def check(name: str, action) -> None:
        try:
            evidence = action()
            checks[name] = {'passed': True, 'evidence': evidence}
        except (AssertionError, KeyError, FileNotFoundError, ValueError,
                RuntimeError, subprocess.CalledProcessError) as error:
            checks[name] = {'passed': False, 'reason': str(error)}

    def physical() -> dict:
        result = read(run / 'RESULT.json')
        assert result['exit_code'] == 0, 'PDS process exit must be zero'
        assert not result['errors'], result['errors']
        stages = ('compile', 'synthesize', 'dev_map', 'pnr', 'report_timing', 'gen_bit_stream')
        assert all(result['stages'][stage] for stage in stages), 'All six stages must finish'
        q = inspect(run)
        assert q['qualified'], 'Final routing, timing, input and bitstream gates must pass'
        assert read(run / 'QUALIFICATION.json') == q, 'Stored qualification is stale'
        assert q['target'] == 'PG2L100H-6IFBG676', q['target']
        assert Path(q['bitstream']).stat().st_size > 0, 'Bitstream must contain data'
        expected = {(kind, corner) for kind in
                    ('Setup', 'Hold', 'Recovery', 'Removal', 'Minimum Pulse Width')
                    for corner in ('Slow', 'Fast')}
        assert {(t['check'], t['corner']) for t in q['timing']['tables']} == expected
        for table in q['timing']['tables']:
            for row in table['rows']:
                assert row['slack_ns'] >= 0 and row['failing_endpoints'] == 0
                assert row['total_negative_slack_ns'] == 0
        uncertainty = observed_uncertainty(Path(q['timing_report']).read_text(encoding='utf-8'))
        capacities = {'lut': 66600, 'ff': 133200, 'distributed_ram': 19900, 'drm': 155, 'apm': 240}
        for resource, capacity in capacities.items():
            assert 0 <= q['routed_resources'][resource] <= capacity, resource
        return {'qualification_sha256': sha(run / 'QUALIFICATION.json'),
                'timing_sha256': q['timing_sha256'], 'bitstream_sha256': q['bitstream_sha256'],
                'uncertainty': uncertainty, 'resources': q['routed_resources'],
                'minimum_slack_ns': {t['check'] + '/' + t['corner']:
                                     min(row['slack_ns'] for row in t['rows'])
                                     for t in q['timing']['tables']}}

    def inputs() -> dict:
        manifest = read(run / 'INPUTS.json')
        paths = ['instrec_fpga/' + row['path'] for row in manifest['files']]
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT.parent, text=True).strip()
        archive = subprocess.check_output(['git', 'archive', '--format=tar', commit, '--', *paths],
                                          cwd=ROOT.parent)
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
            for row in manifest['files']:
                for path in (run / 'inputs' / row['path'], ROOT / row['path']):
                    assert sha(path) == row['sha256'], str(path)
                saved = tar.extractfile('instrec_fpga/' + row['path'])
                assert saved is not None, row['path']
                assert hashlib.sha256(saved.read()).hexdigest() == row['sha256'], row['path']
        return {'committed_source': commit, 'file_count': len(paths),
                'manifest_sha256': sha(run / 'INPUTS.json')}

    def functional() -> dict:
        results = read(HERE / 'RESULTS.json')
        assert Path(results['physical']['full']['run']).resolve() == run, 'Selected run differs'
        assert results['all_selected_gates_passed'] and all(results['verdict'].values()), results['verdict']
        assert results['physical']['full'] == inspect(run), 'Selected physical evidence differs'
        npu = read(HERE / 'evidence/FULL_NPU_IMC_RESULTS.json')
        assert npu['status'] == 'pass', 'Full native NPU simulation must pass'
        for row in npu['inputs']:
            assert sha(Path(row['path'])) == row['sha256'], row['path']
        rollback = read(HERE / 'evidence/INTEGRATION_ROLLBACK_RESULTS.json')
        assert rollback['passed'] and rollback['all_original_hashes_restored']
        assert rollback['live_modified_files_unchanged']
        return {'results_sha256': sha(HERE / 'RESULTS.json'), 'gates': results['verdict'],
                'npu_inputs': len(npu['inputs']), 'rollback_original_hashes_restored': True}

    def artifacts() -> dict:
        paths = [HERE / name for name in ('MODIFIED_FILE.sv', 'DIFF_FILE.patch', 'VERIFICATION.txt', 'ROLLBACK.sh')]
        assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
        assert sha(paths[0]) == sha(ROOT / 'src/cpu/rv32_cpu_subsys.sv')
        assert sha(paths[3]) == sha(HERE / 'ROLLBACK.ps1')
        patch = subprocess.run(['git', 'apply', '--check', '--reverse', str(paths[1])],
                               cwd=ROOT.parent, capture_output=True)
        assert patch.returncode == 0, patch.stderr.decode(errors='replace')
        mode = subprocess.check_output(['git', 'ls-files', '-s', '--',
            'instrec_fpga/experiments/pacerv_shared_system/ROLLBACK.sh'], cwd=ROOT.parent, text=True)
        assert mode.startswith('100755 '), 'Rollback artifact must retain its executable Git mode'
        return {path.name: {'path': str(path), 'sha256': sha(path)} for path in paths}

    check('complete_physical_implementation', physical)
    check('frozen_live_committed_inputs_match', inputs)
    check('full_system_functional_evidence', functional)
    check('review_artifacts_and_rollback', artifacts)
    result = {'objective': 'Complete 100Pro+ whole-system timing acceptance',
              'run': str(run), 'checks': checks, 'passed': all(x['passed'] for x in checks.values())}
    out = HERE / 'evidence/FINAL_ACCEPTANCE.json'
    if out.is_file():
        historical = HERE / 'evidence/history' / sha(out)[:12] / out.name
        historical.parent.mkdir(parents=True, exist_ok=True)
        if historical.is_file() and historical.read_bytes() != out.read_bytes():
            raise RuntimeError('Acceptance history collision')
        shutil.copy2(out, historical)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    assert read(out) == result
    print(json.dumps({'passed': result['passed'],
                      'checks': {name: row['passed'] for name, row in checks.items()},
                      'output': str(out)}, indent=2))
    if result['passed']:
        print('GOAL_ACCEPTANCE_PASS target=PG2L100H-6IFBG676 physical=1 functional=1 inputs=1 rollback=1')
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
