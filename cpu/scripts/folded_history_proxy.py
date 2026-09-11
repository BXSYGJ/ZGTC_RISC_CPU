from counter_policy_proxy import CounterPolicyReplay
from analyze_branch_history import folded_index

MODES = ('baseline3','fold4_low','fold4_middle','fold4_high','full4_reference')


class FoldedHistoryReplay(CounterPolicyReplay):
    def __init__(self, mode='baseline3'):
        if mode not in MODES:
            raise ValueError('Unknown bounded history policy')
        super().__init__()
        self.width = 3 if mode == 'baseline3' else 4
        self.patterns = 16 if mode == 'full4_reference' else 8
        self.fold = {'fold4_low':0,'fold4_middle':1,'fold4_high':2}.get(mode)
        self.counters = [[1]*self.patterns for _ in range(256)]

    def pattern(self, history):
        if type(history) is not int or not 0 <= history < (1 << self.width):
            raise ValueError('Invalid local history value')
        if self.fold is None:
            return history
        return (history & 7) ^ ((history >> 3) << self.fold)

    def step(self, pc, target, taken, conditional):
        if any(type(value) is not int or not 0 <= value < 65536 or value % 4 for value in (pc,target)):
            raise ValueError('Unsupported aligned branch address')
        if type(taken) is not int or type(conditional) is not int or taken not in (0,1) or conditional not in (0,1):
            raise ValueError('Unsupported branch flags')
        index = folded_index(pc)
        tag = pc >> 10
        hit = self.valid[index] and self.tags[index] == tag
        history = self.history[index]
        pattern = self.pattern(history)
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[index][pattern] >= 2) else pc + 4
        if not hit or self.conditional[index] != conditional:
            self.counters[index] = [2 if taken else 1] * self.patterns
            self.history[index] = taken if conditional else 0
        elif conditional:
            counter = self.counters[index][pattern]
            self.counters[index][pattern] = self.transitions[taken][counter]
            self.history[index] = ((history << 1) | taken) & ((1 << self.width)-1)
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction
