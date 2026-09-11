from analyze_branch_history import LocalResolutionReplay, folded_index


class IndexedLoopResolutionProxy:
    def __init__(self, entries=4, confidence_threshold=2, count_bits=8, index_shift=0):
        if type(entries) is not int or entries not in (1, 2, 4, 8, 16):
            raise ValueError('Unsupported loop table size')
        if type(confidence_threshold) is not int or confidence_threshold not in (1, 2, 3):
            raise ValueError('Unsupported confidence threshold')
        if type(count_bits) is not int or not 2 <= count_bits <= 16:
            raise ValueError('Unsupported loop counter width')
        if type(index_shift) is not int or index_shift < 0 or index_shift + entries.bit_length() - 1 > 8:
            raise ValueError('Loop index slice exceeds folded index')
        self.index_shift = index_shift
        self.base = LocalResolutionReplay(3)
        self.entries = [None] * entries
        self.confidence_threshold = confidence_threshold
        self.maximum_count = (1 << count_bits) - 1
        self.overrides = 0
        self.prediction_changes = 0

    def step(self, pc, target, taken, conditional):
        if any(type(value) is not int or not 0 <= value < 65536 or value % 4 for value in (pc, target)):
            raise ValueError('Unsupported branch address')
        if taken not in (0, 1) or conditional not in (0, 1):
            raise ValueError('Invalid branch flags')
        index = folded_index(pc)
        base_hit = self.base.valid[index] and self.base.tags[index] == pc >> 10 and self.base.conditional[index]
        prior_target = self.base.targets[index]
        prediction = self.base.step(pc, target, taken, conditional)
        if not conditional or target >= pc:
            return prediction
        slot = (index >> self.index_shift) & (len(self.entries) - 1)
        entry = self.entries[slot]
        if entry is None or entry['pc'] != pc:
            entry = dict(pc=pc, current=0, previous_trip=None, confidence=0, overflow=False)
            self.entries[slot] = entry
        if base_hit and not entry['overflow'] and entry['previous_trip'] is not None and entry['confidence'] >= self.confidence_threshold:
            alternate = prior_target if entry['current'] < entry['previous_trip'] else pc + 4
            self.overrides += 1
            self.prediction_changes += alternate != prediction
            prediction = alternate
        if taken:
            if entry['current'] == self.maximum_count:
                entry['overflow'] = True
                entry['confidence'] = 0
            else:
                entry['current'] += 1
        else:
            if entry['overflow'] or entry['current'] == 0:
                entry['previous_trip'] = None
                entry['confidence'] = 0
            elif entry['previous_trip'] == entry['current']:
                entry['confidence'] = min(3, entry['confidence'] + 1)
            else:
                entry['previous_trip'] = entry['current']
                entry['confidence'] = 0
            entry['current'] = 0
            entry['overflow'] = False
        return prediction
