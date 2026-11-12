"""Offline hindsight-only stock opportunity geometry.

This module accepts FUTURE realized stock intervals. It is exclusively for
backtesting physical availability and departure-grid sensitivity. Never call
earliest_reachable_hindsight() to generate a live prediction.
"""
from __future__ import annotations
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import ceil
from statistics import median
from typing import Sequence

@dataclass(frozen=True)
class Interval:
    start: int
    end: int  # exclusive
    def __post_init__(self):
        if self.end <= self.start:
            raise ValueError("nonpositive stock interval")


def observed_intervals(times: Sequence[int], quantities: Sequence[int],
                       gaps: Sequence[tuple[int,int]], threshold: int) -> list[Interval]:
    """Stock >= threshold until next observation or collector gap, not beyond last row.

    Input times must be strictly increasing, gaps sorted and non-overlapping.
    An observation after a gap establishes a new quantity at its own timestamp.
    """
    if len(times) != len(quantities) or threshold < 1:
        raise ValueError("invalid observed stock data")
    if any(b <= a for a,b in zip(times,times[1:])):
        raise ValueError("observation timestamps must strictly increase")
    if any(b < a for a,b in gaps):
        raise ValueError("invalid gap")
    out=[]
    for i in range(len(times)-1):
        if quantities[i] < threshold:
            continue
        a,b=times[i],times[i+1]
        j=bisect_left(gaps,(a,-1))
        if j and gaps[j-1][1] >= a:
            continue
        if j < len(gaps) and gaps[j][0] <= b:
            b=min(b,gaps[j][0])
        if b>a:
            out.append(Interval(a,b))
    return out


def touches_gap(gaps: Sequence[tuple[int,int]], start:int,end:int) -> bool:
    i=bisect_right(gaps,(end,2**63-1))-1
    return i>=0 and gaps[i][1]>=start


def earliest_reachable_hindsight(
    start:int, flight_seconds:int, intervals:Sequence[Interval],
    gaps:Sequence[tuple[int,int]], *, max_wait_seconds:int=43200,
    grace_seconds:int=10, grid_seconds:int=1,
    last_observation_timestamp:int|None=None,
) -> int|None:
    """First feasible known-future departure on a chosen grid, for AUDIT ONLY.

    Callers must exclude unobservable full-horizon sessions from denominators.
    Returning None with a too-short observation period means unknown, not failure.
    """
    if flight_seconds<0 or max_wait_seconds<0 or grace_seconds<0 or grid_seconds<1:
        raise ValueError("invalid travel, horizon, grace or grid")
    if last_observation_timestamp is not None and (
        start+max_wait_seconds+flight_seconds+grace_seconds>last_observation_timestamp
    ):
        return None
    latest=start+max_wait_seconds
    for w in intervals:
        if w.end<=start+flight_seconds:
            continue
        if w.start>latest+flight_seconds+grace_seconds:
            break
        low=max(start,w.start-grace_seconds-flight_seconds)
        dep=start+ceil((low-start)/grid_seconds)*grid_seconds
        if dep>latest or dep+flight_seconds>=w.end:
            continue
        if touches_gap(gaps,start,dep+flight_seconds+grace_seconds):
            continue
        return dep
    return None


def grid_seconds_from_past_lifetimes(completed_lifetimes_seconds:Sequence[int]):
    """Adaptive candidate-grid proposal. Input MUST contain only past resolved runs.

    This is not an accuracy guarantee; fine grid may increase model CPU cost.
    """
    values=[float(x) for x in completed_lifetimes_seconds if x>0]
    if len(values)<3:
        return {"grid_seconds":60,"evidence":"sparse","median_lifetime_seconds":None}
    duration=median(values[-30:])
    step=30 if duration<120 else 60 if duration<300 else 120 if duration<900 else 300
    return {"grid_seconds":step,"evidence":"historical",
            "median_lifetime_seconds":duration}
