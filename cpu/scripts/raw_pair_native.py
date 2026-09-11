import hashlib
import re


def inspect_raw_pair_retime(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Missing unique raw-pair CPU')
    core=modules[0]
    blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',core)
    parsed=[(block,{port:signal.strip() for port,signal in re.findall(r'\.(Q|C|P|CE|CLK|D|Z|Z5|COUT|CIN|I[0-5]|S)\s*\(([^)]*)\)',block)}) for block in blocks]
    drivers={}
    for block,pins in parsed:
        for port in ('Q','Z','Z5','COUT'):
            if pins.get(port):
                drivers.setdefault(pins[port],[]).append((block,pins,port))
    def driver(signal):
        matches=drivers.get(signal,[])
        if len(matches)!=1:
            raise ValueError('Missing unique raw-pair driver: '+signal)
        return matches[0]
    def initial(block,width):
        matches=re.findall(r'\.INIT\((\d+)\x27b([01]+)\)',block)
        if len(matches)!=1 or int(matches[0][0])!=width or len(matches[0][1])!=width:
            raise ValueError('Invalid raw-pair truth encoding')
        return int(matches[0][1],2)
    reset=chr(92)+'board/soc/N62_0'
    capture=[]
    for family,count,data in (('raw_pair_relation',3,'N2247'),('ex_operand_a',32,'N2243'),('ex_operand_b',32,'N2245')):
        for bit in range(count):
            identifier=chr(92)+family+'['+str(bit)+']'
            matches=[(block,pins) for block,pins in parsed if block.startswith('GTP_DFF') and re.search(re.escape(identifier)+r'\s+\(',block)]
            if len(matches)!=1:
                raise ValueError('Missing unique raw-pair register: '+identifier)
            block,pins=matches[0]
            preset=family=='raw_pair_relation' and bit==2
            kind='GTP_DFF_PE' if preset else 'GTP_DFF_CE'
            reset_port='P' if preset else 'C'
            output=pins.get('Q')
            if not output or not block.startswith(kind+' ') or pins!={'Q':output,reset_port:reset,'CE':'N2242','CLK':'clk','D':f'{data}[{bit}]'} or initial(block,1)!=int(preset) or '.GRS_EN("TRUE")' not in block:
                raise ValueError('Raw-pair capture/reset differs: '+identifier)
            driver(output)
            if family=='raw_pair_relation':
                if output!=chr(92)+f'early_pair_result[0] [{bit}]' or not re.search(r'\.I[0-5]\s*\('+re.escape(output)+r'\s*\)',core):
                    raise ValueError('Raw-pair captured relation is not active')
            capture.append(dict(family=family,bit=bit,sha256=hashlib.sha256(block.encode()).hexdigest().upper()))
    block,pins,port=driver('N2242')
    expected_inputs=('pipeline_valid[2]','id_fire_with_irq','id_fire_without_irq','interrupt_pending','_N37151',"1'b1")
    if not block.startswith('GTP_LUT6D ') or port!='Z' or tuple(pins.get('I'+str(bit)) for bit in range(6))!=expected_inputs:
        raise ValueError('Raw-pair shared enable mapping differs')
    truth=initial(block,64)>>32
    for value in range(32):
        expected=bool(value&1) or bool(value&(2 if value&8 else 4))
        if (truth>>value)&1!=expected:
            raise ValueError('Raw-pair shared enable truth differs')
    mux,mux_pins,port=driver('N2247[0]')
    if not mux.startswith('GTP_MUX2LUT7 ') or mux_pins!={'Z':'N2247[0]','I0':'_N13143','I1':'_N13140','S':'id_fire'}:
        raise ValueError('Raw-pair signed selection boundary differs')
    predicate,predicate_pins,predicate_port=driver('early_pair_condition[0]')
    expected_predicate={'Z':'early_condition_select[1]','Z5':'early_pair_condition[0]','I0':chr(92)+'early_pair_result[0] [0]','I1':chr(92)+'early_pair_result[0] [1]','I2':chr(92)+'early_pair_result[0] [2]','I3':'ex_instruction[13]','I4':'ex_instruction[14]','I5':"1'b1"}
    if not predicate.startswith('GTP_LUT6D ') or predicate_port!='Z5' or predicate_pins!=expected_predicate:
        raise ValueError('Raw-pair active predicate mapping differs')
    predicate_truth=initial(predicate,64)&0xffffffff
    for value in range(32):
        expected=((value>>1)&1 if value&8 else value&1) if value&16 else (0 if value&8 else (value>>2)&1)
        if (predicate_truth>>value)&1!=expected:
            raise ValueError('Raw-pair active predicate truth differs')
    roots=('N2247[1]','N2247[2]')
    selected={}
    cuts={f'{family}[{bit}]' for family in ('forwarded_a','forwarded_b','id_operand_a','id_operand_b') for bit in range(32)}|{'id_fire'}
    def visit(signal,active):
        if not signal or signal in cuts or signal in ("1'b0","1'b1"):
            return
        if signal in active:
            raise ValueError('Raw-pair native comparison cycle')
        if signal in selected:
            return
        cell,ports,output_port=driver(signal)
        if not re.match(r'GTP_LUT(?:[1-6](?:D|CARRY)?)(?:\s|$)',cell):
            raise ValueError('Raw-pair native comparison crosses inspected operand boundary: '+signal)
        selected[signal]=cell
        for name,value in ports.items():
            if re.fullmatch(r'I[0-5]|CIN',name):
                visit(value,active|{signal})
    for signal in roots:
        visit(signal,set())
    cells=sorted(set(selected.values()))
    return dict(scope='common_capture_and_unsigned_equality_native_cones_not_full_signed_or_CPU_equivalence',capture_registers=capture,enable_truth_inputs=32,predicate_truth_inputs=32,predicate_sha256=hashlib.sha256(predicate.encode()).hexdigest().upper(),signed_selector_sha256=hashlib.sha256(mux.encode()).hexdigest().upper(),comparison_cells=len(cells),comparison_sha256=[hashlib.sha256(cell.encode()).hexdigest().upper() for cell in cells]),cells


def native_comparison_design(native):
    report,cells=inspect_raw_pair_retime(native)
    core=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)[0]
    wires=[line for line in re.findall(r'^    wire [^\n]+',core,re.M) if not re.search(r'\b(?:forwarded_a|forwarded_b|id_operand_a|id_operand_b|id_fire);',line)]
    return '\n'.join(['module raw_native_compare(input wire [31:0] forwarded_a,forwarded_b,id_operand_a,id_operand_b,input wire id_fire,output wire [1:0] relation);',*wires,*cells,'assign relation={N2247[2],N2247[1]};','endmodule'])
