import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from ila_pipeline_minimal_config import validate_config

STAGE = Path(__file__).resolve().parent / "build/ila/20260910-mul-precompute-clock154285-seed2"
SOURCE = Path(__file__).resolve().parent / "build/pds/20260910-192317-0e86d0b4"


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit():
    snapshot = json.loads((STAGE / "source-snapshot.json").read_text(encoding="utf-8-sig"))
    require(Path(snapshot["Root"]).resolve() == (SOURCE / "source").resolve(), "Unexpected source root")
    for relative, expected in snapshot["Files"].items():
        require(digest(SOURCE / "source" / relative) == expected, "Source changed: " + relative)
    require(snapshot["Files"]["rtl/rv32_core.sv"] == "8388B9EDEE1EF129E1AC37C89771A749C15FD15721D4F5A1E928CA534D9E1B4A", "Wrong CPU")
    experiment = Path(__file__).resolve().parent
    delta = json.loads((experiment / "source-inputs.json").read_text(encoding="utf-8"))
    for relative, expected in delta["source_hashes"].items():
        require(digest(experiment / relative) == expected, "Current RTL changed: " + relative)
        require(digest(SOURCE / "source" / relative) == expected, "PDS RTL changed: " + relative)
    from audit_short import main as audit_short_runs
    audit_short_runs()
    copies = {
        "source.adf": "synthesize/pds_soc_top_syn.adf",
        "netlist.v": "synthesize/pds_soc_top_syn.vm",
        "firmware.hex": "firmware.hex",
        "board.fdc": "source/constraints/board.fdc",
        "uart_remotelab.fdc": "source/constraints/uart_remotelab.fdc",
    }
    for target, original in copies.items():
        require(digest(STAGE / target) == digest(SOURCE / original), "Staged input differs: " + target)
    require(digest(STAGE / "firmware.hex") == "3A81494C1DA8B88799246300426A351FE5FFC1462D5334F05942A0F66F5E458C", "Wrong CoreMark firmware")
    firmware = json.loads((experiment / "build/coremark_v0_i6000_p2700000_f154285714_rv32gcc_rv32im_O3_unroll_relax.build.json").read_text(encoding="utf-8-sig"))
    require(firmware["ClockHz"] == 154285714 and firmware["Iterations"] == 6000 and firmware["ValidationRun"] is False, "Wrong firmware configuration")
    require(firmware["EnableM"] == 1 and "-DCPU_CLOCK_HZ=154285714u" in firmware["Flags"], "Wrong firmware ISA or clock flags")
    require(digest(STAGE / "firmware.hex") == firmware["HexSha256"], "Firmware does not match manifest")
    netlist = (STAGE / "netlist.v").read_text(encoding="utf-8-sig")
    instances = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", netlist, re.S)
    require(len(instances) == 1, "CPU instance missing or ambiguous")
    connections = re.findall(r"\.pipeline_valid\s*\(\{([^}]+)\}\)", instances[0])
    require(len(connections) == 1, "Pipeline port missing or ambiguous")
    bits = [bit.strip() for bit in connections[0].split(",")]
    require(len(bits) == 5, "Unexpected pipeline output width")
    fic = (STAGE / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
    output = (STAGE / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig")
    errors = (STAGE / "verify-remapped.stderr.txt").read_text(encoding="utf-8-sig")
    require(not errors.strip(), "Inserter stderr is not empty")
    adf_paths = re.findall(r"^Project.device.designInputFile=(.+)$", fic, re.M)
    require(len(adf_paths) == 1 and Path(adf_paths[0].strip()).resolve() == (STAGE / "source.adf").resolve(), "FIC references wrong ADF")
    aliases = {}
    for index in (0, 1):
        actual = f"board/soc/unused_pipeline_valid[{index}]"
        canonical = f"board/soc/core/pipeline_valid[{index}]"
        if f"Project.unit<0>.dataChannel<{32 + index}>={actual}" in fic:
            require(bits[-1-index] == f"unused_pipeline_valid[{index}]", "Pipeline alias does not match CPU output bit")
            aliases[actual] = canonical
            fic = fic.replace(actual, canonical)
            output = output.replace(actual, canonical)
        else:
            require(f"Project.unit<0>.dataChannel<{32 + index}>={canonical}" in fic, "Missing canonical pipeline data channel")
    result = validate_config(fic, output)
    result.update({"schema": 1, "alias_proof": "rv32_core pipeline output connection" if aliases else "canonical names confirmed by actual Inserter output", "aliases": aliases, "source_build": str(SOURCE), "clock_hz": 154285714, "full_score_qualified": False})
    result["sha256"] = {name: digest(STAGE / name) for name in (*copies, "cpu-remapped.fic", "verify-remapped.stdout.txt", "verify-remapped.stderr.txt", "source-snapshot.json")}
    (STAGE / "mapping-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
