import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_timer_prefix16"
BASE = ROOT.parent / "full_redirect_clock151200"
FIRMWARE_PARENT = ROOT.parent / "full_mul_precompute_clock154285"
sys.path.insert(0, str(PARENT))
import audit_timer_ila as parent_audit

digest = parent_audit.digest
require = parent_audit.require


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_configuration(configuration):
    expected = load(BASE / "configuration.json")
    expected.update(Purpose="Complete timer-prefix CPU clock experiment at 153 MHz; not qualified", ClockHz=153000000)
    require(configuration == expected, "Unexpected clock configuration change")


def audit_inputs():
    record = load(ROOT / "source-inputs.json")
    parent = parent_audit.binding()
    require(record["physical_source_hashes"] == parent["physical_source_hashes"] and len(record["physical_source_hashes"]) == 20, "Incomplete or changed parent RTL inventory")
    for relative, checksum in record["physical_source_hashes"].items():
        require(digest(ROOT / relative) == checksum == digest(parent_audit.PROJECT / relative), "Clock RTL differs from full parent")
    expected_scripts = {"scripts/run_pds.ps1", "scripts/build_pds.tcl", "scripts/pds_soc_top.v.in", "scripts/pds_report.py",
                        "scripts/run_coremark_compiled.py", "scripts/check_coremark.py", "sim/coremark_compiled.cpp"}
    require(set(record["support_scripts"]) == expected_scripts, "Incomplete support script inventory")
    for relative, checksums in record["support_scripts"].items():
        require(digest(BASE / relative) == checksums["parent_sha256"] and digest(ROOT / relative) == checksums["candidate_sha256"], "Support script changed")
        content = (BASE / relative).read_bytes()
        if relative == "scripts/run_pds.ps1":
            require(content.count(b"151200000,154285714") == 1, "Wrong clock whitelist anchor")
            content = content.replace(b"151200000,154285714", b"151200000,153000000,154285714")
        if relative == "scripts/check_coremark.py":
            require(content.count(b"151200000, 154285714") == 1, "Wrong result-parser clock anchor")
            content = content.replace(b"151200000, 154285714", b"151200000, 153000000, 154285714")
        require((ROOT / relative).read_bytes() == content, "Unexpected support script edit")
    expected_firmware = {"sw/start.S", "sw/link_soc.ld", "sw/platform.h", "sw/coremark/core_portme.c", "sw/coremark/core_portme.h", "sw/coremark/ee_printf.c"}
    expected_firmware.update("build/coremark-upstream/" + name for name in ("coremark.h", "core_list_join.c", "core_main.c", "core_matrix.c", "core_state.c", "core_util.c"))
    require(set(record["firmware_sources"]) == expected_firmware, "Incomplete firmware source inventory")
    for relative, checksum in record["firmware_sources"].items():
        require(digest(ROOT / relative) == checksum == digest(FIRMWARE_PARENT / relative), "Clock firmware source changed")
    validate_configuration(load(ROOT / "configuration.json"))
    require(digest(ROOT / "configuration.json") == record["configuration_sha256"], "Clock configuration changed")
    require(digest(ROOT / "prepare_clock.py") == record["generator_sha256"], "Clock generator changed")
    require(record["clock_hz"] == 153000000 and record["parent_clock_hz"] == 151200000, "Wrong staged clocks")
    return record


if __name__ == "__main__":
    record = audit_inputs()
    print("PASS 20 unchanged physical sources, seven bound support inputs and twelve unchanged firmware sources at 153 MHz")
