"""Prepare a frozen lower-clock system copy with matching DDR and peripheral timing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from prepare_pds import prepare, ROOT


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_one(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("Expected exactly one instance: " + old)
    return text.replace(old, new)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ddr-directory", type=Path, required=True,
                        help="A completed prepare_ddr_clock.py output directory")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    directory = args.ddr_directory.resolve(strict=True)
    clock = json.loads((directory / "RESULT.json").read_text(encoding="utf-8"))
    if not clock["commands_passed"] or not clock["live_ip_unchanged"]:
        raise ValueError("DDR generation must have passed")
    hz = int(clock["system_clock_hz"])
    if hz not in (109375000, 93750000, 83333333) or args.seed < 1:
        raise ValueError("Use an evaluated 109.375, 93.75 or 83.333333 MHz point and a positive seed")
    generated = directory / "ddr3_test"
    live_ip = ROOT / "ipcore/ddr3_test"
    for relative, expected in clock["original_ip_hashes"].items():
        if sha(live_ip / relative) != expected:
            raise ValueError("Live IP no longer matches generated-copy baseline: " + relative)
    output = prepare("full", args.seed, 12, "normal", 1)
    inputs = output / "inputs"
    original_manifest = json.loads((output / 'INPUTS.json').read_text(encoding='utf-8'))
    changed = []
    for name in ("ddr3_test.idf", "ddr3_test.v", "ddr3_test_ddrphy_top.v"):
        target = inputs / "ipcore/ddr3_test" / name
        shutil.copy2(generated / name, target)
        changed.append(target.relative_to(inputs).as_posix())

    fdc = inputs / "constraints/ddr3_100h.fdc"
    original = fdc.read_bytes()
    # Only replace generated-clock definitions using the actual regenerated IP.
    source_fdc = (generated / "pnr/ddr_test.fdc").read_text(encoding="utf-8")
    text = original.decode("utf-8")
    for name in ("rst_clk", "ddrphy_sysclk", "phy_dq_clk_0", "phy_dq_clk_1"):
        pattern = r"^create_generated_clock -name \{" + name + r"\}[^\r\n]*"
        lines = re.findall(pattern, source_fdc, re.M)
        if len(lines) != 1:
            raise ValueError("Generated clock definition missing: " + name)
        line = lines[0].replace("{I_ips_ddr_top.", "{ddr3_wrapper.I_ips_ddr_top.")
        text, count = re.subn(pattern, lambda _: line, text, flags=re.M)
        if count != 1:
            raise ValueError("System clock definition missing: " + name)
    fdc.write_bytes(text.encode("utf-8"))
    changed.append(fdc.relative_to(inputs).as_posix())

    top = inputs / "src/ctrl/instrec_top.v"
    text = top.read_text(encoding="utf-8")
    baud = round(hz / 115200)
    inject = round(hz / 48000)
    replacements = (
        ('uart_tx', 'u_uart_tx', f'.BAUD_DIV({baud})'),
        ('uart_rx', 'u_uart_rx', f'.BAUD_DIV({baud})'),
        ('audio_sink', 'u_audio_sink', f".INJECT_GAP_CYCLES(14'd{inject}), "
         f".WR_TIMEOUT_CYCLES(23'd{round(4194304 * hz / 125000000)})"),
        ('sys_ctrl', 'u_sys_ctrl', f'.PLL_TIMEOUT_CYCLES({hz * 5}), .DDR_TIMEOUT_CYCLES({hz // 10})'),
        ('ddr3_ctrl_axi', 'u_ddr3_ctrl_axi', f'.M3_MASK_ENABLE(1), .P3_QUOTA_TIMEOUT({hz // 1000})'),
    )
    for module, instance, parameters in replacements:
        pattern = r'(?m)^([ \t]*)' + module + r'(?:\s*#\([^\r\n]*\))?[ \t]+' + instance + r'[ \t]*\('
        text, count = re.subn(pattern, lambda m: m[1] + module + ' #(' + parameters + ') ' + instance + ' (', text)
        if count != 1:
            raise ValueError('Expected one clock-dependent instance: ' + instance)
    text = re.sub(r'core_clk  [\d.]+ MHz DDR3 controller user clock',
                  f'core_clk  {hz / 1e6:g} MHz DDR3 controller user clock', text)
    top.write_text(text, encoding="utf-8")
    changed.append(top.relative_to(inputs).as_posix())
    cpu_fdc = inputs / 'constraints/pacerv_shared_system.fdc'
    comment = cpu_fdc.read_text(encoding='utf-8')
    comment, count = re.subn(r'share the [\d.]+ MHz user clock',
                             f'share the {hz / 1e6:g} MHz user clock', comment)
    if count != 1:
        raise ValueError('Expected one CPU clock comment')
    cpu_fdc.write_text(comment, encoding='utf-8')
    changed.append(cpu_fdc.relative_to(inputs).as_posix())
    manifest_file = output / "INPUTS.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        source = inputs / entry["path"]
        entry.update(bytes=source.stat().st_size, sha256=sha(source))
    manifest.update(system_clock_hz=hz, pixel_clock_hz=148500000,
                    clock_generation_report_sha256=sha(directory / "RESULT.json"))
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = {
        "scope": "Prepared frozen candidate; not yet compiled, routed or qualified",
        "system_clock_hz": hz, "pixel_clock_hz": 148500000,
        "uart_baud_div": baud, "actual_uart_baud": hz / baud,
        "empty_fifo_injection_cycles": inject,
        "ddr_rate_mbps": clock["actual_rate_mbps"],
        "changed_inputs": changed, "frozen_input_count": len(manifest["files"]),
        "live_sources_unchanged": all(sha(ROOT / item['path']) == item['sha256']
                                      for item in original_manifest['files']),
        "source_build": str(output), "source_clock_report": str(directory / "RESULT.json"),
    }
    (output / "CLOCK_CANDIDATE.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("LOWER_CLOCK_PREPARED " + str(output), flush=True)
    print("CLOCK_CANDIDATE clock_hz=" + str(hz) + " baud_div=" + str(baud) +
          " inject=" + str(inject) + " frozen_changed=" + str(len(changed)), flush=True)


if __name__ == "__main__":
    main()
