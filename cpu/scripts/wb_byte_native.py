import hashlib
import re


def inspect_wb_byte_retime(native):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    modules = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b', native)
    require(len(modules) == 1, 'Missing unique WB byte core')
    core = modules[0]
    cells = re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;', core)
    parsed = [(cell, {name: value.strip() for name, value in re.findall(r'^\s*\.(Q|CLK|C|P|CE|D|Z|Z5|COUT|CIN|I[0-5]|S)\s*\(([^)]*)\)', cell, re.M)}) for cell in cells]
    drivers = {}
    for cell, pins in parsed:
        for port in ('Q', 'Z', 'Z5', 'COUT'):
            if pins.get(port):
                drivers.setdefault(pins[port], []).append((cell, pins))
    captures = []
    roots = []
    for side, pair in (('a', 4), ('b', 2)):
        for relation in ('equal', 'less'):
            for byte in range(4):
                identifier = chr(92) + 'wb_' + side + '_byte_' + relation + '[' + str(byte) + ']'
                matches = [(cell, pins) for cell, pins in parsed if cell.startswith('GTP_DFF') and re.search(re.escape(identifier) + r'\s+\(', cell)]
                require(len(matches) == 1, 'WB byte capture inventory changed')
                cell, pins = matches[0]
                preset = relation == 'equal'
                kind = 'GTP_DFF_P' if preset else 'GTP_DFF_C'
                reset_port = 'P' if preset else 'C'
                signal = chr(92) + 'early_compare_pairs[' + str(pair) + '].byte_' + relation + ' [' + str(byte) + ']'
                require(cell.startswith(kind + ' ') and set(pins) == {'Q', 'CLK', 'D', reset_port}, 'WB byte capture primitive changed')
                require(pins['Q'] == signal and pins['CLK'] == 'clk' and pins[reset_port] == chr(92) + 'board/soc/N62_0', 'WB byte capture wiring changed')
                require(".INIT(1'b" + str(int(preset)) + ')' in cell and '.GRS_EN("TRUE")' in cell, 'WB byte reset value changed')
                roots.append(pins['D'])
                captures.append(dict(side=side, relation=relation, byte=byte, data=pins['D'], output=signal, sha256=hashlib.sha256(cell.encode()).hexdigest().upper()))
    selected = {}
    def visit(signal, active):
        if signal in ('', "1'b0", "1'b1") or re.fullmatch(r'compare_next_(?:a|b|wb)\[\d+\]', signal):
            return
        require(signal not in active, 'WB comparison cone cycle')
        if signal in selected:
            return
        matches = drivers.get(signal, [])
        require(len(matches) == 1, 'WB comparison missing unique driver: ' + signal)
        cell, pins = matches[0]
        require(re.match(r'GTP_(?:LUT[1-6](?:D|CARRY)?|MUX2LUT[5-8])\b', cell) is not None, 'WB comparison crossed combinational boundary')
        selected[signal] = cell
        for port, value in pins.items():
            if re.fullmatch(r'I[0-5]|CIN|S', port):
                visit(value, active | {signal})
    for signal in roots:
        visit(signal, set())
    chosen = sorted(set(selected.values()))
    return dict(scope='actual_byte_capture_and_comparison_cones_not_next_operand_mux_or_full_CPU_equivalence', capture_registers=captures, comparison_cells=len(chosen), comparison_sha256=[hashlib.sha256(cell.encode()).hexdigest().upper() for cell in chosen]), chosen


def native_wb_byte_design(native):
    report, cells = inspect_wb_byte_retime(native)
    core = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b', native)[0]
    wires = [line for line in re.findall(r'^    wire [^\n]+', core, re.M) if not re.search(r'\bcompare_next_(?:a|b|wb);', line)]
    outputs = ['wb_a_equal', 'wb_a_less', 'wb_b_equal', 'wb_b_less']
    assignments = ['assign ' + outputs[index // 4] + '[' + str(index % 4) + ']=' + capture['data'] + ';' for index, capture in enumerate(report['capture_registers'])]
    return '\n'.join(['module wb_byte_native(input wire [31:0] compare_next_a,compare_next_b,compare_next_wb,output wire [3:0] wb_a_equal,wb_a_less,wb_b_equal,wb_b_less);', *wires, *cells, *assignments, 'endmodule'])
