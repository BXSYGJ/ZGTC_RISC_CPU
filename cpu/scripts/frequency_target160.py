from fractions import Fraction

from frequency_promotion import Measurement, compare_measurements as compare_prior_metrics


MIN_CLOCK_HZ = 160000000
MIN_EXECUTION_EFFICIENCY = Fraction(318,100)
MIN_RESOURCE_EFFICIENCY = Fraction(52,1000)


def meets_target(measurement):
    if not isinstance(measurement,Measurement):
        raise TypeError('Expected a validated Measurement')
    return measurement.clock_hz >= MIN_CLOCK_HZ and measurement.execution_efficiency >= MIN_EXECUTION_EFFICIENCY and measurement.resource_efficiency >= MIN_RESOURCE_EFFICIENCY


def compare_measurements(baseline,candidate):
    if not meets_target(baseline):
        raise ValueError('The promotion baseline must already meet the updated 160 MHz target')
    result = compare_prior_metrics(baseline,candidate)
    result['conditions']['candidate_meets_updated_target'] = meets_target(candidate)
    result['allowed'] = all(result['conditions'].values())
    return result
