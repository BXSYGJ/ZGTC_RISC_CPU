import re


def require(condition,message):
    if not condition:
        raise ValueError(message)


def normalize(value):
    return ''.join(value.replace(chr(92),'').split())


def inspect_trap_vector_boundary(native):
    modules=re.findall(r'\bmodule rv32_machine\b(.*?)\bendmodule\b',native,re.S)
    require(len(modules)==1,'Missing unique machine module for trap-vector boundary')
    machine=modules[0]
    cells=[]
    for parameters,name,connections in re.findall(r'GTP_LUT6CARRY\s*/\*.*?\*/\s*#\((.*?)\)\s+(\S+)\s*\((.*?)\);',machine,re.S):
        pins={key:normalize(value) for key,value in re.findall(r'\.(\w+)\s*\(([^()]*)\)',connections)}
        settings=dict(re.findall(r'\.(\w+)\s*\(([^()]*)\)',parameters))
        cells.append(dict(name=name,pins=pins,settings=settings))
    selected={}
    for cell in cells:
        match=re.fullmatch(r'trap_target\[(\d+)\]',cell['pins'].get('Z',''))
        if match:
            bit=int(match[1])
            require(bit not in selected,'Duplicate trap-vector sum driver')
            selected[bit]=cell
    require(set(selected)==set(range(2,32)),'Trap-vector carry output boundary is not complete')
    allowed=re.compile(r"(?:mtvec\[\d+\]|board/soc/core/mem_cause\[(?:[0-4]|31)\]|board/soc/core/mem_exception|1'b[01])")
    for bit,cell in sorted(selected.items()):
        pins=cell['pins']
        for port in ('I0','I1','I2','I3','I4','I5'):
            require(port in pins,'Trap-vector native input inventory changed')
            require(not pins[port] or allowed.fullmatch(pins[port]),'Trap-vector carry depends on redirect selection')
        require(cell['settings'].get('I5_TO_CARRY')=='"TRUE"' and cell['settings'].get('I5_TO_LUT')=='"FALSE"','Trap-vector native carry mode changed')
        if bit>2:
            require(pins.get('CIN')==selected[bit-1]['pins'].get('COUT') and pins.get('CIN'),'Trap-vector carry chain is broken')
        else:
            seeds=[seed for seed in cells if seed['pins'].get('COUT')==pins.get('CIN')]
            require(len(seeds)==1,'Trap-vector carry seed is not unique')
            seed=seeds[0]
            require(seed['settings'].get('INIT')=="64'b"+'0'*64 and not seed['pins'].get('CIN') and all(not seed['pins'].get('I'+str(index)) for index in range(6)),'Trap-vector carry seed is not zero')
    constant_bits=[]
    for parameters,name,connections in re.findall(r'GTP_LUT1\s*/\*.*?\*/\s*#\((.*?)\)\s+(\S+)\s*\((.*?)\);',machine,re.S):
        pins={key:normalize(value) for key,value in re.findall(r'\.(\w+)\s*\(([^()]*)\)',connections)}
        if pins.get('Z') in ('trap_target[0]','trap_target[1]'):
            require(pins.get('I0')=="1'b0" and re.search(r"\.INIT\(2'b10\)",parameters),'Trap-vector low alignment bits changed')
            constant_bits.append(pins['Z'])
    require(sorted(constant_bits)==['trap_target[0]','trap_target[1]'],'Trap-vector low alignment boundary is incomplete')
    return dict(sum_bits=30,constant_low_bits=2,carry_chain_connected=True,redirect_selection_excluded=True,
                carry_cells=[selected[bit]['name'] for bit in range(2,32)])
