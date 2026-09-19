import math
import sqlite3
import statistics
from dataclasses import dataclass

from services.history_service import (
    DB_PATH,
    _build_validated_cycles,
    _collection_coverage,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)


@dataclass
class ModelResult:
    name: str
    anchor_family: str
    predictions: int
    median_absolute_error_seconds: float | None
    mean_absolute_error_seconds: float | None
    p90_absolute_error_seconds: float | None
    window_hit_rate: float | None
    median_window_width_seconds: float | None
    signed_bias_seconds: float | None


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _weighted_recent_mean(values, decay=0.72, limit=10):
    recent = list(values[-limit:])
    weights = [decay ** (len(recent) - 1 - i) for i in range(len(recent))]
    return sum(value * weight for value, weight in zip(recent, weights)) / sum(weights)


def _trimmed_mean(values, fraction=0.10):
    ordered = sorted(values)
    if len(ordered) < 8:
        return statistics.mean(ordered)
    trim = max(1, int(len(ordered) * fraction))
    if trim * 2 >= len(ordered):
        return statistics.mean(ordered)
    return statistics.mean(ordered[trim:-trim])


def _model_estimates(training):
    return {
        "all_median": statistics.median(training),
        "recent_5_median": statistics.median(training[-5:]),
        "recent_10_median": statistics.median(training[-10:]),
        "recent_5_mean": statistics.mean(training[-5:]),
        "weighted_recent_10": _weighted_recent_mean(training, decay=0.72, limit=10),
        "trimmed_mean": _trimmed_mean(training),
    }


def _prediction_half_window(training, center):
    deviations = [abs(value - center) for value in training]
    if not deviations:
        return 60
    return max(60, int(_percentile(deviations, 0.80)))


def _behavior_class(median_zero_wait_seconds):
    if median_zero_wait_seconds is None:
        return "unknown"
    minutes = median_zero_wait_seconds / 60
    if minutes <= 30:
        return "rapid"
    if minutes <= 120:
        return "short"
    if minutes <= 360:
        return "medium"
    if minutes <= 720:
        return "long"
    return "very_long"


def _behavior_description(name):
    return {
        "rapid": "≤30m zero→restock",
        "short": "30m–2h zero→restock",
        "medium": "2–6h zero→restock",
        "long": "6–12h zero→restock",
        "very_long": ">12h zero→restock",
        "unknown": "unknown",
    }.get(name, name)


def _valid_restock_interval_samples(cycles):
    completed = [cycle for cycle in cycles if cycle.get("complete")]
    normal = [cycle for cycle in completed if not cycle.get("tiny_restock")]
    samples = []

    for i in range(1, len(normal)):
        previous = normal[i - 1]
        current = normal[i]
        coverage = _collection_coverage(previous["restock_time"], current["restock_time"])
        reasons = []
        if not coverage["valid"]:
            reasons.append("collector coverage invalid")

        samples.append({
            "from_restock": previous["restock_time"],
            "to_restock": current["restock_time"],
            "seconds": current["restock_time"] - previous["restock_time"],
            "valid": not reasons,
            "exclusion_reasons": reasons,
        })
    return samples


def extract_prediction_samples(country: str, item_name: str):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, bounces = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    if not rows:
        return {
            "wait_samples": [],
            "all_wait_samples": [],
            "restock_interval_samples": [],
            "all_restock_interval_samples": [],
            "lifetimes": [],
            "provider_bounces": bounces,
            "completed_cycles": 0,
            "valid_cycles": 0,
        }

    cycles, _active, wait_samples = _build_validated_cycles(rows)
    completed = [cycle for cycle in cycles if cycle.get("complete")]
    valid_cycles = [cycle for cycle in completed if cycle.get("valid_lifetime")]
    valid_waits = [sample for sample in wait_samples if sample.get("valid")]
    lifetimes = [cycle["lifetime_seconds"] for cycle in valid_cycles]

    all_restock_intervals = _valid_restock_interval_samples(cycles)
    valid_restock_intervals = [s for s in all_restock_intervals if s.get("valid")]

    return {
        "wait_samples": valid_waits,
        "all_wait_samples": wait_samples,
        "restock_interval_samples": valid_restock_intervals,
        "all_restock_interval_samples": all_restock_intervals,
        "lifetimes": lifetimes,
        "provider_bounces": bounces,
        "completed_cycles": len(completed),
        "valid_cycles": len(valid_cycles),
    }


def _backtest_sample_series(samples, anchor_family: str, min_train: int):
    per_model = {}
    historical_values = []

    for sample in samples:
        actual = sample["seconds"]
        if len(historical_values) >= min_train:
            for formula, estimate in _model_estimates(historical_values).items():
                half_window = _prediction_half_window(historical_values, estimate)
                error = actual - estimate
                record = {
                    "actual_restock_timestamp": sample["to_restock"],
                    "predicted_duration_seconds": estimate,
                    "actual_duration_seconds": actual,
                    "signed_error_seconds": error,
                    "absolute_error_seconds": abs(error),
                    "window_hit": abs(error) <= half_window,
                    "window_half_width_seconds": half_window,
                }
                if anchor_family == "depletion":
                    record["anchor_timestamp"] = sample["from_depletion"]
                else:
                    record["anchor_timestamp"] = sample["from_restock"]
                per_model.setdefault((anchor_family, formula), []).append(record)
        historical_values.append(actual)

    return per_model


def _summarize_models(per_model):
    summaries = []
    for (anchor_family, formula), records in per_model.items():
        absolute_errors = [r["absolute_error_seconds"] for r in records]
        signed_errors = [r["signed_error_seconds"] for r in records]
        widths = [r["window_half_width_seconds"] * 2 for r in records]
        summaries.append(ModelResult(
            name=f"{anchor_family}/{formula}",
            anchor_family=anchor_family,
            predictions=len(records),
            median_absolute_error_seconds=statistics.median(absolute_errors) if absolute_errors else None,
            mean_absolute_error_seconds=statistics.mean(absolute_errors) if absolute_errors else None,
            p90_absolute_error_seconds=_percentile(absolute_errors, 0.90),
            window_hit_rate=(sum(1 for r in records if r["window_hit"]) / len(records)) if records else None,
            median_window_width_seconds=statistics.median(widths) if widths else None,
            signed_bias_seconds=statistics.median(signed_errors) if signed_errors else None,
        ))

    summaries.sort(key=lambda result: (
        float("inf") if result.median_absolute_error_seconds is None else result.median_absolute_error_seconds,
        -(result.window_hit_rate or 0),
        float("inf") if result.median_window_width_seconds is None else result.median_window_width_seconds,
    ))
    return summaries


def walk_forward_backtest(country: str, item_name: str, min_train: int = 3):
    extracted = extract_prediction_samples(country, item_name)
    waits = extracted["wait_samples"]
    restock_intervals = extracted["restock_interval_samples"]

    per_model = {}
    per_model.update(_backtest_sample_series(waits, "depletion", min_train))
    per_model.update(_backtest_sample_series(restock_intervals, "restock", min_train))
    summaries = _summarize_models(per_model)

    median_wait = statistics.median([sample["seconds"] for sample in waits]) if waits else None
    median_lifetime = statistics.median(extracted["lifetimes"]) if extracted["lifetimes"] else None
    full_cycle = (median_wait + median_lifetime) if median_wait is not None and median_lifetime is not None else None
    behavior = _behavior_class(median_wait)

    return {
        "country": country,
        "item_name": item_name,
        "behavior_class": behavior,
        "behavior_description": _behavior_description(behavior),
        "median_zero_to_restock_seconds": median_wait,
        "median_stock_lifetime_seconds": median_lifetime,
        "estimated_full_cycle_seconds": full_cycle,
        "valid_wait_samples": len(waits),
        "excluded_wait_samples": len(extracted.get("all_wait_samples", [])) - len(waits),
        "valid_restock_interval_samples": len(restock_intervals),
        "excluded_restock_interval_samples": len(extracted.get("all_restock_interval_samples", [])) - len(restock_intervals),
        "completed_cycles": extracted["completed_cycles"],
        "valid_cycles": extracted["valid_cycles"],
        "provider_bounces_suppressed": len(extracted["provider_bounces"]),
        "models": summaries,
        "records_by_model": per_model,
    }


def list_tracked_items(min_rows: int = 1):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT country, item_name, COUNT(*) AS row_count
            FROM stock_history
            GROUP BY country, item_name
            HAVING COUNT(*) >= ?
            ORDER BY country, item_name
            """,
            (min_rows,),
        ).fetchall()
    return [{"country": c, "item_name": i, "rows": n} for c, i, n in rows]


def _model_is_eligible(model: ModelResult, min_predictions: int):
    return model.predictions >= min_predictions


def choose_item_winner(result, min_predictions: int = 10):
    eligible = [m for m in result["models"] if _model_is_eligible(m, min_predictions)]
    return eligible[0] if eligible else None


def run_model_tournament(min_waits: int = 6, min_predictions: int = 10, min_rows: int = 20):
    items = list_tracked_items(min_rows=min_rows)
    item_results = []

    for entry in items:
        result = walk_forward_backtest(entry["country"], entry["item_name"])
        if result["valid_wait_samples"] < min_waits and result["valid_restock_interval_samples"] < min_waits:
            continue

        winner = choose_item_winner(result, min_predictions=min_predictions)
        item_results.append({
            "country": result["country"],
            "item_name": result["item_name"],
            "behavior_class": result["behavior_class"],
            "valid_waits": result["valid_wait_samples"],
            "valid_restock_intervals": result["valid_restock_interval_samples"],
            "winner": winner,
            "all_models": result["models"],
        })

    class_summary = {}
    anchor_summary = {"depletion": 0, "restock": 0}
    for item in item_results:
        behavior = item["behavior_class"]
        bucket = class_summary.setdefault(behavior, {
            "items": 0,
            "eligible_items": 0,
            "model_wins": {},
            "anchor_wins": {"depletion": 0, "restock": 0},
        })
        bucket["items"] += 1
        winner = item["winner"]
        if winner is None:
            continue
        bucket["eligible_items"] += 1
        bucket["model_wins"][winner.name] = bucket["model_wins"].get(winner.name, 0) + 1
        bucket["anchor_wins"][winner.anchor_family] += 1
        anchor_summary[winner.anchor_family] += 1

    return {
        "items": item_results,
        "class_summary": class_summary,
        "anchor_summary": anchor_summary,
        "min_waits": min_waits,
        "min_predictions": min_predictions,
    }
