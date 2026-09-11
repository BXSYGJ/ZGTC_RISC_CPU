import hashlib
import re


def require(condition,message):
    if not condition:
        raise ValueError(message)


def pins(block):
    return {port:signal.strip() for port,signal in re.findall(r'\.(COUT|CIN|Z|I[0-5])\s*\(([^)]*)\)',block)}


def carry_truth(block,inputs):
    matches = re.findall(r"\.INIT\(64'b([01]{64})\)",block)
    carry_mode = re.findall(r'\.I5_TO_CARRY\("(TRUE|FALSE)"\)',block)
    lut_mode = re.findall(r'\.I5_TO_LUT\("(TRUE|FALSE)"\)',block)
    require(len(matches) == len(carry_mode) == len(lut_mode) == 1, 'Invalid carry configuration')
    truth = int(matches[0],2)
    address = inputs & 31
    lower,upper = (truth >> address) & 1,(truth >> (address+32)) & 1
    input_five,carry_in = (inputs >> 5) & 1,(inputs >> 6) & 1
    carry_out = carry_in if lower else input_five if carry_mode[0] == 'TRUE' else upper
    select = input_five if lut_mode[0] == 'TRUE' else carry_in
    return {'COUT':carry_out,'Z':upper if select else lower}


def inspect_address_chains(native,first_bit,last_bit):
    require((first_bit,last_bit) in ((0,31),(2,15)), 'Unsupported measured address range')
    modules = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',native)
    require(len(modules) == 1, 'Ambiguous native predictor module')
    module = modules[0]
    blocks = re.findall(r'GTP_LUT6CARRY\b[^;]*;',module)
    stages = (last_bit-first_bit+1)//2
    chains = {}
    total = 0
    for prefix,operation,left,right,flag,output in (('N81','eq','fetch_pc','update_pc','update_taken','_N37053'),('N79','lt','update_pc','update_target','update_conditional','N87')):
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
    gate = [block for block in blocks if pins(block).get('Z') == 'loop_pending_taken']
    require(len(gate) == 1, 'Missing unique pending qualification gate')
    gate_ports = pins(gate[0])
    require(gate_ports == dict(COUT='',Z='loop_pending_taken',CIN='train_update_co',I0=chr(92)+'board/soc/core/mem_fence_i',I1='N87',I2='',I3='_N37053',I4='',I5=''), 'Pending qualifier connections differ')
    for inputs in range(128):
        expected = not (inputs & 1) and bool(inputs & 2) and bool(inputs & 8) and bool(inputs & 64)
        require(carry_truth(gate[0],inputs)['Z'] == int(expected), 'Pending qualifier truth differs')
        total += 1
    return dict(scope='binary_native_comparator_stage_induction_and_pending_gate_not_whole_predictor_equivalence',chains=chains,truth_checks=total,pending_gate_sha256=hashlib.sha256(gate[0].encode()).hexdigest().upper())
