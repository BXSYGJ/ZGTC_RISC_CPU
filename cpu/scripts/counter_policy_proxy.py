from analyze_branch_history import LocalResolutionReplay, folded_index

POLICIES = {
    'saturating': ((0,0,1,2),(1,2,3,3)),
    'weak_flip_strong': ((0,0,0,2),(1,3,3,3)),
    'taken_flip_strong': ((0,0,1,2),(1,3,3,3)),
    'not_taken_flip_strong': ((0,0,0,2),(1,2,3,3)),
}


class CounterPolicyReplay(LocalResolutionReplay):
    def __init__(self, policy='saturating'):
        if policy not in POLICIES:
            raise ValueError('Unknown bounded counter policy')
        super().__init__(3)
        self.transitions = POLICIES[policy]

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
            self.history[index] = taken if conditional else 0
        elif conditional:
            counter = self.counters[index][history]
            self.counters[index][history] = self.transitions[taken][counter]
            self.history[index] = ((history << 1) | taken) & 7
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction
