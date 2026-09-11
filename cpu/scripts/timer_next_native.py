import hashlib
import re


def inspect_timer_next(native, retained_increment=False, control_names=None):
    names={'counter_write':'_N4197','counter_enable':'_N4197_inv','compare_low_enable':'_N4202_inv','compare_high_enable':'_N4205_inv','counter_low_data':'_N12880','address_hit':'_N21148'}
    if control_names is not None:
        if not retained_increment or set(control_names)!=set(names) or any(not isinstance(value,str) or not re.fullmatch(r'[A-Za-z_]\w*',value) for value in control_names.values()) or len(set(control_names.values()))!=len(names):
            raise ValueError('Invalid explicit timer control mapping')
        names=dict(control_names)
    counter_write=names['counter_write']
    counter_enable=names['counter_enable']
    compare_low_enable=names['compare_low_enable']
    compare_high_enable=names['compare_high_enable']
    counter_low_data=names['counter_low_data']
    address_hit=names['address_hit']
    increment_evidence=None
    if retained_increment:
        from timer_increment_native import inspect_timer_increment
        increment_evidence=inspect_timer_increment(native)
    modules=re.findall(r'\bmodule\s+rv32_peripherals\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native peripheral module')
    module=modules[0]
    blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',module)
    parsed=[(block,{port:signal.strip() for port,signal in re.findall(r'\.(Q|C|P|CE|CLK|D|Z|Z5|COUT|CIN|I[0-5])\s*\(([^)]*)\)',block)}) for block in blocks]
    drivers={}
    for block,pins in parsed:
        for port in ('Q','Z','Z5','COUT'):
            if pins.get(port):
                drivers.setdefault(pins[port],[]).append((block,pins,port))
    def driver(signal):
        matches=drivers.get(signal,[])
        if len(matches)!=1:
            raise ValueError('Missing unique native timer driver: '+signal)
        return matches[0]
    def digest(text):
        return hashlib.sha256(text.encode()).hexdigest().upper()
    def initial(block,width):
        matches=re.findall(r'\.INIT\((\d+)\x27b([01]+)\)',block)
        if len(matches)!=1 or matches[0][0]!=str(width) or len(matches[0][1])!=width:
            raise ValueError('Invalid timer primitive INIT')
        return int(matches[0][1],2)
    irq,irq_pins,port=driver('irq_timer')
    reset=chr(92)+'board/soc/N62_0'
    if not irq.startswith('GTP_DFF_C ') or irq_pins!={'Q':'irq_timer','C':reset,'CLK':'clk','D':'timer_interrupt_next'} or initial(irq,1)!=0 or '.GRS_EN("TRUE")' not in irq:
        raise ValueError('Timer interrupt register capture differs')
    reducer,reducer_pins,port=driver('timer_interrupt_next')
    if not reducer.startswith('GTP_LUT3 ') or reducer_pins!={'Z':'timer_interrupt_next','I0':'timer_lower_at_least','I1':'timer_upper_equal','I2':'timer_upper_greater'}:
        raise ValueError('Timer interrupt reducer mapping differs')
    reducer_truth=initial(reducer,8)
    for value in range(8):
        if (reducer_truth>>value)&1!=int(bool(value&4) or ((value&3)==3)):
            raise ValueError('Timer interrupt reducer truth differs')
    comparison={}
    for name,offset,reverse in (('timer_upper_equal',32,False),('timer_upper_greater',32,False),('timer_lower_at_least',0,True)):
        signal=name
        cells=[]
        for pair in reversed(range(16)):
            block,pins,port=driver(signal)
            if not block.startswith('GTP_LUT6CARRY ') or port!='COUT' or pins.get('Z')!='' or pins.get('I4')!='' or pins.get('I5')!='' or set(pins)!={'COUT','Z','CIN','I0','I1','I2','I3','I4','I5'}:
                raise ValueError('Timer comparison carry topology differs')
            for parameter in ('I5_TO_CARRY','I5_TO_LUT'):
                if re.findall(r'\.'+parameter+r'\("([A-Z]+)"\)',block)!=['FALSE']:
                    raise ValueError('Timer comparison carry mode differs')
            for bit in range(2):
                for side in range(2):
                    source='timer_compare_next' if bool(side)^reverse else 'timer_value_next'
                    if pins['I'+str(2*bit+side)]!=f'{source}[{offset+2*pair+bit}]':
                        raise ValueError('Timer comparison uses wrong next-state bits')
            truth=initial(block,64)
            for value in range(16):
                left=(value&1)|((value>>1)&2)
                right=((value>>1)&1)|((value>>2)&2)
                if reverse:
                    left,right=right,left
                for floating in range(2):
                    index=value+(floating<<4)
                    select=(truth>>index)&1
                    fallback=(truth>>(index+32))&1
                    for previous in range(2):
                        actual=previous if select else fallback
                        if name=='timer_upper_equal':
                            expected=left==right and (previous if pair else True)
                        else:
                            expected=left>right or (left==right and (previous if pair else name=='timer_lower_at_least'))
                        if actual!=int(expected):
                            raise ValueError('Timer comparison native truth differs')
            cells.append(dict(pair=pair,signal=signal,sha256=digest(block)))
            signal=pins['CIN']
            if bool(signal)!=bool(pair):
                raise ValueError('Timer comparison carry chain length differs')
        comparison[name]=dict(cells=cells,truth_inputs=1024)
    upper_write_control='_N22829_inv'
    if retained_increment:
        selector,selector_pins,selector_port=driver('timer_value_next[0]')
        expected_selector={'Z':'timer_value_next[0]','Z5':counter_low_data,'I0':'req_data[0]','I1':'req_strobe[0]','I2':'timer_value[0]','I3':'timer_incremented[0]','I5':counter_write}
        if not selector.startswith('GTP_LUT6D ') or selector_port!='Z' or {key:value for key,value in selector_pins.items() if key!='I4'}!=expected_selector or not selector_pins.get('I4'):
            raise ValueError('Retained increment write-selector boundary differs')
        upper_write_control=selector_pins['I4']
        control,control_pins,control_port=driver(upper_write_control)
        expected_control_inputs=('req_valid','req_write','rsp_valid','req_address[3]','N36',address_hit)
        if not control.startswith('GTP_LUT6 ') or control_port!='Z' or set(control_pins)!={'Z',*('I'+str(bit) for bit in range(6))} or tuple(control_pins['I'+str(bit)] for bit in range(6))!=expected_control_inputs:
            raise ValueError('Retained increment write-control inputs differ')
        if initial(control,64)!=(1<<51):
            raise ValueError('Retained increment write-control truth differs')
    controls={counter_write,upper_write_control,compare_low_enable,compare_high_enable}
    if retained_increment:
        positive,positive_pins,positive_port=driver(counter_write)
        negative,negative_pins,negative_port=driver(counter_enable)
        expected_enable_inputs=('req_write','req_address[2]','req_address[3]','request_fire',address_hit)
        if not positive.startswith('GTP_LUT5 ') or positive_port!='Z' or not negative.startswith('GTP_LUT6D ') or negative_port!='Z' or negative_pins.get('I5')!="1'b1":
            raise ValueError('Retained increment enable complement mapping differs')
        if tuple(positive_pins.get('I'+str(bit)) for bit in range(5))!=expected_enable_inputs or tuple(negative_pins.get('I'+str(bit)) for bit in range(5))!=expected_enable_inputs:
            raise ValueError('Retained increment enable inputs differ')
        if initial(positive,32)^(initial(negative,64)>>32)!=0xffffffff:
            raise ValueError('Retained increment enable is not a proven complement')
    increment_cutpoints={f'timer_incremented[{bit}]' for bit in range(64)} if retained_increment else set()
    capture=[]
    def expression(signal,data,used,active):
        if retained_increment and signal==counter_enable:
            used.add(counter_write)
            return ('gate',1,[(0,('leaf',counter_write))])
        if signal in ("1'b0","1'b1"):
            return ('constant',int(signal[-1]))
        if signal in controls or signal in increment_cutpoints or re.fullmatch(r'(timer_value|timer_compare|req_data|req_strobe)\[\d+\]',signal):
            used.add(signal)
            return ('leaf',signal)
        if signal in active:
            raise ValueError('Timer capture combinational cycle')
        block,pins,port=driver(signal)
        if block.startswith('GTP_LUT6CARRY ') and signal==data and port=='Z':
            used.add(signal)
            return ('leaf',signal)
        kind=re.match(r'GTP_LUT([1-6])(D)?\b',block)
        if not kind or (kind[2] and kind[1]!='6'):
            raise ValueError('Unrecognized timer capture mux primitive')
        width=5 if port=='Z5' else int(kind[1])
        truth=initial(block,64 if kind[2] else 1<<width)&((1<<(1<<width))-1)
        fixed={bit:int(pins['I'+str(bit)][-1]) for bit in range(width) if pins.get('I'+str(bit)) in ("1'b0","1'b1")}
        fixed_mask=sum(1<<bit for bit in fixed)
        fixed_value=sum(value<<bit for bit,value in fixed.items())
        original_truth=truth
        truth=sum(((original_truth>>((value&~fixed_mask)|fixed_value))&1)<<value for value in range(1<<width))
        support=[bit for bit in range(width) if any(((truth>>value)&1)!=((truth>>(value^(1<<bit)))&1) for value in range(1<<width))]
        terms=[]
        for bit in support:
            source=pins.get('I'+str(bit),'')
            if not source:
                raise ValueError('Timer capture depends on floating input')
            terms.append((bit,expression(source,data,used,active|{signal})))
        return ('gate',truth,terms)
    def evaluate(term,values):
        if term[0]=='constant':
            return term[1]
        if term[0]=='leaf':
            return values[term[1]]
        index=sum(evaluate(child,values)<<bit for bit,child in term[2])
        return (term[1]>>index)&1
    for family in ('timer_value','timer_compare'):
        for bit in range(64):
            output=f'{family}[{bit}]'
            next_signal=f'{family}_next[{bit}]'
            block,pins,port=driver(output)
            compare=family=='timer_compare'
            kind='GTP_DFF_PE' if compare else ('GTP_DFF_CE' if bit<32 else 'GTP_DFF_C')
            reset_port='P' if compare else 'C'
            if not block.startswith(kind+' ') or port!='Q' or pins.get(reset_port)!=reset or pins.get('CLK')!='clk' or initial(block,1)!=int(compare) or '.GRS_EN("TRUE")' not in block:
                raise ValueError('Timer state capture/reset differs')
            expected_ports={'Q',reset_port,'CLK','D'}|({'CE'} if compare or bit<32 else set())
            if set(pins)!=expected_ports:
                raise ValueError('Timer state capture ports differ')
            if not compare and bit>=32:
                if pins['D']!=next_signal:
                    raise ValueError('Timer high capture differs from compared next state')
                capture.append(dict(signal=output,sha256=digest(block),direct_next_capture=True,truth_inputs=0))
                continue
            expected_enable=(compare_low_enable if bit<32 else compare_high_enable) if compare else counter_enable
            if pins['CE']!=expected_enable:
                raise ValueError('Timer state enable mapping differs')
            used={output}
            next_term=expression(next_signal,pins['D'],used,set())
            data_term=expression(pins['D'],pins['D'],used,set())
            enable_term=expression(pins['CE'],pins['D'],used,set())
            leaves=sorted(used)
            if len(leaves)>8:
                raise ValueError('Timer capture proof exceeds inspected local boundary')
            for value in range(1<<len(leaves)):
                values={leaf:(value>>index)&1 for index,leaf in enumerate(leaves)}
                expected=evaluate(data_term,values) if evaluate(enable_term,values) else values[output]
                if evaluate(next_term,values)!=expected:
                    raise ValueError('Timer compared next state differs from actual D/CE capture')
            capture.append(dict(signal=output,sha256=digest(block),direct_next_capture=False,truth_inputs=1<<len(leaves),leaves=leaves))
    report=dict(scope='binary_native_next_state_comparison_and_capture_correspondence_not_full_bus_or_netlist_equivalence',irq_sha256=digest(irq),reducer_sha256=digest(reducer),reset=reset,comparison=comparison,comparison_truth_inputs=3080,state_registers=capture,capture_truth_inputs=sum(record['truth_inputs'] for record in capture),decoded_control_cutpoints=sorted(controls))
    if retained_increment:
        report['increment_boundary']=increment_evidence
        report['increment_enable_complement_truth_inputs']=32
        report['increment_write_control_truth_inputs']=64
        report['increment_write_control_sha256']=digest(control)
    return report
