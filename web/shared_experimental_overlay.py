"""Owner-side additive hook; installing this module enables no routes or flags."""
import os
from services.experimental_shared_departures import rows_for_experimental,unavailable_rows
from services.travel_read_model import build_board
from web.travel_decisions_router import cache


def overlay_response(response,*,now,key=None):
    if os.environ.get('TORN_FREN_SHARED_EXPERIMENTAL_PREVIEW')!='1':
        return response
    location=os.environ.get('TORN_FREN_TRAVEL_EVENT_SNAPSHOT')
    rows=None
    if location:
        try:rows=rows_for_experimental(build_board(cache.read(location),now=now),now=now)
        except (OSError,ValueError,TypeError,KeyError):pass
    if rows is None:
        legacy=response.get('latest',[])
        rows=unavailable_rows(legacy if isinstance(legacy,list) else [])
    if key is not None:
        rows=[row for row in rows if row['item_key']==key]
    return dict(response,latest=rows,source='PRECOMPUTED_SHARED_DEPARTURE_PREVIEW',
        prediction_accuracy_verified=False,shared_departure_overlay=True)
