import argparse
import bisect
import json
import math
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path

from services import history_service
from services.arrival_success_lab import TRAVEL_SECONDS

TARGETS = [
    ("mex", "Dahlia"), ("mex", "Jaguar Plushie"),
    ("cay", "Banana Orchid"), ("cay", "Stingray Plushie"),
    ("can", "Crocus"), ("can", "Wolverine Plushie"),
    ("haw", "Orchid"),
    ("uni", "Heather"), ("uni", "Nessie Plushie"), ("uni", "Red Fox Plushie"),
    ("arg", "Ceibo Flower"), ("arg", "Monkey Plushie"),
    ("swi", "Edelweiss"), ("swi", "Chamois Plushie"),
    ("jap", "Cherry Blossom"),
    ("chi", "Peony"), ("chi", "Panda Plushie"),
    ("uae", "Tribulus Omanense"), ("uae", "Camel Plushie"),
    ("sou", "African Violet"), ("sou", "Lion Plushie"),
]

MIN_QTY = 30
GRACE_SECONDS = 10


def normalize_gaps(raw_gaps):
    out = []
    for g in raw_gaps or []:
        s = g.get("start_timestamp")
        if s is None:
            continue
        e = g.get("end_timestamp")
        out.append((float(s), float(e) if e is not None else float("inf")))
    return sorted(out)


def overlaps_gap(gaps, a, b):
    lo, hi = sorted((float(a), float(b)))
    for gs, ge in gaps:
        if gs > hi:
            break
        if gs <= hi and ge >= lo:
            return True
    return False


def mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def median(xs):
    xs = [float(x) for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def wilson_lower(hits, n, z=1.96):
    if n <= 0:
        return 0.0
    p = hits / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return max(0.0, (center - spread) / den)


def ratio_distance(a, b, floor=1.0):
    if a is None or b is None:
        return 0.0
    a, b = float(a), float(b)
    return abs(a - b) / max(float(floor), 0.5 * (abs(a) + abs(b)))


def circular_hour_distance(a, b):
    ah = (float(a) % 86400.0) / 3600.0
    bh = (float(b) % 86400.0) / 3600.0
    d = abs(ah - bh)
    return min(d, 24.0 - d)


class Timeline:
    def __init__(self, cleaned_rows, cycles, min_qty, gaps=None):
        self.gaps = list(gaps or [])
        rows = sorted((int(ts), int(qty)) for ts, qty, *_ in cleaned_rows)
        self.ts = [r[0] for r in rows]
        self.qty = [r[1] for r in rows]
        self.min_qty = int(min_qty)
        self.first_ts = float(self.ts[0]) if self.ts else 0.0
        self.last_ts = float(self.ts[-1]) if self.ts else 0.0

        self.run_start = [0.0] * len(rows)
        self.run_peak = [0.0] * len(rows)
        start = self.first_ts
        peak = 0.0
        prev_active = None
        previous_ts = None
        for i, (ts, qty) in enumerate(rows):
            active = qty >= self.min_qty
            crossed_gap = previous_ts is not None and overlaps_gap(self.gaps, previous_ts, ts)
            if i == 0 or crossed_gap or active != prev_active:
                start = float(ts)
                peak = float(max(qty, 0)) if active else 0.0
            elif active:
                peak = max(peak, float(qty))
            self.run_start[i] = start
            self.run_peak[i] = peak
            prev_active = active
            previous_ts = ts

        self.windows = []
        for c in cycles:
            rs = int(c["restock_time"])
            dep = int(c["depletion_time"])
            if overlaps_gap(self.gaps, rs, dep):
                continue
            lo = bisect.bisect_left(self.ts, rs)
            hi = bisect.bisect_right(self.ts, dep)
            start_w = None
            end_w = None
            for ts, qty in zip(self.ts[lo:hi], self.qty[lo:hi]):
                if start_w is None and qty >= self.min_qty:
                    start_w = float(ts)
                elif start_w is not None and qty < self.min_qty:
                    end_w = float(ts)
                    break
            if start_w is not None:
                if end_w is None:
                    end_w = float(dep)
                if end_w > start_w:
                    self.windows.append((start_w, end_w))
        self.windows.sort()
        self.window_starts = [x[0] for x in self.windows]

    def _idx(self, t):
        i = bisect.bisect_right(self.ts, int(t)) - 1
        return i if i >= 0 else None

    def crosses_gap(self, a, b):
        return overlaps_gap(self.gaps, a, b)

    def state(self, t):
        i = self._idx(t)
        if i is None:
            return None
        if overlaps_gap(self.gaps, self.ts[i], t):
            return None
        qty = float(self.qty[i])
        active = qty >= self.min_qty
        peak = max(1.0, float(self.run_peak[i])) if active else 1.0
        frac = qty / peak if active else 0.0
        age = max(0.0, float(t) - float(self.run_start[i]))
        j = self._idx(float(t) - 300.0)
        slope_frac = 0.0
        if active and j is not None and self.ts[i] > self.ts[j]:
            mins = (float(self.ts[i]) - float(self.ts[j])) / 60.0
            if mins > 0:
                slope_frac = ((float(self.qty[i]) - float(self.qty[j])) / peak) / mins
        eta = None
        if active and slope_frac < -0.001:
            eta = min(240.0, max(0.0, frac / (-slope_frac)))
        return {
            "active": bool(active), "qty": qty, "fraction": frac, "age": age,
            "slope": slope_frac, "eta": eta,
        }

    def success(self, arrival, grace_seconds):
        a = float(arrival)
        i = bisect.bisect_right(self.window_starts, a + float(grace_seconds)) - 1
        for j in (i, i + 1):
            if 0 <= j < len(self.windows):
                s, e = self.windows[j]
                if (s - float(grace_seconds)) <= a < e:
                    return True
        return False


@dataclass(frozen=True)
class Context:
    t: float
    active: bool
    fraction: float
    age: float
    slope: float
    eta: float | None
    life3: float | None
    wait3: float | None
    rate3: float | None
    span3: float | None
    life_seq: tuple
    wait_seq: tuple
    rate_seq: tuple
    span_seq: tuple


@dataclass(frozen=True)
class Config:
    name: str
    k: int
    lookback_points: int | None
    same_state: bool
    live_weight: float
    cycle_weight: float
    tod_weight: float
    age_scale: float
    frac_scale: float
    slope_scale: float
    eta_scale: float
    prior_strength: float
    earliest_margin: float
    delay_penalty_per_hour: float


def configs():
    specs = [
        (16, 900, True, 0.72, 0.22, 0.06, 600, .22, .012, 22, 3, .02, .000),
        (32, 1400, True, 0.68, 0.24, 0.08, 900, .32, .020, 35, 4, .03, .000),
        (48, 2000, True, 0.62, 0.30, 0.08, 1200, .45, .030, 50, 5, .03, .000),
        (24, 1200, True, 0.78, 0.14, 0.08, 420, .18, .009, 18, 3, .01, .005),
        (32, 1600, False, 0.58, 0.34, 0.08, 900, .35, .022, 35, 4, .04, .005),
        (48, 2200, False, 0.54, 0.38, 0.08, 1200, .50, .035, 55, 5, .05, .010),
        (24, 700, True, 0.76, 0.18, 0.06, 500, .22, .010, 20, 3, .02, .000),
        (40, None, True, 0.62, 0.30, 0.08, 900, .38, .025, 40, 4, .03, .005),
        # Long-flight variants: after multiple possible cycles, recent cycle
        # regime/sequence should matter more than the exact live stock fraction.
        (32, 700, False, 0.20, 0.70, 0.10, 1200, .50, .040, 60, 4, .025, .000),
        (48, 1400, False, 0.30, 0.60, 0.10, 1500, .55, .045, 70, 5, .035, .000),
        (24, 400, False, 0.15, 0.75, 0.10, 1500, .60, .050, 80, 3, .020, .005),
        (64, None, False, 0.25, 0.65, 0.10, 1800, .60, .050, 90, 6, .040, .005),
        (32, 1000, False, 0.25, 0.55, 0.20, 1200, .50, .040, 60, 4, .030, .000),
    ]
    out = []
    for n, s in enumerate(specs, 1):
        k, lb, ss, lw, cw, tw, age, frac, slope, eta, prior, margin, pen = s
        out.append(Config(f"dyn{n}", k, lb, ss, lw, cw, tw, age, frac, slope, eta, prior, margin, pen))
    return out


def load_item(country, item_name, min_qty):
    raw = history_service._get_all_item_rows_with_source(country, item_name)
    cleaned, bounces = history_service._suppress_provider_bounces(raw)
    gaps = normalize_gaps(history_service.get_collection_gaps())
    rows = [(int(ts), int(qty)) for ts, qty, _src in cleaned]
    row_ts = [r[0] for r in rows]
    cycles, _active, _waits = history_service._build_validated_cycles(rows)

    normal = []
    for cyc in cycles:
        if not (
            cyc.get("complete") and not cyc.get("tiny_restock") and cyc.get("valid_lifetime")
            and cyc.get("restock_time") is not None and cyc.get("depletion_time") is not None
            and cyc.get("lifetime_seconds")
        ):
            continue
        rs = int(cyc["restock_time"])
        dep = int(cyc["depletion_time"])
        if overlaps_gap(gaps, rs, dep):
            continue
        # A restock first observed on recovery from an outage has unknown true
        # transition time and a truncated lifetime.  Reject that cycle too.
        j = bisect.bisect_left(row_ts, rs)
        if j > 0 and overlaps_gap(gaps, row_ts[j - 1], rs):
            continue
        normal.append(cyc)
    return cleaned, normal, bounces, gaps


def completed_cycle_features(cycles, gaps=None):
    dep_times = []
    feats = []
    lives, waits, rates, spans = [], [], [], []
    for i, c in enumerate(cycles):
        life = float(c["lifetime_seconds"])
        peak = float(c.get("peak_quantity") or c.get("first_seen_quantity") or 0.0)
        rate = peak / max(life / 60.0, 1e-9)
        wait = None if i == 0 else float(c["restock_time"] - cycles[i - 1]["depletion_time"])
        if i > 0 and overlaps_gap(gaps or [], cycles[i - 1]["depletion_time"], c["restock_time"]):
            wait = None
        span = life + wait if wait is not None else None
        lives.append(life); waits.append(wait); rates.append(rate); spans.append(span)
        feats.append({
            "life3": median(lives[-3:]),
            "wait3": median([x for x in waits[-3:] if x is not None]),
            "rate3": median(rates[-3:]),
            "span3": median([x for x in spans[-3:] if x is not None]),
            "life_seq": tuple(lives[-5:]),
            "wait_seq": tuple(x for x in waits[-5:] if x is not None),
            "rate_seq": tuple(rates[-5:]),
            "span_seq": tuple(x for x in spans[-5:] if x is not None),
        })
        dep_times.append(float(c["depletion_time"]))
    return dep_times, feats


def context_at(t, timeline, dep_times, cycle_feats):
    st = timeline.state(t)
    if st is None:
        return None
    ci = bisect.bisect_right(dep_times, float(t)) - 1
    if ci < 2:
        return None
    cf = cycle_feats[ci]
    return Context(
        t=float(t), active=st["active"], fraction=float(st["fraction"]), age=float(st["age"]),
        slope=float(st["slope"]), eta=st["eta"], life3=cf["life3"], wait3=cf["wait3"],
        rate3=cf["rate3"], span3=cf["span3"],
        life_seq=cf["life_seq"], wait_seq=cf["wait_seq"],
        rate_seq=cf["rate_seq"], span_seq=cf["span_seq"],
    )


def sequence_distance(a, b):
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    aa, bb = a[-n:], b[-n:]
    vals = [ratio_distance(x, y, 1.0) for x, y in zip(aa, bb)]
    return mean(vals) or 0.0


def distance(q, p, cfg):
    if cfg.same_state and q.active != p.active:
        return None
    mismatch = 0.0 if q.active == p.active else 1.5
    live = mismatch + abs(q.age - p.age) / max(60.0, cfg.age_scale)
    if q.active and p.active:
        live += 0.32 * abs(q.fraction - p.fraction) / max(.05, cfg.frac_scale)
        live += 0.26 * abs(q.slope - p.slope) / max(.002, cfg.slope_scale)
        if q.eta is not None and p.eta is not None:
            live += 0.18 * abs(q.eta - p.eta) / max(5.0, cfg.eta_scale)
        elif q.eta is not None or p.eta is not None:
            live += 0.18
    summary_cyc = mean([
        ratio_distance(q.life3, p.life3, 60), ratio_distance(q.wait3, p.wait3, 60),
        ratio_distance(q.rate3, p.rate3, 1), ratio_distance(q.span3, p.span3, 60),
    ]) or 0.0
    seq_cyc = mean([
        sequence_distance(q.life_seq, p.life_seq),
        sequence_distance(q.wait_seq, p.wait_seq),
        sequence_distance(q.rate_seq, p.rate_seq),
        sequence_distance(q.span_seq, p.span_seq),
    ]) or 0.0
    cyc = 0.55 * summary_cyc + 0.45 * seq_cyc
    tod = circular_hour_distance(q.t, p.t) / 4.0
    return cfg.live_weight * live + cfg.cycle_weight * cyc + cfg.tod_weight * tod


def build_points(timeline, dep_times, cycle_feats, step_seconds):
    if not dep_times:
        return []
    start = max(timeline.first_ts, dep_times[min(3, len(dep_times) - 1)])
    t = math.ceil(start / step_seconds) * step_seconds
    out = []
    while t <= timeline.last_ts:
        c = context_at(t, timeline, dep_times, cycle_feats)
        if c is not None:
            out.append(c)
        t += step_seconds
    return out


def _score_delay_from_ranked(ranked_all, history_times, timeline, cfg, delay, travel, grace, qtime):
    """
    Score one candidate leave delay using a neighbor ranking that was computed
    once for this query time.

    V18 originally recomputed + resorted the same state distances for every
    candidate departure.  The distance between query state and a historical
    state does not depend on departure delay, so that was pure duplicate work.
    Eligibility still remains delay-specific and past-only.
    """
    cutoff = float(qtime) - float(delay) - float(travel) - float(grace)
    hi = bisect.bisect_right(history_times, cutoff)
    if hi <= 0:
        return None
    lo = 0 if cfg.lookback_points is None else max(0, hi - cfg.lookback_points)

    chosen = []
    label_end = float(delay) + float(travel) + float(grace)
    for d, idx, p in ranked_all:
        if idx < lo or idx >= hi:
            continue
        if timeline.crosses_gap(p.t, p.t + label_end):
            continue
        chosen.append((d, p))
        if len(chosen) >= cfg.k:
            break

    if len(chosen) < 8:
        return None

    weights = [math.exp(-min(20.0, d)) for d, _ in chosen]
    sw = sum(weights)
    if sw <= 0:
        return None
    raw = sum(
        w * int(timeline.success(p.t + delay + travel, grace))
        for w, (_d, p) in zip(weights, chosen)
    ) / sw
    ne = (sw * sw) / max(1e-9, sum(w * w for w in weights))
    prob = (raw * ne + cfg.prior_strength * 0.5) / (ne + cfg.prior_strength)
    utility = prob - cfg.delay_penalty_per_hour * (delay / 3600.0)
    return {
        "delay": float(delay),
        "prob": float(prob),
        "raw": float(raw),
        "support": float(ne),
        "utility": float(utility),
    }


def plan(qtime, history_points, history_times, timeline, dep_times, cycle_feats, cfg, delays, travel, grace):
    q = context_at(qtime, timeline, dep_times, cycle_feats)
    if q is None:
        return None

    # Compute query-to-history state distances ONCE.  For each future departure
    # delay we then apply the correct past-only cutoff/lookback to this ranking.
    # This preserves the original V18 scoring semantics while removing the
    # dominant repeated O(delays * history * log(history)) work.
    max_hi = bisect.bisect_right(
        history_times,
        float(q.t) - float(travel) - float(grace),
    )
    if max_hi <= 0:
        return None

    ranked_all = []
    for idx in range(max_hi):
        p = history_points[idx]
        d = distance(q, p, cfg)
        if d is None:
            continue
        ranked_all.append((d, idx, p))
    if len(ranked_all) < 8:
        return None
    ranked_all.sort(key=lambda x: x[0])

    curve = []
    for delay in delays:
        x = _score_delay_from_ranked(
            ranked_all, history_times, timeline, cfg,
            delay, travel, grace, q.t,
        )
        if x is not None:
            curve.append(x)

    if not curve:
        return None

    best = max(curve, key=lambda x: (x["utility"], x["prob"], -x["delay"]))
    floor = best["prob"] - cfg.earliest_margin
    near = [
        x for x in curve
        if x["prob"] >= floor and x["utility"] >= best["utility"] - 0.03
    ]
    if near:
        near = sorted(near, key=lambda x: x["delay"])
        step = median([
            b["delay"] - a["delay"] for a, b in zip(curve, curve[1:])
            if b["delay"] > a["delay"]
        ]) or 300.0
        clusters = [[near[0]]]
        for x in near[1:]:
            if x["delay"] - clusters[-1][-1]["delay"] <= step * 1.01:
                clusters[-1].append(x)
            else:
                clusters.append([x])
        # Prefer the strongest coherent probability plateau, then land near its
        # center instead of hugging the earliest edge.
        def cluster_key(cl):
            return (mean([x["prob"] for x in cl]) or 0.0, max(x["prob"] for x in cl), -cl[0]["delay"])
        cluster = max(clusters, key=cluster_key)
        center = 0.5 * (cluster[0]["delay"] + cluster[-1]["delay"])
        chosen = min(cluster, key=lambda x: (abs(x["delay"] - center), -x["prob"]))
    else:
        chosen = best
    return {
        "query_time": float(qtime),
        "departure_time": float(qtime) + chosen["delay"],
        "arrival_time": float(qtime) + chosen["delay"] + travel,
        "probability": chosen["prob"],
        "support": chosen["support"],
    }

def simulate_session(start, planner, timeline, travel, grace, replan_step, max_wait):
    t = float(start)
    deadline = t + float(max_wait)
    first = None
    last = None
    plans = 0
    while t <= deadline:
        p = planner(t)
        if p is not None:
            plans += 1
            first = first or p
            last = p
            if p["departure_time"] <= t + replan_step:
                dep = max(t, p["departure_time"])
                arr = dep + travel
                return {
                    "start": start, "departure": dep, "arrival": arr,
                    "success": timeline.success(arr, grace), "plans": plans,
                    "first_departure": first["departure_time"], "final_probability": p["probability"],
                }
        t += replan_step
    if last is not None:
        dep = min(last["departure_time"], deadline)
        arr = dep + travel
        return {
            "start": start, "departure": dep, "arrival": arr,
            "success": timeline.success(arr, grace), "plans": plans,
            "first_departure": first["departure_time"], "final_probability": last["probability"],
            "session_cap": True,
        }
    return None


def summarize(rows, total):
    hits = sum(int(r["success"]) for r in rows)
    n = len(rows)
    return {
        "valid_starts": int(total), "recommendations": n,
        "coverage": n / total if total else 0.0,
        "successes": hits, "arrival_success_rate": hits / n if n else 0.0,
        "wilson_lower_95": wilson_lower(hits, n),
        "median_wait_seconds": median([r["departure"] - r["start"] for r in rows]),
        "median_plans_seen": median([r["plans"] for r in rows]),
    }


def eval_config(starts, cfg, history_points, history_times, timeline, dep_times, cycle_feats, delays, travel, grace, replan_step, max_wait):
    cache = {}
    def get_plan(t):
        key = int(t)
        if key not in cache:
            cache[key] = plan(t, history_points, history_times, timeline, dep_times, cycle_feats, cfg, delays, travel, grace)
        return cache[key]
    rows = []
    by_start = {}
    for s in starts:
        r = simulate_session(s, get_plan, timeline, travel, grace, replan_step, max_wait)
        if r is not None:
            rows.append(r); by_start[s] = r
    return rows, by_start, summarize(rows, len(starts))


def rank_key(summary, blocks):
    rates = [b["arrival_success_rate"] for b in blocks if b["recommendations"] >= 5]
    recent = rates[-2:] if len(rates) >= 2 else rates
    latest = rates[-1] if rates else 0.0
    recent_avg = mean(recent) or 0.0
    recent_floor = min(recent) if recent else 0.0
    return (
        0.34 * latest + 0.24 * recent_avg + 0.14 * recent_floor
        + 0.14 * summary["arrival_success_rate"] + 0.08 * summary["coverage"]
        + 0.06 * summary["wilson_lower_95"],
        latest, recent_avg, recent_floor, summary["arrival_success_rate"],
    )


def run_item(country, item_name, min_qty, grace, holdout_fraction, topn, history_step, replan_step, eval_step, departure_grid, max_wait, min_cycles=60, min_points=150, min_starts=80):
    cleaned, cycles, bounces, gaps = load_item(country, item_name, min_qty)
    if len(cycles) < int(min_cycles):
        return country, item_name, {"status": "insufficient_cycles", "cycles": len(cycles), "min_cycles_required": int(min_cycles)}
    timeline = Timeline(cleaned, cycles, min_qty, gaps=gaps)
    dep_times, cycle_feats = completed_cycle_features(cycles, gaps=gaps)
    points = build_points(timeline, dep_times, cycle_feats, history_step)
    point_times = [p.t for p in points]
    if len(points) < int(min_points):
        return country, item_name, {"status": "insufficient_points", "points": len(points), "min_points_required": int(min_points)}

    travel = int(TRAVEL_SECONDS[country])
    delays = list(range(0, int(max_wait) + 1, int(departure_grid)))
    first = max(points[min(len(points)-1, 100)].t, timeline.first_ts + 24 * 3600)
    last = timeline.last_ts - max_wait - travel - grace
    starts = []
    t = math.ceil(first / eval_step) * eval_step
    while t <= last:
        if (
            context_at(t, timeline, dep_times, cycle_feats) is not None
            and not timeline.crosses_gap(t, t + max_wait + travel + grace)
        ):
            starts.append(float(t))
        t += eval_step
    if len(starts) < int(min_starts):
        return country, item_name, {"status": "insufficient_starts", "starts": len(starts), "min_starts_required": int(min_starts)}

    split = max(50, int(len(starts) * (1.0 - holdout_fraction)))
    split = min(split, len(starts) - 25)
    train, hold = starts[:split], starts[split:]
    reports = []
    for cfg in configs():
        rows, by, s = eval_config(train, cfg, points, point_times, timeline, dep_times, cycle_feats, delays, travel, grace, replan_step, max_wait)
        blocks = []
        for b in range(4):
            lo = int(len(train) * b / 4); hi = int(len(train) * (b + 1) / 4)
            ss = train[lo:hi]
            rr = [by[x] for x in ss if x in by]
            blocks.append(summarize(rr, len(ss)))
        reports.append((rank_key(s, blocks), cfg, s, blocks))
    reports.sort(key=lambda x: x[0], reverse=True)
    best_key, best_cfg, best_train, best_blocks = reports[0]
    hold_rows, _, hold_sum = eval_config(hold, best_cfg, points, point_times, timeline, dep_times, cycle_feats, delays, travel, grace, replan_step, max_wait)

    finalists = []
    for rk, cfg, tr, bl in reports[:max(1, topn)]:
        rr, _, hs = eval_config(hold, cfg, points, point_times, timeline, dep_times, cycle_feats, delays, travel, grace, replan_step, max_wait)
        finalists.append({"config": asdict(cfg), "rank_key": list(rk), "train": tr, "rolling_train_blocks": bl, "holdout_reporting_only": hs})

    return country, item_name, {
        "status": "complete", "schema": "plushie-flower-dynamic-planner-v19-item-v1",
        "country": country, "item_name": item_name, "travel_seconds": travel,
        "min_quantity": min_qty, "grace_seconds": grace, "cycles": len(cycles),
        "historical_points": len(points), "train_starts": len(train), "holdout_starts": len(hold),
        "provider_bounces_suppressed": len(bounces),
        "known_collection_gaps": len(gaps),
        "selection_rule": "Training-only dynamic leave-time model; holdout is report-only. No GO/WAIT abstention threshold.",
        "goal_definition": ">90% arrival+10s success independently for every flower/plushie, with essentially 100% recommendation coverage on valid data.",
        "selected_on_training": {"config": asdict(best_cfg), "rank_key": list(best_key), "train": best_train, "rolling_train_blocks": best_blocks, "holdout": hold_sum},
        "top_finalists": finalists,
        "holdout_rows": [{
            "start": r["start"], "departure": r["departure"], "arrival": r["arrival"],
            "success": r["success"], "plans": r["plans"],
            "first_departure": r["first_departure"], "final_probability": r["final_probability"],
            "session_cap": bool(r.get("session_cap", False)),
        } for r in hold_rows],
    }


def worker(payload):
    db = Path(payload["db"]).resolve()
    history_service.DB_PATH = db
    history_service._DB_READY = False
    c, i = payload["country"], payload["item"]
    t0 = time.time()
    try:
        _c, _i, report = run_item(c, i, **payload["opts"])
    except Exception as exc:
        report = {"status": "error", "country": c, "item_name": i, "error": repr(exc)}
    report["runtime_seconds"] = round(time.time() - t0, 3)
    return c, i, report


def main():
    ap = argparse.ArgumentParser(description="V19 gap-clean dynamic future leave-time planner for Torn flowers/plushies")
    ap.add_argument("--db", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--topn", type=int, default=8)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--output", default="data/plushie_flower_v19.json")
    ap.add_argument("--min-qty", type=int, default=MIN_QTY)
    ap.add_argument("--grace-seconds", type=int, default=GRACE_SECONDS)
    ap.add_argument("--holdout-fraction", type=float, default=.25)
    ap.add_argument("--history-step-seconds", type=int, default=600)
    ap.add_argument("--replan-step-seconds", type=int, default=300)
    ap.add_argument("--eval-step-seconds", type=int, default=1800)
    ap.add_argument("--departure-grid-seconds", type=int, default=300)
    ap.add_argument("--max-wait-seconds", type=int, default=6*3600)
    ap.add_argument("--min-cycles", type=int, default=60)
    ap.add_argument("--min-points", type=int, default=150)
    ap.add_argument("--min-starts", type=int, default=80)
    a = ap.parse_args()

    db = Path(a.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    history_service.DB_PATH = db
    history_service._DB_READY = False

    only = set(a.only or [])
    targets = [(c, i) for c, i in TARGETS if not only or f"{c}:{i}" in only]
    opts = {
        "min_qty": a.min_qty, "grace": a.grace_seconds, "holdout_fraction": a.holdout_fraction,
        "topn": a.topn, "history_step": a.history_step_seconds, "replan_step": a.replan_step_seconds,
        "eval_step": a.eval_step_seconds, "departure_grid": a.departure_grid_seconds, "max_wait": a.max_wait_seconds,
        "min_cycles": a.min_cycles, "min_points": a.min_points, "min_starts": a.min_starts,
    }
    report = {
        "schema": "plushie-flower-dynamic-planner-v19-master-v1", "created_at": int(time.time()),
        "db_path": str(db),
        "goal": ">90% historical arrival success for each of 21 flowers/plushies; success = stock >=30 at landing or appearing within +10 seconds; dynamic leave time may update as new data arrives; no abstention gaming.",
        "results": {},
    }
    payloads = [{"db": str(db), "country": c, "item": i, "opts": opts} for c, i in targets]
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)

    def store(c, i, r):
        report["results"][f"{c}:{i}"] = r
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        h = r.get("selected_on_training", {}).get("holdout", {})
        print(f"DONE {c}:{i} success={100*float(h.get('arrival_success_rate') or 0):.1f}% coverage={100*float(h.get('coverage') or 0):.1f}% status={r.get('status')}", flush=True)

    if a.workers <= 1 or len(payloads) <= 1:
        for p in payloads:
            store(*worker(p))
    else:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(worker, p) for p in payloads]
            for fut in as_completed(futs):
                store(*fut.result())

    rates = []
    for r in report["results"].values():
        h = r.get("selected_on_training", {}).get("holdout", {})
        if r.get("status") == "complete":
            rates.append(float(h.get("arrival_success_rate") or 0.0))
    report["scoreboard"] = {
        "completed_items": len(rates), "items_above_90": sum(x > .90 for x in rates),
        "all_21_above_90": len(rates) == 21 and all(x > .90 for x in rates),
        "minimum_item_success_rate": min(rates) if rates else None,
        "mean_item_success_rate": mean(rates),
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["scoreboard"], indent=2), flush=True)
    print(f"WROTE {out}", flush=True)


if __name__ == "__main__":
    main()
