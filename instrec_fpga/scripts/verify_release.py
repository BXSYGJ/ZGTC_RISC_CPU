#!/usr/bin/env python3
"""Verify the frozen release without Git, PDS or board access."""
import ast
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    entries = (ROOT / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
    checked = set()
    for entry in entries:
        expected, relative = entry.split('  ', 1)
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise SystemExit('Missing or unsafe release path: ' + relative)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit('Changed release file: ' + relative)
        checked.add(relative)
    actual_files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
                    if p.is_file() and not any(part in ('build', 'reports', '__pycache__')
                                             for part in p.relative_to(ROOT).parts)
                    and p.name != 'SHA256SUMS' and p.suffix != '.pyc'}
    if actual_files != checked:
        raise SystemExit('Unlisted release files: ' + repr(sorted(actual_files - checked)))
    config = json.loads((ROOT / 'scripts/build_sets.json').read_text(encoding='utf-8'))
    assert list(config['sets']) == ['full']
    full = config['sets']['full']
    assert full['top_module'] == 'instrec_top'
    for key in ('sources', 'ip_cores', 'constraints'):
        for relative in full[key]:
            path = (ROOT / relative).resolve()
            assert path.is_relative_to(ROOT) and path.is_file(), relative
    assert full['constraints'][-2:] == ['constraints/ddr3_100h.fdc', 'constraints/clock_groups_async.fdc']
    for relative in full['ip_cores']:
        ip = ROOT / relative
        for row in ET.parse(ip).findall('.//file_list/source/file'):
            dependency = (ip.parent / row.attrib['pathname']).resolve()
            assert dependency.is_relative_to(ROOT) and dependency.is_file(), dependency
    for path in list(ROOT.glob('scripts/*.py')) + list(ROOT.glob('training/src/*.py')):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for relative in full['sources']:
        text = (ROOT / relative).read_text(encoding='utf-8')
        for table in re.findall(r'"(src/[^"\n]+\.hex)"', text):
            assert (ROOT / table).is_file(), table
    lock = json.loads((ROOT / 'SOURCE_LOCK.json').read_text(encoding='utf-8'))
    assert len(lock['classes_zh']) == 8 and lock['cpu']['ENABLE_M'] == 0
    top = (ROOT / 'src/ctrl/instrec_top.v').read_text(encoding='utf-8')
    assert re.search(r'npu_top\s*#', top)
    assert 'rv32_cpu_subsys' in top and 'demo_confidence_player' not in top
    print(f'PASS: {len(checked)} hashes; {len(full["sources"])} RTL sources; local IP, ROM and build dependencies')


if __name__ == '__main__':
    main()
