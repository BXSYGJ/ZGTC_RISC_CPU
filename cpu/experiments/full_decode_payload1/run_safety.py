import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "build/safety-complete"
SUITES = {"test_decode_payload.py": 4, "test_source_delta.py": 5, "test_prefetch_valid.py": 5, "test_return_stack.py": 3, "test_commit_gate.py": 2}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inputs():
    names = list(SUITES) + ["run_safety.py", "rv32_core.sv", "rv32_btb.sv", "change-receipt.json", "decode_payload_tb.sv", "redirect_prime_tb.sv", "prefetch_valid.S", "prefetch_valid_tb.sv", "prefetch_gate_tb.sv.in", "precompute_stall.S", "precompute_stall_tb.sv", "return_stack_tb.sv"]
    names += ["../full_mul_prefetch_valid1/" + name for name in ("rv32_core.sv", "rv32_btb.sv")]
    names += ["../full_mul_precompute/build/riscv32-toolchain.json", "../full_redirect_clock151200/sim/isa/link.ld"]
    names += ["../full_redirect_clock151200/rtl/" + name + ".sv" for name in ("rv32_core", "rv32_btb", "rv32_machine", "rv32_decode", "rv32_alu", "rv32_muldiv")]
    return {name: digest(ROOT / name) for name in names}


def audit():
    record = json.loads((OUTPUT / "manifest.json").read_text())
    require(record["passed"] is True and record["inputs"] == inputs(), "Safety source set changed or run incomplete")
    require(record["suite_counts"] == SUITES, "Wrong safety suite coverage")
    require(digest(OUTPUT / "runner-original.py") == digest(Path(__file__)), "Safety runner changed")
    require(set(record["outputs"]) == {name + ".log" for name in SUITES}, "Incomplete safety logs")
    for suite, count in SUITES.items():
        log = OUTPUT / (suite + ".log")
        require(digest(log) == record["outputs"][log.name], "Safety output changed")
        text = log.read_text()
        require(re.search(r"^Ran " + str(count) + r" tests in ", text, re.M) is not None and re.search(r"^OK$", text, re.M) is not None, "Raw unittest completion missing")
    return {"manifest_sha256": digest(OUTPUT / "manifest.json"), "methods": sum(SUITES.values()), "scope": "source-bound decode-payload differential, multiplier, predictor and commit tests; not exhaustive proof"}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    record = {"schema": 1, "passed": False, "inputs": inputs(), "suite_counts": SUITES, "outputs": {}}
    shutil.copyfile(Path(__file__), OUTPUT / "runner-original.py")
    manifest = OUTPUT / "manifest.json"
    manifest.write_text(json.dumps(record, indent=2) + chr(10))
    for suite in SUITES:
        result = subprocess.run([sys.executable, str(ROOT / suite)], capture_output=True, text=True, timeout=180)
        log = OUTPUT / (suite + ".log")
        log.write_text(result.stdout + result.stderr)
        require(result.returncode == 0, "Safety suite failed: " + suite)
        record["outputs"][log.name] = digest(log)
    require(record["inputs"] == inputs(), "Safety sources changed during execution")
    record["passed"] = True
    manifest.write_text(json.dumps(record, indent=2) + chr(10))
    print(json.dumps(audit(), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    if parser.parse_args().audit:
        print(json.dumps(audit(), indent=2))
    else:
        main()
