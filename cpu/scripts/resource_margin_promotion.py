from fractions import Fraction

from frequency_promotion import Measurement
from frequency_target500 import meets_target


def paired_slacks(values):
    if not isinstance(values, (tuple, list)) or len(values) != 2:
        raise ValueError('Require performance and validation setup slacks')
    if any(type(value) not in (int, str, Fraction) for value in values):
        raise ValueError('Setup slack must use exact integers, strings or Fractions')
    try:
        return tuple(Fraction(value) for value in values)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('Invalid finite setup slack') from error


def metric_conditions(baseline, candidate):
    if not isinstance(baseline, Measurement) or not isinstance(candidate, Measurement):
        raise TypeError('Require source-validated full measurements')
    if not meets_target(baseline):
        raise ValueError('Require an accepted CoreMark 500 baseline')
    return dict(
        candidate_meets_target=meets_target(candidate),
        frequency_nondecreasing=candidate.clock_hz >= baseline.clock_hz,
        execution_efficiency_nondecreasing=candidate.execution_efficiency >= baseline.execution_efficiency,
        resource_efficiency_nondecreasing=candidate.resource_efficiency >= baseline.resource_efficiency,
    )


def compare_resource_margin_promotion(baseline, candidate, baseline_slacks, candidate_slacks):
    conditions = metric_conditions(baseline, candidate)
    previous = paired_slacks(baseline_slacks)
    proposed = paired_slacks(candidate_slacks)
    if min(previous) < 0:
        raise ValueError('Baseline timing must be qualified for both firmware images')
    conditions.update(
        both_setup_slacks_nonnegative=min(proposed) >= 0,
        worst_setup_margin_nondecreasing=min(proposed) >= min(previous),
        resource_or_worst_margin_increases=(candidate.resource_efficiency > baseline.resource_efficiency or min(proposed) > min(previous)),
    )
    return dict(scope='exact_metric_and_setup_slack_policy_only_not_source_hold_IO_or_hardware_qualification', allowed=all(conditions.values()), conditions=conditions)


def check_instrumented_metrics(baseline, instrumented, instrumented_slacks):
    if not isinstance(baseline, Measurement) or not isinstance(instrumented, Measurement):
        raise TypeError('Require source-validated full measurements')
    if not meets_target(baseline):
        raise ValueError('Require the accepted pre-ILA CoreMark 500 baseline')
    conditions = dict(
        coremark_at_least_500=Fraction(instrumented.iterations * instrumented.clock_hz, instrumented.cycles) >= 500,
        frequency_nondecreasing=instrumented.clock_hz >= baseline.clock_hz,
        execution_efficiency_nondecreasing=instrumented.execution_efficiency >= baseline.execution_efficiency,
        resource_efficiency_above_0_05=instrumented.resource_efficiency > Fraction(1, 20),
        both_setup_slacks_nonnegative=min(paired_slacks(instrumented_slacks)) >= 0,
    )
    return dict(scope='exact_instrumented_total_LUT_strict_0_05_floor_and_setup_policy_only_not_source_complete_timing_or_hardware_qualification', allowed=all(conditions.values()), conditions=conditions)


def compare_post_ila_resource_promotion(baseline, candidate, candidate_slacks):
    if not isinstance(baseline, Measurement) or not isinstance(candidate, Measurement):
        raise TypeError('Require source-validated full measurements')
    if Fraction(baseline.iterations * baseline.clock_hz, baseline.cycles) < 500 or baseline.resource_efficiency <= Fraction(1, 20):
        raise ValueError('Require an accepted post-ILA baseline above 0.05 CoreMark/LUT')
    conditions = dict(
        frequency_nondecreasing=candidate.clock_hz >= baseline.clock_hz,
        execution_efficiency_nondecreasing=candidate.execution_efficiency >= baseline.execution_efficiency,
        resource_efficiency_increases=candidate.resource_efficiency > baseline.resource_efficiency,
        both_setup_slacks_nonnegative=min(paired_slacks(candidate_slacks)) >= 0,
    )
    return dict(scope='post_hardware_exact_resource_promotion_policy_only_not_hardware_or_artifact_qualification', allowed=all(conditions.values()), conditions=conditions)
