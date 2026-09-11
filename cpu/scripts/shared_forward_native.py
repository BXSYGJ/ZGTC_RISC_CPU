from forward_maxfan_native import inspect_forward_replication as inspect_selector_replication


SELECT_INPUTS = {
    'a': ('pipeline_valid[3]', 'mem_exception', 'mem_load', '_N36246', '_N36247', '_N20624'),
    'b': ('pipeline_valid[3]', 'mem_exception', 'mem_load', '_N38703', '_N38704', '_N20624'),
}
SELECT_TOTALS = {'a': 40, 'b': 39}


def inspect_forward_replication(native):
    return inspect_selector_replication(native, SELECT_INPUTS, SELECT_TOTALS)
