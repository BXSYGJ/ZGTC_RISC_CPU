"""Verify every staged PDS input against the frozen build manifest."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest",type=Path,default=HERE/"build"/"BUILD_MANIFEST.json")
    args=ap.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
    problems=[]
    for row in manifest["inputs"]:
        path=(PROJECT/row["path"]).resolve()
        if not path.is_relative_to(PROJECT.resolve()): raise ValueError("Manifest path escapes project.")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row["sha256"]:
            problems.append(row["path"])
    if problems: raise RuntimeError("Changed or missing inputs: "+", ".join(problems))
    print(f'INPUT_HASHES_OK files={len(manifest["inputs"])} target={manifest["target"]}')

if __name__=="__main__": main()
