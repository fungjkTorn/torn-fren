"""Synthetic owner-page fixture; no live data or model fitting."""
import json
import time
from test_travel_read_model import departure_snapshot,T
from services.travel_read_model import build_board
from services.experimental_shared_departures import rows_for_experimental
now=int(time.time());offset=now-10-T

def shifted(value):
    if isinstance(value,dict):return {k:shifted(v) for k,v in value.items()}
    if isinstance(value,list):return [shifted(v) for v in value]
    return value+offset if type(value) is int and T-100000<value<T+100000 else value

source=shifted(departure_snapshot(T))
source['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
print(json.dumps({'test_fixture':True,'latest':rows_for_experimental(build_board(source,now=now),now=now)}))
