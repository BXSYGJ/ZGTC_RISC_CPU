#!/usr/bin/env python3
"""Export the afternoon CPU/NPU eight-class baseline without touching live RTL."""
from __future__ import annotations

import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tokenize
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'instrec_fpga'
REF = '0c138d4f8590be1a0dde63e21d680e8d250e32a0'
RUN = APP / 'build/pds/20261103-152639-fb2ffc99'
DEST = APP / 'releases/pacerv-instrec8-20261103'
COMMENT = re.compile(r'"(?:\\.|[^"\\])*"|\\[^\s]+|//[^\n]*|/\*[\s\S]*?\*/')
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\\[^\s]+|[A-Za-z_$][\w$]*|\d+|[^\s]')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_source(data: bytes) -> str:
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('gb18030')


def strip_comments(text: str, c_source: bool = False) -> str:
    pattern = COMMENT
    if c_source:
        pattern = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')

    def replace(match: re.Match) -> str:
        part = match[0]
        if not part.startswith(('//', '/*')):
            return part
        body = part.lstrip('/* ').lower()
        if (re.match(r'(synthesis|synopsys|pragma|cadence|altera|translate_)\b', body)
                or re.search(r'copyright|spdx|licensed under|all rights reserved', body)):
            return part
        return ' ' + '\n' * part.count('\n')

    return pattern.sub(replace, text)


def compact(text: str) -> str:
    return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n',
                  '\n'.join(line.rstrip() for line in text.splitlines())).strip() + '\n'


def executable_tokens(text: str, c_source: bool = False) -> list[str]:
    return TOKEN.findall(strip_comments(text, c_source))


def strip_python(text: str) -> str:
    lines = text.splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            lines[row - 1] = lines[row - 1][:col] + '\n'
    result = ''.join(lines)
    tree = ast.parse(result)
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        node = tree.body[0]
        lines = result.splitlines(keepends=True)
        for row in range(node.lineno - 1, node.end_lineno):
            lines[row] = '\n'
        result = ''.join(lines)
    before, after = ast.parse(text), ast.parse(result)
    if ast.get_docstring(before):
        before.body.pop(0)
    assert ast.dump(before) == ast.dump(after)
    return compact(result)


def main() -> None:
    if DEST.exists():
        raise SystemExit(f'Refusing to replace an existing frozen release: {DEST}')
    archive = subprocess.check_output([
        'git', 'archive', '--format=zip', REF, 'LICENSE',
        'instrec_fpga/src', 'instrec_fpga/ipcore', 'instrec_fpga/constraints',
        'instrec_fpga/scripts', 'instrec_fpga/sw', 'instrec_fpga/reports', 'cpu/rtl',
    ], cwd=ROOT)
    zip_ = zipfile.ZipFile(io.BytesIO(archive))
    blobs = {name: zip_.read(name) for name in zip_.namelist() if not name.endswith('/')}
    build_manifest = json.loads((RUN / 'source-manifest.json').read_text(encoding='utf-8-sig'))
    build_hashes = {}
    for row in build_manifest['Files']:
        relative = Path(row['Path']).relative_to(ROOT).as_posix()
        build_hashes[relative] = row['Sha256'].lower()
        if '/scripts/' in relative:
            continue
        source = blobs[relative]
        disk = (ROOT / relative).read_bytes()
        assert (digest(source) == row['Sha256'].lower()
                or (digest(disk) == row['Sha256'].lower()
                    and source.replace(b'\r\n', b'\n') == disk.replace(b'\r\n', b'\n'))), relative

    modules = {}
    for name, data in blobs.items():
        if name.endswith(('.v', '.sv')) and '/ipcore/' not in name:
            text = strip_comments(data.decode('latin1'))
            declaration = re.search(r'\bmodule\s+(\w+)', text)
            if declaration:
                modules[declaration[1]] = (name, text)
    used, pending = set(), ['instrec_top']
    while pending:
        module = pending.pop()
        if module in used:
            continue
        used.add(module)
        _, text = modules[module]
        for dependency in modules:
            if dependency != module and re.search(r'\b' + re.escape(dependency) + r'\s*(?:#\s*\(|[A-Za-z_]\w*\s*\()', text):
                pending.append(dependency)
    selected = {modules[module][0] for module in used}
    combined = '\n'.join(modules[module][1] for module in used)
    table_names = set(re.findall(r'"([^"\n]+\.hex)"', combined))
    for name in table_names:
        if name.startswith('src/'):
            selected.add('instrec_fpga/' + name)
        else:
            candidates = [key for key in blobs if key.startswith('instrec_fpga/src/') and key.endswith('/' + name)]
            assert len(candidates) == 1, (name, candidates)
            selected.add(candidates[0])
    config = json.loads(blobs['instrec_fpga/scripts/build_sets.json'])['sets']['full']
    config['ip_cores'] = ['ipcore/pll/pll.idf', 'ipcore/ddr3_test/ddr3_test.idf']
    selected.update('instrec_fpga/' + name for name in config['constraints'])
    for ip in config['ip_cores']:
        path = 'instrec_fpga/' + ip
        selected.add(path)
        xml = ET.fromstring(blobs[path])
        selected.update(str(PurePosixPath(path).parent / row.attrib['pathname'])
                        for row in xml.findall('.//file_list/source/file'))
    selected.update(name for name in blobs if name.startswith('instrec_fpga/sw/rv32/'))
    tools = ['run_pds_full.ps1', 'build_full.tcl', 'build_rv32_sw.py', 'weight_upload.py', 'board_check.py', 'check_rtl.py']
    selected.update('instrec_fpga/scripts/' + name for name in tools)
    selected.update(['instrec_fpga/scripts/outputs/weights_image.bin',
                     'instrec_fpga/scripts/outputs/layer_contract.json', 'LICENSE'])
    assert selected <= blobs.keys(), sorted(selected - blobs.keys())

    DEST.mkdir(parents=True)
    provenance = []
    designs = []
    for original in sorted(selected):
        relative = original.removeprefix('instrec_fpga/')
        if original.startswith('cpu/rtl/'):
            relative = 'src/cpu/core/' + PurePosixPath(original).name
        data = blobs[original]
        cleaned = data
        suffix = PurePosixPath(original).suffix
        if suffix in ('.v', '.sv', '.c', '.S', '.ld') and '/ipcore/' not in original:
            text = decode_source(data)
            result = compact(strip_comments(text, suffix in ('.c', '.S', '.ld')))
            if suffix in ('.v', '.sv'):
                result = '// ' + PurePosixPath(original).name + '\n' + result
            assert executable_tokens(text, suffix in ('.c', '.S', '.ld')) == executable_tokens(result, suffix in ('.c', '.S', '.ld')), original
            cleaned = result.encode('utf-8')
        elif suffix == '.py':
            cleaned = strip_python(data.decode('utf-8-sig')).encode('utf-8')
        elif suffix in ('.fdc', '.tcl'):
            text = decode_source(data)
            cleaned = compact('\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))).encode('utf-8')
            if original.endswith('/build_full.tcl'):
                cleaned = b'# Project: __PROJECT_NAME__\n' + cleaned
        if suffix in ('.v', '.sv') and '/ipcore/' not in original:
            designs.append(relative)
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(cleaned)
        provenance.append({'path': relative, 'origin': original, 'git_source_sha256': digest(data),
                           'original_build_sha256': build_hashes.get(original),
                           'sha256': digest(cleaned), 'comment_cleanup': data != cleaned})

    # PowerShell comment extents come from its parser, preserving string literals.
    runner = DEST / 'scripts/run_pds_full.ps1'
    ps_script = '''$p = $args[0]
$tokens = $null; $errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw ($errors | Out-String) }
$s = [System.IO.File]::ReadAllText($p)
foreach ($t in @($tokens | Where-Object { $_.Kind -eq 'Comment' } | Sort-Object { $_.Extent.StartOffset } -Descending)) {
    $s = $s.Remove($t.Extent.StartOffset, $t.Extent.EndOffset - $t.Extent.StartOffset)
}
[System.IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding($false)))
'''
    helper = APP / 'build/strip_release_ps_comments.ps1'
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(ps_script, encoding='utf-8')
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper), str(runner)], check=True)
    runner_text = compact(runner.read_text(encoding='utf-8'))
    runner_text = runner_text.replace("$lines[$li].Trim() -eq $nextStage", "$lines[$li].Trim() -match ('^' + [regex]::Escape($nextStage) + '(\\s|$)')")
    runner.write_text(runner_text, encoding='utf-8')
    config['sources'] = sorted(designs)
    config['ip_cores'] = ['ipcore/pll/pll.idf', 'ipcore/ddr3_test/ddr3_test.idf']
    config['hex_dirs'] = ['src/mel', 'src/ui', 'src/cpu']
    (DEST / 'scripts/build_sets.json').write_text(json.dumps({'schema': 1, 'sets': {'full': config}}, indent=2) + '\n', encoding='utf-8')
    for row in provenance:
        row['sha256'] = digest((DEST / row['path']).read_bytes())
    bitstream = (RUN / 'generate_bitstream/instrec_top.sbit').read_bytes()
    assert digest(bitstream) == '1497faf47b83b64a62027c38b6bf94d12112002c250fc5278c3c28ad2fa46abe'
    (DEST / 'artifacts').mkdir()
    (DEST / 'artifacts/instrec_top.sbit').write_bytes(bitstream)
    timing = json.loads(blobs['instrec_fpga/reports/pcm1808_mel_split_timing_20261103.json'])
    lock = {
        'name': 'PaceRV CPU + NPU eight-class recognizer', 'version': '2026-11-03-afternoon',
        'source_commit': REF, 'source_commit_local_time': '2026-11-03 17:23:50 +08:00',
        'original_build': '20261103-152639-fb2ffc99', 'top_module': 'instrec_top',
        'device': 'PG2L100H-6IFBG676', 'scope': 'Frozen implemented eight-class CPU/NPU application; excludes scripted demo, group5 and Flash expansion',
        'cpu': {'isa': 'RV32I', 'ENABLE_M': 0, 'ENABLE_PREDICTOR': 0, 'rom_bytes': 8192, 'ram_bytes': 8192},
        'input': 'PCM1808 master: 48kHz stereo, 24 significant bits in 32-bit slots; FPGA slave, 147/160 FIR to 44.1kHz',
        'classes_zh': json.loads(blobs['instrec_fpga/scripts/outputs/layer_contract.json'])['classes']['names_zh'],
        'bitstream_sha256': digest(bitstream), 'weights_sha256': digest(blobs['instrec_fpga/scripts/outputs/weights_image.bin']),
        'resources': {'lut': 33967, 'ff': 35466, 'drm': 150.5, 'apm': 92},
        'original_verification': {'program': 'PASS', 'boot_mmio_isa_ddr': 'PASS', 'weights': 'WOK FA0D5236',
            'continuous_inferences_30s': 10, 'hdmi_user_feedback': 'normal waveform/spectrum/dashboard',
            'manual_reset_weight_reload': 'PASS', 'recognition_accuracy': 'not measured; repeated top1=6 observed',
            'timing_meets_constraints': timing['meets_constraints'], 'timing_violations': timing['violations']},
        'cleanup': 'Unreferenced modules and tables omitted; executable tokens preserved; synthesis directives, vendor IP and license retained; paths localized in explicit build set',
        'source_files': provenance,
    }
    (DEST / 'SOURCE_LOCK.json').write_text(json.dumps(lock, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (DEST / '.gitignore').write_text('build/\nreports/\n__pycache__/\n*.pyc\n', encoding='utf-8')
    print(f'Exported {len(provenance)} files, {len(designs)} application/CPU modules -> {DEST}')


if __name__ == '__main__':
    main()
