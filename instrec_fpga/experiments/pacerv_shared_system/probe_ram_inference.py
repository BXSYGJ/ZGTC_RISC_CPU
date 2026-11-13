"""Prepare an isolated byte-lane RAM inference experiment; never edit live RTL."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    out = ROOT / 'build/pacerv_shared_system/pds' / (
        'ram-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-synthesis')
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'src/cpu/rv32_cpu_subsys.sv'
    text = source.read_text(encoding='utf-8')
    old_decl = '    reg [31:0] d_ram_q, d_rom_q;'
    new_decl = ('    reg [31:0] d_rom_q;\n'
                '    (* syn_ramstyle = "block_ram" *) reg [7:0] d_ram0_q, d_ram1_q, d_ram2_q, d_ram3_q;\n'
                '    wire [31:0] d_ram_q = {d_ram3_q, d_ram2_q, d_ram1_q, d_ram0_q};')
    old_read = ('            d_ram_q <= {dmem3[d_word], dmem2[d_word],\n'
                '                        dmem1[d_word], dmem0[d_word]};')
    new_read = '\n'.join(f'            d_ram{i}_q <= dmem{i}[d_word];' for i in range(4))
    if text.count(old_decl) == text.count(old_read) == 1:
        candidate = text.replace(old_decl, new_decl).replace(old_read, new_read)
        adopted = False
    elif new_decl in text and new_read in text:
        candidate = text
        adopted = True
    else:
        raise RuntimeError('The wrapper does not match either supported RAM structure')
    files = [source] + sorted((ROOT / 'src/cpu/vendor/pacerv_h3').glob('*.sv'))
    records = []
    commands = []
    for path in files:
        relative = path.relative_to(ROOT)
        target = out / 'inputs' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if path == source and not adopted:
            target.write_text(candidate, encoding='utf-8')
        else:
            shutil.copy2(path, target)
        records.append({'path': relative.as_posix(), 'bytes': target.stat().st_size,
                        'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        commands.append(f'add_design "{target.as_posix()}"')
    (out / 'src/cpu').mkdir(parents=True)
    shutil.copy2(ROOT / 'src/cpu/prog.hex', out / 'src/cpu/prog.hex')
    commands += ['set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676',
                 'compile -system_verilog -top_module rv32_cpu_subsys',
                 'synthesize -ads -selected_syn_tool_opt 2', 'dev_map', 'exit']
    (out / 'build.tcl').write_text('\n'.join(commands) + '\n', encoding='utf-8')
    manifest = {'scope': 'CPU-only byte-lane inference experiment; no physical qualification',
                'stage': 'map', 'target': 'PG2L100H-6IFBG676', 'files': records,
                'live_wrapper_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'byte_lane_structure_already_adopted': adopted}
    (out / 'INPUTS.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('RAM_PROBE_PREPARED ' + str(out))


if __name__ == '__main__':
    main()
