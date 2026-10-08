import statistics

from services.projection_engine_v5 import _valid_cycle


def _usable_cycles(ctx, anchor_i):
    return [
        c for c in ctx.cycles[: anchor_i + 1]
        if _valid_cycle(c)
    ]


def _spacings(cycles):
    out = []
    for i in range(1, len(cycles)):
        a = cycles[i - 1].get("restock_time")
        b = cycles[i].get("restock_time")
        if a is not None and b is not None and b > a:
            out.append(float(b - a))
    return out


def _depletion_spacings(cycles):
    out = []
    for i in range(1, len(cycles)):
        a = cycles[i - 1].get("depletion_time")
        b = cycles[i].get("depletion_time")
        if a is not None and b is not None and b > a:
            out.append(float(b - a))
    return out


def _estimate(values, method):
    if not values:
        return None
    if method == "last1":
        return values[-1]
    if method == "last2_mean":
        return statistics.mean(values[-2:])
    if method == "last3_mean":
        return statistics.mean(values[-3:])
    if method == "last3_median":
        return statistics.median(values[-3:])
    if method == "last5_mean":
        return statistics.mean(values[-5:])
    if method == "last5_median":
        return statistics.median(values[-5:])
    raise ValueError(method)


def persistence_rows(ctx, depth, basis, method):
    rows = []
    for anchor_i, anchor in enumerate(ctx.cycles):
        target_i = anchor_i + depth
        if target_i >= len(ctx.cycles):
            break
        if not _valid_cycle(anchor) or not _valid_cycle(ctx.cycles[target_i]):
            continue

        known = _usable_cycles(ctx, anchor_i)
        if len(known) < max(ctx.min_history, 3):
            continue

        if basis == "restock_spacing":
            vals = _spacings(known)
        elif basis == "depletion_spacing":
            vals = _depletion_spacings(known)
        elif basis == "cycle_length":
            vals = [
                float(c["depletion_time"]) - float(c["restock_time"])
                for c in known
                if c.get("restock_time") is not None
                and c.get("depletion_time") is not None
            ]
        else:
            raise ValueError(basis)

        step = _estimate(vals, method)
        if step is None or step <= 0:
            continue

        anchor_ts = float(anchor["depletion_time"])
        target = ctx.cycles[target_i]
        actual_r = float(target["restock_time"])
        actual_d = float(target["depletion_time"])

        # Pure persistence: repeat the latest estimated interval depth times
        # from the known depletion anchor. This intentionally stays simple.
        predicted_r = anchor_ts + float(step) * depth

        recent_lives = [
            float(c["depletion_time"]) - float(c["restock_time"])
            for c in known[-5:]
            if c.get("restock_time") is not None
            and c.get("depletion_time") is not None
        ]
        life_est = statistics.median(recent_lives) if recent_lives else 300.0

        rows.append({
            "anchor_timestamp": int(anchor_ts),
            "depth": depth,
            "raw_predicted_restock_timestamp": predicted_r,
            "actual_restock_timestamp": actual_r,
            "actual_depletion_timestamp": actual_d,
            "actual_lifetime_seconds": actual_d - actual_r,
            "lifetime_estimate_seconds": life_est,
            "wait_estimate_seconds": step,
            "forecast_mode": f"persistence:{basis}:{method}",
            "predicted_wait_total_seconds": None,
            "predicted_bridge_lifetime_total_seconds": None,
            "actual_wait_total_seconds": None,
            "actual_bridge_lifetime_total_seconds": None,
            "wait_component_error_seconds": None,
            "lifetime_component_error_seconds": None,
            "direct_horizon_error_seconds": actual_r - predicted_r,
        })
    return rows


def persistence_grid(ctx, max_depth=5):
    methods = (
        "last1",
        "last2_mean",
        "last3_mean",
        "last3_median",
        "last5_mean",
        "last5_median",
    )
    bases = ("restock_spacing", "depletion_spacing")
    for depth in range(1, max_depth + 1):
        for basis in bases:
            for method in methods:
                rows = persistence_rows(ctx, depth, basis, method)
                if rows:
                    yield (
                        f"persist_d{depth}[{basis}|{method}]",
                        rows,
                    )
