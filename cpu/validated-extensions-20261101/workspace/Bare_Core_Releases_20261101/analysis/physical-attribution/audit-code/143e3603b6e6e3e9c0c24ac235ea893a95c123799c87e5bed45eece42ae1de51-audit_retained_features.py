"""Verify preserved architectural feature cones in an actual final physical export."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(path):
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    if digest(report["source"]) != report["source_sha256"]:
        raise ValueError("Actual physical export changed after the area audit")
    if digest(report["native_report"]["path"]) != report["native_report"]["sha256"]:
        raise ValueError("Actual native route report changed after the area audit")
    binding = report["physical_build_binding"]
    if digest(binding["manifest"]) != binding["manifest_sha256"]:
        raise ValueError("Physical build manifest changed after the area audit")
    core_cells = [cell for cell in report["cells"] if cell["region"] == "core"]
    features = {}
    for counter in ("mcycle", "minstret"):
        bits = {}
        for cell in core_cells:
            match = re.search(r"/machine/" + counter + r"\[(\d+)\]", cell["provenance"])
            if cell["resource"] == "FF" and match:
                bits.setdefault(int(match[1]), []).append({key: cell[key] for key in ("physical_instance", "provenance", "ports")})
        if set(bits) != set(range(64)):
            raise ValueError("Not all 64 actual counter flip-flop bits remain: " + counter)
        features[counter] = {"retained_bit_indices": sorted(bits), "physical_flip_flops": {str(bit): cells for bit, cells in bits.items()},
                             "all_64_bits_present": True}
    for name, marker in (("rvc_frontend", "/frontend/"), ("rvc_expand", "/expand/"),
                         ("predictor", "/predictor/"), ("return_stack", "/predictor/return_stack."), ("multiply_divide", "/multiply_divide.unit/"),
                         ("machine_csrs_exceptions_interrupt_logic", "/machine/"), ("decoder", "/decoder/"), ("alu", "/alu/")):
        selected = [cell for cell in core_cells if marker in cell["provenance"]]
        if not selected:
            raise ValueError("A required physical core feature cone disappeared: " + name)
        resources = {kind: sum(cell["resource"] == kind for cell in selected) for kind in ("LUT6", "FF", "DistributedRAM", "APM")}
        features[name] = {"retained_physical_cells": len(selected), "resources": resources,
                          "examples": [{key: cell[key] for key in ("physical_instance", "provenance")} for cell in selected[:3]]}
    register_file = [cell for cell in core_cells if re.search(r"/registers_\d+/", cell["provenance"]) and cell["resource"] == "DistributedRAM"]
    if not register_file:
        raise ValueError("Actual register-file memory sites are missing")
    features["register_file"] = {"physical_ram_slots": len(register_file),
                                 "cells": [{key: cell[key] for key in ("physical_instance", "provenance")} for cell in register_file]}
    return {"schema": "bare-core-physical-feature-preservation/v1", "status": "PASS",
            "release": binding["release"], "physical_build_directory": binding["build_directory"],
            "inventory": str(path), "inventory_sha256": digest(path), "physical_export_sha256": report["source_sha256"],
            "source_closure": binding["core_source_joins"], "parameters": binding["parameters"],
            "features": features,
            "scope": "Actual physical site/provenance presence plus exact unchanged core source identity; behavioral qualification is the separate extraction miter and original full source simulation",
            "hardware_measurement": False, "audit_script_sha256": digest(__file__)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.inventory.resolve())
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if json.loads(args.output.read_text(encoding="utf-8")) != result:
            raise ValueError("Feature receipt reopening failed")
        print("PHYSICAL_FEATURE_PASS release=" + result["release"] + " mcycle_bits=64 minstret_bits=64 cones=8")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("PHYSICAL_FEATURE_FAIL " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
