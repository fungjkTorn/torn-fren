import bisect
import math
import random
import statistics
from dataclasses import dataclass

from services.projection_engine_v4 import build_item_context
from services.projection_grand_tournament_v7_engine import (
    MIN_STOCK,
    SHORT_WAIT_SECONDS,
    QuantityTimeline,
    _hour_distance,
    _percentile,
    _wilson_lower,
)


DECISION_OFFSETS_MINUTES = (0, 15, 30, 45, 60, 75, 90, 105, 120)
DIRECT_LOOKBACKS = (20, 40, 80, None)
DIRECT_AGE_WINDOWS = (15, 30, 60, None)
DIRECT_TOD_HOURS = (None, 3.0, 6.0)
DIRECT_METHODS = ("median", "mean", "q25", "q40", "q60", "q75", "weighted")
DIRECT_FRACTIONS = (0.0, 0.25, 0.50, 0.75)

MC_LOOKBACKS = (20, 40, 80, None)
MC_QUANTILES = (0.25, 0.40, 0.50, 0.60, 0.75)
MC_FRACTIONS = (0.0, 0.25, 0.50, 0.75)


def _valid_cycle(c):
    return (
        c.get("restock_time") is not None
        and c.get("depletion_time") is not None
        and float(c["depletion_time"]) > float(c["restock_time"])
        and not c.get("_excluded_regime")
        and c.get("_valid_for_training", True)
    )


def _weighted_mean(values):
    vals = [float(v) for v in values]
    if not vals:
        return None
    weights = list(range(1, len(vals) + 1))
    return sum(v*w for v,w in zip(vals,weights)) / sum(weights)


def _estimate(values, method):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    if method == "median":
        return statistics.median(vals)
    if method == "mean":
        return statistics.mean(vals)
    if method == "q25":
        return _percentile(vals, 0.25)
    if method == "q40":
        return _percentile(vals, 0.40)
    if method == "q60":
        return _percentile(vals, 0.60)
    if method == "q75":
        return _percentile(vals, 0.75)
    if method == "weighted":
        return _weighted_mean(vals[-10:])
    raise ValueError(method)


def _usable_window(timeline, cycle):
    return timeline.usable_window_for_cycle(cycle, MIN_STOCK)


def _find_actual_earliest_reachable(cycles, timeline, anchor_i, now_ts, travel_seconds):
    earliest_arrival = float(now_ts) + float(travel_seconds)
    for target_i in range(anchor_i + 1, len(cycles)):
        target = cycles[target_i]
        if not _valid_cycle(target):
            continue
        window = _usable_window(timeline, target)
        if not window:
            continue
        # A trip can depart now or later. The window is usable if some arrival
        # at/after now+travel still lands before quantity falls below 30.
        if float(window["end"]) <= earliest_arrival:
            continue
        return {
            "target_i": target_i,
            "target_depth": target_i - anchor_i,
            "start": float(window["start"]),
            "end": float(window["end"]),
            "duration": float(window["duration"]),
        }
    return None


def build_live_decisions(country, item_name, max_depth=8, min_history=8):
    ctx = build_item_context(
        country.lower(), item_name, max_depth=max_depth, min_history=min_history
    )
    timeline = QuantityTimeline(country.lower(), item_name)
    cycles = ctx.cycles
    decisions = []

    for anchor_i, anchor in enumerate(cycles):
        if not _valid_cycle(anchor):
            continue
        dep = int(anchor["depletion_time"])
        next_restock = None
        for j in range(anchor_i + 1, len(cycles)):
            if _valid_cycle(cycles[j]):
                next_restock = int(cycles[j]["restock_time"])
                break

        for offset_min in DECISION_OFFSETS_MINUTES:
            now_ts = dep + offset_min * 60
            # This decision belongs to this depletion only while no later normal
            # restock has occurred. It simulates opening the site during the
            # currently observed sold-out period.
            if next_restock is not None and now_ts >= next_restock:
                break
            qty_now = timeline.quantity_at(now_ts)
            if qty_now is None or qty_now >= MIN_STOCK:
                continue

            target = _find_actual_earliest_reachable(
                cycles, timeline, anchor_i, now_ts, ctx.travel_seconds
            )
            if target is None:
                continue

            prior_cycles = [c for c in cycles[: anchor_i + 1] if _valid_cycle(c)]
            if len(prior_cycles) < min_history:
                continue

            last_life = float(anchor["depletion_time"]) - float(anchor["restock_time"])
            last_gap = None
            if anchor_i > 0 and _valid_cycle(cycles[anchor_i - 1]):
                last_gap = float(anchor["restock_time"]) - float(cycles[anchor_i - 1]["depletion_time"])

            decisions.append({
                "anchor_i": anchor_i,
                "anchor_timestamp": dep,
                "decision_timestamp": int(now_ts),
                "age_seconds": float(now_ts - dep),
                "hour": (now_ts % 86400) / 3600.0,
                "last_lifetime_seconds": last_life,
                "last_gap_seconds": last_gap,
                "actual_target_depth": target["target_depth"],
                "actual_start_horizon": target["start"] - now_ts,
                "actual_end_horizon": target["end"] - now_ts,
                "actual_duration": target["duration"],
                "actual_start": target["start"],
                "actual_end": target["end"],
            })
    return ctx, timeline, decisions


def _direct_history(current, history, lookback, age_window_min, tod_hours):
    usable = history
    if age_window_min is not None:
        w = age_window_min * 60
        same_age = [
            r for r in usable
            if abs(float(r["age_seconds"]) - float(current["age_seconds"])) <= w
        ]
        if len(same_age) >= 8:
            usable = same_age
    if tod_hours is not None:
        tod = [
            r for r in usable
            if _hour_distance(
                r["decision_timestamp"], current["decision_timestamp"]
            ) <= tod_hours
        ]
        if len(tod) >= 8:
            usable = tod
    if lookback:
        usable = usable[-lookback:]
    return usable


def direct_rows(ctx, timeline, decisions, lookback, age_window_min, tod_hours, method, fraction):
    rows = []
    history = []
    for current in decisions:
        usable = _direct_history(current, history, lookback, age_window_min, tod_hours)
        if len(usable) < ctx.min_history:
            history.append(current)
            continue

        start_h = _estimate([r["actual_start_horizon"] for r in usable], method)
        duration = _estimate([r["actual_duration"] for r in usable], "median")
        if start_h is None or duration is None or duration <= 0:
            history.append(current)
            continue

        arrival = (
            float(current["decision_timestamp"])
            + float(start_h)
            + float(duration) * float(fraction)
        )
        rows.append(_score_row(timeline, current, arrival, "direct"))
        history.append(current)
    return rows


def _prior_components(cycles, timeline, anchor_i, lookback):
    parts = []
    for i in range(1, anchor_i + 1):
        prev = cycles[i - 1]
        cur = cycles[i]
        if not (_valid_cycle(prev) and _valid_cycle(cur)):
            continue
        gap = float(cur["restock_time"]) - float(prev["depletion_time"])
        life = float(cur["depletion_time"]) - float(cur["restock_time"])
        window = _usable_window(timeline, cur)
        if gap <= 0 or life <= 0 or not window:
            continue
        parts.append({
            "gap": gap,
            "life": life,
            "usable_duration": float(window["duration"]),
        })
    if lookback:
        parts = parts[-lookback:]
    return parts


def _bootstrap_arrival_horizons(
    ctx, timeline, cycles, current, lookback, samples, seed
):
    parts = _prior_components(cycles, timeline, current["anchor_i"], lookback)
    if len(parts) < ctx.min_history:
        return []

    age = float(current["age_seconds"])
    surviving = [p for p in parts if p["gap"] > age]
    if len(surviving) < 5:
        surviving = parts

    rng = random.Random(seed)
    arrivals = []
    for _ in range(samples):
        # Simulate from the current real depletion. The first wait is
        # conditional on the fact that no restock has occurred by decision time.
        first = rng.choice(surviving)
        sim_restock = float(current["anchor_timestamp"]) + float(first["gap"])
        sim_usable_duration = float(first["usable_duration"])

        for _depth in range(1, 9):
            window_start = sim_restock
            window_end = sim_restock + sim_usable_duration
            earliest_arrival = float(current["decision_timestamp"]) + float(ctx.travel_seconds)
            if window_end > earliest_arrival:
                arrivals.append({
                    "start_horizon": window_start - float(current["decision_timestamp"]),
                    "duration": sim_usable_duration,
                })
                break

            bridge = rng.choice(parts)
            sim_dep = sim_restock + float(bridge["life"])
            nxt = rng.choice(parts)
            sim_restock = sim_dep + float(nxt["gap"])
            sim_usable_duration = float(nxt["usable_duration"])
    return arrivals


def mechanics_rows(ctx, timeline, decisions, lookback, quantile, fraction, samples=300):
    cycles = ctx.cycles
    rows = []
    for idx, current in enumerate(decisions):
        sims = _bootstrap_arrival_horizons(
            ctx, timeline, cycles, current, lookback, samples,
            seed=(int(current["decision_timestamp"]) ^ (idx * 7919))
        )
        if len(sims) < 25:
            continue
        start_h = _percentile([x["start_horizon"] for x in sims], quantile)
        duration = statistics.median(x["duration"] for x in sims)
        arrival = (
            float(current["decision_timestamp"])
            + float(start_h)
            + float(duration) * float(fraction)
        )
        rows.append(_score_row(timeline, current, arrival, "mechanics"))
    return rows


def _score_row(timeline, current, arrival, family):
    departure = float(arrival)
    qty = timeline.quantity_at(arrival)
    success = int(qty is not None and qty >= MIN_STOCK)
    short_wait = 0
    wait_seconds = None
    if not success:
        nxt = timeline.first_at_least(
            arrival, threshold=MIN_STOCK, within=SHORT_WAIT_SECONDS
        )
        if nxt is not None and nxt[0] > int(arrival):
            short_wait = 1
            wait_seconds = nxt[0] - int(arrival)

    return {
        "family": family,
        "anchor_timestamp": current["anchor_timestamp"],
        "decision_timestamp": current["decision_timestamp"],
        "age_seconds": current["age_seconds"],
        "actual_target_depth": current["actual_target_depth"],
        "recommended_arrival_timestamp": float(arrival),
        "quantity_on_arrival": qty,
        "success_30": success,
        "short_wait_3m": short_wait,
        "wait_seconds": wait_seconds,
        "early_window": int(arrival < float(current["actual_start"])),
        "late_window": int(arrival >= float(current["actual_end"])),
    }


def summarize(rows):
    n = len(rows)
    if not n:
        return {
            "n": 0, "success_30_rate": None,
            "success_or_short_wait_rate": None, "short_wait_only_rate": None,
            "early_rate": None, "late_rate": None, "wilson_lower_95": None,
        }
    hits = sum(r["success_30"] for r in rows)
    short = sum((not r["success_30"]) and r["short_wait_3m"] for r in rows)
    return {
        "n": n,
        "success_30_rate": hits / n,
        "success_or_short_wait_rate": (hits + short) / n,
        "short_wait_only_rate": short / n,
        "early_rate": sum(r["early_window"] for r in rows) / n,
        "late_rate": sum(r["late_window"] for r in rows) / n,
        "wilson_lower_95": _wilson_lower(hits, n),
    }


def split_rows(ctx, rows):
    return (
        [r for r in rows if r["decision_timestamp"] < ctx.split_timestamp],
        [r for r in rows if r["decision_timestamp"] >= ctx.split_timestamp],
    )


def rolling_folds(ctx, rows, folds=4):
    train = [r for r in rows if r["decision_timestamp"] < ctx.split_timestamp]
    stamps = sorted({r["decision_timestamp"] for r in train})
    if len(stamps) < 80:
        return []
    size = max(20, len(stamps) // folds)
    out = []
    for i in range(folds):
        part = stamps[i*size:] if i == folds-1 else stamps[i*size:(i+1)*size]
        allowed = set(part)
        out.append(summarize([r for r in train if r["decision_timestamp"] in allowed]))
    return out
