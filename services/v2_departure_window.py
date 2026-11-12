"""Shared geometry for an estimated V2 stocked interval; no model fitting."""
import math


def departure_window(prediction):
    if not isinstance(prediction,dict):return None
    def number(name):
        value=prediction.get(name)
        return float(value) if type(value) in (int,float) and math.isfinite(value) and value>0 else None
    flight=number('travel_seconds')
    estimate=number('estimate_timestamp')
    arrival=number('recommended_arrival_timestamp')
    late=number('window_end_timestamp')
    depletion=number('target_depletion_timestamp')
    lifetime=number('expected_stock_lifetime_seconds')
    if flight is None or depletion is None or not (estimate or arrival or late):return None
    earliest=max(arrival or estimate or 0,late or estimate or 0)
    buffer=max(60,min(300,round(lifetime*.10))) if lifetime else 60
    latest=depletion-buffer
    if latest<=earliest:return None
    return dict(earliest_arrival_epoch=earliest,latest_arrival_epoch=latest,
        earliest_departure_epoch=earliest-flight,latest_departure_epoch=latest-flight)
