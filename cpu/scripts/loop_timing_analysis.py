import csv
from collections import Counter

from load_use_profile import require
from test_loop_predictor_small import Reference

HEADER = ['cycle', 'query', 'update', 'fetch_pc', 'predicted_pc', 'update_pc', 'target', 'taken', 'conditional', 'prior_prediction', 'valid',
          'tag0', 'count0', 'trip0', 'confidence0', 'overflow0', 'direction0', 'tag1', 'count1', 'trip1', 'confidence1', 'overflow1', 'direction1']


def analyze_rows(rows):
    reader = csv.reader(rows)
    require(next(reader, None) == ['schema', '1', 'sampling', 'pre_positive_edge_after_negative_edge', 'target_pc', '1300'], 'Wrong timing metadata')
    require(next(reader, None) == HEADER, 'Wrong timing header')
    model = Reference()
    previous_cycle = -1
    records = 0
    queries = 0
    state_checks = 0
    query_states = Counter()
    exit_states = Counter()
    query_cycle_samples = []
    near_exit_queries = 0
    near_exit_with_same_cycle_taken = 0
    footer = None
    for fields in reader:
        if fields and fields[0] == 'END':
            require(len(fields) == 4 and all(value.isascii() and value.isdecimal() for value in fields[1:]), 'Malformed footer')
            footer = list(map(int, fields[1:]))
            require(next(reader, None) is None, 'Trailing timing data')
            break
        require(len(fields) == len(HEADER) and all(value.isascii() and value.isdecimal() for value in fields), 'Malformed timing row')
        row = dict(zip(HEADER, map(int, fields)))
        require(row['cycle'] > previous_cycle and row['query'] in (0, 1) and row['update'] in (0, 1) and row['query'] + row['update'] > 0, 'Invalid event clock or flags')
        require(row['taken'] in (0, 1) and row['conditional'] in (0, 1), 'Invalid training flags')
        expected_valid = sum(1 << slot for slot in model.loops)
        require(row['valid'] == expected_valid, 'Loop valid state differs from independent training replay')
        for slot, entry in model.loops.items():
            suffix = str(slot)
            expected = dict(tag=entry['pc'] >> 2, count=entry['count'], trip=entry['trip'] or 0,
                            confidence=entry['confidence'], overflow=int(entry['overflow']))
            for name, value in expected.items():
                require(row[name + suffix] == value, 'Loop state mismatch: ' + name + suffix)
                state_checks += 1
            require(row['direction' + suffix] in (0, 1), 'Invalid loop direction')
            if entry['confidence'] >= 2:
                require(row['direction' + suffix] == int(entry['count'] < entry['trip']), 'Qualified registered direction disagrees with count/trip')
                state_checks += 1
        if row['query']:
            require(row['fetch_pc'] == 0x514, 'Unexpected queried PC')
            hit, taken, target = model.cycle(1, 0, row['fetch_pc'], 0, 0, 0, 0, 0)
            prediction = target if hit and taken else row['fetch_pc'] + 4
            require(row['predicted_pc'] == prediction, 'Actual query differs from pre-training prediction')
            entry = model.loops.get((model.index(0x514) >> 5) & 1)
            qualified = entry is not None and entry['pc'] == 0x514 and entry['confidence'] >= 2
            key = (int(qualified), entry['count'] if qualified else -1, entry['trip'] if qualified else -1, int(prediction != 0x518))
            query_states[key] += 1
            queries += 1
            if qualified and entry['count'] + 1 == entry['trip']:
                near_exit_queries += 1
                pending = row['update'] and row['update_pc'] == row['fetch_pc'] and row['taken'] and row['conditional'] and row['target'] < row['update_pc']
                near_exit_with_same_cycle_taken += int(bool(pending))
            if qualified and entry['count'] >= entry['trip'] - 1 and len(query_cycle_samples) < 24:
                query_cycle_samples.append(dict(cycle=row['cycle'], count=entry['count'], trip=entry['trip'], prediction=prediction,
                                                update=row['update'], update_pc=row['update_pc'], update_taken=row['taken']))
        if row['update']:
            if row['update_pc'] == 0x514 and not row['taken']:
                entry = model.loops.get((model.index(0x514) >> 5) & 1)
                qualified = entry is not None and entry['pc'] == 0x514 and entry['confidence'] >= 2
                key = (int(qualified), entry['count'] if qualified else -1, entry['trip'] if qualified else -1, int(row['prior_prediction'] != 0x518))
                exit_states[key] += 1
            model.cycle(1, 0, row['fetch_pc'], 1, row['update_pc'], row['target'], row['taken'], row['conditional'])
        previous_cycle = row['cycle']
        records += 1
    require(footer is not None and footer == [records, queries, queries] and queries > 0, 'Incomplete record or query capture checks')
    return dict(schema=1, scope='actual_pre_edge_loop_state_and_verified_prediction_captures_not_performance_promotion',
                records=records, queries=queries, captures_checked=footer[2], state_checks=state_checks,
                query_states=[dict(qualified=key[0], count=key[1], trip=key[2], predicted_taken=key[3], occurrences=value) for key, value in sorted(query_states.items())],
                exit_states=[dict(qualified=key[0], count=key[1], trip=key[2], prior_predicted_taken=key[3], occurrences=value) for key, value in sorted(exit_states.items())],
                near_exit_query_samples=query_cycle_samples, near_exit_queries=near_exit_queries,
                near_exit_with_same_cycle_taken=near_exit_with_same_cycle_taken)
