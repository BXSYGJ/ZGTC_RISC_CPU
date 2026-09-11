import hashlib
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def split_success_trace(path, retired):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    require(len(lines) == retired, 'ISA retirement count differs from raw trace length')
    prefix = list(lines)
    tail = []
    while prefix and len(prefix[-1].split()) == 6 and prefix[-1].split()[2] == '0000006f':
        tail.append(prefix.pop())
    require(len(prefix) >= 3, 'ISA success trace has no mailbox sequence')
    ending = [line.split() for line in prefix[-3:]]
    require(all(len(fields) == 6 and fields[0] == 'R' for fields in ending), 'Malformed ISA success sequence')
    require(ending[0][2:] == ['10000f37','1','30','10000000'] and ending[1][2:] == ['00100f93','1','31','00000001'], 'ISA success mailbox address/data setup differs')
    require(ending[2][2] == '01ff2023' and ending[2][3] == '0', 'ISA success mailbox store differs')
    addresses = [int(fields[1],16) for fields in ending]
    require(addresses[1] == addresses[0]+4 and addresses[2] == addresses[1]+4, 'ISA success sequence addresses differ')
    loop_pc = addresses[2]+4
    expected_loop = f'R {loop_pc:08x} 0000006f 0 0 {loop_pc+4:08x}'
    require(all(line == expected_loop for line in tail), 'ISA terminal suffix is not the same success self-loop')
    return prefix, tail


def verify_pair(directory, reference_directory, entry, reference_entry):
    stem = entry['name'] + '_' + entry['configuration']
    current_trace = Path(directory) / (stem + '.trace')
    reference_trace = Path(reference_directory) / (stem + '.trace')
    current_prefix,current_tail = split_success_trace(current_trace,entry['retired'])
    reference_prefix,reference_tail = split_success_trace(reference_trace,reference_entry['retired'])
    require(current_prefix == reference_prefix, 'ISA architectural work before terminal self-loop differs')
    current_memory = Path(directory) / (stem + '.memory')
    reference_memory = Path(reference_directory) / (stem + '.memory')
    require(current_memory.read_bytes() == reference_memory.read_bytes(), 'ISA final memory differs')
    require(entry['retired']-reference_entry['retired'] == len(current_tail)-len(reference_tail), 'ISA retirement delta is not entirely terminal self-loop work')
    return dict(name=entry['name'],configuration=entry['configuration'],work_retired=len(current_prefix),
        parent_terminal_iterations=len(reference_tail),candidate_terminal_iterations=len(current_tail),
        trace_sha256=hashlib.sha256(current_trace.read_bytes()).hexdigest().upper(),
        reference_trace_sha256=hashlib.sha256(reference_trace.read_bytes()).hexdigest().upper(),
        memory_sha256=hashlib.sha256(current_memory.read_bytes()).hexdigest().upper())
