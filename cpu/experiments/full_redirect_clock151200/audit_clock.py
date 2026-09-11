import json
from pathlib import Path

from audit_short import digest, require

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_redirect_prime"
CLOCK_HZ = 151200000


def audit_sources():
    metadata = json.loads((ROOT / "source-inputs.json").read_text(encoding="utf-8"))
    configuration = json.loads((ROOT / "configuration.json").read_text(encoding="utf-8"))
    parent_configuration = json.loads((PARENT / "configuration.json").read_text(encoding="utf-8"))
    require(configuration["ClockHz"] == CLOCK_HZ, "Wrong candidate clock")
    require(parent_configuration["ClockHz"] == 154285714, "Wrong parent clock")
    require(set(configuration) == set(parent_configuration), "Configuration fields differ")
    require({name for name in configuration if configuration[name] != parent_configuration[name]} == {"Purpose", "ClockHz"}, "Non-clock configuration change")
    expected = metadata["source_hashes"]
    actual_names = {filename.relative_to(ROOT).as_posix() for folder, suffix in (("rtl", "*.sv"), ("fpga", "*.sv"), ("constraints", "*.fdc")) for filename in (ROOT / folder).glob(suffix)}
    require(len(expected) == 20 and set(expected) == actual_names, "Physical source set differs")
    require(metadata["changed_physical_inputs"] == [] and metadata["parent_hashes"] == expected, "Unexpected physical delta")
    for relative, value in expected.items():
        require(digest(ROOT / relative) == value == digest(PARENT / relative), "Changed physical source: " + relative)
    return configuration


def validate_firmware(manifest, validation, iterations):
    require(manifest["ClockHz"] == CLOCK_HZ and manifest["Iterations"] == iterations, "Wrong firmware clock or duration")
    require(manifest["ValidationRun"] is validation, "Wrong firmware validation seed")
    require(manifest["EnableM"] == 1 and manifest["Isa"] == "rv32im", "Wrong firmware ISA")
    require(manifest["UpstreamRevision"] == "1f483d5b8316753a742cbf5590caf5bd0a4e4777", "Wrong benchmark revision")
    clock_flags = [flag for flag in manifest["Flags"] if flag.startswith("-DCPU_CLOCK_HZ=")]
    require(clock_flags == ["-DCPU_CLOCK_HZ=151200000u"], "Wrong or duplicate firmware clock flags")
    require(manifest["ConsoleDelayCycles"] == (2700000 if iterations == 6000 else 0), "Wrong console pacing")
    require(manifest["Optimization"] == "O3" and manifest["UnrollLoops"] is True and manifest["LinkerRelaxation"] is True and manifest["LinkTimeOptimization"] is False, "Wrong compiler configuration")
    return True


if __name__ == "__main__":
    print(json.dumps(audit_sources(), indent=2))
