import hashlib
import re


def inspect_predictor_index(native):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def module(name):
        matches = re.findall(r'\bmodule\s+' + name + r'\b[\s\S]*?\bendmodule\b', native)
        require(len(matches) == 1, 'Missing unique predictor audit module: ' + name)
        return matches[0]

    def cells(text):
        return re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;', text)

    def pins(cell):
        return {name: value.strip() for name, value in re.findall(r'^\s*\.([^\s.(]+)\s*\(([^)]*)\)', cell, re.M) if name != 'INIT'}

    def table(cell, width):
        matches = re.findall(r'\.INIT\((\d+)\x27b([01]+)\)', cell)
        require(len(matches) == 1 and int(matches[0][0]) == width and len(matches[0][1]) == width, 'Invalid predictor LUT truth encoding')
        return int(matches[0][1], 2)

    core = module('rv32_core')
    predictor = module('rv32_btb')
    core_cells = cells(core)
    predictor_cells = cells(predictor)
    slash = chr(92)
    bit_zero = [slash + 'predictor/fetch_index [0]'] + [slash + 'predictor/fetch_index_' + str(index) for index in range(1, 5)]

    driver_records = []
    truth_inputs = 0
    for index, signal in enumerate(bit_zero):
        matches = [cell for cell in core_cells if pins(cell).get('Z5') == signal]
        require(len(matches) == 1, 'Missing unique index-zero driver: ' + signal)
        cell = matches[0]
        connections = pins(cell)
        expected = dict(Z='N1615[2]' if index == 0 else '', Z5=signal, I0='prediction_hit', I1='next_pc[2]', I2='next_pc[14]', I3=slash + 'predictor/N67', I4='_N12831', I5="1'b1")
        require(cell.startswith('GTP_LUT6D ') and connections == expected, 'Predictor shared LUT pins changed')
        value = table(cell, 64)
        for pattern in range(32):
            require((value >> pattern) & 1 == ((pattern >> 1) ^ (pattern >> 2)) & 1, 'Predictor bit-zero XOR changed')
            truth_inputs += 1
        driver_records.append(dict(bit=0, signal=signal, cell_sha256=hashlib.sha256(cell.encode()).hexdigest().upper()))
    base_signals = ['fetch_index_alias[' + str(bit) + ']' if bit < 6 else slash + 'fetch_index[' + str(bit) + ']_dirfix' for bit in range(1, 8)]
    numbered = ['fetch_index_' + str(index) for index in range(5, 34)]
    expected_signals = set(base_signals + numbered)
    observed = []
    counts = [5] + [0] * 7
    signal_bits = {'fetch_index_alias[0]': 0, **{'fetch_index_' + str(index): 0 for index in range(1, 5)}}
    for cell in predictor_cells:
        connections = pins(cell)
        signal = connections.get('Z', '')
        if signal not in expected_signals:
            continue
        observed.append(signal)
        require(cell.startswith('GTP_LUT2 ') and set(connections) == {'Z', 'I0', 'I1'}, 'Predictor replica primitive changed')
        matches = re.fullmatch(r'fetch_pc\[(\d+)\]', connections['I0'])
        require(matches is not None, 'Predictor replica first operand changed')
        bit = int(matches[1]) - 2
        require(1 <= bit <= 7 and connections['I1'] == 'fetch_pc[' + str(10 + ((bit - 4) % 8)) + ']', 'Predictor replica folded operand changed')
        if signal in base_signals:
            require(signal == base_signals[bit - 1], 'Predictor original bit assignment changed')
        value = table(cell, 4)
        for pattern in range(4):
            require((value >> pattern) & 1 == ((pattern >> 1) ^ pattern) & 1, 'Predictor replica XOR changed')
            truth_inputs += 1
        counts[bit] += 1
        signal_bits[signal] = bit
        driver_records.append(dict(bit=bit, signal=signal, cell_sha256=hashlib.sha256(cell.encode()).hexdigest().upper()))
    require(len(observed) == len(expected_signals) and set(observed) == expected_signals, 'Predictor replica driver inventory changed')
    require(counts == [5, 5, 5, 5, 6, 6, 5, 4], 'Predictor replica bit distribution changed')
    require('assign fetch_index_alias[0] = fetch_index[0];' in predictor, 'Predictor original index-zero alias changed')
    instance = re.findall(r'\brv32_btb\s+predictor\s*\([\s\S]*?;', core)
    require(len(instance) == 1, 'Predictor hierarchy instance changed')
    bindings = pins(instance[0])
    require(bindings.get('fetch_index') == "{1'bx, 1'bx, 1'bx, 1'bx, 1'bx, 1'bx, 1'bx, " + slash + 'predictor/fetch_index [0] }', 'Predictor original index-zero binding changed')
    for index in range(1, 5):
        require(bindings.get('fetch_index_' + str(index)) == slash + 'predictor/fetch_index_' + str(index), 'Predictor replica hierarchy binding changed')
    loads = {signal: 0 for signal in signal_bits}
    for cell in predictor_cells:
        for port, expression in pins(cell).items():
            if port in {'Z', 'Z5', 'Q', 'COUT'}:
                continue
            values = [part.strip() for part in expression.strip('{}').split(',')]
            for signal in values:
                if signal in loads:
                    loads[signal] += 1
    require(all(count > 0 for count in loads.values()), 'Unused predictor index replica')
    return dict(scope='actual_synthesis_index_XOR_and_hierarchy_not_full_predictor_or_postroute_proof', driver_count=len(driver_records), bit_driver_counts=counts, truth_inputs=truth_inputs, predictor_local_primitive_input_loads=loads, maximum_local_load=max(loads.values()), drivers=driver_records, native_sha256=hashlib.sha256(native.encode()).hexdigest().upper())
