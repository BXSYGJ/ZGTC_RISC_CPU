import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_timer_prefix16"
BASE = ROOT.parent / "full_redirect_clock151200"
FIRMWARE_PARENT = ROOT.parent / "full_mul_precompute_clock154285"
sys.path.insert(0, str(PARENT))
import audit_timer_ila as parent_audit

STAGE = PARENT / "build/ila/timer-prefix16-seed1-native-core"
digest = parent_audit.digest
require = parent_audit.require


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def prepare():
    require(not (ROOT / "source-inputs.json").exists(), "Clock project already staged")
    bound = parent_audit.binding()
    parent_audit.mapping(STAGE)
    physical = parent_audit.qualify(STAGE, audit_mapping=False, source=parent_audit.SOURCE, placement_seed=1)
    require(physical["physical_timing_passed"] is True and physical["clock_hz"] == 151200000, "Parent physical gate failed")
    sources = bound["physical_source_hashes"]
    require(len(sources) == 20, "Incomplete parent RTL inventory")
    copies = {}
    for relative, checksum in sources.items():
        original = parent_audit.PROJECT / relative
        require(digest(original) == checksum, "Parent staged RTL changed")
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        require(not destination.exists(), "Clock source already exists")
        shutil.copyfile(original, destination)
        require(digest(destination) == checksum, "Clock RTL copy differs")
        copies[relative] = checksum
    support = {}
    for relative in ("scripts/run_pds.ps1", "scripts/build_pds.tcl", "scripts/pds_soc_top.v.in", "scripts/pds_report.py",
                     "scripts/run_coremark_compiled.py", "scripts/check_coremark.py", "sim/coremark_compiled.cpp"):
        original = BASE / relative
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = original.read_bytes()
        if relative == "scripts/run_pds.ps1":
            before = b"151200000,154285714"
            require(content.count(before) == 1, "Clock whitelist anchor differs")
            content = content.replace(before, b"151200000,153000000,154285714")
        if relative == "scripts/check_coremark.py":
            before = b"151200000, 154285714"
            require(content.count(before) == 1, "Result-parser clock anchor differs")
            content = content.replace(before, b"151200000, 153000000, 154285714")
        destination.write_bytes(content)
        support[relative] = {"parent_sha256": digest(original), "candidate_sha256": digest(destination)}
    firmware_sources = ["sw/start.S", "sw/link_soc.ld", "sw/platform.h", "sw/coremark/core_portme.c", "sw/coremark/core_portme.h", "sw/coremark/ee_printf.c"]
    firmware_sources += ["build/coremark-upstream/" + name for name in ("coremark.h", "core_list_join.c", "core_main.c", "core_matrix.c", "core_state.c", "core_util.c")]
    for relative in firmware_sources:
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIRMWARE_PARENT / relative, destination)
        require(digest(destination) == digest(FIRMWARE_PARENT / relative), "Firmware source copy differs")
    configuration = read_json(BASE / "configuration.json")
    configuration.update(Purpose="Complete timer-prefix CPU clock experiment at 153 MHz; not qualified", ClockHz=153000000)
    (ROOT / "configuration.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    record = {"schema": 1, "scope": "exact parent full-system RTL; only configured clock and firmware clock change",
              "parent": str(PARENT), "parent_stage": str(STAGE), "parent_physical_qualification_sha256": digest(STAGE / "physical-qualification.json"),
              "physical_source_hashes": copies, "support_scripts": support,
              "firmware_sources": {relative: digest(ROOT / relative) for relative in firmware_sources},
              "configuration_sha256": digest(ROOT / "configuration.json"), "generator_sha256": digest(Path(__file__)),
              "parent_clock_hz": 151200000, "clock_hz": 153000000, "hardware_validated": False}
    (ROOT / "source-inputs.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("PASS identical complete-system RTL staged for 153 MHz")


if __name__ == "__main__":
    prepare()
