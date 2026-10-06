import math
import statistics
from dataclasses import dataclass

from services.projection_grand_tournament_v8_live_engine import (
    MIN_STOCK,
    SHORT_WAIT_SECONDS,
    build_live_decisions,
    summarize,
)


DEFAULT_WAIT_MINUTES = tuple(range(0, 181, 5))


@dataclass(frozen=True)
class ProbabilityConfig:
    family: str
    lookback: int | None = None
    age_window_minutes: int = 0
    half_life: float | None = None
    state_scale: float | None = None

    @property
    def name(self):
        return (
            f"{self.family}|lb={self.lookback}|age={self.age_window_minutes}|"
            f"half={self.half_life}|state={self.state_scale}"
        )


def config_grid():
    # Keep this intentionally bounded.  The overnight runner evaluates many
    # items, so we want materially different hypotheses rather than thousands
    # of near-duplicate knobs.
    for lb in (5, 8, 10, 12, 15, 20, 30, 40, 60, 80):
        for age in (0, 15):
            yield ProbabilityConfig("recent_uniform", lb, age)

    for half in (3.0, 5.0, 8.0, 12.0):
        for age in (0, 15):
            yield ProbabilityConfig(
                "recent_exponential", 30, age, half_life=half
            )

    for lb in (8, 10, 15, 20):
        for scale in (0.75, 1.5):
            yield ProbabilityConfig(
                "recent_state", lb, 0, state_scale=scale
            )


def _median_abs_deviation(values):
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return None
    med = statistics.median(vals)
    dev = [abs(v - med) for v in vals]
    mad = statistics.median(dev)
    return max(mad * 1.4826, 1.0)


def _state_vector(ctx, timeline, decision):
    cycle = ctx.cycles[int(decision["anchor_i"])]
    peak = float(cycle.get("peak_quantity") or 0.0)
    life = float(cycle.get("lifetime_seconds") or decision.get("last_lifetime_seconds") or 0.0)
    gap = decision.get("last_gap_seconds")
    gap = float(gap) if gap is not None else None
    depletion_rate = peak / max(life / 60.0, 1.0)
    usable = timeline.usable_window_for_cycle(cycle, MIN_STOCK)
    safe = float(usable["duration"]) if usable else 0.0
    return {
        "peak": peak,
        "life": life,
        "gap": gap,
        "rate": depletion_rate,
        "safe": safe,
    }


def _state_weights(current_state, prior_states, scale):
    keys = ("peak", "life", "gap", "rate", "safe")
    spreads = {}
    for key in keys:
        spreads[key] = _median_abs_deviation([s.get(key) for s in prior_states])

    out = []
    for state in prior_states:
        terms = []
        for key in keys:
            a = current_state.get(key)
            b = state.get(key)
            spread = spreads.get(key)
            if a is None or b is None or spread is None:
                continue
            terms.append(((float(a) - float(b)) / spread) ** 2)
        d2 = sum(terms) / max(len(terms), 1)
        out.append(math.exp(-0.5 * d2 / max(float(scale) ** 2, 1e-9)))
    return out


def _base_weights(n, config):
    if n <= 0:
        return []
    if config.family != "recent_exponential":
        return [1.0] * n
    half = max(float(config.half_life or 5.0), 0.1)
    # Newest row has age 0 cycles, next newest age 1, etc.
    ages = list(reversed(range(n)))
    return [0.5 ** (age / half) for age in ages]


def _weighted_probability(hits, weights):
    den = sum(weights)
    if den <= 0:
        return None
    return sum(float(h) * float(w) for h, w in zip(hits, weights)) / den


def _choose_wait(prior, current, ctx, timeline, config, wait_minutes):
    if not prior:
        return None

    age_window = int(config.age_window_minutes or 0) * 60
    if age_window == 0:
        usable = [r for r in prior if int(r["age_seconds"]) == int(current["age_seconds"])]
    else:
        usable = [
            r for r in prior
            if abs(int(r["age_seconds"]) - int(current["age_seconds"])) <= age_window
        ]

    if config.lookback:
        usable = usable[-int(config.lookback):]
    if len(usable) < 5:
        return None

    weights = _base_weights(len(usable), config)
    if config.family == "recent_state":
        current_state = current["_state"]
        state_w = _state_weights(
            current_state, [r["_state"] for r in usable],
            float(config.state_scale or 1.0),
        )
        weights = [a * b for a, b in zip(weights, state_w)]

    scored = []
    travel = float(ctx.travel_seconds)
    for wait_min in wait_minutes:
        offset = float(wait_min) * 60.0 + travel
        hits = []
        local_weights = []
        for row, weight in zip(usable, weights):
            # Historical path is queried at the exact analogous horizon.
            qty = timeline.quantity_at(float(row["decision_timestamp"]) + offset)
            if qty is None:
                continue
            hits.append(int(qty >= MIN_STOCK))
            local_weights.append(weight)
        if len(hits) < 5:
            continue
        probability = _weighted_probability(hits, local_weights)
        if probability is None:
            continue
        scored.append((probability, -float(wait_min), float(wait_min), len(hits)))

    if not scored:
        return None
    best = max(scored)
    return {
        "wait_minutes": best[2],
        "predicted_probability": best[0],
        "prior_samples": best[3],
    }


def score_config(ctx, timeline, decisions, config, wait_minutes=DEFAULT_WAIT_MINUTES):
    rows = []
    prepared = []
    max_wait_seconds = max(wait_minutes) * 60
    resolution_horizon = (
        float(ctx.travel_seconds) + float(max_wait_seconds) + SHORT_WAIT_SECONDS
    )

    for decision in decisions:
        d = dict(decision)
        d["_state"] = _state_vector(ctx, timeline, d)
        prepared.append(d)

    for current in prepared:
        now_ts = float(current["decision_timestamp"])
        # Strict no-leakage rule: a prior state can influence this decision only
        # after the entire candidate-departure horizon has already resolved.
        prior = [
            r for r in prepared
            if float(r["decision_timestamp"]) + resolution_horizon < now_ts
        ]
        choice = _choose_wait(
            prior, current, ctx, timeline, config, wait_minutes
        )
        if choice is None:
            continue

        departure = now_ts + choice["wait_minutes"] * 60.0
        arrival = departure + float(ctx.travel_seconds)
        qty = timeline.quantity_at(arrival)
        success = int(qty is not None and qty >= MIN_STOCK)

        short_wait = 0
        if not success:
            nxt = timeline.first_at_least(
                arrival, threshold=MIN_STOCK, within=SHORT_WAIT_SECONDS
            )
            if nxt is not None and nxt[0] > int(arrival):
                short_wait = 1

        rows.append({
            "anchor_timestamp": current["anchor_timestamp"],
            "decision_timestamp": current["decision_timestamp"],
            "age_seconds": current["age_seconds"],
            "recommended_wait_minutes": choice["wait_minutes"],
            "recommended_departure_timestamp": departure,
            "recommended_arrival_timestamp": arrival,
            "predicted_probability": choice["predicted_probability"],
            "prior_samples": choice["prior_samples"],
            "quantity_on_arrival": qty,
            "success_30": success,
            "short_wait_3m": short_wait,
            "early_window": int(arrival < float(current["actual_start"])),
            "late_window": int(arrival >= float(current["actual_end"])),
        })
    return rows


def _fold_summaries(ctx, rows, folds=4):
    train = [r for r in rows if r["decision_timestamp"] < ctx.split_timestamp]
    stamps = sorted({r["decision_timestamp"] for r in train})
    if len(stamps) < 80:
        return []
    size = max(20, len(stamps) // folds)
    output = []
    for i in range(folds):
        part = (
            stamps[i * size:]
            if i == folds - 1
            else stamps[i * size:(i + 1) * size]
        )
        allowed = set(part)
        output.append(summarize(
            [r for r in train if r["decision_timestamp"] in allowed]
        ))
    return output


def _rank(train, folds):
    if not train or train.get("success_30_rate") is None:
        return (-1.0, -1.0, -1.0)
    stable = [
        f["success_30_rate"] for f in folds
        if (f.get("n") or 0) >= 20 and f.get("success_30_rate") is not None
    ]
    fold_mean = statistics.mean(stable) if stable else 0.0
    fold_floor = min(stable) if stable else 0.0
    return (
        float(train.get("success_30_rate") or 0.0),
        float(fold_mean),
        float(fold_floor),
    )


def run_item(country, item_name, max_depth=8):
    ctx, timeline, decisions = build_live_decisions(
        country, item_name, max_depth=max_depth, min_history=8
    )
    candidates = []
    for config in config_grid():
        rows = score_config(ctx, timeline, decisions, config)
        train_rows = [
            r for r in rows if r["decision_timestamp"] < ctx.split_timestamp
        ]
        hold_rows = [
            r for r in rows if r["decision_timestamp"] >= ctx.split_timestamp
        ]
        folds = _fold_summaries(ctx, rows)
        train = summarize(train_rows)
        hold = summarize(hold_rows)
        rank_key = _rank(train, folds)
        candidates.append({
            "family": config.family,
            "config": config.name,
            "train": train,
            "holdout": hold,
            "rolling_train_folds": folds,
            "rank_key": list(rank_key),
        })

    candidates.sort(key=lambda r: tuple(r["rank_key"]), reverse=True)
    return {
        "country": country.lower(),
        "item_name": item_name,
        "travel_seconds": ctx.travel_seconds,
        "decision_points": len(decisions),
        "candidate_configs_tested": len(candidates),
        "success_definition": "quantity_on_arrival >= 30",
        "selection_rule": (
            "Configuration selected on chronological training success, then "
            "training-fold mean/floor. Holdout is reporting only."
        ),
        "selected_on_training": candidates[0] if candidates else None,
        "top_finalists": candidates[:10],
    }
