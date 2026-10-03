import math
from dataclasses import dataclass

from services.projection_chain_lab_v2 import _interval_crosses_travel_day
from services.projection_chain_lab_v3 import (
    BASE_METHODS,
    EXTRA_LIFETIME_METHODS,
    EXTRA_WAIT_METHODS,
    _estimate_lifetime,
    _estimate_wait,
)
from services.projection_engine_v4 import (
    DIRECT_HORIZON_METHODS,
    ItemContext,
    point_forecast_pair as v4_point_forecast_pair,
)

# V5 extends V4 with explicit future-cycle bridge families.
#
# After the observed depletion anchor, D1 remains a depletion->restock forecast.
# For D2+ we compare:
#
#   decomposition:
#       previous predicted restock + predicted lifetime + predicted zero wait
#
#   direct spacing:
#       previous predicted restock + predicted restock->restock interval
#
#   hybrid:
#       blend(decomposition bridge, direct spacing bridge)
#
#   direct horizon (already in V4):
#       anchor depletion + predicted elapsed time directly to depth N
#
# This lets the holdout data tell us whether recursion itself is the source of
# deeper-horizon error instead of assuming one mechanism.

SPACING_METHODS = (
    "all_median",
    "recent3_mean",
    "recent5_mean",
    "recent5_median",
    "recent10_median",
    "weighted_recent5",
    "ewma35",
    "ewma55",
    "trimmed10_mean",
    "blend_recent5_all",
    "trend5_clipped",
    "recent_regime",
    "same_hour_median",
    "tod_recent_blend",
)

HYBRID_DIRECT_WEIGHTS = (0.25, 0.50, 0.75)


@dataclass(frozen=True)
class BridgeConfig:
    family: str
    wait_method: str
    spacing_method: str | None = None
    direct_weight: float | None = None

    @property
    def label(self):
        if self.family == "decomposition":
            return self.wait_method
        if self.family == "direct_spacing":
            return f"spacing[{self.wait_method}|{self.spacing_method}]"
        if self.family == "hybrid":
            pct = int(round(float(self.direct_weight) * 100))
            return (
                f"hybrid{pct}[{self.wait_method}|{self.spacing_method}]"
            )
        raise ValueError(self.family)


def _valid_cycle(c):
    return (
        not c.get("_excluded_regime")
        and c.get("_valid_for_training", True)
        and c.get("restock_time") is not None
        and c.get("depletion_time") is not None
    )


def _known_spacing_rows(cycles, anchor_i, anchor_ts):
    """
    Restock->restock intervals whose ending restock was already observed before
    the current depletion anchor. No future spacing leaks into the estimate.
    """
    rows = []
    for i in range(1, anchor_i + 1):
        previous = cycles[i - 1]
        current = cycles[i]
        if not _valid_cycle(previous) or not _valid_cycle(current):
            continue

        start = int(previous["restock_time"])
        end = int(current["restock_time"])
        if end > anchor_ts or end <= start:
            continue
        if _interval_crosses_travel_day(start, end):
            continue

        rows.append({
            "from_depletion": start,
            "to_restock": end,
            "seconds": float(end - start),
        })
    return rows


def _valid_ground_truth_bridge(ctx, anchor_i, target_i):
    cycles = ctx.cycles
    waits = ctx.wait_rows
    anchor_ts = int(cycles[anchor_i]["depletion_time"])
    actual_dep = int(cycles[target_i]["depletion_time"])

    chain = cycles[anchor_i : target_i + 1]
    if any(not _valid_cycle(c) for c in chain):
        return False
    if _interval_crosses_travel_day(anchor_ts, actual_dep):
        return False

    valid_bridge_map = {
        int(r["from_depletion"]): int(r["to_restock"])
        for r in waits
        if r.get("from_depletion") is not None
        and r.get("to_restock") is not None
    }
    for bridge_i in range(anchor_i, target_i):
        source_dep = int(cycles[bridge_i]["depletion_time"])
        expected = valid_bridge_map.get(source_dep)
        actual = int(cycles[bridge_i + 1]["restock_time"])
        if expected is None or expected != actual:
            return False
    return True


def bridge_point_forecast(ctx, lifetime_method, config):
    if config.family == "decomposition":
        return v4_point_forecast_pair(
            ctx, lifetime_method, config.wait_method
        )

    rows = []
    cycles = ctx.cycles
    waits = ctx.wait_rows

    for anchor_i, anchor in enumerate(cycles):
        if not _valid_cycle(anchor):
            continue

        anchor_ts = int(anchor["depletion_time"])
        known_cycles = [
            c for c in cycles[: anchor_i + 1] if _valid_cycle(c)
        ]
        known_waits = [
            r for r in waits if int(r["from_depletion"]) < anchor_ts
        ]
        spacing_rows = _known_spacing_rows(
            cycles, anchor_i, anchor_ts
        )

        if (
            len(known_cycles) < ctx.min_history
            or len(known_waits) < ctx.min_history
            or len(spacing_rows) < ctx.min_history
        ):
            continue

        first_wait = _estimate_wait(
            config.wait_method, known_waits, anchor_ts
        )
        if not first_wait or first_wait <= 0:
            continue

        projected_restock = float(anchor_ts) + float(first_wait)
        predicted_wait_total = float(first_wait)
        predicted_lifetime_total = 0.0
        predicted_spacing_total = 0.0

        for depth in range(1, ctx.max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break

            bridge_decomp = None
            bridge_spacing = None

            if depth > 1:
                life_bridge = _estimate_lifetime(
                    lifetime_method, known_cycles, projected_restock
                )
                wait_bridge = _estimate_wait(
                    config.wait_method,
                    known_waits,
                    projected_restock + float(life_bridge or 0),
                )
                spacing_bridge = _estimate_wait(
                    config.spacing_method,
                    spacing_rows,
                    projected_restock,
                )

                if (
                    not life_bridge or life_bridge <= 0
                    or not wait_bridge or wait_bridge <= 0
                    or not spacing_bridge or spacing_bridge <= 0
                ):
                    break

                bridge_decomp = float(life_bridge) + float(wait_bridge)
                bridge_spacing = float(spacing_bridge)

                if config.family == "direct_spacing":
                    bridge = bridge_spacing
                elif config.family == "hybrid":
                    w = float(config.direct_weight)
                    bridge = w * bridge_spacing + (1.0 - w) * bridge_decomp
                else:
                    raise ValueError(config.family)

                projected_restock += bridge
                predicted_wait_total += float(wait_bridge)
                predicted_lifetime_total += float(life_bridge)
                predicted_spacing_total += float(spacing_bridge)

            target_lifetime = _estimate_lifetime(
                lifetime_method, known_cycles, projected_restock
            )
            if not target_lifetime or target_lifetime <= 0:
                break

            if not _valid_ground_truth_bridge(ctx, anchor_i, target_i):
                break

            target = cycles[target_i]
            actual_restock = float(target["restock_time"])
            actual_depletion = float(target["depletion_time"])

            actual_spacing_total = 0.0
            if depth > 1:
                actual_spacing_total = sum(
                    float(cycles[j]["restock_time"])
                    - float(cycles[j - 1]["restock_time"])
                    for j in range(anchor_i + 2, target_i + 1)
                )

            rows.append({
                "anchor_timestamp": anchor_ts,
                "depth": depth,
                "raw_predicted_restock_timestamp": float(projected_restock),
                "actual_restock_timestamp": actual_restock,
                "actual_depletion_timestamp": actual_depletion,
                "actual_lifetime_seconds": actual_depletion - actual_restock,
                "lifetime_estimate_seconds": float(target_lifetime),
                "wait_estimate_seconds": float(first_wait),
                "forecast_mode": config.family,
                "bridge_label": config.label,
                "bridge_decomposition_seconds": bridge_decomp,
                "bridge_spacing_seconds": bridge_spacing,
                "predicted_wait_total_seconds": predicted_wait_total,
                "predicted_bridge_lifetime_total_seconds": predicted_lifetime_total,
                "predicted_spacing_total_seconds": predicted_spacing_total,
                "actual_spacing_total_seconds": actual_spacing_total,
                "spacing_component_error_seconds": (
                    actual_spacing_total - predicted_spacing_total
                    if depth > 1 else 0.0
                ),
            })

    return rows


def spacing_candidate_configs(wait_methods=None):
    waits = (
        tuple(wait_methods)
        if wait_methods is not None
        else tuple(BASE_METHODS) + tuple(EXTRA_WAIT_METHODS)
    )

    for wait in waits:
        for spacing in SPACING_METHODS:
            yield BridgeConfig(
                "direct_spacing",
                wait_method=wait,
                spacing_method=spacing,
            )
            for weight in HYBRID_DIRECT_WEIGHTS:
                yield BridgeConfig(
                    "hybrid",
                    wait_method=wait,
                    spacing_method=spacing,
                    direct_weight=weight,
                )
