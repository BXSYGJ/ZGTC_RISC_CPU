import argparse
import hashlib
import json
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MANIFEST = "PACKAGE_MANIFEST.json"


def safe_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or str(path) != name:
        raise ValueError(f"Unsafe archive path: {name}")
    return name


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_file(root, name):
    safe_name(name)
    candidate = root.joinpath(*PurePosixPath(name).parts)
    if not candidate.is_file() or any(part.is_symlink() for part in (candidate, *candidate.parents)):
        raise ValueError(f"Missing file or symbolic link: {name}")
    candidate.resolve().relative_to(root.resolve())
    if candidate.stat().st_size > MAX_FILE:
        raise ValueError(f"File exceeds package limit: {name}")
    return candidate


def collect(root):
    names = {"README.md", "LICENSE", "cpu/README.md", "cpu/docs/FINAL_REPORT.md", "cpu/docs/DELIVERY.md"}
    for folder in ("rtl", "fpga", "sim", "sw", "scripts", "constraints", "docs"):
        base = root / "cpu" / folder
        for path in base.rglob("*"):
            if "__pycache__" not in path.parts and path.is_file() and path.suffix in (".sv", ".v", ".ps1", ".py", ".json", ".tcl", ".in", ".c", ".h", ".S", ".ld", ".fdc", ".md"):
                names.add(path.relative_to(root).as_posix())
    builds = ("20260906-084257-19eabaa6", "20260906-085652-923daadd", "20260906-090117-f30c955c",
              "20260906-045333-71b3fa93", "20260906-053005-95ba4365", "20260906-052715-72552263",
              "20260906-054530-890e77ff", "20260906-101502-edfc3c44",
              "20260906-104204-5211e88d", "20260906-104810-9afe8b00")
    for build in builds:
        prefix = f"cpu/build/pds/{build}"
        manifest = json.loads(source_file(root, prefix + "/manifest.json").read_text(encoding="utf-8-sig"))
        if manifest["Device"] != "PG2L200H-6FBB676" or not manifest["TimingConstraintsMet"]:
            raise ValueError(f"Unaccepted hardware implementation: {build}")
        for relative, key in (("generate_bitstream/pds_soc_top.sbit", "BitstreamSha256"), ("firmware.hex", "FirmwareSha256")):
            name = prefix + "/" + relative
            if sha256(source_file(root, name).read_bytes()).upper() != manifest[key].upper():
                raise ValueError(f"Artifact identity mismatch: {name}")
            names.add(name)
        for relative in ("manifest.json", "report_timing/pds_soc_top.rtr", "pds_soc_top.v", "build.tcl"):
            names.add(prefix + "/" + relative)
        resource = prefix + "/resource-summary.json"
        if (root / resource).is_file():
            names.add(resource)
    stems = [f"coremark-box5-{mode}-r{run}" for mode in ("f162", "cache0", "cache1", "bp0") for run in (1, 2)]
    stems += ["coremark-box5-f162-validation-r1", "coremark-box5-f162-stress-r2"]
    stems += [f"coremark-box3-f180-loadbubble-{suffix}" for suffix in ("r1", "r2", "validation-r1", "stress-r1", "stress-r2")]
    for stem in stems:
        for suffix in (".uart", ".json", "-session.txt"):
            names.add("cpu/build/hardware/" + stem + suffix)
    for suffix in ("r2", "validation-r1", "stress-r1", "stress-r2"):
        names.add(f"cpu/build/hardware/coremark-box3-f180-loadbubble-{suffix}-boot-session.txt")
    for name in ("f162-evidence.json", "f180-evidence.json", "f180-box3-capture-sessions.json",
                 "coremark-box3-f180-precommand-session.txt", "frequency-resource-audit.json", "pds-frequency-search.json",
                 "coremark-box5-f162-stress-r1.uart", "coremark-box5-f162-stress-r1-session.txt",
                 "ila-algorithm-captures.json", "ila-firmware-symbols.txt", "ila-algorithm-5-ui.png"):
        names.add("cpu/build/hardware/" + name)
    for index in range(6):
        names.add(f"cpu/build/hardware/ila-algorithm-{index}.csv")
    for stem in ("scope-box5-55", "scope-box5-aa"):
        names.add(f"cpu/build/hardware/{stem}.uart")
        names.add(f"cpu/build/hardware/{stem}-session.txt")
    for folder in ("ila-analysis", "scope-box5-55", "scope-box5-aa"):
        for path in (root / "cpu/build/hardware" / folder).iterdir():
            if path.is_file() and path.suffix in (".json", ".csv", ".svg", ".png"):
                names.add(path.relative_to(root).as_posix())
    ila_prefix = "cpu/build/ila/prototype"
    ila = json.loads(source_file(root, ila_prefix + "/manifest.json").read_text(encoding="utf-8-sig"))
    for relative, key in (("generate_bitstream/pds_soc_top.sbit", "BitstreamSha256"), ("cpu.fic", "FicSha256")):
        name = ila_prefix + "/" + relative
        if sha256(source_file(root, name).read_bytes()).upper() != ila[key].upper():
            raise ValueError(f"ILA artifact identity mismatch: {name}")
        names.add(name)
    names.add(ila_prefix + "/manifest.json")
    names.add(ila_prefix + "/report_timing/pds_soc_top.rtr")
    for name in ("core_list_join.c", "core_main.c", "core_matrix.c", "core_state.c", "core_util.c", "coremark.h", "LICENSE.md", "README.md"):
        names.add("cpu/build/coremark-upstream/" + name)
    names.add("cpu/build/riscv32-toolchain.json")
    for build in ("20260906-093431-81311775", "20260906-094427-8f09321a"):
        for name in ("run.json", "results.json"):
            names.add(f"cpu/build/isa/{build}/{name}")
    return {name: source_file(root, name).read_bytes() for name in sorted(names)}


def write_package(files, output):
    if MANIFEST in files or sum(map(len, files.values())) > MAX_TOTAL:
        raise ValueError("Reserved manifest or oversized package")
    entries = []
    for name, data in sorted(files.items()):
        safe_name(name)
        if len(data) > MAX_FILE:
            raise ValueError("Oversized package entry")
        entries.append({"path": name, "bytes": len(data), "sha256": sha256(data)})
    manifest = {"schema": 1, "status": "engineering_snapshot_not_final_acceptance",
                "created_utc": datetime.now(timezone.utc).isoformat(), "files": entries,
                "limitations": "Hashes check integrity, not authorship. Historical bitstreams are not claimed to reproduce byte-for-byte from current RTL. See cpu/docs/FINAL_REPORT.md."}
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
        archive.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return verify_package(output)


def verify_package(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [safe_name(entry.filename) for entry in entries]
        if len(names) != len(set(names)) or names.count(MANIFEST) != 1:
            raise ValueError("Duplicate entries or missing manifest")
        if sum(entry.file_size for entry in entries) > MAX_TOTAL:
            raise ValueError("Oversized archive")
        for entry in entries:
            if entry.file_size > MAX_FILE or stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                raise ValueError("Unsupported archive entry")
        manifest = json.loads(archive.read(MANIFEST))
        if manifest.get("schema") != 1 or manifest.get("status") != "engineering_snapshot_not_final_acceptance":
            raise ValueError("Unsupported package manifest")
        listed = manifest["files"]
        expected = [safe_name(entry["path"]) for entry in listed]
        if len(expected) != len(set(expected)) or set(names) != set(expected) | {MANIFEST}:
            raise ValueError("Unlisted or missing archive contents")
        for entry in listed:
            data = archive.read(entry["path"])
            if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
                raise ValueError(f"Content integrity failure: {entry['path']}")
        return {"status": manifest["status"], "files": len(listed), "bytes": sum(entry["bytes"] for entry in listed),
                "archive_sha256": sha256(Path(path).read_bytes())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        if args.project or args.output:
            parser.error("Verification cannot be combined with creation")
        result = verify_package(args.verify)
    else:
        if not args.project or not args.output:
            parser.error("Creation requires project and output")
        result = write_package(collect(args.project.resolve()), args.output)
        args.output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
