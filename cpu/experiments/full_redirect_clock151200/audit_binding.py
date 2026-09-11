import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "build/pds/20260910-233603-e3b63565"
sys.path.insert(0, str(ROOT / "scripts"))
from run_coremark_compiled import hardware_parameters
from audit_ila_mapping import FIRMWARE_HASHES


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_wrapper(text, parameters, clock_hz, firmware):
    matches = re.findall(r"rv32_board_top\s*#\((.*?)\)\s*board\s*\(", text, re.S)
    require(len(matches) == 1, "Missing or ambiguous board instance")
    pattern = r"\.([A-Z_0-9]+)\(([^()]*)\)"
    entries = re.findall(pattern, matches[0])
    require(not re.sub(pattern, "", matches[0]).replace(",", "").strip(), "Unparsed board parameters")
    actual = dict(entries)
    require(len(actual) == len(entries), "Duplicate board parameter")
    expected = dict(parameters, CLOCK_HZ=clock_hz, UART_BAUD=115200)
    require(set(actual) == set(expected) | {"INIT_FILE"}, "Wrong board parameter set")
    for name, value in expected.items():
        require(int(actual[name]) == value, "Wrong physical parameter: " + name)
    require(actual["INIT_FILE"].startswith('"') and actual["INIT_FILE"].endswith('"'), "Unquoted firmware path")
    require(Path(actual["INIT_FILE"][1:-1]).resolve() == firmware.resolve(), "Wrong physical firmware path")
    pll = re.findall(r"rv32_pll\s*#\(\.CLOCK_HZ\((\d+)\)\)\s*clock_source", text)
    require(pll == [str(clock_hz)], "Wrong PLL wrapper clock")
    direct = re.findall(r"if\((\d+)==27000000\)", text)
    require(direct == [str(clock_hz)], "Wrong direct-clock selection")
    return expected


def audit(source=SOURCE, validation=False, scope=False):
    from audit_clock import audit_sources
    audit_sources()
    require(not (scope and validation), "Scope and CoreMark validation are mutually exclusive")
    if scope:
        from audit_scope_firmware import audit as audit_scope
        audit_scope(source / "firmware.hex")
    else:
        require(digest(source / "firmware.hex") == FIRMWARE_HASHES[validation], "Wrong physical firmware seed")
    configuration = json.loads((ROOT / "configuration.json").read_text(encoding="utf-8-sig"))
    parameters = hardware_parameters(configuration)
    wrapper = source / "pds_soc_top.v"
    expected = validate_wrapper(wrapper.read_text(encoding="utf-8-sig"), parameters, configuration["ClockHz"], source / "firmware.hex")
    snapshot = json.loads((source / "source-snapshot.json").read_text(encoding="utf-8-sig"))
    for relative, value in snapshot["Files"].items():
        require(digest(source / "source" / relative) == value == digest(ROOT / relative), "Physical source changed: " + relative)
    require(('add_design "' + wrapper.as_posix() + '"') in (source / "build.tcl").read_text(encoding="utf-8-sig"), "Synthesis script does not reference wrapper")
    result = {"schema": 1, "scope": "current physical-source and parameter binding, not hardware or timing qualification",
              "clock_hz": configuration["ClockHz"], "hardware_parameters": parameters, "board_parameters": expected,
              "wrapper_sha256": digest(wrapper), "build_script_sha256": digest(source / "build.tcl"),
              "configuration_sha256": digest(ROOT / "configuration.json"), "physical_firmware_sha256": digest(source / "firmware.hex"),
              "physical_source_hashes": snapshot["Files"]}
    destination = source / "scope-configuration-binding.json" if scope else ROOT / "build" / ("configuration-binding-v1.json" if validation else "configuration-binding.json")
    text = json.dumps(result, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to overwrite changed binding")
    destination.write_text(text, encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--scope", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.source, arguments.validation, arguments.scope), indent=2))


