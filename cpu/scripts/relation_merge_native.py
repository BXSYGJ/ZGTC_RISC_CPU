import hashlib
import re

from forward_maxfan_native import inspect_forward_replication

FORWARD_INPUTS={
    'a':('pipeline_valid[3]','mem_exception','mem_load','_N36530','_N36531','_N20855'),
    'b':('pipeline_valid[3]','mem_exception','mem_load','_N38988','_N38989','_N20855'),
}
SIGNALS=(
    ('early_compare_left[0][31]','early_compare_right[0][31]'),
    ('early_compare_left[1][31]','early_compare_right[0][31]'),
    ('trace_data[31]','early_compare_right[0][31]'),
    ('early_compare_left[0][31]','early_compare_left[1][31]'),
    ('early_compare_left[0][31]','trace_data[31]'),
    ('early_compare_left[1][31]','trace_data[31]'),
)


def inspect_relation_replication(native):
    return inspect_forward_replication(native,FORWARD_INPUTS,{'a':40,'b':41})


def inspect_merged_relations(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native CPU module')
    core=modules[0]
    def normalize(signal):
        return re.sub(r'[\s\\]','',signal)
    gates={}
    for block in re.findall(r'GTP_LUT[1-6]\b[^;]*;',core):
        width=int(re.match(r'GTP_LUT([1-6])',block)[1])
        pins={port:normalize(signal) for port,signal in re.findall(r'\.(Z|I[0-5])\s*\(([^)]*)\)',block)}
        initial=re.findall(r'\.INIT\((\d+)\x27b([01]+)\)',block)
        if len(initial)!=1 or int(initial[0][0])!=2**width or len(initial[0][1])!=2**width:
            raise ValueError('Invalid native LUT truth table')
        gates.setdefault(pins.get('Z'),[]).append(dict(width=width,pins=pins,initial=int(initial[0][1],2),block=block))
    def driver(signal):
        matched=gates.get(signal,[])
        if len(matched)!=1:
            raise ValueError('Missing unique merged relation driver: '+signal)
        return matched[0]
    loads={}
    for signal in re.findall(r'\.I[0-5]\s*\(([^)]*)\)',core):
        signal=normalize(signal)
        loads[signal]=loads.get(signal,0)+1
    records=[]
    for pair,(left_signal,right_signal) in enumerate(SIGNALS):
        signal=f'early_pair_condition[{pair}]'
        gate=driver(signal)
        inputs=set(gate['pins'].values())
        unsigned=f'early_compare_pairs[{pair}].unsigned_less'
        if gate['width']!=6 or not {unsigned,left_signal,right_signal,'ex_instruction[13]','ex_instruction[14]'}.issubset(inputs) or loads.get(signal,0)==0:
            raise ValueError('Relation signed/condition merge is not direct or active')
        visited=set()
        def evaluate(net,values,stack=()):
            if net in values:
                return values[net]
            if net in stack or len(stack)>12:
                raise ValueError('Cyclic or excessive relation cone')
            actual=driver(net)
            visited.add(net)
            index=sum(evaluate(actual['pins']['I'+str(bit)],values,stack+(net,))<<bit for bit in range(actual['width']))
            return (actual['initial']>>index)&1
        for pattern in range(512):
            equal_bits=pattern&15
            unsigned_less=(pattern>>4)&1
            left_sign=(pattern>>5)&1
            right_sign=(pattern>>6)&1
            selection=(pattern>>7)&3
            values={unsigned:unsigned_less,left_signal:left_sign,right_signal:right_sign,'ex_instruction[13]':selection&1,'ex_instruction[14]':selection>>1}
            values.update({f'early_compare_pairs[{pair}].byte_equal[{byte}]':(equal_bits>>byte)&1 for byte in range(4)})
            expected=int(equal_bits==15) if selection==0 else unsigned_less if selection==3 else (left_sign if left_sign!=right_sign else unsigned_less) if selection==2 else 0
            if evaluate(signal,values)!=expected:
                raise ValueError('Merged relation truth-table mismatch: '+str(pair))
        records.append(dict(pair=pair,checks=512,signal=signal,consumers=loads[signal],cone={net:hashlib.sha256(driver(net)['block'].encode()).hexdigest().upper() for net in sorted(visited)}))
    return dict(checks=3072,pairs=records)
