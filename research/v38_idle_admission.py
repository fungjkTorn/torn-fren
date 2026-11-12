"""Read-only, bounded Linux CPU idle+pressure admission for 25%-CPU shadow jobs.

One-minute load is a runnable-task count, not CPU utilization. This guarded
option is restricted to V38 private inference, with a 25%-of-one-core cgroup
quota, Nice=19 and no production model routing. Missing measurements fail
closed. CPU idle is sampled, not inferred from ps lifetime %CPU.
"""
from __future__ import annotations

import os
from pathlib import Path
import time

MIN_IDLE_FRACTION = 0.25  # 0.5 core free on a two-core VM
MAX_PSI_SOME_AVG10 = 55.0  # scheduler contention warning, not an idle substitute
MAX_PSI_FULL_AVG10 = 2.0
MAX_STEAL_FRACTION = 0.08
MAX_LOAD_PER_CORE = 1.75


def parse_cpu(line):
    parts = line.split()
    if len(parts) < 9 or parts[0] != "cpu":
        raise ValueError("missing aggregate Linux CPU line")
    fields = [int(x) for x in parts[1:9]]
    if any(x < 0 for x in fields):
        raise ValueError("negative CPU counters")
    total = sum(fields)
    return total, fields[3], fields[7]  # all, actual idle, steal


def parse_pressure(text):
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts or parts[0] not in ("some", "full"):
            continue
        props = dict(x.split("=", 1) for x in parts[1:] if "=" in x)
        values[parts[0]] = float(props["avg10"])
    if not all(k in values for k in ("some", "full")):
        raise ValueError("missing CPU PSI averages")
    if not all(0.0 <= x <= 100.0 for x in values.values()):
        raise ValueError("invalid CPU PSI averages")
    return values


def assess(before, after, pressure, *, slots, load1):
    btotal, bidle, bsteal = before
    atotal, aidle, asteal = after
    elapsed = atotal - btotal
    if elapsed <= 0:
        raise ValueError("CPU sample interval not increasing")
    didle, dsteal = aidle - bidle, asteal - bsteal
    if not 0 <= didle <= elapsed or not 0 <= dsteal <= elapsed:
        raise ValueError("CPU counter regression")
    idle_fraction = didle / elapsed
    steal_fraction = dsteal / elapsed
    # A 25%-of-one-core worker uses at most 12.5% of a 2-core host;
    # demand 25% host idle to preserve an additional ~12.5% for poller/web.
    headroom = idle_fraction >= MIN_IDLE_FRACTION
    contention = pressure["some"] <= MAX_PSI_SOME_AVG10 and (
        pressure["full"] <= MAX_PSI_FULL_AVG10
    )
    # On an almost idle host, CPU 'some' PSI may still be high because one
    # short-lived process waited for CPU at some point in the last ten seconds.
    # This is not evidence that both cores are saturated (PSI full = 0).
    # Keep the conservative original PSI test when the VM is actually busy.
    quiet_host = (idle_fraction >= 0.50 and
                  load1 <= slots * 0.80 and
                  pressure["full"] <= 0.50 and
                  steal_fraction <= 0.03)
    safe = ((headroom and contention and
             steal_fraction <= MAX_STEAL_FRACTION and
             load1 <= slots * MAX_LOAD_PER_CORE) or quiet_host)
    return {
        "allowed": bool(safe), "admission_mode": "measured_linux_idle_psi",
        "quiet_host_override": bool(quiet_host and not contention),
        "idle_fraction": round(idle_fraction, 3),
        "estimated_idle_cores": round(idle_fraction * slots, 3),
        "min_idle_fraction": MIN_IDLE_FRACTION,
        "psi_some_avg10": round(pressure["some"], 3),
        "psi_full_avg10": round(pressure["full"], 3),
        "steal_fraction": round(steal_fraction, 3),
        "cpu_slots": int(slots), "one_minute_load": round(load1, 3),
        "max_load1_secondary": round(slots * MAX_LOAD_PER_CORE, 3),
    }


def inspect(*, sample_seconds=2.0, sleeper=time.sleep,
            stat_file="/proc/stat", psi_file="/proc/pressure/cpu",
            slots=None, load1=None):
    if not 1 <= float(sample_seconds) <= 5:
        raise ValueError("invalid CPU sample duration")
    slots = max(1, int(slots or len(os.sched_getaffinity(0))))
    try:
        before = parse_cpu(Path(stat_file).read_text().splitlines()[0])
        sleeper(sample_seconds)
        after = parse_cpu(Path(stat_file).read_text().splitlines()[0])
        pressure = parse_pressure(Path(psi_file).read_text())
        observed_load = float(os.getloadavg()[0] if load1 is None else load1)
        return assess(before, after, pressure, slots=slots, load1=observed_load)
    except (OSError, ValueError, KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
        return {"allowed": False, "admission_mode": "measured_linux_idle_psi",
                "reason": "MEASURED_HEADROOM_UNAVAILABLE",
                "error_type": type(exc).__name__, "cpu_slots": slots}
