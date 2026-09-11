import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts'))
from load_use_profile import file_hash, load_json, require
from scope_decode import parse_captures, decode_triggered_uart, transitions, waveform_svg


def run(command, output, timeout=600):
    completed = subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=timeout)
    text = completed.stdout+completed.stderr
    output.write_text(text,encoding='utf-8')
    require(completed.returncode == 0, 'Current scope command failed: '+str(output))
    return text


def main():
    source = ROOT/'build/pds/20260910-222004-7326e2e2'
    snapshot = load_json(source/'source-snapshot.json')
    require(snapshot['Files'] == load_json(ROOT/'source-inputs.json')['source_hashes'], 'Current scope CPU source changed')
    for relative,expected in snapshot['Files'].items():
        require(file_hash(source/'source'/relative) == expected,'Physical captured source changed: '+relative)
    name = 'scope_p0_s1234_t4628571420_rv32gcc_f154285714'
    firmware_root = ROOT.parent/'full_control_commit'
    firmware = firmware_root/'build'/(name+'.hex')
    metadata = load_json(firmware_root/'build'/(name+'.build.json'))
    require(metadata['ClockHz'] == 154285714 and metadata['SampleCycles'] == 1234 and metadata['TimeoutCycles'] == 4628571420 and metadata['ConsoleDelayCycles'] == 0, 'Current scope timebase parameters changed')
    require(metadata['HexSha256'] == file_hash(firmware),'Current scope firmware changed')
    for relative,expected in metadata['SourceHashes'].items():
        require(file_hash(ROOT/relative) == expected,'Scope firmware source changed: '+relative)
    top = (source/'pds_soc_top.v').read_text()
    parameter_groups = re.findall(r'rv32_board_top #\((.*?)\) board\(',top,re.S)
    require(len(parameter_groups) == 1,'Physical board parameters ambiguous')
    actual = dict((key,int(value)) for key,value in re.findall(r'\.(\w+)\((\d+)\)',parameter_groups[0]))
    expected = dict(DATA_OVERLAP=1,BTB_INDEX_BITS=8,EARLY_D_REQUEST=1,FAST_DCACHE_WRITE=1,FAST_DCACHE_READ=1,FETCH_OVERLAP=1,ENABLE_M=1,CLOCK_HZ=154285714,ENABLE_PREDICTOR=1,LOAD_USE_BUBBLE=1,FAST_ICACHE_HIT=1,ICACHE_SET_BITS=9,CACHE_SET_BITS=6,ENABLE_CACHE=1,UART_BAUD=115200)
    require(actual == expected,'Physical hardware parameters changed')
    parameters = {key:value for key,value in actual.items() if key not in ('CLOCK_HZ','UART_BAUD')}
    instantiation = 'rv32_soc #(.CLOCK_HZ(3200),.BAUD(100),'+','.join(f'.{key}({value})' for key,value in parameters.items())+') soc(.*);'
    bench = (ROOT/'sim/scope_tb.sv').read_text()
    require(bench.count('rv32_soc #(.CLOCK_HZ(3200),.BAUD(100)) soc(.*);') == 1,'Scope SoC anchor changed')
    bench = bench.replace('rv32_soc #(.CLOCK_HZ(3200),.BAUD(100)) soc(.*);',instantiation)
    bench = bench.replace("send_byte(8'h55,2813);","send_byte(8'h55,16071);").replace("repeat(8000)","repeat(45714)")
    wait_line = '        wait(timeout_count==1);'
    require(bench.count(wait_line) == 1,'Scope timeout anchor changed')
    injected = ["        @(negedge clk); soc.core.machine.mcycle=soc.core.machine.mcycle+64'd4294967296;",
                '        repeat(10000) @(negedge clk);',
                '        if(timeout_count!=0) $fatal(1,"Scope timeout before full 30-second interval");',
                "        @(negedge clk); soc.core.machine.mcycle=soc.core.machine.mcycle+64'd333604124;",
                wait_line]
    bench = bench.replace(wait_line,'\n'.join(injected))
    output = ROOT/'build/scope-current'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    output.mkdir(parents=True)
    for relative in snapshot['Files']:
        if relative.startswith('rtl/'):
            destination = output/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source/'source'/relative,destination)
    testbench = output/'scope_tb.sv'
    testbench.write_text(bench)
    shutil.copyfile(firmware,output/'firmware.hex')
    sources = sorted((output/'rtl').glob('*.sv'))+[testbench]
    inputs = {item.relative_to(output).as_posix():file_hash(item) for item in sources}
    record = dict(scope='current CPU application simulation, not board or physical timing proof',source_snapshot=snapshot,
                  firmware_metadata=metadata,firmware_sha256=file_hash(firmware),physical_parameters=actual,
                  simulation_overrides=dict(CLOCK_HZ=3200,BAUD=100,clock_period_ns=10,uart_injected_bit_cycles=16071,key_pulse_cycles=45714,
                                            timeout_counter_jumps=[4294967296,333604124]),input_hashes=inputs,runner_sha256=file_hash(Path(__file__)),passed=False,hardware_validated=False)
    (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print('CURRENT_SCOPE_RUN='+output.as_posix(),flush=True)
    run(['iverilog','-g2012','-Wall','-s','scope_tb','-o',output/'scope.vvp',*sources],output/'compile.log',90)
    text = run(['vvp',output/'scope.vvp','+firmware='+str(output/'firmware.hex'),'+uart='+str(output/'scope.uart')],output/'execute.log')
    require(len(re.findall(r'^PASS scope cycles=\d+ dumps=2 timeout=1 empty=1$',text,re.M)) == 1,'Scope terminal assertion missing')
    captures = parse_captures((output/'scope.uart').read_text(),expected_clock_hz=154285714)
    require(len(captures) == 2 and {capture['trigger_mask'] for capture in captures} == {1,2},'Both input channels required')
    for index,capture in enumerate(captures):
        require(capture['period_cycles'] == 1234 and capture['late_samples'] == 0,'Scope sampling period or late count failed')
        if capture['trigger_mask'] == 2:
            require(decode_triggered_uart(capture,9600) == 0x55,'Actual current-clock UART waveform mismatch')
        else:
            require([level for timestamp,level in transitions(capture,0)] == [0,1,0],'Actual KEY pulse pattern mismatch')
        (output/f'capture-{index}.svg').write_text(waveform_svg(capture))
    for relative,expected in inputs.items():
        require(file_hash(output/relative) == expected,'Scope simulation input changed')
    record.update(passed=True,captures=[{key:value for key,value in capture.items() if key != 'records'} for capture in captures],
                  capture_sha256=file_hash(output/'scope.uart'),execute_sha256=file_hash(output/'execute.log'),
                  compiled_sha256=file_hash(output/'scope.vvp'),decoder_sha256=file_hash(ROOT/'scripts/scope_decode.py'))
    (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(text)
    print('PASS current 154.286-MHz scope: correct timebase, UART55, KEY pattern, EMPTY and 64-bit 30-second timeout; simulation only')


if __name__ == '__main__':
    main()

