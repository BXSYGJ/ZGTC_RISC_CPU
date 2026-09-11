import hashlib
import re


def inspect_arithmetic_group(native):
    modules=re.findall(r'\bmodule\s+rv32_alu\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native ALU module')
    alu=modules[0]
    records=[]
    for suffix in ('zero','one'):
        for bit in range(16):
            signal=f'arithmetic_high_{suffix}[{bit}]'
            matches=re.findall(r'GTP_LUT3\b[^;]*\.Z\s*\('+re.escape(signal)+r'\s*\)[^;]*;',alu)
            if len(matches)!=1:
                raise ValueError('Missing unique arithmetic group mux: '+signal)
            block=matches[0]
            pins=dict((name,value.strip()) for name,value in re.findall(r'\.(I[0-2])\s*\(([^)]*)\)',block))
            if pins!=dict(I0='operation[0]',I1=f'difference_high_{suffix}[{bit}]',I2=f'sum_high_{suffix}[{bit}]'):
                raise ValueError('Arithmetic group mux inputs changed: '+signal)
            if re.findall(r'\.INIT\(8\x27b([01]+)\)',block)!=['11011000']:
                raise ValueError('Arithmetic group mux INIT changed: '+signal)
            consumers=re.findall(r'\.I[0-5]\s*\('+re.escape(signal)+r'\s*\)',alu)
            if not consumers:
                raise ValueError('Arithmetic group mux lacks active consumers: '+signal)
            records.append(dict(signal=signal,pins=pins,init='11011000',consumers=len(consumers),driver_sha256=hashlib.sha256(block.encode()).hexdigest().upper()))
    return records
