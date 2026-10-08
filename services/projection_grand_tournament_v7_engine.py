import bisect
import math
import statistics
from dataclasses import dataclass

from services.arrival_success_lab import TRAVEL_SECONDS
from services.history_service import (
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)
from services.projection_engine_v4 import build_item_context


MIN_STOCK = 30
SHORT_WAIT_SECONDS = 180


@dataclass(frozen=True)
class GrandConfig:
    horizon_method: str
    lookback: int | None
    tod_hours: float | None
    duration_method: str
    arrival_fraction: float
    bias_method: str

    @property
    def name(self):
        return (
            f"h={self.horizon_method}|lb={self.lookback}|tod={self.tod_hours}|"
            f"dur={self.duration_method}|f={self.arrival_fraction:.2f}|"
            f"bias={self.bias_method}"
        )


HORIZON_METHODS = (
    "last1",
    "last2_mean",
    "last3_mean",
    "last5_mean",
    "median",
    "mean",
    "weighted_mean",
    "trimmed_mean",
    "ewma35",
    "ewma55",
    "trend",
    "q25",
    "q40",
    "q60",
    "q75",
)

LOOKBACKS = (10, 20, 40, 80, None)
TOD_HOURS = (None, 3.0, 6.0)
DURATION_METHODS = (
    "last1",
    "last3_mean",
    "last5_median",
    "recent10_median",
    "median",
)
ARRIVAL_FRACTIONS = (0.0, 0.10, 0.25, 0.40, 0.50, 0.65, 0.80)
BIAS_METHODS = ("none", "recent10", "recent20", "all")


def _percentile(values, q):
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    x = (len(vals) - 1) * q
    lo = int(math.floor(x))
    hi = int(math.ceil(x))
    if lo == hi:
        return vals[lo]
    frac = x - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac


def _hour_distance(a_ts, b_ts):
    a = (float(a_ts) % 86400.0) / 3600.0
    b = (float(b_ts) % 86400.0) / 3600.0
    return abs(((a - b + 12.0) % 24.0) - 12.0)


def _estimate(values, method):
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return None
    if method == "last1":
        return vals[-1]
    if method == "last2_mean":
        return statistics.mean(vals[-2:])
    if method == "last3_mean":
        return statistics.mean(vals[-3:])
    if method == "last5_mean":
        return statistics.mean(vals[-5:])
    if method == "last5_median":
        return statistics.median(vals[-5:])
    if method == "recent10_median":
        return statistics.median(vals[-10:])
    if method == "median":
        return statistics.median(vals)
    if method == "mean":
        return statistics.mean(vals)
    if method == "weighted_mean":
        recent = vals[-10:]
        weights = list(range(1, len(recent) + 1))
        return sum(v * w for v, w in zip(recent, weights)) / sum(weights)
    if method == "trimmed_mean":
        work = sorted(vals[-20:])
        if len(work) >= 8:
            trim = max(1, len(work) // 10)
            work = work[trim:-trim]
        return statistics.mean(work)
    if method in ("ewma35", "ewma55"):
        alpha = 0.35 if method == "ewma35" else 0.55
        out = vals[0]
        for v in vals[1:]:
            out = alpha * v + (1.0 - alpha) * out
        return out
    if method == "trend":
        recent = vals[-8:]
        if len(recent) < 3:
            return statistics.median(vals)
        xs = list(range(len(recent)))
        xb, yb = statistics.mean(xs), statistics.mean(recent)
        den = sum((x - xb) ** 2 for x in xs)
        slope = (
            sum((x - xb) * (y - yb) for x, y in zip(xs, recent)) / den
            if den else 0.0
        )
        pred = yb + slope * (len(recent) - xb)
        lo = _percentile(vals, 0.10)
        hi = _percentile(vals, 0.90)
        return min(hi, max(lo, pred))
    if method == "q25":
        return _percentile(vals, 0.25)
    if method == "q40":
        return _percentile(vals, 0.40)
    if method == "q60":
        return _percentile(vals, 0.60)
    if method == "q75":
        return _percentile(vals, 0.75)
    raise ValueError(method)


class QuantityTimeline:
    def __init__(self, country, item_name):
        raw = _get_all_item_rows_with_source(country, item_name)
        cleaned, _ = _suppress_provider_bounces(raw)
        self.rows = [(int(ts), int(qty)) for ts, qty, _source in cleaned]
        self.timestamps = [ts for ts, _ in self.rows]

    def quantity_at(self, timestamp):
        i = bisect.bisect_right(self.timestamps, int(timestamp)) - 1
        if i < 0:
            return None
        return self.rows[i][1]

    def first_at_least(self, timestamp, threshold=MIN_STOCK, within=None):
        start = bisect.bisect_left(self.timestamps, int(timestamp))
        end_ts = None if within is None else int(timestamp) + int(within)
        # State may already satisfy threshold before the next change.
        current = self.quantity_at(timestamp)
        if current is not None and current >= threshold:
            return int(timestamp), current
        for i in range(start, len(self.rows)):
            ts, qty = self.rows[i]
            if end_ts is not None and ts > end_ts:
                break
            if qty >= threshold:
                return ts, qty
        return None

    def usable_window_for_cycle(self, cycle, threshold=MIN_STOCK):
        r = int(cycle["restock_time"])
        d = int(cycle["depletion_time"])
        if d <= r:
            return None
        start_i = bisect.bisect_left(self.timestamps, r)
        end_i = bisect.bisect_right(self.timestamps, d)

        start = None
        end = None
        last_qty = self.quantity_at(r)
        if last_qty is not None and last_qty >= threshold:
            start = r
        for i in range(start_i, end_i):
            ts, qty = self.rows[i]
            if start is None and qty >= threshold:
                start = ts
            if start is not None and qty < threshold:
                end = ts
                break
        if start is None:
            return None
        if end is None:
            end = d
        if end <= start:
            return None
        return {
            "start": float(start),
            "end": float(end),
            "duration": float(end - start),
        }


def _wilson_lower(hits, n, z=1.959963984540054):
    if n <= 0:
        return None
    p = hits / n
    den = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1 - p) + z*z/(4*n)) / n)
    return (center - margin) / den


def build_examples(country, item_name, max_depth=7, min_history=8):
    ctx = build_item_context(
        country.lower(), item_name, max_depth=max_depth, min_history=min_history
    )
    timeline = QuantityTimeline(country.lower(), item_name)
    cycles = ctx.cycles
    examples_by_depth = {d: [] for d in range(1, max_depth + 1)}

    for anchor_i, anchor in enumerate(cycles):
        if (
            anchor.get("_excluded_regime")
            or not anchor.get("_valid_for_training", True)
            or anchor.get("depletion_time") is None
        ):
            continue
        anchor_ts = float(anchor["depletion_time"])
        for depth in range(1, max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break
            target = cycles[target_i]
            if (
                target.get("_excluded_regime")
                or not target.get("_valid_for_training", True)
            ):
                continue
            window = timeline.usable_window_for_cycle(target, MIN_STOCK)
            if window is None:
                continue
            examples_by_depth[depth].append({
                "anchor_timestamp": int(anchor_ts),
                "depth": depth,
                "horizon_start": window["start"] - anchor_ts,
                "horizon_end": window["end"] - anchor_ts,
                "usable_duration": window["duration"],
                "actual_start": window["start"],
                "actual_end": window["end"],
            })
    return ctx, timeline, examples_by_depth


def _history_for(current, history, lookback, tod_hours):
    usable = history
    if tod_hours is not None:
        nearby = [
            r for r in history
            if _hour_distance(r["anchor_timestamp"], current["anchor_timestamp"])
            <= tod_hours
        ]
        if len(nearby) >= 8:
            usable = nearby
    if lookback:
        usable = usable[-lookback:]
    return usable


def _bias(residuals, method):
    if method == "none" or not residuals:
        return 0.0
    vals = residuals
    if method == "recent10":
        vals = vals[-10:]
    elif method == "recent20":
        vals = vals[-20:]
    elif method != "all":
        raise ValueError(method)
    return statistics.median(vals) if len(vals) >= 5 else 0.0


def point_rows_for_base(
    ctx,
    timeline,
    examples_by_depth,
    horizon_method,
    lookback,
    tod_hours,
    duration_method,
    bias_method,
):
    rows = []
    for depth, examples in examples_by_depth.items():
        residuals = []
        history = []
        for current in examples:
            if len(history) < ctx.min_history:
                history.append(current)
                continue
            usable = _history_for(current, history, lookback, tod_hours)
            if len(usable) < ctx.min_history:
                history.append(current)
                continue

            horizon = _estimate(
                [r["horizon_start"] for r in usable], horizon_method
            )
            duration = _estimate(
                [r["usable_duration"] for r in usable], duration_method
            )
            if horizon is None or duration is None or duration <= 0:
                history.append(current)
                continue

            correction = _bias(residuals, bias_method)
            predicted_start_horizon = float(horizon) + correction
            actual_start_horizon = float(current["horizon_start"])
            residual = actual_start_horizon - predicted_start_horizon

            rows.append({
                "anchor_timestamp": current["anchor_timestamp"],
                "depth": depth,
                "predicted_start_horizon": predicted_start_horizon,
                "predicted_duration": float(duration),
                "actual_start": current["actual_start"],
                "actual_end": current["actual_end"],
            })
            residuals.append(residual)
            history.append(current)
    return rows


def score_fraction_rows(ctx, timeline, point_rows, fraction):
    scored = []
    travel = float(ctx.travel_seconds)
    for row in point_rows:
        anchor = float(row["anchor_timestamp"])
        arrival = (
            anchor
            + float(row["predicted_start_horizon"])
            + float(row["predicted_duration"]) * float(fraction)
        )
        departure = arrival - travel
        actionable = departure >= anchor

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

        scored.append({
            **row,
            "recommended_arrival_timestamp": arrival,
            "recommended_departure_timestamp": departure,
            "actionable_from_anchor": int(actionable),
            "quantity_on_arrival": qty,
            "success_30": success,
            "short_wait_3m": short_wait,
            "wait_seconds": wait_seconds,
            "early_window": int(arrival < float(row["actual_start"])),
            "late_window": int(arrival >= float(row["actual_end"])),
        })
    return scored


def active_rows(rows):
    grouped = {}
    for r in rows:
        grouped.setdefault(r["anchor_timestamp"], []).append(r)
    selected = []
    for group in grouped.values():
        reachable = sorted(
            (r for r in group if r["actionable_from_anchor"]),
            key=lambda r: r["depth"],
        )
        if reachable:
            selected.append(reachable[0])
    return selected


def summarize(rows, eligible_anchors=None):
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "coverage": 0.0 if eligible_anchors else None,
            "success_30_rate": None,
            "success_or_short_wait_rate": None,
            "short_wait_only_rate": None,
            "early_rate": None,
            "late_rate": None,
            "wilson_lower_95": None,
            "median_quantity_on_arrival": None,
        }
    hits = sum(r["success_30"] for r in rows)
    short_only = sum(
        (not r["success_30"]) and r["short_wait_3m"] for r in rows
    )
    quantities = [
        r["quantity_on_arrival"] for r in rows
        if r["quantity_on_arrival"] is not None
    ]
    return {
        "n": n,
        "coverage": (
            n / eligible_anchors if eligible_anchors else None
        ),
        "success_30_rate": hits / n,
        "success_or_short_wait_rate": (hits + short_only) / n,
        "short_wait_only_rate": short_only / n,
        "early_rate": sum(r["early_window"] for r in rows) / n,
        "late_rate": sum(r["late_window"] for r in rows) / n,
        "wilson_lower_95": _wilson_lower(hits, n),
        "median_quantity_on_arrival": (
            statistics.median(quantities) if quantities else None
        ),
    }


def period_active(ctx, rows, period):
    split = ctx.split_timestamp
    if split is None:
        return [], 0
    if period == "train":
        subset = [r for r in rows if r["anchor_timestamp"] < split]
    elif period == "holdout":
        subset = [r for r in rows if r["anchor_timestamp"] >= split]
    else:
        raise ValueError(period)
    anchors = {r["anchor_timestamp"] for r in subset}
    return active_rows(subset), len(anchors)


def rolling_folds(ctx, rows, folds=4):
    train = [r for r in rows if r["anchor_timestamp"] < ctx.split_timestamp]
    anchors = sorted({r["anchor_timestamp"] for r in train})
    if len(anchors) < 40:
        return []
    size = max(10, len(anchors) // folds)
    out = []
    for i in range(folds):
        part = anchors[i * size:] if i == folds - 1 else anchors[i*size:(i+1)*size]
        aset = set(part)
        subset = [r for r in train if r["anchor_timestamp"] in aset]
        active = active_rows(subset)
        out.append(summarize(active, len(aset)))
    return out


def config_grid():
    for horizon_method in HORIZON_METHODS:
        for lookback in LOOKBACKS:
            for tod_hours in TOD_HOURS:
                for duration_method in DURATION_METHODS:
                    for bias_method in BIAS_METHODS:
                        yield (
                            horizon_method, lookback, tod_hours,
                            duration_method, bias_method,
                        )
