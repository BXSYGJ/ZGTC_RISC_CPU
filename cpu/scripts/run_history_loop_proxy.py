from loop_prediction_index_proxy import IndexedLoopResolutionProxy
from run_history_proxy import RunHistoryReplay


class RunHistoryLoopProxy(IndexedLoopResolutionProxy):
    def __init__(self, mode='both_run_saturating'):
        super().__init__(entries=2, confidence_threshold=2, count_bits=5, index_shift=5)
        self.base = RunHistoryReplay(mode)
