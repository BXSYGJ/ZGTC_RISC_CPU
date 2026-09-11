import hashlib
import re

from loop_pending_address_native import carry_truth, pins, require


def inspect_single_bank(native):
    first_bit,last_bit = 2,15
    require((first_bit,last_bit) in ((0,31),(2,15)), 'Unsupported measured address range')
    modules = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',native)
    require(len(modules) == 1, 'Ambiguous native predictor module')
    module = modules[0]
    blocks = re.findall(r'GTP_LUT6CARRY\b[^;]*;',module)
    stages = (last_bit-first_bit+1)//2
    chains = {}
    total = 0
    for prefix,operation,left,right,flag,output in (('N87','eq','fetch_pc','update_pc','update_taken','_N37578'),('N85','lt','update_pc','update_target','update_conditional','N92')):
        entries = []
        for block in blocks:
            match = re.search(re.escape(chr(92)+prefix+'.'+operation)+r'_(\d+)\s',block)
            if match:
                entries.append((int(match[1]),block))
        require(len(entries) == stages and sorted(index for index,block in entries) == list(range(stages)), 'Wrong native comparison stage inventory')
        records = []
        for index,block in sorted(entries):
            low_bit = first_bit+2*index
            port_map = pins(block)
            expected = dict(COUT='' if index == stages-1 else chr(92)+prefix+f'.co [{2*index}]',Z=output if index == stages-1 else '',CIN='' if index == 0 else chr(92)+prefix+f'.co [{2*(index-1)}]',I0=f'{left}[{low_bit}]',I1=f'{right}[{low_bit}]',I2=f'{left}[{low_bit+1}]',I3=f'{right}[{low_bit+1}]',I4=flag if index == stages-1 else '',I5='')
            require(port_map == expected, 'Native comparator data, flag or carry wiring differs')
            require('.I5_TO_CARRY("FALSE")' in block and '.I5_TO_LUT("FALSE")' in block, 'Native comparator carry mode differs')
            selected_port = 'Z' if index == stages-1 else 'COUT'
            for inputs in range(128):
                left_value = (inputs & 1) | ((inputs >> 1) & 2)
                right_value = ((inputs >> 1) & 1) | ((inputs >> 2) & 2)
                carry_in,enabled = (inputs >> 6) & 1,(inputs >> 4) & 1
                if operation == 'eq':
                    expected_value = left_value == right_value and (index == 0 or carry_in)
                else:
                    expected_value = right_value < left_value or (index != 0 and right_value == left_value and carry_in)
                if index == stages-1:
                    expected_value = enabled and expected_value
                require(carry_truth(block,inputs)[selected_port] == int(expected_value), 'Native comparator stage truth differs')
                total += 1
            records.append(hashlib.sha256(block.encode()).hexdigest().upper())
        chains[operation] = dict(stages=stages,first_bit=first_bit,last_bit=last_bit,output=output,flag=flag,stage_sha256=records)
    cells = re.findall(r'GTP_\w+\b[^;]*;',module)
    gates = (("GTP_LUT6","_N4481",6,dict(Z='_N4481',I0=chr(92)+'board/soc/core/mem_fence_i',I1='N92',I2='train_update',I3='loop_ahead_direction[0]',I4='loop_direction[0]',I5='_N37578')),("GTP_LUT3","N1683",3,dict(Z='N1683',I0='N92',I1='train_update',I2='update_index[5]')))
    gate_hashes = {}
    for kind,output,width,expected_ports in gates:
        matches = [cell for cell in cells if cell.startswith(kind+' ') and pins(cell).get('Z') == output]
        require(len(matches) == 1 and pins(matches[0]) == expected_ports, 'Native direction/admission gate wiring differs')
        truth = re.findall(r"\.INIT\("+str(1<<width)+r"'b([01]+)\)",matches[0])
        require(len(truth) == 1 and len(truth[0]) == 1<<width, 'Invalid native direction/admission truth table')
        table = int(truth[0],2)
        for inputs in range(1<<width):
            if width == 6:
                pending = not (inputs & 1) and bool(inputs & 2) and bool(inputs & 4) and bool(inputs & 32)
                expected = bool(inputs & (8 if pending else 16))
            else:
                expected = bool(inputs & 1) and bool(inputs & 2) and not (inputs & 4)
            require((table >> inputs) & 1 == int(expected), 'Native direction/admission truth differs')
            total += 1
        gate_hashes[output] = hashlib.sha256(matches[0].encode()).hexdigest().upper()
    registers = [cell for cell in cells if cell.startswith('GTP_DFF') and re.search(r'\.Q\s*\(\s*'+re.escape(chr(92))+r'?loop_',cell)]
    observed = {}
    for cell in registers:
        port_map = {port:signal.strip() for port,signal in re.findall(r'\.(Q|D|CLK|CE|R|C)\s*\(([^)]*)\)',cell)}
        output = port_map.get('Q','').replace(chr(92),'').replace(' ','')
        require(output not in observed and port_map.get('CLK') == 'clk', 'Duplicate or wrongly clocked native loop register')
        observed[output] = port_map
    expected_outputs = {f'{name}[0]' for name in ('loop_valid','loop_overflow','loop_direction','loop_ahead_direction')}
    for name,width in (('loop_tags',14),('loop_count',5),('loop_trip',5),('loop_confidence',2)):
        expected_outputs.update(f'{name}[0][{index}]' for index in range(width))
    require(set(observed) == expected_outputs, 'Native single-bank register inventory differs')
    for index in range(14):
        require(observed[f'loop_tags[0][{index}]']['D'] == f'update_pc[{index+2}]', 'Native loop tag data mapping differs')
    return dict(scope='binary_native_address_chains_direction_admission_and_register_inventory_not_whole_predictor_equivalence',chains=chains,truth_checks=total,gate_sha256=gate_hashes,single_bank_register_bits=len(observed),tag_bits=14)
