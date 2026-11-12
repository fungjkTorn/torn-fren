"""Research worker admission guard for Oracle's single-core VM.

This is an intentionally conservative, fail-closed overload guard. It does
not change systemd or the public V37 services and cannot guarantee latency.
"""
from __future__ import annotations

import os


def inspect(*, load_1m=None, slots=None, max_load_per_slot=0.80):
    # Only a CPUQuota=25%, Nice=19, read-only research service opts into
    # measured admission. All other callers retain the original conservative
    # <=0.8/core load guard, including offline tests and VM launch preflight.
    if (os.environ.get("TORN_FREN_V38_IDLE_ADMISSION") == "1"
            and load_1m is None and slots is None):
        from research.v38_idle_admission import inspect as idle_inspect
        return idle_inspect()
    if slots is None:
        slots=len(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else os.cpu_count()
    if load_1m is None:
        load_1m=os.getloadavg()[0]
    slots=max(1,int(slots or 1))
    load_1m=float(load_1m)
    if not 0.1 <= max_load_per_slot <= 1.0:
        raise ValueError("load cutoff outside safe range")
    return {
        "allowed": load_1m <= slots*max_load_per_slot,
        "one_minute_load": round(load_1m,3),
        "cpu_slots": slots,
        "normalized_load": round(load_1m/slots,3),
        "admission_threshold": max_load_per_slot,
    }
