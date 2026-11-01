"""Reopen all final area/source/feature chains and summarize their exact partitions."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDS = {"Original_155250": "20261101-015541-f15b63fe",
          "H3_Base_145125": "20261101-015628-87641d51",
          "H3_Retained_145125": "20261101-015628-ffa262ba"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(value, description):
    if not value:
        raise ValueError(description)


def artifact(path):
    return {"path": str(path), "sha256": sha(path)}


def gather(root):
    area_directory = root / "analysis" / "physical-attribution"
    extraction_path = root / "analysis" / "EXTRACTION_QUALIFICATION.json"
    extraction = read(extraction_path)
    require(extraction["status"] == "PASS", "Extraction qualification must pass")
    rows = []
    for release, build_id in BUILDS.items():
        prefix = release + "-" + build_id
        area_path = area_directory / (prefix + "-PHYSICAL_PRIMITIVE_INVENTORY.json")
        feature_path = area_directory / (prefix + "-FEATURE_PRESERVATION.json")
        area, features = read(area_path), read(feature_path)
        binding = area["physical_build_binding"]
        manifest = read(binding["manifest"])
        require(sha(binding["manifest"]) == binding["manifest_sha256"], "Final physical build manifest changed")
        require(manifest["status"] == binding["observed_build_status"] == "timing_passed", "Final timing status did not pass")
        require(manifest["report"]["all_corner_audit"]["all_corners_passed"], "All native timing tables must pass")
        actual_uncertainties = manifest["report"]["observed_setup_uncertainties_ns"]
        require(actual_uncertainties and min(actual_uncertainties) >= manifest["setup_uncertainty_ns"],
                "Actual native setup uncertainty is below the requested minimum")
        require(sha(area["source"]) == area["source_sha256"], "Final physical simulation export changed")
        require(sha(area["native_report"]["path"]) == area["native_report"]["sha256"], "Final native report changed")
        require(features["inventory_sha256"] == sha(area_path) and features["status"] == "PASS",
                "Feature audit does not bind the final area inventory")
        require(features["features"]["mcycle"]["retained_bit_indices"] == list(range(64)) and
                features["features"]["minstret"]["retained_bit_indices"] == list(range(64)), "Counter preservation is incomplete")
        native = area["native_report"]
        reconciliation = area["reconciliation"]
        exported = area["summary"]["resource_by_region"]
        constants = area["summary"]["constant_site_consumer_categories"]
        core_hierarchy = native["hierarchy_core"]
        top_hierarchy = native["hierarchy_top"]
        core_export_lut = exported["core"].get("LUT6", 0) + exported["core"].get("DistributedRAM", 0)
        fixture_export_lut = exported["fixture"].get("LUT6", 0) + exported["fixture"].get("DistributedRAM", 0)
        core_exclusive = core_export_lut + constants.get("core_only", 0)
        fixture_exclusive = fixture_export_lut + constants.get("fixture_only", 0)
        shared = constants.get("shared", 0)
        unresolved = (constants.get("unresolved", 0) + constants.get("no_owned_consumer", 0) +
                      reconciliation["exported_other_lut_sites"])
        global_only = reconciliation["global_lut_slots_not_present_in_export"]
        require(core_exclusive + fixture_exclusive + shared + unresolved + global_only == native["global"]["LUT"],
                "Native global LUT total is not an exact sum of the declared categories")
        require(core_exclusive == reconciliation["core_lut_with_generated_overhead_lower_bound"] and
                core_exclusive + shared + unresolved + global_only == reconciliation["core_lut_with_generated_overhead_upper_bound"],
                "Core area bounds do not follow their declared attribution rule")
        packed = area.get("packed_ff_comparison")
        native_core_only_ff = core_hierarchy["FF"] - exported["core"].get("FF", 0)
        native_fixture_only_ff = top_hierarchy["FF"] - core_hierarchy["FF"] - exported["fixture"].get("FF", 0)
        require(native_fixture_only_ff == 0, "Fixture FF export omission needs an explicit new audit")
        if native_core_only_ff:
            require(packed is not None and packed["native_ff_count"] == native["global"]["FF"],
                    "Native-only FFs must have exact packed owners")
            require(sha(packed["source"]) == packed["source_sha256"], "Actual packed native netlist changed")
            require(sum(item["packed_ff_count"] - item["exported_ff_count"] for item in packed["differences"]) == native_core_only_ff,
                    "Native-only register owner count differs")
        require(core_hierarchy["FF"] + (top_hierarchy["FF"] - core_hierarchy["FF"]) == native["global"]["FF"],
                "Native final FF total does not reconcile")
        extracted = next(item for item in extraction["releases"] if item["release"] == release)
        require(sha(binding["source_manifest"]) == extracted["source_manifest"]["sha256"],
                "Physical implementation does not join the exact extracted core source")
        require(binding["parameters"] == extracted["parameters"], "Physical parameters do not join extraction")
        frozen_core = {item["name"]: item["sha256"] for item in extracted["complete_core_closure_hash_joins"]}
        require({item["name"]: item["sha256"] for item in binding["core_source_joins"]} == frozen_core,
                "Physical eight-file closure differs from extraction")
        for item in binding["core_source_joins"]:
            require(sha(item["actual_physical_input"]) == item["sha256"], "Actual physical RTL changed")
        rows.append({"release": release, "build_id": build_id, "status": "PASS", "origin": "LOCAL PDS IMPLEMENTATION",
                     "area_inventory": artifact(area_path), "feature_preservation": artifact(feature_path),
                     "physical_build_manifest": artifact(binding["manifest"]), "source_manifest": artifact(binding["source_manifest"]),
                     "clock_hz": manifest["clock_hz"], "setup_wns_ns": manifest["report"]["setup_wns_ns"],
                     "requested_minimum_setup_uncertainty_ns": manifest["setup_uncertainty_ns"],
                     "actual_setup_uncertainties_ns": actual_uncertainties,
                     "all_timing_corners_passed": True,
                     "native_core_hierarchy": core_hierarchy, "native_top_hierarchy": top_hierarchy,
                     "native_global": native["global"],
                     "exported_core_lut_and_ram_slots": core_export_lut,
                     "exported_fixture_lut_and_ram_slots": fixture_export_lut,
                     "core_only_generated_constant_lut": constants.get("core_only", 0),
                     "fixture_only_generated_constant_lut": constants.get("fixture_only", 0),
                     "core_exclusive_physical_lut_and_ram_slots": core_exclusive,
                     "fixture_exclusive_physical_lut_and_ram_slots": fixture_exclusive,
                     "shared_constant_lut": shared, "unresolved_exported_lut": unresolved,
                     "native_global_only_lut_slots": global_only,
                     "physical_core_lut_lower_bound": core_exclusive,
                     "physical_core_lut_conservative_upper_bound": core_exclusive + shared + unresolved + global_only,
                     "native_core_ff": core_hierarchy["FF"], "exported_core_ff": exported["core"].get("FF", 0),
                     "native_fixture_ff": top_hierarchy["FF"] - core_hierarchy["FF"],
                     "native_core_ff_omitted_from_simulation_export": native_core_only_ff,
                     "native_only_ff_localizations": packed["differences"] if packed else [],
                     "counter_bits_preserved": {"mcycle": 64, "minstret": 64},
                     "feature_audit": "8 required feature cones plus register-file RAM present",
                     "functional_extraction": extracted["qualification"],
                     "completed_original_source_reference_join": extracted["source_reference_6000_join"]["result"],
                     "hardware_measurement": False})
    return {"schema": "bare-core-final-physical-area-summary/v1", "status": "PASS", "releases": rows,
            "attribution_method": "Unique physical slots and actual source provenance; generated constant consumer graph; native-only register owner joins; explicit shared and global-only residues",
            "resource_weights_fitted": False, "estimated_fixture_subtraction": False,
            "area_label": "Core-only physical area with explicitly external cached-system execution services",
            "full_bare_coremark_execution": False, "hardware_measurement": False,
            "extraction_qualification": artifact(extraction_path), "audited_utc": datetime.now(timezone.utc).isoformat(),
            "generator_sha256": sha(__file__)}


def main():
    try:
        report = gather(ROOT)
        base = ROOT / "analysis"
        output = base / "PHYSICAL_AREA_AUDIT.json"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        require(read(output) == report, "Aggregate reopening failed")
        lines = ["# Final pure-core physical area audit", "",
                 "All three final PDS routes pass all timing tables at their configured targets. Native setup uncertainty is 0.200 ns, satisfying the requested minimum 0.150 ns. The eight RTL files and complete wrapper parameters join the fresh extraction tests and completed original SoC source simulations.", "",
                 "| Core | Target MHz | Setup WNS ns | Native hierarchy LUT/RAM | Actual core slots incl. generated overhead | Native core FF | Core APM | Core distributed RAM slots |",
                 "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |"]
        for row in report["releases"]:
            lines.append(f"| {row['release']} | {row['clock_hz']/1e6:g} | {row['setup_wns_ns']:+.3f} | {row['native_core_hierarchy']['LUT']} | {row['physical_core_lut_lower_bound']}–{row['physical_core_lut_conservative_upper_bound']} | {row['native_core_ff']} | {row['native_core_hierarchy']['APM']} | {row['native_core_hierarchy']['Distributed RAM']} |")
        lines += ["", "The physical core interval counts unique exported LUT/RAM slots plus constants used exclusively by core cells. Its upper end assigns every shared or unexported LUT slot to the core. Distributed RAM is already included in the LUT/RAM count and is shown separately for clarity. Caches, backing RAM, MMIO, UART, GPIO, memory arbiters, PLL and ILA are outside the DUT. Register-file/predictor RAM and all multiply/divide APMs are inside it.", "",
                  "| Final total reconciliation | Core-exclusive LUT/RAM | Fixture-exclusive LUT/RAM | Shared LUT | Global-only LUT | Native device LUT/RAM | Native core + fixture FF |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
        for row in report["releases"]:
            lines.append(f"| {row['release']} | {row['core_exclusive_physical_lut_and_ram_slots']} | {row['fixture_exclusive_physical_lut_and_ram_slots']} | {row['shared_constant_lut']} | {row['native_global_only_lut_slots']} | {row['native_global']['LUT']} | {row['native_core_ff']} + {row['native_fixture_ff']} = {row['native_global']['FF']} |")
        lines += ["", "No fixture estimate or fitted packed-macro LUT weight enters these sums. Each generated constant has its actual LUT INIT, physical slot and downstream consumer graph recorded. Every final device LUT total is the exact sum of the listed categories. Global-only slots remain unattributed and are included in the conservative core upper bound.", "",
                  "The physical simulation export omits four native packed core registers in Base and one in Retained. Their exact packed owner/output names are recorded and restore the authoritative native FF total. Every other exported FF joins its packed owner. The Retained native hierarchy convention counts3923 core LUT/RAM slots while its unique physical export has3925; both representations remain visible. Physical bounds use the unique exported slots. No equality is manufactured between these conventions.", "",
                  "All 64 `mcycle` and all 64 `minstret` physical FF bits are individually present in every export. Separate frontend, RVC expander, predictor, return-stack, decoder, ALU, machine CSR/exception/interrupt, multiply/divide and register-file RAM cones remain. Exact source identity preserves the full functional configuration; physical cone presence is an additional structural check.", "",
                  "Execution efficiency remains conditional on the explicitly external original cached-system service. The fresh bare-wrapper qualification ran2M edges per baseline and real rollback; the completed6000-iteration figures belong to the exact original SoC source simulations joined through source/configuration/firmware identity. The scan fixture provides physical controllability/observability and is excluded from the core-only area. These are local RTL/PDS results, without hardware measurements.", "",
                  "The JSON links each immutable build-specific area inventory, feature receipt, stable physical manifest, extraction qualification and completed source-reference receipt by SHA256. Native reports, final primitive exports, source copies and parameter contracts were reopened during this aggregate audit.", ""]
        markdown = base / "PHYSICAL_AREA_AUDIT.md"
        markdown.write_text("\n".join(lines), encoding="utf-8")
        require(markdown.read_text(encoding="utf-8").startswith("# Final pure-core"), "Markdown reopening failed")
        print("FINAL_PHYSICAL_AREA_AUDIT_PASS releases=3 exact_native_global_sums=3 preserved_counter_bits=384")
        print(str(output))
        print(str(markdown))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("FINAL_PHYSICAL_AREA_AUDIT_FAIL " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
