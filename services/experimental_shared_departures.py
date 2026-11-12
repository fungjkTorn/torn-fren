"""Translate the shared board into the existing experimental page's row shape."""
import math


def rows_for_experimental(board,*,now):
    if not isinstance(board,dict) or not isinstance(board.get('rows'),list):
        raise ValueError('invalid shared board')
    issued=board['asof_epoch'];age=board['source_poll_age_seconds']
    source_end=board['evaluated_at_epoch']+180-age if type(age) is int else now-1
    rows=[]
    for row in board['rows']:
        d=row['decision'];departure=row['departure_epoch'];deadline=row['departure_deadline_epoch']
        until=min(issued+660,source_end,d.get('valid_until_epoch',issued+660),
            deadline if deadline is not None else issued+660)
        available=departure is not None and now<=until
        wait=departure-now if available else None
        label=('Reconfirm before leaving' if wait is not None and wait<=0 else
               f'Leave in {math.ceil(wait/60)}m' if wait is not None else 'Await a fresh recommendation')
        rows.append({'item_key':row['item_key'],
            'model_config':row['policy']+' / '+d.get('execution_policy','event_adapter'),
            'status':d['status'],'status_label':label,
            'departure':departure if available else None,
            'arrival':row['arrival_epoch'] if available else None,
            'valid_until':until,'actionable':available,'shared_departure_preview':True,
            'flight_seconds':d['player_flight_seconds'],
            'publication_tolerance_seconds':d.get('publication_tolerance_seconds',0),
            'departure_deadline_epoch':deadline,'model_departure_epoch':d.get('model_departure_epoch'),
            'evidence':row['evidence'],'prediction_accuracy_verified':False,
            'restock_model_name':row['event_model_name']})
    return rows


def unavailable_rows(legacy):
    return [{'item_key':r['item_key'],'model_config':None,'status':'SHARED_FEED_UNAVAILABLE',
        'status_label':'Await a fresh recommendation','departure':None,'arrival':None,
        'valid_until':None,'actionable':False,'shared_departure_preview':True}
        for r in legacy if isinstance(r,dict) and isinstance(r.get('item_key'),str)]
