from fractions import Fraction

from frequency_promotion import Measurement


PREFERRED_CLOCK_HZ = 160000000
MIN_FALLBACK_CLOCK_HZ = 157165000
MIN_EXECUTION_EFFICIENCY = Fraction(318, 100)
MIN_RESOURCE_EFFICIENCY = Fraction(52, 1000)
MIN_COREMARK = Fraction(500)


def coremark(measurement):
    if not isinstance(measurement, Measurement):
        raise TypeError('Expected a validated Measurement')
    return Fraction(measurement.iterations * measurement.clock_hz, measurement.cycles)


def meets_target(measurement):
    score = coremark(measurement)
    return (measurement.clock_hz >= MIN_FALLBACK_CLOCK_HZ
            and measurement.execution_efficiency >= MIN_EXECUTION_EFFICIENCY
            and measurement.resource_efficiency >= MIN_RESOURCE_EFFICIENCY
            and score >= MIN_COREMARK)


def compare_resource_promotion(baseline, candidate):
    if not meets_target(baseline):
        raise ValueError('Resource promotion requires an accepted CoreMark 500 baseline')
    conditions = dict(
        candidate_meets_target=meets_target(candidate),
        frequency_nondecreasing=candidate.clock_hz >= baseline.clock_hz,
        execution_efficiency_nondecreasing=candidate.execution_efficiency >= baseline.execution_efficiency,
        resource_efficiency_increases=candidate.resource_efficiency > baseline.resource_efficiency,
    )
    return dict(scope='exact_metric_policy_only_not_artifact_or_hardware_qualification',
                allowed=all(conditions.values()), conditions=conditions)


def compare_score_resource_tradeoff(baseline, candidate):
    if not isinstance(baseline, Measurement) or not isinstance(candidate, Measurement):
        raise TypeError('Both inputs must be validated Measurement objects')
    if not meets_target(baseline):
        raise ValueError('Score/resource tradeoff requires an accepted CoreMark 500 baseline')
    conditions = dict(
        coremark_nondecreasing=coremark(candidate) >= coremark(baseline),
        resource_efficiency_nondecreasing=candidate.resource_efficiency >= baseline.resource_efficiency,
    )
    return dict(scope='exact_metric_policy_only_not_artifact_or_hardware_qualification',
                allowed=all(conditions.values()), conditions=conditions,
                execution_efficiency_increases=candidate.execution_efficiency > baseline.execution_efficiency,
                execution_efficiency_decreases=candidate.execution_efficiency < baseline.execution_efficiency,
                clock_reduced=candidate.clock_hz < baseline.clock_hz)


def compare_execution_clock_tradeoff(baseline, candidate):
    if not isinstance(baseline, Measurement) or not isinstance(candidate, Measurement):
        raise TypeError('Both inputs must be validated Measurement objects')
    if not meets_target(baseline):
        raise ValueError('Clock tradeoff requires an accepted CoreMark 500 baseline')
    conditions = dict(
        coremark_nondecreasing=coremark(candidate) >= coremark(baseline),
        execution_efficiency_nondecreasing=candidate.execution_efficiency >= baseline.execution_efficiency,
        resource_efficiency_nondecreasing=candidate.resource_efficiency >= baseline.resource_efficiency,
    )
    return dict(scope='exact_metric_policy_only_not_artifact_or_hardware_qualification',
                allowed=all(conditions.values()), conditions=conditions,
                execution_efficiency_increases=candidate.execution_efficiency > baseline.execution_efficiency,
                clock_reduced=candidate.clock_hz < baseline.clock_hz)


def compare_execution_promotion(baseline, candidate):
    if not meets_target(baseline):
        raise ValueError('Execution promotion requires an accepted CoreMark 500 baseline')
    conditions = dict(
        candidate_meets_target=meets_target(candidate),
        frequency_nondecreasing=candidate.clock_hz >= baseline.clock_hz,
        execution_efficiency_increases=candidate.execution_efficiency > baseline.execution_efficiency,
        resource_efficiency_nondecreasing=candidate.resource_efficiency >= baseline.resource_efficiency,
    )
    return dict(scope='exact_metric_policy_only_not_artifact_or_hardware_qualification',
                allowed=all(conditions.values()), conditions=conditions)
