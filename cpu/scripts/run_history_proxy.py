from counter_policy_proxy import CounterPolicyReplay
from analyze_branch_history import folded_index

MODES = ('baseline3','taken_run_saturating','taken_run_modulo','both_run_saturating')


class RunHistoryReplay(CounterPolicyReplay):
    def __init__(self, mode='baseline3'):
        if mode not in MODES:
            raise ValueError('Unknown bounded run history policy')
        super().__init__()
        self.mode = mode

    def advance(self, history, taken):
        if self.mode == 'baseline3':
            return ((history << 1) | taken) & 7
        if self.mode == 'taken_run_saturating':
            return min(7,history+1) if taken else 0
        if self.mode == 'taken_run_modulo':
            return ((history+1)&7) if taken else 0
        same_direction = (history >> 2) == taken
        return (taken << 2) | (min(3,(history&3)+1) if same_direction else 0)

    def initial(self, taken, conditional):
        if not conditional:
            return 0
        return (taken << 2) if self.mode == 'both_run_saturating' else taken

    def step(self, pc, target, taken, conditional):
        if any(type(value) is not int or not 0 <= value < 65536 or value % 4 for value in (pc,target)):
            raise ValueError('Unsupported aligned branch address')
        if type(taken) is not int or type(conditional) is not int or taken not in (0,1) or conditional not in (0,1):
            raise ValueError('Unsupported branch flags')
        index = folded_index(pc)
        tag = pc >> 10
        hit = self.valid[index] and self.tags[index] == tag
        history = self.history[index]
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[index][history] >= 2) else pc + 4
        if not hit or self.conditional[index] != conditional:
            self.counters[index] = [2 if taken else 1] * 8
            self.history[index] = self.initial(taken,conditional)
        elif conditional:
            counter = self.counters[index][history]
            self.counters[index][history] = self.transitions[taken][counter]
            self.history[index] = self.advance(history,taken)
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction
