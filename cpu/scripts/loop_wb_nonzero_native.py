import hashlib
import itertools
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pins(block):
    return {port: signal.strip() for port, signal in re.findall(r'\.(Q|C|CE|CLK|D|Z|I[0-5])\s*\(([^)]*)\)', block)}


def lut_value(block, values, open_value=0):
    configuration = re.findall(r"\.INIT\((\d+)'b([01]+)\)", block)
    require(len(configuration) == 1, 'Missing unique native LUT truth table')
    width, bits = int(configuration[0][0]), configuration[0][1]
    require(width in (2, 4, 8, 16, 32, 64) and len(bits) == width, 'Invalid native LUT truth width')
    ports = pins(block)
    index = 0
    for bit in range(width.bit_length()-1):
        signal = ports.get('I' + str(bit))
        require(signal is not None, 'Native LUT input missing')
        if signal == "1'b0":
            value = 0
        elif signal == "1'b1":
            value = 1
        elif signal == '':
            value = (open_value >> bit) & 1
        else:
            require(signal in values, 'Native LUT root input missing: ' + signal)
            value = values[signal]
        index |= value << bit
    return (int(bits, 2) >> index) & 1


def inspect_wb_nonzero_register(native):
    modules = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b', native)
    require(len(modules) == 1, 'Ambiguous native CPU module')
    core = modules[0]
    registers = [(block, pins(block)) for block in re.findall(r'GTP_DFF_CE\b[^;]*;', core)]
    gates = [(block, pins(block)) for block in re.findall(r'GTP_LUT[1-6](?:D|CARRY)?\b[^;]*;', core)]
    def register(output):
        matches = [(block, ports) for block, ports in registers if ports.get('Q') == output]
        require(len(matches) == 1, 'Missing unique WB destination register: ' + output)
        return matches[0]
    def gate(output):
        matches = [(block, ports) for block, ports in gates if ports.get('Z') == output]
        require(len(matches) == 1, 'Missing unique native driver: ' + output)
        return matches[0]
    flag, flag_pins = register('wb_rd_nonzero')
    require(flag_pins.get('CLK') == 'clk' and flag_pins.get('C') and flag_pins.get('CE'), 'Invalid WB flag capture controls')
    def check_capture(block, ports):
        require(all(ports.get(name) == flag_pins[name] for name in ('CLK', 'C', 'CE')), 'WB destination capture controls differ')
        require(re.findall(r"\.INIT\(1'b([01])\)", block) == ['0'] and re.findall(r'\.GRS_EN\("([A-Z]+)"\)', block) == ['TRUE'], 'WB destination reset configuration differs')
    check_capture(flag, flag_pins)
    destinations = []
    source_bits = []
    for bit in range(5):
        block, ports = register(f'trace_rd[{bit}]')
        check_capture(block, ports)
        require(ports.get('D') == f'mem_instruction[{bit+7}]', 'WB destination data mapping differs')
        source_bits.append(ports['D'])
        destinations.append(hashlib.sha256(block.encode()).hexdigest().upper())
    precompute, precompute_pins = gate(flag_pins['D'])
    require(precompute.startswith('GTP_LUT5 '), 'WB qualifier is not a five-input precomputation')
    require({precompute_pins.get('I'+str(bit)) for bit in range(5)} == set(source_bits), 'WB nonzero source bits differ')
    for value in range(32):
        values = {signal: (value >> bit) & 1 for bit, signal in enumerate(source_bits)}
        require(lut_value(precompute, values) == int(value != 0), 'WB nonzero truth table differs')
    enable, enable_pins = gate(flag_pins['CE'])
    fault, fault_pins = gate('mem_fault')
    require(enable.startswith('GTP_LUT6CARRY ') and '.I5_TO_CARRY("FALSE")' in enable and '.I5_TO_LUT("TRUE")' in enable, 'Unsupported WB enable carry mode')
    roots = sorted({signal for ports in (enable_pins, fault_pins) for name, signal in ports.items() if name.startswith('I') and signal not in ('', "1'b0", "1'b1")})
    require('mem_fire' in roots and len(roots) <= 8, 'Unexpected WB capture logic roots')
    checks = 0
    for combination in itertools.product((0, 1), repeat=len(roots)):
        values = dict(zip(roots, combination))
        expected = values['mem_fire'] and not lut_value(fault, values)
        for open_value in range(64):
            require(lut_value(enable, values, open_value) == int(expected), 'WB enable differs from nonfaulting MEM completion')
            checks += 1
    consumers = re.findall(r'\.I[0-5]\s*\(wb_rd_nonzero\)', core)
    require(consumers, 'WB qualifier has no native consumers')
    return dict(scope='listed_native_WB_flag_capture_and_truth_cones_not_whole_CPU_formal_equivalence',
                register_sha256=hashlib.sha256(flag.encode()).hexdigest().upper(), precompute_sha256=hashlib.sha256(precompute.encode()).hexdigest().upper(),
                enable_sha256=hashlib.sha256(enable.encode()).hexdigest().upper(), fault_sha256=hashlib.sha256(fault.encode()).hexdigest().upper(),
                destination_registers_sha256=destinations, clock=flag_pins['CLK'], enable=flag_pins['CE'], clear=flag_pins['C'],
                input=flag_pins['D'], truth_inputs=32, capture_truth_checks=checks, capture_roots=roots, consumers=len(consumers))
