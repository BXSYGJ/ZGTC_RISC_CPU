import unittest

from loop_timing_analysis import HEADER, analyze_rows


def synthetic_lines():
    initial = [10, 1, 0, 1300, 1304, 0, 0, 0, 0, 0, 0] + [0] * 12
    training = [11, 0, 1, 0, 4, 1300, 1284, 1, 1, 1304, 0] + [0] * 12
    trained = [12, 1, 0, 1300, 1284, 0, 0, 0, 0, 0, 1, 325, 1, 0, 0, 0, 1] + [0] * 6
    return ['schema,1,sampling,pre_positive_edge_after_negative_edge,target_pc,1300', ','.join(HEADER)] + [','.join(map(str, row)) for row in (initial, training, trained)] + ['END,3,2,2']


class LoopTimingAnalysisTests(unittest.TestCase):
    def test_pre_training_state_and_capture_conservation(self):
        result = analyze_rows(iter(synthetic_lines()))
        self.assertEqual((result['records'], result['queries'], result['captures_checked']), (3, 2, 2))
        self.assertEqual(result['state_checks'], 5)

    def test_counts_all_qualified_pending_queries(self):
        from test_loop_predictor_small import Reference
        model = Reference()
        rows = []
        def emit(update, taken):
            hit, predicted, target = model.cycle(1, 0, 1300, 0, 0, 0, 0, 0)
            values = [len(rows)+1, 1, update, 1300, target if hit and predicted else 1304, 1300, 1284, taken, 1, 1284, sum(1 << slot for slot in model.loops)]
            for slot in range(2):
                entry = model.loops.get(slot)
                values += [entry['pc'] >> 2, entry['count'], entry['trip'] or 0, entry['confidence'], int(entry['overflow']), int(entry['trip'] is None or entry['count'] < entry['trip'])] if entry else [0]*6
            rows.append(','.join(map(str, values)))
            model.cycle(1, 0, 1300, update, 1300, 1284, taken, 1)
        for repeat in range(5):
            for iteration in range(3):
                if repeat >= 3 and iteration == 2:
                    emit(0, 1)
                emit(1, 1)
            emit(1, 0)
        lines = ['schema,1,sampling,pre_positive_edge_after_negative_edge,target_pc,1300', ','.join(HEADER)] + rows + [f'END,{len(rows)},{len(rows)},{len(rows)}']
        result = analyze_rows(iter(lines))
        self.assertEqual(result['near_exit_queries'], 4)
        self.assertEqual(result['near_exit_with_same_cycle_taken'], 2)

    def test_rejects_protocol_and_conservation_corruption(self):
        cases = [synthetic_lines()[:-1], synthetic_lines() + ['trailing'],
                 synthetic_lines()[:-1] + ['END,3,2,1'], synthetic_lines()[:-1] + ['END,4,2,2']]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                analyze_rows(iter(lines))

    def test_rejects_state_query_and_clock_corruption(self):
        for field, value, reason in (('tag0', 324, 'state mismatch'), ('count0', 2, 'state mismatch'),
                                    ('valid', 0, 'valid state'), ('predicted_pc', 1304, 'pre-training'),
                                    ('cycle', 11, 'event clock'), ('fetch_pc', 1304, 'queried PC')):
            with self.subTest(field=field):
                lines = synthetic_lines()
                fields = lines[4].split(',')
                fields[HEADER.index(field)] = str(value)
                lines[4] = ','.join(fields)
                with self.assertRaisesRegex(ValueError, reason):
                    analyze_rows(iter(lines))


if __name__ == '__main__':
    unittest.main(verbosity=2)
