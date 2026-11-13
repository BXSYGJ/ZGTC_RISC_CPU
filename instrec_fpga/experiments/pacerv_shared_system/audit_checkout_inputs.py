"""Check that Git checkout bytes reproduce every input of a selected PDS build."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_directory', type=Path)
    args = parser.parse_args()
    manifest_path = args.build_directory.resolve(strict=True) / 'INPUTS.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    report = {'manifest': str(manifest_path),
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'inputs': [], 'passed': False}
    for entry in manifest['files']:
        command = ['git', 'cat-file', '--filters', ':instrec_fpga/' + entry['path']]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
        actual = hashlib.sha256(run.stdout).hexdigest() if run.returncode == 0 else None
        report['inputs'].append({'path': entry['path'], 'expected_sha256': entry['sha256'],
                                 'checkout_sha256': actual, 'exit_status': run.returncode,
                                 'matches': actual == entry['sha256']})
    report['passed'] = all(item['matches'] for item in report['inputs'])
    out = args.build_directory.resolve() / 'CHECKOUT_INPUT_AUDIT.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    mismatches = [item['path'] for item in report['inputs'] if not item['matches']]
    print(f'CHECKOUT_INPUTS total={len(report["inputs"])} mismatches={len(mismatches)}')
    if mismatches:
        print(json.dumps(mismatches, indent=2))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
