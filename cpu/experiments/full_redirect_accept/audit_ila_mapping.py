import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from ila_pipeline_minimal_config import validate_config

STAGE = Path(__file__).resolve().parent / "build/ila/20260910-redirect-accept-seed2"
SOURCE = Path(__file__).resolve().parent / "build/pds/20260910-230437-872a1ac3"


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


FIRMWARE_HASHES = {False: "3A81494C1DA8B88799246300426A351FE5FFC1462D5334F05942A0F66F5E458C",
                   True: "2ADF9F2AE73D10112FE9AB105E1C22D342701E625A69C452150D6296E7A0C046"}



def normalize_pipeline_mapping(netlist, fic, output):
    modules = re.findall(r"\bmodule rv32_core\b(.*?)\bendmodule\b", netlist, re.S)
    require(len(modules) == 1, "CPU module missing or ambiguous")
    drivers = {}
    aliases = {}
    for index, register in enumerate(("if_valid", "id_valid", "ex_valid", "mem_valid")):
        pattern = (r"\bGTP_DFF_C\s*/\*\s*" + register + r"\s*\*/\s*#\([^;]*?\)\s*"
                   + register + r"\s*\(\s*\.Q\s*\(pipeline_valid\[" + str(index) + r"\]\)")
        require(len(re.findall(pattern, modules[0], re.S)) == 1, "Wrong pipeline register driver: " + register)
        drivers[index] = f"board/soc/core/pipeline_valid[{index}]"
        if index == 1:
            instances = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", netlist, re.S)
            require(len(instances) == 1, "CPU instance missing or ambiguous")
            connections = re.findall(r"\.pipeline_valid\s*\(\{([^}]+)\}\)", instances[0])
            require(len(connections) == 1, "Missing pipeline output connection")
            bits = [bit.strip() for bit in connections[0].split(",")]
            require(len(bits) == 5 and bits[-2] == "unused_pipeline_valid[1]", "Wrong ID-valid alias connection")
            actual = "board/soc/unused_pipeline_valid[1]"
            aliases[actual] = drivers[index]
            drivers[index] = actual
        require(f"Project.unit<0>.dataChannel<{32 + index}>={drivers[index]}" in fic, "Missing pipeline data channel")
    actual = drivers[3]
    canonical = "board/soc/unused_pipeline_valid[3]"
    aliases[actual] = canonical
    for actual, canonical in aliases.items():
        fic = fic.replace(actual, canonical)
        output = output.replace(actual, canonical)
    return fic, output, aliases


def audit(stage=STAGE, source=SOURCE, validation=False, scope=False):
    require(stage.resolve().is_relative_to((Path(__file__).resolve().parent / "build/ila").resolve()), "Unexpected ILA workspace")
    snapshot = json.loads((stage / "source-snapshot.json").read_text(encoding="utf-8-sig"))
    require(Path(snapshot["Root"]).resolve() == (source / "source").resolve(), "Unexpected source root")
    for relative, expected in snapshot["Files"].items():
        require(digest(source / "source" / relative) == expected, "Source changed: " + relative)
    require(snapshot["Files"]["rtl/rv32_core.sv"] == "FB691C04B9221F0DDEB7EF897F5C30D052128696051E62BEB4BD646C0F335B01", "Wrong CPU")
    experiment = Path(__file__).resolve().parent
    delta = json.loads((experiment / "source-inputs.json").read_text(encoding="utf-8"))
    for relative, expected in delta["source_hashes"].items():
        require(digest(experiment / relative) == expected, "Current RTL changed: " + relative)
        require(digest(source / "source" / relative) == expected, "PDS RTL changed: " + relative)
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
        require(digest(stage / target) == digest(source / original), "Staged input differs: " + target)
    require(not (scope and validation), "Scope and CoreMark validation are mutually exclusive")
    application = None
    if scope:
        from audit_scope_firmware import audit as audit_scope
        from audit_binding import audit as audit_physical
        application = audit_scope(stage / "firmware.hex")
        audit_physical(source, scope=True)
    else:
        require(digest(stage / "firmware.hex") == FIRMWARE_HASHES[validation], "Wrong CoreMark firmware")
        firmware = json.loads((experiment.parent / "full_mul_precompute_clock154285/build" / ("coremark_v" + str(int(validation)) + "_i6000_p2700000_f154285714_rv32gcc_rv32im_O3_unroll_relax.build.json")).read_text(encoding="utf-8-sig"))
        require(firmware["ClockHz"] == 154285714 and firmware["Iterations"] == 6000 and firmware["ValidationRun"] is validation, "Wrong firmware configuration")
        require(firmware["EnableM"] == 1 and "-DCPU_CLOCK_HZ=154285714u" in firmware["Flags"], "Wrong firmware ISA or clock flags")
        require(digest(stage / "firmware.hex") == firmware["HexSha256"], "Firmware does not match manifest")
    netlist = (stage / "netlist.v").read_text(encoding="utf-8-sig")
    fic = (stage / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
    output = (stage / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig")
    errors = (stage / "verify-remapped.stderr.txt").read_text(encoding="utf-8-sig")
    require(not errors.strip(), "Inserter stderr is not empty")
    adf_paths = re.findall(r"^Project.device.designInputFile=(.+)$", fic, re.M)
    require(len(adf_paths) == 1 and Path(adf_paths[0].strip()).resolve() == (stage / "source.adf").resolve(), "FIC references wrong ADF")
    fic, output, aliases = normalize_pipeline_mapping(netlist, fic, output)
    result = validate_config(fic, output)
    result.update({"schema": 1, "alias_proof": "native if/id/ex/mem register Q drivers and actual Inserter output", "aliases": aliases, "source_build": str(source), "clock_hz": 154285714, "full_score_qualified": False})
    if application is not None:
        result["application_firmware"] = application
    result["sha256"] = {name: digest(stage / name) for name in (*copies, "cpu-remapped.fic", "verify-remapped.stdout.txt", "verify-remapped.stderr.txt", "source-snapshot.json")}
    (stage / "mapping-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, default=STAGE)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--scope", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.stage, arguments.source, arguments.validation, arguments.scope), indent=2))

