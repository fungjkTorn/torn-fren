"""Monkey's time-of-day depletion with a correction from four completed batches."""
from functools import lru_cache
from statistics import median

from deploy.scripts.v163_readonly_event_first_preview import _window, predict_events

KEY = "arg:Monkey Plushie"
POLICY = "MONKEY_HOUR_LAST4_MINUTE_V1"


def forecast(item, phases, *, asof, horizon, min_qty):
    base = predict_events(item, phases, asof=asof, horizon=horizon, min_qty=min_qty)
    raw = base["restock_events"]
    if len(raw) < 2:
        return dict(base, monkey_model_policy=POLICY)
    completed = phases["observed_bounded_stocked_windows"]

    @lru_cache(maxsize=None)
    def hourly(count, quarter, fallback):
        older = completed[max(0, count-512):count]
        if len(older) < 24:
            return fallback
        center = quarter * 900 + 450
        lengths = []
        for start, end in older:
            distance = abs(start % 86400 - center)
            if min(distance, 86400-distance) <= 7200:
                lengths.append(end-start)
        if len(lengths) < 12:
            return fallback
        weight = len(lengths)/(len(lengths)+12)
        return max(1, round(weight*median(lengths)+(1-weight)*fallback))

    residuals = []
    for i in range(max(24, len(completed)-4), len(completed)):
        start, end = completed[i]
        older = completed[max(0, i-512):i]
        fallback = round(median(b-a for a,b in older))
        residuals.append(end-start-hourly(i, (start % 86400)//900, fallback))
    correction = .5*median(residuals) if len(residuals) == 4 else 0
    opening = raw[0]["predicted_restock_epoch"]
    expected_stock = raw[0]["estimated_stocked_duration_seconds"]
    empty = raw[1]["predicted_restock_epoch"]-opening-expected_stock
    events = []
    for event in raw:
        duration = max(1, round(hourly(len(completed), (opening % 86400)//900, expected_stock)+correction))
        previous = event["predicted_restock_epoch"]
        window = _window(item, asof, opening, duration,
                         opening+event["restock_early_epoch"]-previous,
                         opening+event["restock_late_epoch"]-previous, duration)
        events.append(dict(event, **(window | {"restock_relative_to_now_seconds": opening-asof})))
        opening += duration+empty
    supported = sum(event["expected_departure_epoch"] is not None for event in events)
    return dict(base, restock_events=events, currently_supported_departures=supported,
                unreachable_restock_events=len(events)-supported, monkey_model_policy=POLICY)
