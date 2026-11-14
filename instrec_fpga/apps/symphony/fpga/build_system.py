"""Prepare/build the native 1080p symphony application on the frozen RTOS125 system.

Only an isolated build copy changes. The RTOS builder retains its mapped CPU ROM
audit and guarded map-to-PNR continuation. The selected historical inputs stay
byte-identical. No board programming or timing search runs here.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RTOS = ROOT / "rtos"
ASSET_NAMES = ("symphony_font.hex", "symphony_guide.hex", "symphony_library.hex")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rtos_builder():
    spec = importlib.util.spec_from_file_location("symphony_rtos_builder", RTOS / "build_system.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError("Unexpected frozen source layout: " + label)
    return text.replace(old, new, 1)


def patch_bars_data(text: str) -> str:
    text = replace_once(text, "output reg frame_ready,", "output reg frame_ready,\n    output reg frame_update,",
                        "bars_data frame-ready port")
    text = replace_once(text, "frame_ready <= 0;", "frame_ready <= 0;\n            frame_update <= 0;",
                        "bars_data pixel reset")
    text = replace_once(text, "request_sync <= {request_sync[0], request_toggle};",
                        "frame_update <= 1'b0;\n            request_sync <= {request_sync[0], request_toggle};",
                        "bars_data pixel default")
    text = replace_once(text, "frame_ready <= 1;", "frame_ready <= 1;\n                frame_update <= 1'b1;",
                        "bars_data exact frame commit")
    return text


def state_bindings() -> str:
    """The controller/renderer share only pixel-domain state and synchronous reads."""
    return """
    // Native HDMI application state; physical KEY1 no longer triggers a dump.
    wire app_page_library;
    wire [3:0] app_filter_class;
    wire [5:0] app_selected_index;
    wire [6:0] app_item_count, app_history_count;
    wire [31:0] app_result_time_ms, app_result_sequence;
    wire app_selected_valid, app_selected_bookmark;
    wire [2:0] app_selected_class;
    wire [7:0] app_selected_confidence;
    wire [31:0] app_selected_time_ms, app_selected_sequence;
    wire [5:0] app_rd_index;
    wire app_rd_all, app_rd_valid, app_rd_bookmark;
    wire [2:0] app_rd_class;
    wire [7:0] app_rd_confidence;
    wire [31:0] app_rd_time_ms, app_rd_sequence;
    wire [31:0] app_dropped_results_unused;

    symphony_state u_symphony_state (
        .pix_clk(pix_clk), .pix_rst_n(rst_pix_n), .key1_n(key1_n),
        .frame_start(vsync_pulse), .result_update(result_frame_update),
        .result_class(frame_class[2:0]),
        .result_percentages({b7,b6,b5,b4,b3,b2,b1,b0}),
        .page_library(app_page_library), .filter_class(app_filter_class),
        .selected_index(app_selected_index), .item_count(app_item_count),
        .history_count(app_history_count), .result_time_ms(app_result_time_ms),
        .result_sequence(app_result_sequence),
        .selected_valid(app_selected_valid), .selected_class(app_selected_class),
        .selected_confidence(app_selected_confidence), .selected_time_ms(app_selected_time_ms),
        .selected_sequence(app_selected_sequence), .selected_bookmark(app_selected_bookmark),
        .rd_index(app_rd_index), .rd_all(app_rd_all), .rd_valid(app_rd_valid),
        .rd_class(app_rd_class), .rd_confidence(app_rd_confidence),
        .rd_time_ms(app_rd_time_ms), .rd_sequence(app_rd_sequence), .rd_bookmark(app_rd_bookmark),
        .dropped_results(app_dropped_results_unused)
    );
"""


def patch_top(text: str) -> str:
    text = replace_once(text, "wire result_frame_ready;",
                        "wire result_frame_ready;\n    wire result_frame_update;", "frame-update wire")
    text = replace_once(text, ".frame_ready (result_frame_ready),",
                        ".frame_ready (result_frame_ready),\n        .frame_update(result_frame_update),",
                        "bars_data commit output")
    text = replace_once(text, ".key1_n          (key1_n)", ".key1_n          (1'b1)",
                        "old diagnostic key binding")
    text = replace_once(text, "dashboard_renderer u_ui_renderer (",
                        state_bindings() + "\n    symphony_renderer u_ui_renderer (", "native renderer")
    renderer_fields = """
        .page_library(app_page_library), .filter_class(app_filter_class),
        .selected_index(app_selected_index), .item_count(app_item_count),
        .history_count(app_history_count), .result_time_ms(app_result_time_ms),
        .result_sequence(app_result_sequence),
        .selected_valid(app_selected_valid), .selected_class(app_selected_class),
        .selected_confidence(app_selected_confidence), .selected_time_ms(app_selected_time_ms),
        .selected_sequence(app_selected_sequence), .selected_bookmark(app_selected_bookmark),
        .rd_index(app_rd_index), .rd_all(app_rd_all), .rd_valid(app_rd_valid),
        .rd_class(app_rd_class), .rd_confidence(app_rd_confidence),
        .rd_time_ms(app_rd_time_ms), .rd_sequence(app_rd_sequence), .rd_bookmark(app_rd_bookmark),
"""
    return replace_once(text, "        .vsync_pulse(vsync_pulse), .rgb(ui_rgb),",
                        renderer_fields + "        .vsync_pulse(vsync_pulse), .rgb(ui_rgb),",
                        "renderer state ports")


def prepare(stage: str, label: str) -> Path:
    rtos = load_rtos_builder()
    sources = sorted(HERE.glob("symphony_*.v"))
    assets = [HERE / "assets" / name for name in ASSET_NAMES]
    asset_manifest = HERE / "assets" / "ASSETS.json"
    required = [HERE / "symphony_renderer.v", HERE / "symphony_state.v", asset_manifest, *assets]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError("Native application source missing: " + str(path))
    asset_records = json.loads(asset_manifest.read_text(encoding="utf-8"))
    for asset in assets:
        if sha(asset) != asset_records["assets"][asset.name]:
            raise RuntimeError("Generated UI asset differs from ASSETS.json: " + asset.name)
    controls = [Path(__file__).resolve(), *sources, *assets, asset_manifest]
    controls += [p for p in (HERE / "gen_assets.py",) if p.is_file()]
    source_records = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
                      for p in controls]
    # Prepare and map use the same map-only recipe; full additionally continues
    # after the inherited CPU ROM audit. A prepare invocation starts no tools.
    out = rtos.prepare("map" if stage == "prepare" else stage, label)
    inputs = out / "inputs"
    shutil.copyfile(out / "INPUTS.json", out / "PREPARED_RTOS_INPUTS.json")
    shutil.copyfile(out / "build.tcl", out / "PREPARED_RTOS_BUILD.tcl")
    diffs = []
    for relative, patch in (("src/ctrl/instrec_top.v", patch_top), ("src/ui/bars_data.v", patch_bars_data)):
        path = inputs / relative
        original = path.read_text(encoding="utf-8")
        changed = patch(original)
        path.write_text(changed, encoding="utf-8", newline="\n")
        diffs.extend(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                        fromfile="rtos125/" + relative, tofile="symphony/" + relative))
    for source in [*sources, *assets]:
        target = inputs / "src/ui" / source.name
        if target.exists():
            raise RuntimeError("Native source would replace an unrelated frozen file: " + source.name)
        shutil.copyfile(source, target)
        if source.suffix == ".hex":
            shutil.copyfile(source, out / "src/ui" / source.name)
    recipe = (out / "build.tcl").read_text(encoding="utf-8")
    additions = "".join('add_design "' + (inputs / "src/ui" / source.name).as_posix() + '"\n'
                        for source in sources)
    recipe = replace_once(recipe, "set_arch ", additions + "set_arch ", "new HDL in recipe")
    if "-gplace_seed 2" not in (RTOS / "baseline125/SOURCE_BUILD_RECIPE.tcl").read_text(encoding="utf-8"):
        raise RuntimeError("Frozen placement seed changed")
    if "-fix_hold_violation_iterations 8" not in (RTOS / "baseline125/SOURCE_BUILD_RECIPE.tcl").read_text(encoding="utf-8"):
        raise RuntimeError("Frozen hold configuration changed")
    (out / "build.tcl").write_text(recipe, encoding="utf-8", newline="\n")
    (out / "APPLICATION.patch").write_text("".join(diffs), encoding="utf-8", newline="\n")
    manifest = json.loads((out / "INPUTS.json").read_text(encoding="utf-8"))
    manifest.update(scope="complete PG100 125 MHz FreeRTOS/native eight-class symphony HDMI application",
                    application="symphony-native-hdmi", requested_stage=stage,
                    application_source_files=source_records, hdmi_renderer_latency_clocks=5,
                    inference_commit="bars_data exact coherent frame commit; one-cycle pixel-domain pulse",
                    user_key={"port": "key1_n", "pin": "C23", "domain": "pix_clk", "old_diagnostic_tied_high": True},
                    placement_seed=2, hold_fix_iterations=8,
                    application_patch_sha256=sha(out / "APPLICATION.patch"),
                    prepared_rtos_inputs_sha256=sha(out / "PREPARED_RTOS_INPUTS.json"))
    manifest["added_rtl"] += ["src/ui/" + p.name for p in sources]
    manifest["application_hex"] = ["src/ui/" + p.name for p in assets]
    baseline = rtos.verify_sources()
    manifest["changed_baseline_files"] = [item["path"] for item in baseline["files"]
                                           if sha(inputs / item["path"]) != item["sha256"]]
    manifest["files"] = [{"path": p.relative_to(inputs).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
                         for p in sorted(inputs.rglob("*")) if p.is_file()]
    for record in source_records:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError("Application source changed during preparation: " + record["path"])
    (out / "INPUTS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("SYMPHONY_SYSTEM_PREPARED " + str(out), flush=True)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare", "compile", "map", "full"), default="prepare")
    parser.add_argument("--label", default="symphony-native")
    parser.add_argument("--minutes", type=int, default=90)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", args.label) or not 1 <= args.minutes <= 240:
        parser.error("invalid build label or time limit")
    out = prepare(args.stage, args.label)
    if args.stage != "prepare":
        load_rtos_builder().run(out, args.minutes)
    manifest = json.loads((out / "INPUTS.json").read_text(encoding="utf-8"))
    for record in manifest["application_source_files"]:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError("Application source changed after freezing: " + record["path"])
    load_rtos_builder().verify_sources()
    print("SYMPHONY_SYSTEM_PASS stage=" + args.stage + " path=" + str(out), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
