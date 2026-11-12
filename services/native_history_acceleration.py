"""Exact history-query reuse within one immutable native inference only."""
import bisect
from contextlib import contextmanager
from functools import lru_cache


@contextmanager
def immutable_history_queries(history, engine=None):
    """Keep one read-only connection; discard all caches after this inference.

    No model outputs, training rows, or query boundaries are changed. The caller
    must already have installed the frozen read-only history adapter. This scope
    runs in an isolated item child, never against the changing collector.
    """
    names=('_collection_coverage','_collection_gap_overlap','_event_boundary_is_clean',
           '_get_poll_cycle_start_timestamp','_get_successful_poll_timestamps',
           '_historical_observation_timestamps')
    saved={name:getattr(history,name) for name in names}
    connect=history._connect;mean=history._leave_one_out_mean
    connection=connect()
    peak_list=None;peak_sum=None
    gap_queries={}
    original_overlap=engine.overlaps_gap if engine is not None and hasattr(engine,"overlaps_gap") else None

    def indexed_overlap(gaps,a,b):
        identity=id(gaps)
        cached=gap_queries.get(identity)
        if cached is None:
            starts=[];ends=[];maximum=float("-inf")
            for start,end in gaps:
                starts.append(start);maximum=max(maximum,end);ends.append(maximum)
            cached=(gaps,starts,ends);gap_queries[identity]=cached
        lo,hi=sorted((float(a),float(b)))
        index=bisect.bisect_right(cached[1],hi)-1
        return index>=0 and cached[2][index]>=lo

    @contextmanager
    def borrow():
        yield connection

    def exact_mean(values,index):
        nonlocal peak_list,peak_sum
        if values is not peak_list:
            peak_list=values
            peak_sum=sum(values) if all(type(v) is int for v in values) else None
        if peak_sum is None:return mean(values,index)
        count=len(values)-1
        if count==0:return None
        numerator=peak_sum-values[index]
        quotient,remainder=divmod(numerator,count)
        return quotient if remainder==0 else numerator/count

    try:
        if original_overlap is not None:engine.overlaps_gap=indexed_overlap
        history._connect=borrow
        history._leave_one_out_mean=exact_mean
        for name,fn in saved.items():setattr(history,name,lru_cache(maxsize=100000)(fn))
        yield
    finally:
        for name,fn in saved.items():setattr(history,name,fn)
        history._connect=connect;history._leave_one_out_mean=mean
        if original_overlap is not None:engine.overlaps_gap=original_overlap
        connection.close()
