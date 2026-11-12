"""Evidence-qualified earliest-target outcome, independent of arrival success.

Historical oracle windows frequently have an observed restock but no reliable
subsequent <30 crossing / depletion timestamp. Such an *open* event must NOT
be counted as an earliest-target arrival hit just because its restock time
preceded landing. Stock at landing is scored separately, and takes precedence
for user-visible flight success.

No model inference uses this grading helper. Oracle evidence only after issue.
"""
from __future__ import annotations


def grade_target_window(*, arrival, state, restock, depletion, grace=10):
    """Return (verified_hit: bool|None, reason: str).

    None means insufficient evidence and must not enter the denominator.
    """
    if restock is None:
        return None, "NO_ORACLE_TARGET"
    if state not in ("SUCCESS","FAILURE"):
        return None, "UNSCORABLE_STOCK_AT_LANDING"
    if depletion is None:
        return None, "UNKNOWN_TARGET_DEPLETION"
    if not isinstance(arrival,int) or not isinstance(restock,int) or not isinstance(depletion,int):
        return None, "INVALID_TARGET_TIMESTAMPS"
    if not restock < depletion:
        return None, "INVALID_TARGET_WINDOW"
    landing=arrival+grace
    hit=(state=="SUCCESS" and restock<=landing<depletion)
    return hit, ("STOCK_CONFIRMED_IN_TARGET_WINDOW" if hit else
                 "NO_STOCK_CONFIRMED_IN_TARGET_WINDOW")
