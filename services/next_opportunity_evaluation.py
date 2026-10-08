"""Research-only, hindsight evaluation of departure efficiency.

Does not predict restocks. Ground-truth stock windows must be built from
observations available to the evaluator; never use the oracle to train a live
prediction without a chronological, causally filtered process.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class QualifiedStockWindow:
    start_timestamp: float
    end_timestamp: float

    def __post_init__(self):
        if self.start_timestamp >= self.end_timestamp:
            raise ValueError("stock window must have positive duration")


def arrival_in_stock(arrival_timestamp: float, windows: Iterable[QualifiedStockWindow], grace_seconds: float = 10.0) -> bool:
    """A successful arrival is stocked now or starts within the next grace seconds."""
    if grace_seconds < 0:
        raise ValueError("grace_seconds must be nonnegative")
    return any(w.start_timestamp <= arrival_timestamp + grace_seconds and arrival_timestamp < w.end_timestamp
               for w in windows)


def earliest_viable_leave(now_timestamp: float, travel_seconds: float,
                          windows: Iterable[QualifiedStockWindow],
                          grace_seconds: float = 10.0,
                          max_wait_seconds: float | None = None) -> float | None:
    """Earliest departure to ANY observed viable window; hindsight audit ONLY.

    A five-hour natural stock wait is not an avoidable inefficiency. If no
    stock window is reachable within the requested patience, returns None.
    """
    if travel_seconds < 0 or grace_seconds < 0 or (max_wait_seconds is not None and max_wait_seconds < 0):
        raise ValueError("travel, grace, and wait limit must be nonnegative")
    options = []
    for w in windows:
        departure = max(now_timestamp, w.start_timestamp - travel_seconds - grace_seconds)
        if departure + travel_seconds < w.end_timestamp and (
            max_wait_seconds is None or departure - now_timestamp <= max_wait_seconds
        ):
            options.append(departure)
    return min(options) if options else None


def evaluate_departure(*, now_timestamp: float, recommended_leave_timestamp: float,
                       travel_seconds: float, windows: Iterable[QualifiedStockWindow],
                       grace_seconds: float = 10.0,
                       max_wait_seconds: float | None = None,
                       excess_delay_threshold_seconds: float = 30 * 60) -> dict:
    """Separate success from unavoidable restock wait and avoidable delay.

    This is a diagnostic oracle in hindsight; it is not a model probability or
    a label for forecasting exact next restock times.
    """
    stock_windows = tuple(windows)
    if recommended_leave_timestamp < now_timestamp:
        raise ValueError("recommended departure precedes evaluation time")
    if excess_delay_threshold_seconds < 0:
        raise ValueError("excess delay threshold must be nonnegative")
    oracle = earliest_viable_leave(now_timestamp, travel_seconds, stock_windows, grace_seconds, max_wait_seconds)
    arrive = recommended_leave_timestamp + travel_seconds
    success = arrival_in_stock(arrive, stock_windows, grace_seconds)
    # We only call a delay 'avoidable' when a successful recommendation
    # demonstrably missed an earlier viable time. Failures are separate.
    excess = (max(0.0, recommended_leave_timestamp - oracle)
              if success and oracle is not None else None)
    return {
        "arrival_success": success,
        "actual_wait_seconds": recommended_leave_timestamp - now_timestamp,
        "earliest_feasible_leave_timestamp_hindsight": oracle,
        "unavoidable_wait_seconds_hindsight": None if oracle is None else max(0.0, oracle - now_timestamp),
        "avoidable_delay_seconds_hindsight": excess,
        "skipped_earlier_feasible_departure": excess is not None and excess > excess_delay_threshold_seconds,
        "viable_within_wait_budget": oracle is not None,
        "forced_wait_cap": bool(max_wait_seconds is not None and
                                recommended_leave_timestamp - now_timestamp >= max_wait_seconds),
    }
