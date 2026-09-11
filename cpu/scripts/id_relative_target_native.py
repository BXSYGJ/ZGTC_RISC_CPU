import hashlib
import re


def inspect_id_relative_target(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    decoders=re.findall(r'\bmodule\s+rv32_decode\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1 or len(decoders)!=1:
        raise ValueError('Missing unique native CPU/decoder')
    core=modules[0]
    blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',core)
    parsed=[(block,{port:signal.strip() for port,signal in re.findall(r'\.(Q|C|CE|CLK|D|Z|COUT|CIN|I[0-5])\s*\(([^)]*)\)',block)}) for block in blocks]
    def unique(port,signal):
        matches=[(block,pins) for block,pins in parsed if pins.get(port)==signal]
        if len(matches)!=1:
            raise ValueError('Missing unique target native driver: '+signal)
        return matches[0]
    _,pc_pins=unique('Q','ex_pc[0]')
    reset=pc_pins.get('C')
    if not reset:
        raise ValueError('Missing target asynchronous reset')
    def register(signal,data,enable):
        block,pins=unique('Q',signal)
        if not block.startswith('GTP_DFF_CE ') or pins!={'Q':signal,'C':reset,'CE':enable,'CLK':'clk','D':data}:
            raise ValueError('Target native capture differs: '+signal)
        if re.findall(r'\.INIT\(1\x27b([01])\)',block)!=['0'] or re.findall(r'\.GRS_EN\("([A-Z]+)"\)',block)!=['TRUE']:
            raise ValueError('Target native capture reset differs: '+signal)
        return hashlib.sha256(block.encode()).hexdigest().upper()
    _,target_pins=unique('Q','early_target[0]')
    data_match=re.fullmatch(r'(N\d+)\[0\]',target_pins.get('D',''))
    if data_match is None:
        raise ValueError('Target native adder data prefix differs')
    adder_prefix=data_match[1]
    registers={}
    adder=[]
    previous_carry=''
    for bit in range(32):
        registers['target_'+str(bit)]=register(f'early_target[{bit}]',f'{adder_prefix}[{bit}]','id_fire')
        registers['pc_'+str(bit)]=register(f'ex_pc[{bit}]',f'id_pc[{bit}]','id_fire')
        block,pins=unique('Z',f'{adder_prefix}[{bit}]')
        if not block.startswith('GTP_LUT6CARRY ') or set(pins)!={'Z','COUT','CIN',*('I'+str(index) for index in range(6))}:
            raise ValueError('Target adder primitive differs')
        if pins['CIN']!=previous_carry or (bit<31 and not pins['COUT']) or (bit==31 and pins['COUT']):
            raise ValueError('Target adder carry chain differs')
        if re.findall(r'\.I5_TO_CARRY\("([A-Z]+)"\)',block)!=['TRUE'] or re.findall(r'\.I5_TO_LUT\("([A-Z]+)"\)',block)!=[('TRUE' if bit==0 else 'FALSE')]:
            raise ValueError('Target adder carry mode differs')
        truth=re.findall(r'\.INIT\(64\x27b([01]{64})\)',block)
        if len(truth)!=1:
            raise ValueError('Target adder truth encoding differs')
        previous_carry=pins['COUT']
        adder.append(hashlib.sha256(block.encode()).hexdigest().upper())
        if not re.search(r'\.I[0-5]\s*\(early_target\['+str(bit)+r'\]\)',core):
            raise ValueError('Captured target has no active native consumer')
    aliases={}
    for signal,offset in (('id_rd',7),('id_rs1',15),('id_rs2',20)):
        for bit in range(5):
            aliases[f'{signal}[{bit}]']=register(f'{signal}[{bit}]',f'if_instruction[{offset+bit}]','if_fire')
    instances=re.findall(r'\brv32_decode decoder \([\s\S]*?\);',core)
    if len(instances)!=1 or re.search(r'GTP_DFF|always\s*@',decoders[0]):
        raise ValueError('Actual native decoder instance or combinational boundary differs')
    return dict(scope='native_capture_and_carry_structure_not_full_netlist_equivalence_or_timing',adder_prefix=adder_prefix,target_registers=32,pc_registers=32,alias_registers=15,carry_cells=32,register_sha256=registers,alias_sha256=aliases,carry_sha256=adder,decoder_sha256=hashlib.sha256(decoders[0].encode()).hexdigest().upper(),decoder_instance_sha256=hashlib.sha256(instances[0].encode()).hexdigest().upper())


def native_adder_design(native):
    report=inspect_id_relative_target(native)
    adder_prefix=report['adder_prefix']
    core=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)[0]
    decoder=re.findall(r'\bmodule\s+rv32_decode\b[\s\S]*?\bendmodule\b',native)[0]
    instance=re.findall(r'\brv32_decode decoder \([\s\S]*?\);',core)[0]
    blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',core)
    adder=[next(block for block in blocks if re.search(r'\.Z\s*\('+re.escape(adder_prefix)+r'\['+str(bit)+r'\]\)',block)) for bit in range(32)]
    wires=[line for line in re.findall(r'^    wire [^\n]+',core,re.M) if not re.search(r'\b(?:id_pc|id_instruction);',line)]
    wrapper='\n'.join(['module relative_native_adder(input wire [31:0] id_pc,id_instruction,output wire [31:0] value);',*wires,'assign id_rd=id_instruction[11:7]; assign id_rs1=id_instruction[19:15]; assign id_rs2=id_instruction[24:20];','assign value='+adder_prefix+';',instance.replace('rv32_decode decoder','relative_native_decode decoder'),*adder,'endmodule',decoder.replace('module rv32_decode','module relative_native_decode')])
    return wrapper
