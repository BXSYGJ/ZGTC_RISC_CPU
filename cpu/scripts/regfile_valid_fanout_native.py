import re
from collections import Counter

from load_use_profile import require

OUTPUTS = {'DO', 'Q', 'Z', 'Z5', 'COUT'}
PARAMETERS = {'INIT', 'INIT_0', 'INIT_1', 'GRS_EN'}
CLEAR = chr(92)+'board/soc/N62_0'


def pins(cell):
    return {port: signal.strip() for port, signal in re.findall(r'\.(\w+)\s*\(([^)]*)\)', cell) if port not in PARAMETERS}


def signals(expression):
    return [value.strip() for value in expression.replace('{', '').replace('}', '').split(',') if value.strip()]


def external(signal):
    return bool(re.fullmatch(r'(?:id_rs[12]|trace_rd|trace_data)(?:\[\d+\])?', signal) or signal in ('trace_write', 'clk', CLEAR) or re.fullmatch(r"\d+'[bhd][0-9a-fxz]+", signal, re.I))


def fanout_inventory(native):
    modules = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b', native)
    require(len(modules) == 1, 'Ambiguous native CPU for fanout')
    module = modules[0]
    cells = re.findall(r'GTP_\w+\b[^;]*;', module)
    expected = {f'id_register_{side}_valid'+suffix for side in ('a','b') for suffix in ('','_1','_2','_3','_4')}
    annotated = re.findall(r'\(\* PAP_MAX_FANOUT=16 \*\)\s+wire (id_register_[ab]_valid(?:_\d+)?);', module)
    require(len(annotated) == 10 and set(annotated) == expected, 'Actual max-fanout annotation inventory differs')
    port_maps = [pins(cell) for cell in cells]
    all_loads = Counter(signal for ports in port_maps for port,expression in ports.items() if port not in OUTPUTS for signal in signals(expression))
    drivers = {name: [cells[index] for index,ports in enumerate(port_maps) if ports.get('Z') == name] for name in expected}
    require(all(len(value) == 1 for value in drivers.values()), 'Validity clone driver missing or duplicated')
    result = {}
    for side in ('a','b'):
        base_name = f'id_register_{side}_valid'
        base_cell = drivers[base_name][0]
        base_ports = {port:signal for port,signal in pins(base_cell).items() if port != 'Z'}
        base_truth = re.findall(r"\.INIT\(32'b([01]{32})\)", base_cell)
        require(base_cell.startswith('GTP_LUT5 ') and len(base_truth) == 1, 'Validity base LUT shape changed')
        for suffix in ('','_1','_2','_3','_4'):
            name = base_name+suffix
            cell = drivers[name][0]
            require(cell.startswith('GTP_LUT5 ') and {port:signal for port,signal in pins(cell).items() if port != 'Z'} == base_ports and re.findall(r"\.INIT\(32'b([01]{32})\)",cell) == base_truth, 'Validity clone function or input differs')
            loads = all_loads[name]
            require(loads == (7 if suffix == '_4' else 16), 'Actual validity clone fanout differs')
            references = len(re.findall(r'\(\s*'+re.escape(name)+r'\s*\)',module))
            require(references == loads+1, 'Unaccounted validity clone pin connection')
            result[name] = loads
    return result


def extract(native):
    fanout_inventory(native)
    modules = re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b', native)
    require(len(modules) == 1, 'Ambiguous native CPU')
    cells = re.findall(r'GTP_\w+\b[^;]*;', modules[0])
    drivers = {}
    for index, cell in enumerate(cells):
        for port, expression in pins(cell).items():
            if port in OUTPUTS:
                for signal in signals(expression):
                    drivers.setdefault(signal, []).append(index)
    selected = set()
    def visit(signal):
        if external(signal):
            return
        matches = drivers.get(signal, [])
        require(len(matches) == 1, 'Missing or duplicate native driver: '+signal)
        index = matches[0]
        if index in selected:
            return
        selected.add(index)
        for port, expression in pins(cells[index]).items():
            if port not in OUTPUTS:
                for source in signals(expression):
                    visit(source)
    for side in ('a', 'b'):
        for bit in range(32):
            visit(f'id_operand_{side}[{bit}]')
    selected_cells = [cells[index] for index in sorted(selected)]
    kinds = Counter(cell.split()[0] for cell in selected_cells)
    require(kinds == dict(GTP_LUT5=54, GTP_MUX2LUT7=8, GTP_LUT6=47, GTP_DFF_CE=31, GTP_MUX2LUT8=2, GTP_RAM32X2DP=32, GTP_LUT6D=2, GTP_LUT4=16), 'Native register-file cone inventory changed')
    views = set()
    for cell in selected_cells:
        if not cell.startswith('GTP_RAM32X2DP '):
            continue
        ports = pins(cell)
        match = re.fullmatch(r'\{(N299|N306)\[(\d+)\], \1\[(\d+)\]\}', ports['DO'])
        require(match is not None, 'Native register RAM output packing changed')
        view, high, low = match[1], int(match[2]), int(match[3])
        require(high == low+1 and low in range(0, 32, 2) and (view, low) not in views, 'Native register RAM bit or view duplicated')
        views.add((view, low))
        require(ports == dict(DO=f'{{{view}[{high}], {view}[{low}]}}', DI=f'{{trace_data[{high}], trace_data[{low}]}}', RADDR='id_rs1' if view == 'N299' else 'id_rs2', WADDR='trace_rd', WCLK='clk', WE='trace_write'), 'Native register RAM read/write wiring differs')
        require(re.findall(r"\.INIT_[01]\(32'b([01]{32})\)", cell) == ['0'*32, '0'*32], 'Native register RAM initializers changed')
    require(views == {(view, bit) for view in ('N299', 'N306') for bit in range(0, 32, 2)}, 'Native register RAM view inventory incomplete')
    valid_bits = set()
    for cell in selected_cells:
        if not cell.startswith('GTP_DFF_CE '):
            continue
        ports = pins(cell)
        match = re.fullmatch(r'register_valid\[(\d+)\]', ports['Q'])
        require(match is not None, 'Unexpected native state in register cone')
        bit = int(match[1])
        require(bit in range(1, 32) and bit not in valid_bits, 'Native validity register missing or duplicated')
        valid_bits.add(bit)
        require(ports == dict(Q=f'register_valid[{bit}]', C=CLEAR, CE='trace_write', CLK='clk', D=f'N1283[{bit}]'), 'Native validity register controls differ')
        require('.GRS_EN("TRUE")' in cell and ".INIT(1'b0)" in cell, 'Native validity register reset changed')
        gate = cells[drivers[f'N1283[{bit}]'][0]]
        require(gate.startswith('GTP_LUT6 ') and pins(gate) == dict(Z=f'N1283[{bit}]', **{f'I{index}': f'trace_rd[{index}]' for index in range(5)}, I5=f'register_valid[{bit}]'), 'Native validity feedback ports changed')
        values = re.findall(r"\.INIT\(64'b([01]{64})\)", gate)
        require(len(values) == 1, 'Native validity feedback truth table missing')
        truth = int(values[0], 2)
        for stimulus in range(64):
            require((truth >> stimulus) & 1 == int(bool(stimulus & 32) or (stimulus & 31) == bit), 'Native validity feedback truth differs')
    require(valid_bits == set(range(1, 32)), 'Native validity state incomplete')
    all_cells = re.findall(r'GTP_\w+\b[^;]*;', native)
    resets = [cell for cell in all_cells if pins(cell).get('Z') == 'N62_0']
    require(len(resets) == 1 and resets[0].startswith('GTP_INV ') and pins(resets[0]) == dict(Z='N62_0', I='rst_n'), 'Actual upstream clear inversion changed')
    require(not any(re.search(r'\.Q\s*\(\s*'+re.escape(chr(92))+r'registers\[', cell) for cell in cells), 'Unexpected register-data flip-flops remain')
    return selected_cells


def wrapper(cells):
    vectors, scalars = {}, set()
    for cell in cells:
        for expression in pins(cell).values():
            for signal in signals(expression):
                if external(signal):
                    continue
                match = re.fullmatch(r'(\w+)\[(\d+)\]', signal)
                if match:
                    vectors[match[1]] = max(vectors.get(match[1], 0), int(match[2]))
                else:
                    require(re.fullmatch(r'\w+', signal) is not None, 'Unsupported native wire declaration')
                    scalars.add(signal)
    header = ['module candidate_regfile(input wire clk,rst_n,trace_write,input wire [4:0] wb_rd,id_rs1,id_rs2,input wire [31:0] wb_data,output wire [31:0] id_operand_a,id_operand_b);', 'wire [4:0] trace_rd=wb_rd;', 'wire [31:0] trace_data=wb_data;', 'wire '+CLEAR+' ;', 'assign '+CLEAR+' = !rst_n;']
    header += [f'wire [{width}:0] {name};' for name, width in sorted(vectors.items()) if name not in ('id_operand_a', 'id_operand_b')]
    header += ['wire '+name+';' for name in sorted(scalars)]
    return chr(10).join(header+cells+['endmodule'])
