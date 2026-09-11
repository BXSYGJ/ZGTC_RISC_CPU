import hashlib
import json
import mmap
import re
import struct
from collections import Counter
from functools import lru_cache
from itertools import zip_longest
from pathlib import Path


RECORD = struct.Struct('<QII')
DRIVER_SHA256 = '54E439C391BEA141D0E1D87074AC614743B8A6B8D1838C976CDE63E73BB2D114'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def firmware_image(path):
    words = Path(path).read_text(encoding='ascii').splitlines()
    require(len(words) == 16384 and all(re.fullmatch('[0-9a-fA-F]{8}', word) for word in words), 'Invalid64KiB firmware image')
    return b''.join(struct.pack('<I', int(word, 16)) for word in words)


def extract_cycle_pc(disassembly, image, function):
    require(re.findall(r'^\s*[0-9a-fA-F]+ <([^>]+)>:', disassembly, re.M) == [function], 'Missing, duplicate, or unrelated timer function')
    instructions = [(int(match[0], 16), int(match[1], 16)) for match in
                    re.findall(r'^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s', disassembly, re.M)]
    matches = [(address, instruction) for address, instruction in instructions if instruction & 0xfffff07f == 0xb0002073]
    require(len(matches) == 1, 'Timer function must have exactly one mcycle low read')
    address, instruction = matches[0]
    require(address % 4 == 0 and address+4 <= len(image), 'Timer boundary outside aligned firmware')
    require(int.from_bytes(image[address:address+4], 'little') == instruction, 'ELF boundary differs from loaded firmware')
    return address


@lru_cache(maxsize=16384)
def instruction_info(instruction):
    opcode = instruction & 127
    funct3 = (instruction >> 12) & 7
    funct7 = instruction >> 25
    first = (instruction >> 15) & 31
    second = (instruction >> 20) & 31
    destination = (instruction >> 7) & 31
    require(instruction & 3 == 3, 'Non-RV32 instruction in trace')
    if opcode in (0x37, 0x17, 0x6f):
        return 'no_register_source', None, None, 0
    if opcode == 0x67:
        require(funct3 == 0, 'Illegal JALR in trace')
        return 'jalr_address', first, None, 0
    if opcode == 0x63:
        require(funct3 not in (2, 3), 'Illegal branch in trace')
        return 'branch_compare', first, second, 0
    if opcode == 0x03:
        require(funct3 in (0, 1, 2, 4, 5), 'Illegal load in trace')
        return 'load_address', first, None, destination
    if opcode == 0x23:
        require(funct3 <= 2, 'Illegal store in trace')
        return 'store', first, second, 0
    if opcode in (0x13, 0x33):
        if opcode == 0x33:
            require(funct7 in (0, 1) or (funct7 == 32 and funct3 in (0, 5)), 'Illegal register ALU instruction')
            if funct7 == 1:
                return 'multiply' if funct3 <= 3 else 'divide', first, second, 0
        else:
            second = None
            if funct3 == 1:
                require(funct7 == 0, 'Illegal left shift immediate')
            if funct3 == 5:
                require(funct7 in (0, 32), 'Illegal right shift immediate')
        operation = 'integer_add_sub' if funct3 == 0 else 'integer_shift' if funct3 in (1, 5) else 'integer_compare' if funct3 in (2, 3) else 'integer_logic'
        return operation, first, second, 0
    if opcode == 0x73:
        if funct3 == 0:
            require(instruction in (0x00000073, 0x00100073, 0x30200073, 0x10500073), 'Unsupported system instruction')
            return 'system', None, None, 0
        require(funct3 in (1, 2, 3, 5, 6, 7), 'Illegal CSR instruction')
        return 'csr_register' if funct3 < 4 else 'csr_immediate', first if funct3 < 4 else None, None, 0
    if opcode == 0x0f:
        require(funct3 in (0, 1), 'Illegal fence in trace')
        return 'fence', None, None, 0
    raise ValueError(f'Unsupported opcode in trace: {instruction:08x}')


def dependency_kind(previous_instruction, instruction):
    previous_destination = instruction_info(previous_instruction)[3]
    operation, first, second, _ = instruction_info(instruction)
    first_dependency = previous_destination != 0 and first == previous_destination
    second_dependency = previous_destination != 0 and second == previous_destination
    if not (first_dependency or second_dependency):
        return 'no_adjacent_load_dependency', 0
    mask = int(first_dependency) | (int(second_dependency) << 1)
    if operation == 'store':
        operation = {1: 'store_address', 2: 'store_data', 3: 'store_address_data'}[mask]
    return operation, mask


def trace_records(path, metadata, image):
    path = Path(path)
    require(metadata['schema'] == 1 and metadata['record_bytes'] == RECORD.size, 'Unsupported trace schema')
    require(metadata['records'] >= 2 and path.stat().st_size == metadata['records']*RECORD.size, 'Truncated or inconsistent trace length')
    previous_cycle = None
    with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        for record_index in range(metadata['records']):
            cycle, address, instruction = RECORD.unpack_from(mapped, record_index*RECORD.size)
            require(previous_cycle is None or cycle > previous_cycle, 'Trace cycles are not strictly increasing')
            require(address % 4 == 0 and address+4 <= len(image), 'Trace PC outside aligned firmware')
            require(int.from_bytes(image[address:address+4], 'little') == instruction, 'Trace instruction differs from firmware')
            instruction_info(instruction)
            if address == metadata['start_pc']:
                require(record_index == 0, 'Duplicate trace start')
            if address == metadata['stop_pc']:
                require(record_index == metadata['records']-1, 'Early or duplicate trace stop')
            if record_index == 0:
                require(address == metadata['start_pc'] and cycle == metadata['start_cycle'], 'Trace start metadata mismatch')
            if record_index == metadata['records']-1:
                require(address == metadata['stop_pc'] and cycle == metadata['stop_cycle'], 'Trace stop metadata mismatch')
                require(cycle-metadata['start_cycle'] == metadata['cycles'], 'Trace cycle span mismatch')
            previous_cycle = cycle
            yield cycle, address, instruction


def compare_records(baseline_records, candidate_records):
    groups = {}
    transitions = {}
    sequence_digest = hashlib.sha256()
    previous_baseline = previous_candidate = None
    count = 0
    for baseline, candidate in zip_longest(baseline_records, candidate_records):
        require(baseline is not None and candidate is not None, 'Trace record counts differ')
        require(baseline[1:] == candidate[1:], 'Retired instruction sequence differs')
        sequence_digest.update(struct.pack('<II', baseline[1], baseline[2]))
        if previous_baseline is not None:
            kind, dependency_mask = dependency_kind(previous_baseline[2], baseline[2])
            baseline_gap = baseline[0]-previous_baseline[0]
            candidate_gap = candidate[0]-previous_candidate[0]
            require(baseline_gap > 0 and candidate_gap > 0, 'Nonpositive retirement gap')
            delta = candidate_gap-baseline_gap
            group = groups.setdefault(kind, dict(intervals=0, baseline_cycles=0, candidate_cycles=0, delta_cycles=0, delta_histogram=Counter()))
            group['intervals'] += 1
            group['baseline_cycles'] += baseline_gap
            group['candidate_cycles'] += candidate_gap
            group['delta_cycles'] += delta
            group['delta_histogram'][delta] += 1
            if dependency_mask:
                key = previous_baseline[1], baseline[1], baseline[2], dependency_mask
                transition = transitions.setdefault(key, dict(load_pc=key[0], consumer_pc=key[1], instruction=key[2], dependency_mask=key[3], category=kind,
                    occurrences=0, baseline_cycles=0, candidate_cycles=0, delta_cycles=0))
                transition['occurrences'] += 1
                transition['baseline_cycles'] += baseline_gap
                transition['candidate_cycles'] += candidate_gap
                transition['delta_cycles'] += delta
        previous_baseline, previous_candidate = baseline, candidate
        count += 1
    require(count >= 2, 'Empty or incomplete trace comparison')
    for group in groups.values():
        group['delta_histogram'] = dict(sorted(group['delta_histogram'].items()))
    return dict(records=count, intervals=count-1, instruction_sequence_sha256=sequence_digest.hexdigest().upper(), groups=groups,
        transitions=sorted(transitions.values(), key=lambda item: (-item['delta_cycles'], item['load_pc'], item['consumer_pc'])),
        interpretation='Observed retirement-interval differences grouped by adjacent-load dependencies; not direct internal stall-counter attribution')
