import hashlib
import re


BYTE_INIT='0000000000000001000000000000000100000000000000000000000000000000'
REDUCE_INIT='1000000000000000100000000000000000000000000000000000000000000000'


def inspect_wb_byte_zero(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native CPU module')
    core=modules[0]
    gates=[]
    for block in re.findall(r'GTP_LUT(?:6CARRY|4|5)\b[^;]*;',core):
        pins=dict((name,value.strip()) for name,value in re.findall(r'\.(COUT|Z|CIN|I[0-5])\s*\(([^)]*)\)',block))
        gates.append((block,pins))
    def unique_driver(signal,port):
        matches=[gate for gate in gates if gate[1].get(port)==signal]
        if len(matches)!=1:
            raise ValueError('Missing unique WB zero driver: '+signal)
        return matches[0]
    def check_shape(block,pins,initial,carry,lut):
        if re.findall(r'\.INIT\(64\x27b([01]+)\)',block)!=[initial] or re.findall(r'\.I5_TO_CARRY\("([A-Z]+)"\)',block)!=[carry] or re.findall(r'\.I5_TO_LUT\("([A-Z]+)"\)',block)!=[lut]:
            raise ValueError('WB zero native primitive configuration changed')
        if pins.get('I4','')!='':
            raise ValueError('WB zero unused input changed')
    records=[]
    for byte_index in range(4):
        signal=f'early_wb_byte_zero[{byte_index}]'
        lower,lower_pins=unique_driver(signal,'Z')
        if lower.startswith('GTP_LUT5 '):
            if re.findall(r'\.INIT\(32\x27b([01]+)\)',lower)!=['00000000000000010000000000000000'] or set(lower_pins)!={'Z','I0','I1','I2','I3','I4'}:
                raise ValueError('WB zero LUT5 configuration changed')
            upper,upper_pins=unique_driver(lower_pins['I4'],'Z')
            if not upper.startswith('GTP_LUT4 ') or re.findall(r'\.INIT\(16\x27b([01]+)\)',upper)!=['0000000000000001'] or set(upper_pins)!={'Z','I0','I1','I2','I3'}:
                raise ValueError('WB zero LUT4 configuration changed')
            for offset in range(4):
                if lower_pins.get('I'+str(offset))!=f'trace_data[{byte_index*8+offset}]' or upper_pins.get('I'+str(offset))!=f'trace_data[{byte_index*8+offset+4}]':
                    raise ValueError('WB zero byte source bits changed')
            records.append(dict(byte=byte_index,signal=signal,carry=lower_pins['I4'],source_bits=list(range(byte_index*8,byte_index*8+8)),lower_sha256=hashlib.sha256(lower.encode()).hexdigest().upper(),upper_sha256=hashlib.sha256(upper.encode()).hexdigest().upper(),primitive_layout='LUT4_then_LUT5'))
            continue
        check_shape(lower,lower_pins,BYTE_INIT,'TRUE','FALSE')
        if lower_pins.get('I5','')!='' or not lower_pins.get('CIN'):
            raise ValueError('WB zero byte carry connection changed')
        upper,upper_pins=unique_driver(lower_pins['CIN'],'COUT')
        check_shape(upper,upper_pins,BYTE_INIT,'FALSE','TRUE')
        if upper_pins.get('CIN','')!='' or upper_pins.get('I5')!="1'b1":
            raise ValueError('WB zero upper carry seed changed')
        for offset in range(4):
            if lower_pins.get('I'+str(offset))!=f'trace_data[{byte_index*8+offset}]' or upper_pins.get('I'+str(offset))!=f'trace_data[{byte_index*8+offset+4}]':
                raise ValueError('WB zero byte source bits changed')
        records.append(dict(byte=byte_index,signal=signal,carry=lower_pins['CIN'],source_bits=list(range(byte_index*8,byte_index*8+8)),lower_sha256=hashlib.sha256(lower.encode()).hexdigest().upper(),upper_sha256=hashlib.sha256(upper.encode()).hexdigest().upper()))
    reducer,reducer_pins=unique_driver('early_data_zero[3]','Z')
    if reducer.startswith('GTP_LUT4 '):
        if re.findall(r'\.INIT\(16\x27b([01]+)\)',reducer)!=['1000000000000000'] or set(reducer_pins)!={'Z','I0','I1','I2','I3'}:
            raise ValueError('WB zero LUT4 final reduction changed')
    else:
        check_shape(reducer,reducer_pins,REDUCE_INIT,'FALSE','TRUE')
        if reducer_pins.get('CIN','')!='' or reducer_pins.get('I5')!="1'b1":
            raise ValueError('WB zero final byte reduction changed')
    if any(reducer_pins.get('I'+str(index))!=f'early_wb_byte_zero[{index}]' for index in range(4)):
        raise ValueError('WB zero final byte reduction changed')
    consumers=re.findall(r'\.I[0-5]\s*\(early_data_zero\[3\]\s*\)',core)
    if not consumers:
        raise ValueError('WB zero result has no active consumers')
    return dict(bytes=records,reducer_sha256=hashlib.sha256(reducer.encode()).hexdigest().upper(),consumers=len(consumers))
