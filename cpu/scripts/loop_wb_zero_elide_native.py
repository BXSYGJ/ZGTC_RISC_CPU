import hashlib
import itertools
import re
from pathlib import Path

from loop_wb_nonzero_native import require


def inspect_forwarding(native):
    modules = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b', native)
    require(len(modules) == 1, 'Ambiguous native CPU module')
    core = modules[0]
    require('wb_rd_nonzero' not in core, 'Unexpected stateful WB qualifier')
    drivers = {}
    for block in re.findall(r'GTP_LUT[1-6](?:D|CARRY)?\b[^;]*;', core):
        ports = {port:signal.strip() for port,signal in re.findall(r'\.(Z5|Z|COUT|CIN|I[0-5])\s*\(([^)]*)\)',block)}
        for output in ('Z','Z5','COUT'):
            if ports.get(output):
                require(ports[output] not in drivers, 'Duplicate native driver')
                drivers[ports[output]] = (block, ports)
    tables = {}
    def table(signal):
        if signal not in tables:
            require(signal in drivers, 'Missing native selector driver: ' + signal)
            block, ports = drivers[signal]
            matches = re.findall(r"\.INIT\((\d+)'b([01]+)\)", block)
            require(len(matches) == 1, 'Missing unique native selector INIT')
            width, bits = int(matches[0][0]), matches[0][1]
            require(width in (2,4,8,16,32,64) and len(bits) == width, 'Invalid selector INIT width')
            inputs = [ports['I'+str(bit)] for bit in range(width.bit_length()-1)]
            truth = int(bits, 2)
            if signal == ports.get('Z5'):
                width = 32
                truth &= (1 << width)-1
                inputs = inputs[:5]
            elif 'CARRY' in block:
                carry_mode = re.findall(r'\.I5_TO_CARRY\("(TRUE|FALSE)"\)',block)
                lut_mode = re.findall(r'\.I5_TO_LUT\("(TRUE|FALSE)"\)',block)
                require(len(carry_mode) == len(lut_mode) == 1 and width == 64, 'Invalid native carry modes')
                original_truth = truth
                inputs.append(ports['CIN'])
                truth = 0
                width = 128
                for index in range(width):
                    address = index & 31
                    lower = (original_truth >> address) & 1
                    upper = (original_truth >> (address+32)) & 1
                    input_five, carry_in = (index >> 5) & 1, (index >> 6) & 1
                    if signal == ports.get('COUT'):
                        value = carry_in if lower else input_five if carry_mode[0] == 'TRUE' else upper
                    else:
                        select = input_five if lut_mode[0] == 'TRUE' else carry_in
                        value = upper if select else lower
                    truth |= value << index
            fixed = {bit:int(value[-1]) for bit,value in enumerate(inputs) if value in ("1'b0","1'b1")}
            legal = [index for index in range(width) if all((index >> bit) & 1 == value for bit,value in fixed.items())]
            active = [bit for bit in range(len(inputs)) if bit not in fixed and any(((truth >> index) ^ (truth >> (index ^ (1 << bit)))) & 1 for index in legal)]
            require(all(inputs[bit] for bit in active), 'Active floating native selector input')
            tables[signal] = (truth, inputs, fixed, active)
        return tables[signal]
    def evaluate(signal, values, stack=()):
        if signal in values:
            return values[signal]
        require(signal not in stack, 'Native selector cycle')
        truth, inputs, fixed, active = table(signal)
        index = sum(value << bit for bit,value in fixed.items())
        for bit in active:
            index |= evaluate(inputs[bit], values, stack+(signal,)) << bit
        return (truth >> index) & 1
    def roots(signal, allowed, stack=()):
        if signal in allowed:
            return {signal}
        require(signal not in stack, 'Native selector cycle')
        _, inputs, _, active = table(signal)
        return set().union(*(roots(inputs[bit], allowed, stack+(signal,)) for bit in active))
    mux_checks = 0
    match_checks = 0
    zero_checks = 0
    selector_hashes = {}
    wb_valid = chr(92)+'board/unused_trace_valid'
    wb_bits = [f'trace_rd[{bit}]' for bit in range(5)]
    for operand, offset, raw_array in (('a',15,'early_compare_left[3]'),('b',20,'early_compare_right[1]')):
        sample = drivers[f'forwarded_{operand}[0]'][1]
        selector = sample['I2']
        source_bits = [f'ex_instruction[{offset+bit}]' for bit in range(5)]
        allowed = set(source_bits+wb_bits+[wb_valid,'wb_writes'])
        require(roots(selector, allowed) == allowed, 'Unexpected native WB matching roots')
        for source, destination, valid, writes in itertools.product(range(32),range(32),(0,1),(0,1)):
            values = {signal:(source >> bit) & 1 for bit,signal in enumerate(source_bits)}
            values.update({signal:(destination >> bit) & 1 for bit,signal in enumerate(wb_bits)})
            values.update({wb_valid:valid,'wb_writes':writes})
            require(evaluate(selector, values) == int(valid and writes and source == destination), 'Native WB match differs from zero-elided RTL')
            match_checks += 1
        zero_signal = sample['I5']
        uses_signal = chr(92)+'ex_decode.uses_rs'+str(1 if operand=='a' else 2)
        require(roots(zero_signal, set(source_bits+[uses_signal])) == set(source_bits+[uses_signal]), 'Unexpected native zeroing roots')
        for source, uses in itertools.product(range(32),(0,1)):
            values = {signal:(source >> bit) & 1 for bit,signal in enumerate(source_bits)}
            values[uses_signal] = uses
            require(evaluate(zero_signal, values) == int(source == 0 or not uses), 'Native x0 clearing differs')
            zero_checks += 1
        for bit in range(32):
            signal = f'forwarded_{operand}[{bit}]'
            block, ports = drivers[signal]
            expected_ports = dict(Z=signal,I0=f'trace_data[{bit}]',I1=sample['I1'],I2=selector,I3=chr(92)+f'early_compare_left[1] [{bit}]',I4=chr(92)+f'{raw_array} [{bit}]',I5=zero_signal)
            if operand == 'a' and 8 <= bit <= 13:
                inputs = [wb_valid,'wb_writes','_N36522','_N36523','_N38929','_N20611','mem_match_a',zero_signal,f'trace_data[{bit}]',expected_ports['I3'],expected_ports['I4']]
                require(roots(signal,set(inputs)) == set(inputs), 'Split forwarding roots differ')
                for combination in range(1 << len(inputs)):
                    values = {name:(combination >> index) & 1 for index,name in enumerate(inputs)}
                    expected = 0 if values[zero_signal] else values[expected_ports['I3']] if values['_N38929'] and values['_N20611'] and values['mem_match_a'] else values[f'trace_data[{bit}]'] if values[wb_valid] and values['wb_writes'] and values['_N36522'] and values['_N36523'] else values[expected_ports['I4']]
                    require(evaluate(signal,values) == expected, 'Split native forwarding mux priority differs')
                    mux_checks += 1
            else:
                require(ports == expected_ports, 'Native forwarding data/control mapping differs')
                for combination in range(64):
                    values = {ports['I'+str(index)]:(combination >> index) & 1 for index in range(6)}
                    expected = 0 if combination & 32 else (combination >> 3) & 1 if combination & 2 else combination & 1 if combination & 4 else (combination >> 4) & 1
                    require(evaluate(signal, values) == expected, 'Native forwarding mux priority differs')
                    mux_checks += 1
        selector_hashes[operand] = hashlib.sha256(drivers[selector][0].encode()).hexdigest().upper()
    split_cut_checks = 0
    source_bits = [f'ex_instruction[{15+bit}]' for bit in range(5)]
    for source,destination in itertools.product(range(32),range(32)):
        values = {signal:(source >> bit) & 1 for bit,signal in enumerate(source_bits)}
        values.update({signal:(destination >> bit) & 1 for bit,signal in enumerate(wb_bits)})
        for signal,mask in (('_N36522',12),('_N36523',19)):
            require(evaluate(signal,values) == int((source & mask) == (destination & mask)), 'Split native WB partial match differs')
            split_cut_checks += 1
    for valid,exception,load in itertools.product((0,1),repeat=3):
        values = {'pipeline_valid[3]':valid,'mem_exception':exception,'mem_load':load}
        require(evaluate('_N38929',values) == int(valid and not exception and not load), 'Split native MEM activity differs')
        split_cut_checks += 1
    for destination,writes in itertools.product(range(32),(0,1)):
        values = {f'mem_instruction[{7+bit}]':(destination >> bit) & 1 for bit in range(5)}
        values['mem_writes'] = writes
        require(evaluate('_N20611',values) == int(writes and destination != 0), 'Split native MEM write qualifier differs')
        split_cut_checks += 1
    trace_roots = set(wb_bits+[wb_valid,'wb_writes'])
    require(roots('trace_write', trace_roots) == trace_roots, 'Unexpected native retirement qualifier roots')
    trace_checks = 0
    for destination, valid, writes in itertools.product(range(32),(0,1),(0,1)):
        values = {signal:(destination >> bit) & 1 for bit,signal in enumerate(wb_bits)}
        values.update({wb_valid:valid,'wb_writes':writes})
        require(evaluate('trace_write',values) == int(valid and writes and destination != 0), 'Native trace x0 guard differs')
        trace_checks += 1
    return dict(scope='listed_binary_native_forwarding_cones_not_whole_CPU_or_four_state_vendor_equivalence', match_checks=match_checks, zero_checks=zero_checks, mux_checks=mux_checks, trace_checks=trace_checks, split_cut_checks=split_cut_checks, selector_sha256=selector_hashes, checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper())
