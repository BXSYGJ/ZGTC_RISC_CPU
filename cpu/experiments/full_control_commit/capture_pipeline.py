import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'scripts'))
sys.path.insert(0, str(ROOT / 'build/compiled/20260910-195856-6bf511dd/source/scripts'))
from load_use_profile import file_hash, load_json, require
from run_coremark_compiled import verify_artifacts, validate_compiler_warnings, check_simulation_result
import ila_analyze
ila_analyze.PROFILES['ControlCommit154285MinimalRtl'] = (154285714, 'cpu_clk')
ila_analyze.COMPACT_PROFILES += ('ControlCommit154285MinimalRtl',)
from ila_analyze import header_for, read_capture, read_symbols, summarize, render_svg

PROFILE = 'ControlCommit154285MinimalRtl'
SHORT = ROOT / 'build/compiled/20260910-195856-6bf511dd'
OUTPUT = ROOT / 'build/ila-pipeline-rtl/control-commit'


def run(command, log, timeout=300):
    completed = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout)
    text = completed.stdout + completed.stderr
    log.write_text(text, encoding='utf-8')
    require(completed.returncode == 0, 'Command failed: ' + str(log))
    return text


def main():
    manifest = load_json(SHORT / 'manifest.json')
    verify_artifacts(SHORT, manifest)
    require(manifest['SourceSnapshot']['rtl/rv32_core.sv'] == 'C1E4F75D98B27AAE9125866C7A394AA801036C5E53C0C23C1E8BFC46F0B71E64', 'Wrong diagnostic CPU')
    require(manifest['FirmwareBuild']['Iterations'] == 10 and manifest['FirmwareSha256'] == '9BF59DB30CC17C9F81FC3D77D561319205DD60993204B75557D76A401400A4BC', 'Wrong short diagnostic firmware')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), OUTPUT / 'capture-generator-original.py')
    source = OUTPUT / 'source'
    shutil.copytree(SHORT / 'source', source)
    shutil.copyfile(SHORT / 'firmware.hex', OUTPUT / 'firmware.hex')
    prefix = manifest['FirmwareBuild']['Toolchain']['Prefix']
    elf = ROOT.parent / 'full_mul_precompute_clock154285/build/coremark_v0_i10_f154285714_rv32gcc_rv32im_O3_unroll_relax.elf'
    run([prefix + 'objcopy', '-O', 'binary', elf, OUTPUT / 'firmware.bin'], OUTPUT / 'objcopy.log')
    binary = (OUTPUT / 'firmware.bin').read_bytes()
    require(len(binary) <= 65536, 'ELF image exceeds memory')
    padded = binary + bytes(65536 - len(binary))
    hex_text = ''.join(f'{int.from_bytes(padded[offset:offset+4], "little"):08x}\n' for offset in range(0,65536,4))
    require(hex_text == (OUTPUT / 'firmware.hex').read_text(), 'ELF symbols do not belong to actual firmware')
    symbols_path = OUTPUT / 'symbols.txt'
    run([prefix + 'nm', '-S', '--defined-only', elf], symbols_path)
    symbols = read_symbols(symbols_path)
    names = ('core_bench_list', 'core_bench_matrix', 'core_bench_state')
    addresses = []
    for name in names:
        matches = [address for address, size, symbol in symbols if symbol == name]
        require(len(matches) == 1, 'Missing unique algorithm entry: ' + name)
        addresses.append(matches[0])
    soc = source / 'rtl/rv32_soc.sv'
    original_soc = soc.read_text()
    anchor = '    output wire [63:0] retired_count\n'
    require(original_soc.count(anchor) == 1, 'SoC port anchor changed')
    observed_soc = original_soc.replace(anchor, '    output wire [63:0] retired_count,\n    output wire [41:0] pipeline_ila\n')
    assign = '    assign pipeline_ila={core.mem_fire,core.fetch_complete,core.mem_flush,core.ex_fire,core.id_fire,core.pipeline_valid,core.ex_pc};\n'
    require(observed_soc.count('endmodule') == 1, 'Unexpected SoC modules')
    soc.write_text(observed_soc.replace('endmodule', assign + 'endmodule'))
    harness = source / 'sim/coremark_compiled.cpp'
    original_harness = harness.read_text()
    setup = ['        std::ofstream wave[3];', '        unsigned wave_count[3] = {};', '        bool wave_started[3] = {};',
             '        const uint32_t wave_entry[3] = {' + ','.join(hex(address) + 'U' for address in addresses) + '};']
    for index, name in enumerate(names):
        setup.extend(['        wave[' + str(index) + '].open(' + json.dumps(str(OUTPUT / (name + '.csv'))) + ');',
                      '        if (!wave[' + str(index) + ']) throw std::runtime_error("Cannot open diagnostic capture");',
                      '        wave[' + str(index) + '] << ' + json.dumps(','.join(header_for(PROFILE)) + '\n') + ';'])
    marker = '        bool previous_tx = true;'
    require(original_harness.count(marker) == 1, 'Harness setup anchor changed')
    observed_harness = original_harness.replace(marker, '\n'.join(setup) + '\n' + marker)
    marker = '            tick();\n            const bool serial_tx'
    sampling = ['            const uint64_t wave_value = model->pipeline_ila;',
                '            for (unsigned algorithm = 0; algorithm < 3; ++algorithm) {',
                '                if (!wave_started[algorithm] && ((wave_value >> 38) & 1U) && static_cast<uint32_t>(wave_value) == wave_entry[algorithm]) wave_started[algorithm] = true;',
                '                if (wave_started[algorithm] && wave_count[algorithm] < 1024) {',
                '                    wave[algorithm] << wave_count[algorithm]++;',
                '                    for (unsigned bit = 0; bit < 42; ++bit) wave[algorithm] << "," << ((wave_value >> bit) & 1U);',
                '                    wave[algorithm] << "\\n";',
                '                }', '            }']
    require(observed_harness.count(marker) == 1, 'Harness cycle anchor changed')
    harness.write_text(observed_harness.replace(marker, '\n'.join(sampling) + '\n' + marker))
    command = [argument.replace(str(SHORT), str(OUTPUT)) for argument in manifest['CompileCommand']]
    (OUTPUT / 'inputs.json').write_text(json.dumps(dict(scope='RTL diagnostic only; output observation ports are not synthesized ILA',
        source_snapshot=manifest['SourceSnapshot'], base_manifest_sha256=file_hash(SHORT / 'manifest.json'),
        observed_soc_sha256=file_hash(soc), observed_harness_sha256=file_hash(harness),
        firmware_sha256=file_hash(OUTPUT / 'firmware.hex'), elf_sha256=file_hash(elf), symbols_sha256=file_hash(symbols_path),
        physical_clock_hz=154285714, simulation_clock_hz_parameter=3200, simulation_uart_baud=100,
        compile_command=command, script_sha256=file_hash(Path(__file__))), indent=2) + '\n')
    compile_text = run(command, OUTPUT / 'compile.log')
    validate_compiler_warnings(compile_text, source)
    execute_text = run([OUTPUT / 'objects/Vrv32_soc', OUTPUT / 'uart.log', '10000000'], OUTPUT / 'execute.log')
    result = check_simulation_result((OUTPUT / 'uart.log').read_text(), manifest['FirmwareBuild'], manifest['HardwareParameters'], True)
    require(result == load_json(SHORT / 'result.json'), 'Observation ports changed complete diagnostic CoreMark result')
    reports = {}
    for name, address in zip(names, addresses):
        capture = OUTPUT / (name + '.csv')
        samples = read_capture(capture, PROFILE)
        require(samples[0]['ex_pc'] == address and samples[0]['ex_fire'], 'Algorithm trigger missing')
        report = summarize(samples, symbols, PROFILE)
        report.update(measurement_kind='rtl_simulation_not_hardware', capture_sha256=file_hash(capture))
        reports[name] = report
        (OUTPUT / (name + '.svg')).write_text(render_svg(samples, 'RTL ONLY - ' + name, profile=PROFILE), encoding='utf-8')
    (OUTPUT / 'results.json').write_text(json.dumps(dict(scope='three algorithm windows from actual current-source RTL; not board evidence',
        firmware_result=result, algorithm_windows=reports, inputs_sha256=file_hash(OUTPUT / 'inputs.json'),
        compile_log_sha256=file_hash(OUTPUT / 'compile.log'), executable_sha256=file_hash(OUTPUT / 'objects/Vrv32_soc'),
        uart_sha256=file_hash(OUTPUT / 'uart.log'), hardware_validated=False), indent=2) + '\n')
    print(json.dumps(reports, indent=2))
    print('PASS actual current-source three 1024-cycle algorithm windows; full short result unchanged; RTL ONLY')


if __name__ == '__main__':
    main()
