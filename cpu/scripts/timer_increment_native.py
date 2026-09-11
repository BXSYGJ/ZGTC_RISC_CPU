import hashlib
import re


def inspect_timer_increment(native):
    modules=re.findall(r'\bmodule\s+rv32_peripherals\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous increment peripheral module')
    blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',modules[0])
    gates=[]
    for block in blocks:
        pins={port:signal.strip() for port,signal in re.findall(r'\.(Z|Z5|COUT|CIN|I[0-5])\s*\(([^)]*)\)',block)}
        gates.append((block,pins))
    def output(signal):
        matches=[entry for entry in gates if entry[1].get('Z')==signal]
        if len(matches)!=1:
            raise ValueError('Missing unique timer increment output: '+signal)
        return matches[0]
    def initial(block):
        matches=re.findall(r'\.INIT\(64\x27b([01]+)\)',block)
        if len(matches)!=1 or len(matches[0])!=64:
            raise ValueError('Missing increment INIT')
        return int(matches[0],2)
    records=[]
    first,pins=output('timer_incremented[0]')
    if first.startswith('GTP_LUT1 '):
        if pins!={'Z':'timer_incremented[0]','I0':'timer_value[0]'} or re.findall(r'\.INIT\(2\x27b([01]{2})\)',first)!=['01']:
            raise ValueError('Increment bit zero inverter differs')
        zero_samples=2
        shared_zero=False
    else:
        if not first.startswith('GTP_LUT6D ') or pins.get('I0')!='timer_value[0]' or pins.get('I5')!="1'b1":
            raise ValueError('Increment bit zero select or source differs')
        truth=initial(first)
        for value in range(32):
            if (truth>>(32+value))&1!=int(not (value&1)):
                raise ValueError('Increment bit zero depends on unrelated inputs')
        zero_samples=32
        shared_zero=True
    records.append(dict(bit=0,sha256=hashlib.sha256(first.encode()).hexdigest().upper(),truth_inputs=zero_samples,shared_z5_not_part_of_increment=shared_zero))
    previous_carry=''
    for bit in range(1,64):
        signal=f'timer_incremented[{bit}]'
        block,pins=output(signal)
        if not block.startswith('GTP_LUT6CARRY ') or set(pins)!={'Z','COUT','CIN','I0','I1','I2','I3','I4','I5'}:
            raise ValueError('Increment carry primitive differs')
        if pins['CIN']!=previous_carry or bool(pins['COUT'])!=(bit<63):
            raise ValueError('Increment carry connection differs')
        expected_inputs=([f'timer_value[{index}]' for index in range(bit+1)]+['']*(4-bit)) if bit<3 else [f'timer_value[{bit}]','','','','']
        if [pins['I'+str(index)] for index in range(5)]!=expected_inputs or pins['I5']!=("1'b1" if bit==1 else "1'b0"):
            raise ValueError('Increment carry depends on non-counter input')
        for parameter,expected in (('I5_TO_CARRY','TRUE'),('I5_TO_LUT','TRUE' if bit==1 else 'FALSE')):
            if re.findall(r'\.'+parameter+r'\("([A-Z]+)"\)',block)!=[expected]:
                raise ValueError('Increment carry mode differs')
        truth=initial(block)
        samples=0
        for value in range(32):
            lower=(truth>>value)&1
            upper=(truth>>(value+32))&1
            for carry in ((1,) if bit==2 else (0,1)):
                actual_value=upper if (bit==1 or carry) else lower
                actual_carry=carry if lower else int(bit==1)
                if bit==1:
                    expected_value=(value&1)^((value>>1)&1)
                    expected_carry=1
                elif bit==2:
                    expected_value=((value>>2)&1)^int((value&3)==3)
                    expected_carry=int((value&7)==7)
                else:
                    expected_value=(value&1)^carry
                    expected_carry=(value&1)&carry
                if actual_value!=expected_value or actual_carry!=expected_carry:
                    raise ValueError('Increment carry truth differs')
                samples+=1
        previous_carry=pins['COUT']
        records.append(dict(bit=bit,sha256=hashlib.sha256(block.encode()).hexdigest().upper(),truth_inputs=samples,carry=previous_carry))
    return dict(scope='binary_64bit_increment_function_and_control_isolation_not_timing_or_full_netlist_equivalence',outputs=64,truth_inputs=sum(record['truth_inputs'] for record in records),bits=records,bit1_carry_seed=1,bit2_absorbs_three_counter_bits=True)
