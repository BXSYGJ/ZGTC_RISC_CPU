import hashlib
import re


def inspect_mem_nonzero_register(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native CPU module')
    core=modules[0]
    registers=[]
    for block in re.findall(r'GTP_DFF_CE\b[^;]*;',core):
        pins={port:signal.strip() for port,signal in re.findall(r'\.(Q|C|CE|CLK|D)\s*\(([^)]*)\)',block)}
        registers.append((block,pins))
    def register(output):
        matches=[entry for entry in registers if entry[1].get('Q')==output]
        if len(matches)!=1:
            raise ValueError('Missing unique MEM destination register: '+output)
        return matches[0]
    block,pins=register('mem_rd_nonzero')
    clear=pins.get('C')
    def check_capture(text,ports):
        if ports.get('CE')!='ex_fire' or ports.get('CLK')!='clk' or not clear or ports.get('C')!=clear:
            raise ValueError('MEM destination capture controls differ')
        if re.findall(r'\.INIT\(1\x27b([01])\)',text)!=['0'] or re.findall(r'\.GRS_EN\("([A-Z]+)"\)',text)!=['TRUE']:
            raise ValueError('MEM destination initial/reset configuration differs')
    check_capture(block,pins)
    destinations=[]
    for bit in range(7,12):
        destination,destination_pins=register(f'mem_instruction[{bit}]')
        check_capture(destination,destination_pins)
        if destination_pins.get('D')!=f'ex_instruction[{bit}]':
            raise ValueError('MEM destination data mapping differs')
        destinations.append(hashlib.sha256(destination.encode()).hexdigest().upper())
    drivers=[]
    for gate in re.findall(r'GTP_LUT5\b[^;]*;',core):
        gate_pins={port:signal.strip() for port,signal in re.findall(r'\.(Z|I[0-4])\s*\(([^)]*)\)',gate)}
        if gate_pins.get('Z')==pins.get('D'):
            drivers.append((gate,gate_pins))
    if len(drivers)!=1:
        raise ValueError('Missing unique EX nonzero precomputation')
    gate,gate_pins=drivers[0]
    if tuple(gate_pins.get('I'+str(bit)) for bit in range(5))!=tuple(f'ex_instruction[{bit}]' for bit in range(7,12)):
        raise ValueError('EX nonzero source bits differ')
    initial=re.findall(r'\.INIT\(32\x27b([01]+)\)',gate)
    if len(initial)!=1 or len(initial[0])!=32:
        raise ValueError('EX nonzero truth table missing')
    truth=int(initial[0],2)
    for value in range(32):
        if ((truth>>value)&1)!=int(value!=0):
            raise ValueError('EX nonzero truth table differs')
    consumers=re.findall(r'\.I[0-5]\s*\(mem_rd_nonzero\)',core)
    if not consumers:
        raise ValueError('MEM nonzero register has no active consumers')
    return dict(register_sha256=hashlib.sha256(block.encode()).hexdigest().upper(),precompute_sha256=hashlib.sha256(gate.encode()).hexdigest().upper(),destination_registers_sha256=destinations,clock=pins['CLK'],enable=pins['CE'],clear=clear,input=pins['D'],truth_inputs=32,consumers=len(consumers))
