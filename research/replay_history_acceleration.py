"""Research-only memoization for a single monotonically advancing causal mirror.

No predictions are cached. Closed-interval collector queries can be reused
because a sealed replay appends only later timestamps. Changing gap metadata,
source path or the first heartbeat invalidates every query cache. Full native
cycle classification and model planning still run at every issue.
"""
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import sqlite3


@contextmanager
def cached_history():
    from services import history_service as h
    names=('_collection_coverage','_collection_gap_overlap','_event_boundary_is_clean',
           '_get_poll_cycle_start_timestamp','_get_successful_poll_timestamps',
           '_historical_observation_timestamps')
    originals={n:getattr(h,n) for n in names}
    original_mean=h._leave_one_out_mean
    wrappers={n:lru_cache(maxsize=100000)(f) for n,f in originals.items()}
    for n,f in wrappers.items():setattr(h,n,f)
    last=None;last_issue=None;peak_list=None;peak_sum=None

    def exact_mean(values,index):
        nonlocal peak_list,peak_sum
        if values is not peak_list:
            peak_list=values
            peak_sum=sum(values) if all(type(v) is int for v in values) else None
        if peak_sum is None:return original_mean(values,index)
        n=len(values)-1
        if n==0:return None
        numerator=peak_sum-values[index]
        quotient,remainder=divmod(numerator,n)
        return quotient if remainder==0 else numerator/n
    h._leave_one_out_mean=exact_mean

    def advance(source,issued):
        nonlocal last,last_issue
        if last_issue is not None and issued<=last_issue:
            raise ValueError('cache requires strictly increasing issue clocks')
        path=Path(source).resolve(strict=True)
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as con:
            con.execute('PRAGMA query_only=ON')
            gaps=tuple(con.execute('SELECT start_timestamp,end_timestamp,reason FROM collection_gaps ORDER BY start_timestamp'))
            first=con.execute("SELECT MIN(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle'").fetchone()[0]
        identity=(str(path),first,gaps)
        if identity!=last:
            for wrapper in wrappers.values():wrapper.cache_clear()
            last=identity
        last_issue=issued

    try:yield advance
    finally:
        for n,f in originals.items():setattr(h,n,f)
        h._leave_one_out_mean=original_mean
