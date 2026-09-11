import hashlib
import re


def inspect_forward_match(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native CPU module')
    core=modules[0]
    blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',core)
    parsed=[(block,{port:signal.strip() for port,signal in re.findall(r'\.(Q|C|P|CE|CLK|D|Z|I[0-5])\s*\(([^)]*)\)',block)}) for block in blocks]
    drivers={}
    for block,pins in parsed:
        for port in ('Z','Q'):
            if port in pins:
                drivers.setdefault((port,pins[port]),[]).append((block,pins))
    lut_cache={}
    def unique(port,signal):
        matches=drivers.get((port,signal),[])
        if len(matches)!=1:
            raise ValueError('Missing unique native driver: '+signal)
        return matches[0]
    def lut(signal):
        if signal in lut_cache:
            return lut_cache[signal]
        block,pins=unique('Z',signal)
        kind=re.match(r'GTP_LUT([1-6])\b',block)
        if not kind:
            raise ValueError('Unknown native comparison primitive')
        width=int(kind[1])
        initial=re.findall(r'\.INIT\((\d+)\x27b([01]+)\)',block)
        if len(initial)!=1 or int(initial[0][0])!=1<<width or len(initial[0][1])!=1<<width or set(pins)!={'Z',*('I'+str(index) for index in range(width))}:
            raise ValueError('Invalid native LUT truth table')
        lut_cache[signal]=(block,pins,width,int(initial[0][1],2))
        return lut_cache[signal]
    def table(signal,inputs,function):
        block,pins,width,truth=lut(signal)
        if tuple(pins['I'+str(index)] for index in range(width))!=tuple(inputs):
            raise ValueError('Native control inputs differ')
        for value in range(1<<width):
            bits=tuple((value>>index)&1 for index in range(width))
            if (truth>>value)&1!=int(function(*bits)):
                raise ValueError('Native control truth differs')
        return hashlib.sha256(block.encode()).hexdigest().upper(),1<<width
    def equality(outputs,left,right):
        leaves=set(left+right)
        visited=set()
        used=set()
        def inspect(signal,active):
            if signal in leaves:
                used.add(signal)
                return
            if signal in active:
                raise ValueError('Native comparison cycle')
            block,pins,width,truth=lut(signal)
            visited.add(signal)
            for index in range(width):
                inspect(pins['I'+str(index)],active|{signal})
        for output in outputs:
            inspect(output,set())
        if used!=leaves:
            raise ValueError('Native comparison leaf inventory differs')
        def evaluate(signal,values):
            if signal in values:
                return values[signal]
            block,pins,width,truth=lut(signal)
            index=sum(evaluate(pins['I'+str(bit)],values)<<bit for bit in range(width))
            values[signal]=(truth>>index)&1
            return values[signal]
        for left_value in range(32):
            for right_value in range(32):
                values={signal:(left_value>>index)&1 for index,signal in enumerate(left)}
                values.update({signal:(right_value>>index)&1 for index,signal in enumerate(right)})
                if all(evaluate(output,values) for output in outputs)!=(left_value==right_value):
                    raise ValueError('Native precomputed equality differs')
        return dict(outputs=outputs,truth_inputs=1024,gate_sha256={signal:hashlib.sha256(lut(signal)[0].encode()).hexdigest().upper() for signal in sorted(visited)})
    first,first_pins=unique('Q','mem_match_a')
    reset=first_pins.get('P')
    if not reset:
        raise ValueError('Missing asynchronous preset')
    def register(output,kind,enable,data,initial):
        block,pins=unique('Q',output)
        reset_port='P' if initial else 'C'
        if not block.startswith(kind+' ') or pins!={'Q':output,reset_port:reset,'CE':enable,'CLK':'clk','D':data}:
            raise ValueError('Native register capture mapping differs: '+output)
        if re.findall(r'\.INIT\(1\x27b([01])\)',block)!=[str(initial)] or re.findall(r'\.GRS_EN\("([A-Z]+)"\)',block)!=['TRUE']:
            raise ValueError('Native register reset configuration differs')
        return hashlib.sha256(block.encode()).hexdigest().upper()
    destination=[]
    for bit in range(5):
        destination.append(register(f'ex_instruction[{bit+7}]','GTP_DFF_CE','id_fire',f'id_rd[{bit}]',0))
        destination.append(register(f'mem_instruction[{bit+7}]','GTP_DFF_CE','ex_fire',f'ex_instruction[{bit+7}]',0))
        for shift,source in ((15,'id_rs1'),(20,'id_rs2')):
            destination.append(register(f'ex_instruction[{bit+shift}]','GTP_DFF_CE','id_fire',f'{source}[{bit}]',0))
    enable=first_pins.get('CE')
    enable_hash,enable_cases=table(enable,('ex_fire','id_fire_with_irq','id_fire_without_irq','interrupt_pending'),lambda ex_fire,id_irq,id_normal,irq:ex_fire or (id_irq if irq else id_normal))
    records={}
    for suffix,source,shift in (('a','id_rs1',15),('b','id_rs2',20)):
        signal='mem_match_'+suffix
        block,pins=unique('Q',signal)
        register_hash=register(signal,'GTP_DFF_PE',enable,pins.get('D'),1)
        data_block,data_pins,width,truth=lut(pins['D'])
        if width!=6 or data_pins.get('I2')!='ex_fire' or data_pins.get('I3')!='id_fire':
            raise ValueError('Native match transfer selector differs')
        selector_hash,selector_cases=table(pins['D'],tuple(data_pins['I'+str(index)] for index in range(6)),lambda joint,id_only,ex_fire,id_fire,ex_low,ex_high:(joint if id_fire else ex_low and ex_high) if ex_fire else id_only)
        id_sources=[f'{source}[{bit}]' for bit in range(5)]
        ex_destination=[f'ex_instruction[{bit+7}]' for bit in range(5)]
        mem_destination=[f'mem_instruction[{bit+7}]' for bit in range(5)]
        ex_sources=[f'ex_instruction[{bit+shift}]' for bit in range(5)]
        comparisons=[equality([data_pins['I0']],id_sources,ex_destination),equality([data_pins['I1']],id_sources,mem_destination),equality([data_pins['I4'],data_pins['I5']],ex_sources,ex_destination)]
        consumers=len(re.findall(r'\.I[0-5]\s*\('+signal+r'\)',core))
        if not consumers:
            raise ValueError('Retimed match has no active consumers')
        records[suffix]=dict(register_sha256=register_hash,data=pins['D'],selector_sha256=selector_hash,selector_truth_inputs=selector_cases,comparisons=comparisons,consumers=consumers)
    return dict(scope='binary_native_match_data_and_capture_mapping_not_full_netlist_equivalence',reset=reset,enable=enable,enable_sha256=enable_hash,enable_truth_inputs=enable_cases,pipeline_registers_sha256=destination,match=records,truth_inputs=6288)
