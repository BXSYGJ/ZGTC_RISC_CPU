"""Create a fresh, relocated build workspace; never edit the archived evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

RELEASES = ('Original_155250', 'H3_Retained_145125', 'H3_Base_145125')
ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8-sig')


def check(path, digest):
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual.lower() != digest.lower():
        raise RuntimeError(f'Source hash mismatch: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--release', choices=RELEASES, required=True)
    parser.add_argument('--variant', choices=('ila', 'bare'), required=True)
    parser.add_argument('--pds-root', type=Path)
    args = parser.parse_args()
    dest = args.destination.resolve()
    if dest.exists() or dest.is_relative_to(ROOT):
        raise RuntimeError('Choose a new destination outside the immutable publication folder.')
    dest.mkdir(parents=True)
    source = ROOT / 'workspace'
    folder = 'ILA_Core_Releases_20261101' if args.variant == 'ila' else 'Bare_Core_Releases_20261101'
    target = dest / folder
    shutil.copytree(source / folder / 'scripts', target / 'scripts')
    if args.variant == 'ila':
        baseline = Path('Current_Paper_and_Sub7000_Core_Releases_20261012') / 'cores' / args.release
        shutil.copytree(source / baseline, dest / baseline)
        script = target / 'scripts' / 'Build-MinimalIla.ps1'
    else:
        release = target / args.release
        original = source / folder / args.release
        shutil.copytree(original / 'source', release / 'source')
        manifest = read(original / 'SOURCE_MANIFEST.json')
        for row in manifest['rtl']:
            local = release / 'source' / 'rtl' / row['name']
            check(local, row['sha256'])
            row['path'] = row['source'] = str(local)
        for key in ('wrapper', 'physical_fixture', 'boundary'):
            name = Path(manifest[key]['path'].replace(chr(92), '/')).name
            local = release / 'source' / name
            check(local, manifest[key]['sha256'])
            manifest[key]['path'] = str(local)
        # This is newly generated preparation metadata, not an old execution receipt.
        manifest['relocation'] = {'origin_manifest': str(original / 'SOURCE_MANIFEST.json'),
                                  'purpose': 'fresh build, no validation receipt copied',
                                  'rtl_bytes_changed': False}
        write(release / 'SOURCE_MANIFEST.json', manifest)
        script = target / 'scripts' / 'Build-BareCore.ps1'
    if args.pds_root:
        pds = args.pds_root.resolve()
        if not (pds / 'bin' / 'pds_shell.exe').is_file():
            raise RuntimeError('PDS root must contain bin/pds_shell.exe.')
        if any(char in str(pds) for char in "'\r\n"):
            raise RuntimeError('PDS path contains unsupported PowerShell quote characters.')
        text = script.read_text(encoding='utf-8-sig')
        old = "[System.IO.Path]::Combine('D:/','PDS_2022.2-SP6.4','bin'"
        new = "[System.IO.Path]::Combine('" + pds.as_posix() + "','bin'"
        if text.count(old) != 1:
            raise RuntimeError('Expected exactly one PDS installation binding.')
        script.write_text(text.replace(old, new), encoding='utf-8-sig')
    receipt = {'variant': args.variant, 'release': args.release, 'workspace': str(dest),
               'build_script': str(script), 'historical_validation_copied': False,
               'build_executed': False}
    write(dest / 'REBUILD_PREPARATION.json', receipt)
    print('REBUILD_WORKSPACE_READY ' + str(dest))
    print('BUILD_SCRIPT ' + str(script))


if __name__ == '__main__':
    main()
