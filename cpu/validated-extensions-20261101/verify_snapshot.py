"""Verify the immutable source snapshot without installed FPGA tools (Python 3.11+)."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / 'SNAPSHOT_MANIFEST.json').read_text(encoding='utf-8-sig'))
    total = 0
    for row in manifest['entries']:
        path = (ROOT / row['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise RuntimeError(f"Missing or invalid snapshot entry: {row['path']}")
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != row['bytes'] or digest.lower() != row['sha256'].lower():
            raise RuntimeError(f"Snapshot mismatch: {row['path']}")
        total += row['bytes']
    print(f"SNAPSHOT_PASS files={len(manifest['entries'])} bytes={total}")


if __name__ == '__main__':
    main()
