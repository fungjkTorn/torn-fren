import math
import statistics

from services.projection_engine_v5 import _valid_cycle


def _hour_distance(a_ts, b_ts):
    a = (float(a_ts) % 86400.0) / 3600.0
    b = (float(b_ts) % 86400.0) / 3600.0
    d = abs(a - b)
    return min(d, 24.0 - d)


def _median(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _mean(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _known_waits(ctx, anchor_ts):
    return [
        r for r in ctx.wait_rows
        if r.get("from_depletion") is not None
        and r.get("to_restock") is not None
        and int(r["from_depletion"]) < int(anchor_ts)
    ]


def _known_cycles(ctx, anchor_i):
    return [
        c for c in ctx.cycles[: anchor_i + 1]
        if _valid_cycle(c)
    ]


def _feature_vector(ctx, anchor_i):
    anchor = ctx.cycles[anchor_i]
    anchor_ts = int(anchor["depletion_time"])
    cycles = _known_cycles(ctx, anchor_i)
    waits = _known_waits(ctx, anchor_ts)

    lifetimes = [c.get("lifetime_seconds") for c in cycles]
    wait_secs = [r.get("seconds") for r in waits]

    spacings = []
    for i in range(1, len(cycles)):
        a = cycles[i - 1].get("restock_time")
        b = cycles[i].get("restock_time")
        if a is not None and b is not None and b > a:
            spacings.append(float(b - a))

    return {
        "anchor_ts": anchor_ts,
        "last_lifetime": lifetimes[-1] if lifetimes else None,
        "life3": _mean(lifetimes[-3:]),
        "life5": _mean(lifetimes[-5:]),
        "life5_med": _median(lifetimes[-5:]),
        "last_wait": wait_secs[-1] if wait_secs else None,
        "wait3": _mean(wait_secs[-3:]),
        "wait5": _mean(wait_secs[-5:]),
        "wait5_med": _median(wait_secs[-5:]),
        "spacing3": _mean(spacings[-3:]),
        "spacing5": _mean(spacings[-5:]),
        "spacing5_med": _median(spacings[-5:]),
        "hour": (anchor_ts % 86400) / 3600.0,
    }


FEATURES = (
    "last_lifetime",
    "life3",
    "life5",
    "life5_med",
    "last_wait",
    "wait3",
    "wait5",
    "wait5_med",
    "spacing3",
    "spacing5",
    "spacing5_med",
)


def _scale(history, feature):
    vals = [h["features"].get(feature) for h in history]
    vals = [float(v) for v in vals if v is not None]
    if len(vals) < 5:
        return 1.0
    med = statistics.median(vals)
    dev = [abs(v - med) for v in vals]
    mad = statistics.median(dev)
    return max(60.0, mad * 1.4826)


def _distance(a, b, history, tod_weight=0.25):
    parts = []
    for feature in FEATURES:
        av = a.get(feature)
        bv = b.get(feature)
        if av is None or bv is None:
            continue
        scale = _scale(history, feature)
        parts.append(abs(float(av) - float(bv)) / scale)

    if not parts:
        return 1e9

    base = sum(parts) / len(parts)
    hour_penalty = _hour_distance(
        a["anchor_ts"], b["anchor_ts"]
    ) / 6.0
    return base + tod_weight * hour_penalty


def _examples(ctx, depth=2):
    out = []
    cycles = ctx.cycles
    for anchor_i, anchor in enumerate(cycles):
        target_i = anchor_i + depth
        if target_i >= len(cycles):
            break
        if not _valid_cycle(anchor) or not _valid_cycle(cycles[target_i]):
            continue

        anchor_ts = int(anchor["depletion_time"])
        target_r = int(cycles[target_i]["restock_time"])
        target_d = int(cycles[target_i]["depletion_time"])
        if target_r <= anchor_ts:
            continue

        out.append({
            "anchor_i": anchor_i,
            "anchor_ts": anchor_ts,
            "features": _feature_vector(ctx, anchor_i),
            "horizon_seconds": float(target_r - anchor_ts),
            "target_lifetime_seconds": float(target_d - target_r),
            "actual_restock_timestamp": float(target_r),
            "actual_depletion_timestamp": float(target_d),
        })
    return out


def analog_horizon_rows(
    ctx,
    depth=2,
    neighbors=15,
    recent_limit=120,
    tod_weight=0.25,
    recency_weight=0.35,
):
    """
    Walk-forward KNN/analog model for a fixed projection depth.

    For each historical anchor, predict the full anchor-depletion -> target
    restock horizon from earlier anchors with similar recent lifetime/wait/
    spacing state. No future anchor is ever available to the neighbor pool.
    """
    examples = _examples(ctx, depth=depth)
    rows = []

    for idx, current in enumerate(examples):
        history = examples[:idx]
        if recent_limit:
            history = history[-recent_limit:]
        if len(history) < max(ctx.min_history, neighbors):
            continue

        scored = []
        for age, prior in enumerate(history):
            dist = _distance(
                current["features"],
                prior["features"],
                history,
                tod_weight=tod_weight,
            )
            # Mild preference for newer analogs without excluding older regimes.
            freshness = (len(history) - age) / max(1, len(history))
            adjusted = dist * (1.0 + recency_weight * freshness)
            scored.append((adjusted, prior))

        scored.sort(key=lambda x: x[0])
        chosen = scored[:neighbors]

        weights = [1.0 / max(0.05, d) for d, _ in chosen]
        total = sum(weights)
        horizon = sum(
            w * r["horizon_seconds"] for w, (_, r) in zip(weights, chosen)
        ) / total
        life = sum(
            w * r["target_lifetime_seconds"] for w, (_, r) in zip(weights, chosen)
        ) / total

        predicted_restock = current["anchor_ts"] + horizon
        actual_restock = current["actual_restock_timestamp"]

        rows.append({
            "anchor_timestamp": current["anchor_ts"],
            "depth": depth,
            "raw_predicted_restock_timestamp": predicted_restock,
            "actual_restock_timestamp": actual_restock,
            "actual_depletion_timestamp": current["actual_depletion_timestamp"],
            "actual_lifetime_seconds": current["target_lifetime_seconds"],
            "lifetime_estimate_seconds": life,
            "wait_estimate_seconds": horizon,
            "forecast_mode": "analog_horizon",
            "predicted_wait_total_seconds": None,
            "predicted_bridge_lifetime_total_seconds": None,
            "actual_wait_total_seconds": None,
            "actual_bridge_lifetime_total_seconds": None,
            "wait_component_error_seconds": None,
            "lifetime_component_error_seconds": None,
            "direct_horizon_error_seconds": (
                actual_restock - predicted_restock
            ),
            "analog_neighbors": neighbors,
            "analog_recent_limit": recent_limit,
            "analog_tod_weight": tod_weight,
            "analog_recency_weight": recency_weight,
        })
    return rows


def analog_grid(ctx, depth=2):
    for neighbors in (5, 8, 12, 16, 24):
        for recent_limit in (40, 80, 120, 200, None):
            for tod_weight in (0.0, 0.25, 0.5, 1.0):
                for recency_weight in (0.0, 0.20, 0.40):
                    rows = analog_horizon_rows(
                        ctx,
                        depth=depth,
                        neighbors=neighbors,
                        recent_limit=recent_limit,
                        tod_weight=tod_weight,
                        recency_weight=recency_weight,
                    )
                    if rows:
                        label = (
                            f"analog_d{depth}[k={neighbors},recent={recent_limit},"
                            f"tod={tod_weight},recency={recency_weight}]"
                        )
                        yield label, rows
