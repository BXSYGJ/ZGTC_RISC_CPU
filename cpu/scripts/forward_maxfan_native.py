import hashlib
import re


SELECT_INIT='0000001000000000000000000000000000000000000000000000000000000000'
SELECT_INPUTS={
    'a':('pipeline_valid[3]','mem_exception','mem_load','_N36524','_N36525','_N20855'),
    'b':('pipeline_valid[3]','mem_exception','mem_load','_N38982','_N38983','_N20855'),
}


def inspect_forward_replication(native,expected_inputs=None,expected_totals=None):
    if expected_inputs is None:
        expected_inputs=SELECT_INPUTS
    if expected_totals is None:
        expected_totals={'a':51,'b':42}
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native CPU module')
    core=modules[0]
    gates=[]
    for block in re.findall(r'GTP_LUT6\b[^;]*;',core):
        pins=dict((port,signal.strip()) for port,signal in re.findall(r'\.(Z|I[0-5])\s*\(([^)]*)\)',block))
        gates.append((block,pins))
    loads={}
    for signal in re.findall(r'\.(?:I[0-5]|CE|D|CIN)\s*\(([^)]*)\)',core):
        signal=signal.strip()
        loads[signal]=loads.get(signal,0)+1
    records={}
    for operand,inputs in expected_inputs.items():
        matched=[(block,pins) for block,pins in gates if tuple(pins.get('I'+str(index)) for index in range(6))==inputs]
        if len(matched)!=(3 if operand=='a' else 2):
            raise ValueError('Forward replica count or source mapping changed: '+operand)
        copies=[]
        for block,pins in matched:
            if re.findall(r'\.INIT\(64\x27b([01]+)\)',block)!=[SELECT_INIT]:
                raise ValueError('Forward replica truth table changed')
            output=pins.get('Z')
            if not output or sum(gate_pins.get('Z')==output for _,gate_pins in gates)!=1:
                raise ValueError('Forward replica output is not uniquely driven')
            consumers=loads.get(output,0)
            if not 0<consumers<=24:
                raise ValueError('Forward replica fanout is not within target')
            copies.append(dict(signal=output,consumers=consumers,sha256=hashlib.sha256(block.encode()).hexdigest().upper()))
        if sum(record['consumers'] for record in copies)!=expected_totals[operand]:
            raise ValueError('Forward selector total mapped consumers changed')
        records[operand]=copies
    return records
