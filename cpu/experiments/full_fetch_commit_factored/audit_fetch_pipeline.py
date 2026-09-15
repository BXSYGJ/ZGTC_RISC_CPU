import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHORT = ROOT / 'build/compiled/20260911-094801-420d3685'
OUTPUT = ROOT / 'build/ila-pipeline-rtl/fetch-commit153000'
sys.path.insert(0, str(ROOT.parents[1] / 'scripts'))
sys.path.insert(0, str(SHORT / 'source/scripts'))
from load_use_profile import file_hash, load_json, require
from run_coremark_compiled import verify_artifacts, validate_compiler_warnings, check_simulation_result
from audit_fetch_long import portable
import ila_analyze
ila_analyze.PROFILES['FetchCommit153000MinimalRtl'] = (153000000, 'cpu_clk')
ila_analyze.COMPACT_PROFILES += ('FetchCommit153000MinimalRtl',)
from ila_analyze import read_capture, read_symbols, summarize, render_svg


def validate_mem_transfers(samples):
    require(all(not sample["mem_fire"] or sample["mem_valid"] for sample in samples), "MEM fire without valid instruction")
    require(all(not following["wb_valid"] or previous["mem_fire"] for previous, following in zip(samples, samples[1:])), "WB without preceding MEM fire")


def main():
    manifest = load_json(SHORT / 'manifest.json')
    verify_artifacts(SHORT, manifest)
    from audit_fetch_inputs import audit_inputs
    audit_inputs()
    require(manifest['ConfigurationInput']['ClockHz'] == 153000000 and manifest['FirmwareBuild']['ClockHz'] == 153000000, 'Wrong capture clock')
    for relative, expected in manifest['SourceSnapshot'].items():
        require(file_hash(ROOT / relative) == expected, 'Current capture source changed: ' + relative)
    inputs = load_json(OUTPUT / 'inputs.json')
    require(inputs['base_manifest_sha256'] == file_hash(SHORT / 'manifest.json'), 'Original short binding changed')
    require(inputs['source_snapshot'] == manifest['SourceSnapshot'], 'Diagnostic source inventory changed')
    for relative, expected in inputs['source_snapshot'].items():
        actual = OUTPUT / 'source' / relative
        if relative == 'rtl/rv32_soc.sv':
            expected = inputs['observed_soc_sha256']
        elif relative == 'sim/coremark_compiled.cpp':
            expected = inputs['observed_harness_sha256']
        require(file_hash(actual) == expected, 'Diagnostic captured input changed: ' + relative)
    require(inputs['script_sha256'] == file_hash(OUTPUT / 'capture-generator-original.py') == file_hash(ROOT / 'capture_fetch_pipeline.py'), 'Original diagnostic generator changed')
    require(inputs['physical_clock_hz'] == 153000000 and inputs['simulation_clock_hz_parameter'] == 3200 and inputs['simulation_uart_baud'] == 100, 'Capture timebase changed')
    original_soc = (SHORT / 'source/rtl/rv32_soc.sv').read_text()
    anchor = '    output wire [63:0] retired_count\n'
    require(original_soc.count(anchor) == 1 and original_soc.count('endmodule') == 1, 'SoC observation anchor changed')
    expected_soc = original_soc.replace(anchor, '    output wire [63:0] retired_count,\n    output wire [41:0] pipeline_ila\n')
    assignment = '    assign pipeline_ila={core.mem_fire,core.fetch_complete,core.mem_flush,core.ex_fire,core.id_fire,core.pipeline_valid,core.ex_pc};\n'
    require((OUTPUT / 'source/rtl/rv32_soc.sv').read_text() == expected_soc.replace('endmodule', assignment + 'endmodule'), 'Observation changed SoC logic')
    require(inputs['compile_command'] == [argument.replace(portable(SHORT), portable(OUTPUT)) for argument in manifest['CompileCommand']], 'Actual build parameters changed')
    require(inputs['firmware_sha256'] == file_hash(OUTPUT / 'firmware.hex') == manifest['FirmwareSha256'], 'Diagnostic firmware changed')
    elf = ROOT / 'firmware/coremark_v0_i10_f153000000_rv32gcc_rv32im_O3_unroll_relax.elf'
    require(file_hash(elf) == inputs['elf_sha256'], 'Algorithm ELF changed')
    symbols_path = OUTPUT / 'symbols.txt'
    require(file_hash(symbols_path) == inputs['symbols_sha256'], 'ELF-bound symbols changed')
    binary = (OUTPUT / 'firmware.bin').read_bytes()
    require(len(binary) <= 65536, 'ELF binary exceeds memory')
    padded = binary + bytes(65536 - len(binary))
    words = [f'{int.from_bytes(padded[offset:offset+4], "little"):08x}' for offset in range(0,65536,4)]
    require(words == (OUTPUT / 'firmware.hex').read_text().splitlines(), 'ELF binary differs from firmware')
    memory_source = OUTPUT / "source/rtl/rv32_burst_ram.sv"
    compile_text = (OUTPUT / "compile.log").read_text()
    validate_compiler_warnings(compile_text.replace(portable(memory_source), str(memory_source)), OUTPUT / "source")
    result = check_simulation_result((OUTPUT / 'uart.log').read_text(), manifest['FirmwareBuild'], manifest['HardwareParameters'], True)
    require(result == load_json(SHORT / 'result.json'), 'Observation changed full diagnostic CoreMark result')
    require('PASS compiled RTL simulation' in (OUTPUT / 'execute.log').read_text(), 'Diagnostic execution not terminal')
    symbols = read_symbols(symbols_path)
    reports = {}
    for name in ('core_bench_list', 'core_bench_matrix', 'core_bench_state'):
        addresses = [address for address, size, symbol in symbols if symbol == name]
        require(len(addresses) == 1, 'Algorithm symbol missing')
        capture = OUTPUT / (name + '.csv')
        samples = read_capture(capture, 'FetchCommit153000MinimalRtl')
        validate_mem_transfers(samples)
        require(samples[0]['ex_pc'] == addresses[0] and samples[0]['ex_fire'], 'Algorithm trigger missing')
        report = summarize(samples, symbols, 'FetchCommit153000MinimalRtl')
        report.update(measurement_kind='rtl_simulation_not_hardware', capture_sha256=file_hash(capture),
                      time_axis_interpretation='cycles; microseconds normalized to nominal hardware clock, not simulated elapsed time')
        reports[name] = report
        (OUTPUT / (name + '.svg')).write_text(render_svg(samples, 'RTL ONLY - ' + name, profile='FetchCommit153000MinimalRtl'), encoding='utf-8')
        (OUTPUT / (name + '-zoom.svg')).write_text(render_svg(samples, 'RTL ONLY - ' + name + ' - 16-cycle zoom', length=16, profile='FetchCommit153000MinimalRtl'), encoding='utf-8')
    evidence = dict(scope='three algorithm windows from actual current-source RTL; not board evidence',
                    firmware_result=result, algorithm_windows=reports, inputs_sha256=file_hash(OUTPUT / 'inputs.json'),
                    compile_log_sha256=file_hash(OUTPUT / 'compile.log'), executable_sha256=file_hash(OUTPUT / 'objects/Vrv32_soc'),
                    uart_sha256=file_hash(OUTPUT / 'uart.log'), hardware_validated=False,
                    checker_source='original source-bound compiled short-run scripts', auditor_sha256=file_hash(Path(__file__)),
                    analyzer_sha256=file_hash(ROOT.parents[1] / 'scripts/ila_analyze.py'),
                    config_checker_sha256=file_hash(ROOT.parents[1] / 'scripts/ila_pipeline_minimal_config.py'))
    (OUTPUT / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    print('PASS actual current-source three 1024-cycle algorithm windows; full short result unchanged; RTL ONLY')


if __name__ == '__main__':
    main()
