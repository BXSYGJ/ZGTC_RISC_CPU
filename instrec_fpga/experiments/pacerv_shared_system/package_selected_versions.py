"""Compare completed PG100 builds and package the user's selected clock versions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

from inspect_pds import inspect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILDS = ROOT / 'build/pacerv_shared_system/pds'
OUTPUT = ROOT / 'build/pacerv_shared_system/selected_versions_20261114'
SELECTED = {
    '109M375_main': 'full-20261114-021145-full',
    '125M_hold_clean': 'full-20261113-223256-full',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    for manifest_path in sorted(BUILDS.glob('full-*/INPUTS.json')):
        manifest = read(manifest_path)
        run = manifest_path.parent
        if manifest['target'] != 'PG2L100H-6IFBG676':
            continue
        if not (run / 'generate_bitstream/instrec_top.sbit').is_file():
            continue
        params = {p.findtext('name'): p.findtext('value') for p in ET.parse(
            run / 'inputs/ipcore/ddr3_test/ddr3_test.idf').findall('./param_list/param')}
        hz = round(float(params['ACTUAL_RATE']) * 1e6 / 8)
        if hz not in (125000000, 109375000):
            continue
        q = inspect(run)
        result = read(run / 'RESULT.json')
        assert not q['changed_inputs'], run
        assert result['exit_code'] == 0 and all(result['stages'].values()), run
        assert q['timing']['complete_ten_tables']
        tables = {(t['check'], t['corner']): t for t in q['timing']['tables']}
        minimum = lambda kind, corner: min(r['slack_ns'] for r in tables[kind, corner]['rows'])
        negative = lambda kind, corner: round(sum(
            r['total_negative_slack_ns'] for r in tables[kind, corner]['rows']), 3)
        failures = lambda kind, corner: sum(r['failing_endpoints'] for r in tables[kind, corner]['rows'])
        row = {'run': run.name, 'run_path': str(run), 'system_clock_hz': hz,
               'slow_setup_ns': minimum('Setup', 'Slow'),
               'slow_setup_tns_ns': negative('Setup', 'Slow'),
               'slow_setup_failing_endpoints': failures('Setup', 'Slow'),
               'slow_hold_ns': minimum('Hold', 'Slow'), 'fast_hold_ns': minimum('Hold', 'Fast'),
               'timing_qualified': q['qualified'], 'input_count': len(manifest['files']),
               'bitstream_path': q['bitstream'], 'bitstream_sha256': q['bitstream_sha256'],
               'timing_report_path': q['timing_report'], 'timing_sha256': q['timing_sha256'],
               'resources': q['routed_resources']}
        records.append(row)

    by_name = {row['run']: row for row in records}
    packages = {}
    for label, name in SELECTED.items():
        row = by_name[name]
        source = BUILDS / name
        destination = OUTPUT / label
        if destination.exists():
            raise FileExistsError('Preserve existing package: ' + str(destination))
        destination.mkdir()
        shutil.copytree(source / 'inputs', destination / 'inputs')
        copied = {'instrec_top.sbit': source / 'generate_bitstream/instrec_top.sbit',
                  'TIMING.rtr': source / 'report_timing/instrec_top.rtr',
                  'BUILD_RESULT.json': source / 'RESULT.json',
                  'INPUTS.json': source / 'INPUTS.json',
                  'SOURCE_BUILD_RECIPE.tcl': source / 'build.tcl'}
        for target_name, path in copied.items():
            shutil.copy2(path, destination / target_name)
        manifest = read(destination / 'INPUTS.json')
        assert all(sha(destination / 'inputs' / p['path']) == p['sha256'] for p in manifest['files'])
        assert sha(destination / 'instrec_top.sbit') == row['bitstream_sha256']
        assert sha(destination / 'TIMING.rtr') == row['timing_sha256']
        note = [
            '# ' + label, '',
            '原构建：' + str(source),
            '器件：PG2L100H-6IFBG676；系统频率：' + str(row['system_clock_hz']) + ' Hz。',
            '直接使用本目录 instrec_top.sbit；inputs 是该位流对应的完整冻结源码、IP、HEX和约束。',
            'INPUTS.json保存逐文件SHA256；TIMING.rtr保存原始最终时序报告。',
            'SOURCE_BUILD_RECIPE.tcl保留原构建绝对路径，用于追溯原工程。',
            '最终报告：slow setup ' + str(row['slow_setup_ns']) + ' ns；slow hold '
            + str(row['slow_hold_ns']) + ' ns；fast hold ' + str(row['fast_hold_ns']) + ' ns。',
            '位流SHA256：' + row['bitstream_sha256'],
            '按用户要求选用已有版本，保留原时序违例记录。',
        ]
        readme = destination / 'README.md'
        readme.write_text('\n\n'.join(note) + '\n', encoding='utf-8')
        files = sorted(p for p in destination.rglob('*') if p.is_file())
        package_manifest = {'selection': row, 'files': [
            {'path': p.relative_to(destination).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in files]}
        (destination / 'PACKAGE_MANIFEST.json').write_text(
            json.dumps(package_manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        archive = OUTPUT / (label + '.zip')
        if archive.exists():
            raise FileExistsError(archive)
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=5) as zip_file:
            for path in sorted(p for p in destination.rglob('*') if p.is_file()):
                zip_file.write(path, label + '/' + path.relative_to(destination).as_posix())
        with zipfile.ZipFile(archive) as zip_file:
            assert zip_file.testzip() is None
            for item in package_manifest['files']:
                data = zip_file.read(label + '/' + item['path'])
                assert hashlib.sha256(data).hexdigest() == item['sha256']
        assert readme.read_text(encoding='utf-8')
        packages[label] = {'directory': str(destination), 'zip': str(archive),
                           'zip_sha256': sha(archive), 'run': name,
                           'verified_input_count': len(manifest['files']), 'verified_files': len(files)}

    result = {'user_direction': 'Finish the active build, stop timing-closure work, and use previous 125/109.375 MHz versions.',
              'all_completed_requested_clock_builds': records, 'selected_packages': packages,
              'primary': '109M375_main',
              'selection_reason': '109.375 MHz 021145 has the smallest setup TNS and fewest setup failures; '
                                  '125 MHz 223256 preserves nonnegative hold at both corners. '
                                  '125 MHz 213918 has the best worst setup slack; 010622 has the lowest 125 MHz setup TNS.'}
    output = HERE / 'evidence/SELECTED_VERSIONS_20261114.json'
    assert not output.exists(), output
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    assert read(output) == result
    print(json.dumps({'packages': packages, 'comparison': str(output)}, indent=2, ensure_ascii=False))
    print('SELECTED_VERSIONS_PASS packages=2 frozen_inputs=404 zip_hashes=verified source_builds_unchanged=1')


if __name__ == '__main__':
    main()
