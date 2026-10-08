import math
import statistics
from dataclasses import dataclass

from services.projection_engine_v4 import build_item_context
from services.projection_grand_tournament_v7_engine import (
    MIN_STOCK,
    SHORT_WAIT_SECONDS,
    QuantityTimeline,
)
from services.projection_grand_tournament_v8_live_engine import _valid_cycle, summarize


DECISION_OFFSETS_MINUTES = tuple(range(0, 181, 10))
WAIT_MINUTES = tuple(range(0, 241, 5))


@dataclass(frozen=True)
class V10Config:
    family: str
    lookback: int
    age_window: int
    feature_set: str = "none"
    scale: float = 1.0
    half_life: float | None = None
    tod_hours: float | None = None

    @property
    def name(self):
        return (
            f"{self.family}|lb={self.lookback}|age={self.age_window}|"
            f"features={self.feature_set}|scale={self.scale}|"
            f"half={self.half_life}|tod={self.tod_hours}"
        )


def config_grid():
    # Broad enough for an overnight run, but every family represents a real
    # modeling hypothesis.  Avoid a giant near-duplicate hyperparameter zoo.
    lookbacks = (5, 8, 10, 12, 15, 20, 30, 40, 60, 80)
    for lb in lookbacks:
        for age in (0, 10, 20, 30):
            yield V10Config("uniform", lb, age)

    for half in (2.0, 3.0, 5.0, 8.0, 12.0, 20.0):
        for age in (0, 10, 20):
            yield V10Config("exponential", 40, age, half_life=half)

    for lb in (6, 8, 10, 12, 15, 20, 30, 40):
        for features in ("timing", "demand", "all"):
            for scale in (0.5, 0.75, 1.0, 1.5, 2.0):
                yield V10Config(
                    "state", lb, 10, feature_set=features, scale=scale
                )

    for lb in (8, 10, 12, 15, 20, 30):
        for tod in (3.0, 6.0, 9.0):
            yield V10Config("tod", lb, 20, tod_hours=tod)


def _usable_window(timeline, cycle):
    return timeline.usable_window_for_cycle(cycle, MIN_STOCK)


def _earliest_reachable(cycles, timeline, anchor_i, now_ts, travel):
    earliest_arrival = float(now_ts) + float(travel)
    for i in range(anchor_i + 1, len(cycles)):
        c = cycles[i]
        if not _valid_cycle(c):
            continue
        w = _usable_window(timeline, c)
        if w and float(w["end"]) > earliest_arrival:
            return {
                "start": float(w["start"]),
                "end": float(w["end"]),
                "depth": i - anchor_i,
            }
    return None


def build_dense_decisions(country, item_name, max_depth=10, min_history=8):
    ctx = build_item_context(
        country.lower(), item_name, max_depth=max_depth, min_history=min_history
    )
    timeline = QuantityTimeline(country.lower(), item_name)
    cycles = ctx.cycles
    out = []

    for anchor_i, anchor in enumerate(cycles):
        if not _valid_cycle(anchor):
            continue
        dep = int(anchor["depletion_time"])
        next_restock = None
        for j in range(anchor_i + 1, len(cycles)):
            if _valid_cycle(cycles[j]):
                next_restock = int(cycles[j]["restock_time"])
                break

        prior_valid = [c for c in cycles[:anchor_i + 1] if _valid_cycle(c)]
        if len(prior_valid) < min_history:
            continue

        for off in DECISION_OFFSETS_MINUTES:
            now = dep + off * 60
            if next_restock is not None and now >= next_restock:
                break
            qty = timeline.quantity_at(now)
            if qty is None or qty >= MIN_STOCK:
                continue

            target = _earliest_reachable(
                cycles, timeline, anchor_i, now, ctx.travel_seconds
            )
            if target is None:
                continue

            life = float(anchor["depletion_time"] - anchor["restock_time"])
            gap = None
            if anchor_i > 0 and _valid_cycle(cycles[anchor_i - 1]):
                gap = float(
                    anchor["restock_time"] - cycles[anchor_i - 1]["depletion_time"]
                )
            window = _usable_window(timeline, anchor)
            peak = float(anchor.get("peak_quantity") or 0)
            safe = float(window["duration"]) if window else 0.0
            rate = peak / max(life / 60.0, 1.0)

            out.append({
                "anchor_i": anchor_i,
                "anchor_timestamp": dep,
                "decision_timestamp": now,
                "age_seconds": float(now - dep),
                "hour": (now % 86400) / 3600.0,
                "actual_start": target["start"],
                "actual_end": target["end"],
                "actual_target_depth": target["depth"],
                "_state": {
                    "gap": gap,
                    "life": life,
                    "peak": peak,
                    "safe": safe,
                    "rate": rate,
                },
            })
    return ctx, timeline, out


def _mad(values):
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(vals) < 3:
        return 1.0
    m = statistics.median(vals)
    return max(1.0, statistics.median(abs(v - m) for v in vals) * 1.4826)


def _hour_distance(a, b):
    ha = (float(a) % 86400.0) / 3600.0
    hb = (float(b) % 86400.0) / 3600.0
    d = abs(ha - hb)
    return min(d, 24.0 - d)


def _feature_keys(feature_set):
    if feature_set == "timing":
        return ("gap", "life")
    if feature_set == "demand":
        return ("peak", "safe", "rate")
    if feature_set == "all":
        return ("gap", "life", "peak", "safe", "rate")
    return ()


def _filter_history(prior, current, config):
    age_w = int(config.age_window) * 60
    if age_w == 0:
        rows = [
            r for r in prior
            if int(r["age_seconds"]) == int(current["age_seconds"])
        ]
    else:
        rows = [
            r for r in prior
            if abs(float(r["age_seconds"]) - float(current["age_seconds"])) <= age_w
        ]

    if config.tod_hours is not None:
        narrowed = [
            r for r in rows
            if _hour_distance(
                r["decision_timestamp"], current["decision_timestamp"]
            ) <= float(config.tod_hours)
        ]
        if len(narrowed) >= 5:
            rows = narrowed

    return rows[-int(config.lookback):]


def _weights(rows, current, config):
    n = len(rows)
    w = [1.0] * n

    if config.family == "exponential":
        half = max(float(config.half_life or 5.0), 0.1)
        ages = list(reversed(range(n)))
        w = [0.5 ** (a / half) for a in ages]

    keys = _feature_keys(config.feature_set)
    if keys:
        spreads = {
            k: _mad([r["_state"].get(k) for r in rows]) for k in keys
        }
        state_weights = []
        for r in rows:
            terms = []
            for k in keys:
                a = current["_state"].get(k)
                b = r["_state"].get(k)
                if a is None or b is None:
                    continue
                terms.append(((float(a) - float(b)) / spreads[k]) ** 2)
            d2 = sum(terms) / max(1, len(terms))
            s = max(float(config.scale), 0.1)
            state_weights.append(math.exp(-0.5 * d2 / (s * s)))
        w = [a * b for a, b in zip(w, state_weights)]

    return w


def _choose_wait(prior, current, ctx, timeline, config):
    rows = _filter_history(prior, current, config)
    if len(rows) < 5:
        return None

    weights = _weights(rows, current, config)
    travel = float(ctx.travel_seconds)
    scored = []

    for wait in WAIT_MINUTES:
        horizon = wait * 60.0 + travel
        hits = []
        ww = []
        for r, weight in zip(rows, weights):
            qty = timeline.quantity_at(
                float(r["decision_timestamp"]) + horizon
            )
            if qty is None:
                continue
            hits.append(int(qty >= MIN_STOCK))
            ww.append(float(weight))
        if len(hits) < 5 or sum(ww) <= 0:
            continue
        p = sum(h * weight for h, weight in zip(hits, ww)) / sum(ww)

        # Tie-break to the soonest departure. The product wants the next useful
        # opportunity, not a later equally-good one.
        scored.append((p, -wait, wait, len(hits)))

    if not scored:
        return None
    best = max(scored)
    return {
        "wait_minutes": float(best[2]),
        "predicted_probability": float(best[0]),
        "samples": int(best[3]),
    }


def _score(ctx, timeline, current, choice):
    departure = float(current["decision_timestamp"]) + choice["wait_minutes"] * 60
    arrival = departure + float(ctx.travel_seconds)
    qty = timeline.quantity_at(arrival)
    hit = int(qty is not None and qty >= MIN_STOCK)

    short = 0
    if not hit:
        nxt = timeline.first_at_least(
            arrival, threshold=MIN_STOCK, within=SHORT_WAIT_SECONDS
        )
        short = int(nxt is not None and nxt[0] > int(arrival))

    return {
        "decision_timestamp": current["decision_timestamp"],
        "anchor_timestamp": current["anchor_timestamp"],
        "age_seconds": current["age_seconds"],
        "actual_target_depth": current["actual_target_depth"],
        "recommended_wait_minutes": choice["wait_minutes"],
        "predicted_probability": choice["predicted_probability"],
        "quantity_on_arrival": qty,
        "success_30": hit,
        "short_wait_3m": short,
        "early_window": int(arrival < float(current["actual_start"])),
        "late_window": int(arrival >= float(current["actual_end"])),
    }


def score_config(ctx, timeline, decisions, config):
    max_horizon = max(WAIT_MINUTES) * 60 + float(ctx.travel_seconds) + SHORT_WAIT_SECONDS
    rows = []
    for current in decisions:
        now = float(current["decision_timestamp"])
        # No historical path is allowed to vote until every departure horizon
        # that V10 may inspect has fully resolved.
        prior = [
            r for r in decisions
            if float(r["decision_timestamp"]) + max_horizon < now
        ]
        choice = _choose_wait(prior, current, ctx, timeline, config)
        if choice:
            rows.append(_score(ctx, timeline, current, choice))
    return rows


def _folds(ctx, rows, k=4):
    train = [r for r in rows if r["decision_timestamp"] < ctx.split_timestamp]
    stamps = sorted({r["decision_timestamp"] for r in train})
    if len(stamps) < 80:
        return []
    size = max(20, len(stamps) // k)
    out = []
    for i in range(k):
        part = stamps[i*size:] if i == k-1 else stamps[i*size:(i+1)*size]
        allowed = set(part)
        out.append(summarize([r for r in train if r["decision_timestamp"] in allowed]))
    return out


def _rank(train, folds):
    rates = [
        f["success_30_rate"] for f in folds
        if (f.get("n") or 0) >= 20 and f.get("success_30_rate") is not None
    ]
    recent = rates[-1] if rates else 0.0
    mean = statistics.mean(rates) if rates else 0.0
    floor = min(rates) if rates else 0.0
    overall = float(train.get("success_30_rate") or 0.0)

    # Current-regime performance matters most, but stability still prevents a
    # tiny recent streak from dominating.
    score = 0.40 * recent + 0.25 * mean + 0.20 * overall + 0.15 * floor
    return (score, recent, mean, floor, overall)


def run_item(country, item_name, max_depth=10):
    ctx, timeline, decisions = build_dense_decisions(
        country, item_name, max_depth=max_depth
    )
    results = []
    for config in config_grid():
        rows = score_config(ctx, timeline, decisions, config)
        train_rows = [r for r in rows if r["decision_timestamp"] < ctx.split_timestamp]
        hold_rows = [r for r in rows if r["decision_timestamp"] >= ctx.split_timestamp]
        train = summarize(train_rows)
        hold = summarize(hold_rows)
        folds = _folds(ctx, rows)
        rank = _rank(train, folds)
        results.append({
            "config": config.name,
            "family": config.family,
            "train": train,
            "holdout": hold,
            "rolling_train_folds": folds,
            "rank_key": list(rank),
        })

    results.sort(key=lambda r: tuple(r["rank_key"]), reverse=True)
    selected = results[0] if results else None

    return {
        "country": country.lower(),
        "item_name": item_name,
        "travel_seconds": ctx.travel_seconds,
        "decision_offsets_minutes": list(DECISION_OFFSETS_MINUTES),
        "departure_wait_grid_minutes": [min(WAIT_MINUTES), max(WAIT_MINUTES), 5],
        "decision_points": len(decisions),
        "candidate_configs_tested": len(results),
        "success_definition": "quantity_on_arrival >= 30",
        "selection_rule": (
            "Training only: 40% latest chronological fold, 25% fold mean, "
            "20% overall train, 15% fold floor. Holdout is reporting only."
        ),
        "selected_on_training": selected,
        "top_finalists": results[:15],
    }
