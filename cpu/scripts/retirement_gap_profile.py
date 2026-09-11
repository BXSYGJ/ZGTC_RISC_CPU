import hashlib
import struct
from collections import Counter

from load_use_profile import dependency_kind, instruction_info, require


def accumulate(group, gap):
    group['intervals'] += 1
    group['cycles'] += gap
    group['extra_cycles_above_one_per_interval'] += gap - 1
    group['max_gap'] = max(group['max_gap'], gap)
    group['gap_histogram'][gap] += 1


def empty_group():
    return dict(intervals=0, cycles=0, extra_cycles_above_one_per_interval=0, max_gap=0, gap_histogram=Counter())


def summarize_records(records):
    axes = dict(consumer_operation={}, adjacent_load_dependency={}, preceding_control={})
    transitions = {}
    sequence = hashlib.sha256()
    previous = None
    first_cycle = None
    count = 0
    for current in records:
        cycle, address, instruction = current
        require(all(type(value) is int and value >= 0 for value in current), 'Invalid trace record values')
        require(address < 65536 and address % 4 == 0 and instruction <= 0xffffffff, 'Invalid trace address or instruction')
        operation = instruction_info(instruction)[0]
        sequence.update(struct.pack('<II', address, instruction))
        if previous is None:
            first_cycle = cycle
        else:
            gap = cycle - previous[0]
            require(gap > 0, 'Nonpositive retirement gap')
            dependency, mask = dependency_kind(previous[2], instruction)
            preceding = {0x63: 'branch', 0x6f: 'jal', 0x67: 'jalr'}.get(previous[2] & 127, 'other')
            for axis, label in (('consumer_operation', operation), ('adjacent_load_dependency', dependency), ('preceding_control', preceding)):
                accumulate(axes[axis].setdefault(label, empty_group()), gap)
            key = (previous[1], address)
            if key not in transitions:
                transitions[key] = dict(producer_pc=previous[1], consumer_pc=address, producer_instruction=previous[2],
                                        consumer_instruction=instruction, dependency_mask=mask, category=dependency, **empty_group())
            transition = transitions[key]
            require(transition['producer_instruction'] == previous[2] and transition['consumer_instruction'] == instruction, 'Instruction changed at a repeated transition')
            accumulate(transition, gap)
        previous = current
        count += 1
    require(count >= 2, 'Incomplete retirement trace')
    span = previous[0] - first_cycle
    for groups in axes.values():
        require(sum(group['intervals'] for group in groups.values()) == count - 1, 'Interval conservation failed')
        require(sum(group['cycles'] for group in groups.values()) == span, 'Cycle conservation failed')
        for group in groups.values():
            group['gap_histogram'] = dict(sorted(group['gap_histogram'].items()))
    for transition in transitions.values():
        transition['gap_histogram'] = dict(sorted(transition['gap_histogram'].items()))
    require(sum(item['extra_cycles_above_one_per_interval'] for item in transitions.values()) == span - count + 1, 'Transition overhead conservation failed')
    return dict(schema=1, scope='observed_retirement_intervals_not_internal_stall_or_misprediction_attribution',
                records=count, intervals=count - 1, cycles=span,
                extra_cycles_above_one_per_interval=span - count + 1,
                instruction_sequence_sha256=sequence.hexdigest().upper(), axes=axes,
                transitions=sorted(transitions.values(), key=lambda item: (-item['extra_cycles_above_one_per_interval'], item['producer_pc'], item['consumer_pc'])),
                interpretation='Each axis partitions the same intervals; do not add axes together. Gap minus one is arithmetic overhead, not independently removable stall cycles.')
