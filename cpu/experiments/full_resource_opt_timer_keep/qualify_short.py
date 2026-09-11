import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "build/full-resource-opt-timer-keep-stage"
sys.path.insert(0, str(STAGE / "scripts"))
from run_coremark_compiled import check_simulation_result, file_hash, verify_artifacts


def audit():
    accepted = ROOT / "build/regfile-valid-fanout-stage"
    source = json.loads((accepted / "build/pds/20260909-124605-a402f7e8/source-snapshot.json").read_text(encoding="utf-8-sig"))
    expected = dict(source["Files"])
    expected["rtl/rv32_peripherals.sv"] = file_hash(Path(__file__).parent / "rv32_peripherals.sv")
    for relative, digest in expected.items():
        if file_hash(STAGE / relative).upper() != digest.upper():
            raise ValueError("Unexpected full-function source change: " + relative)
    results = []
    for mode, reference in [(False,"20260909-124427-6703b76c"), (True,"20260909-124442-609daef4")]:
        candidates = []
        for directory in (STAGE / "build/compiled").iterdir():
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
            firmware = manifest["FirmwareBuild"]
            if (manifest["SimulationPassed"] and firmware["ValidationRun"] == mode
                    and firmware["Iterations"] == 10 and firmware["ConsoleDelayCycles"] == 0):
                candidates.append((directory, manifest))
        if len(candidates) != 1:
            raise ValueError("Need one completed short run per dataset")
        directory, manifest = candidates[0]
        if manifest["FirmwareBuild"]["Iterations"] != 10 or not manifest["ImplementationInputsBound"]:
            raise ValueError("Wrong short-run scope")
        verify_artifacts(directory, manifest)
        for relative, digest in manifest["SourceSnapshot"].items():
            if file_hash(STAGE / relative).upper() != digest.upper():
                raise ValueError("Runtime source changed: " + relative)
        actual = check_simulation_result((directory / "coremark.sim.uart").read_text(), manifest["FirmwareBuild"], manifest["HardwareParameters"], True)
        baseline = accepted / "build/compiled" / reference
        original = json.loads((baseline / "manifest.json").read_text(encoding="utf-8-sig"))
        verify_artifacts(baseline, original)
        target = check_simulation_result((baseline / "coremark.sim.uart").read_text(), original["FirmwareBuild"], original["HardwareParameters"], True)
        if actual != target or manifest["FirmwareSha256"].upper() != original["FirmwareSha256"].upper():
            raise ValueError("Short-run behavior or firmware regressed")
        results.append({"run":directory.name,"reference":reference,"manifest_sha256":file_hash(directory / "manifest.json"),"result":actual})
    result = {"scope":"complete_peripherals_paired_short_only","source_files":expected,"results":results,"paired_short_passed":True,"inserted_ila_validated":False,"full_score_qualified":False}
    (STAGE / "build/short-qualification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    audit()
