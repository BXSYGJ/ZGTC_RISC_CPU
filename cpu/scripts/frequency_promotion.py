from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Measurement:
    iterations: int
    cycles: int
    clock_hz: int
    luts: int

    def __post_init__(self):
        for name in ('iterations', 'cycles', 'clock_hz', 'luts'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'{name} must be a positive integer')

    @property
    def execution_efficiency(self):
        return Fraction(self.iterations * 1000000, self.cycles)

    @property
    def resource_efficiency(self):
        return Fraction(self.iterations * self.clock_hz, self.cycles * self.luts)

    @property
    def meets_target(self):
        return self.clock_hz >= 150000000 and self.execution_efficiency >= Fraction(318, 100) and self.resource_efficiency >= Fraction(52, 1000)


def compare_measurements(baseline, candidate):
    if not isinstance(baseline, Measurement) or not isinstance(candidate, Measurement):
        raise TypeError('Both inputs must be validated Measurement objects')
    if not baseline.meets_target:
        raise ValueError('The promotion baseline must already meet all three target thresholds')
    conditions = dict(
        candidate_meets_target=candidate.meets_target,
        frequency_increases=candidate.clock_hz > baseline.clock_hz,
        execution_efficiency_nondecreasing=candidate.execution_efficiency >= baseline.execution_efficiency,
        resource_efficiency_nondecreasing=candidate.resource_efficiency >= baseline.resource_efficiency,
    )
    return dict(scope='exact_metric_policy_only_not_artifact_or_hardware_qualification',allowed=all(conditions.values()),conditions=conditions)
