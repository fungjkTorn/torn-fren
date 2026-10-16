"""Project an explicit precomputed departure without inventing stock events."""
import re


def project_recommendation(record, *, item_key, issued, model_sha, now,
                           poll_age_seconds, player_flight_seconds):
    if not isinstance(record,dict):
        raise ValueError('invalid departure recommendation')
    if (record.get('item_key')!=item_key or record.get('asof_epoch')!=issued
        or record.get('model_sha')!=model_sha
        or not isinstance(model_sha,str) or not re.fullmatch('[0-9a-f]{40}',model_sha)):
        raise ValueError('mixed departure identity, issue or source')
    flight=record.get('player_flight_seconds')
    if type(flight) is not int or not 60<=flight<=86400:
        raise ValueError('invalid recommendation flight')
    if (record.get('target_quantity')!=30 or record.get('depletion_stock_quantity')!=0
        or record.get('event_timing_prediction_supported') is not False
        or not isinstance(record.get('policy'),str) or not record['policy']
        or not isinstance(record.get('model_name'),str) or not record['model_name']):
        raise ValueError('invalid departure model contract')
    departure=record.get('departure_epoch')
    if departure is not None and (type(departure) is not int or not issued<=departure<=issued+28800):
        raise ValueError('invalid recommended departure')
    if type(now) is not int or type(issued) is not int or issued>now:
        raise ValueError('invalid departure clock')
    status='MODEL_ABSTAIN';reason=record.get('status','NO_SUPPORTED_DEPARTURE')
    if (poll_age_seconds is None or not 0<=poll_age_seconds<=180 or now-issued>=300):
        status='STALE_DATA';reason='RECOMMENDATION_RECHECK_REQUIRED'
    elif player_flight_seconds!=flight:
        reason='FLIGHT_SPECIFIC_RECOMPUTATION_REQUIRED'
    elif departure is not None and departure<now:
        status='DEPARTURE_PASSED';reason='POINT_DEPARTURE_PASSED_RECHECK'
    elif departure is not None:
        status='ESTIMATED_DEPARTURE_WINDOW_OPEN' if departure==now else 'WAIT_FOR_ESTIMATED_DEPARTURE'
        reason='POINT_DEPARTURE_RECONFIRM_REQUIRED'
    active=status in ('ESTIMATED_DEPARTURE_WINDOW_OPEN','WAIT_FOR_ESTIMATED_DEPARTURE')
    chosen=departure if active else None
    return {'item_key':item_key,'asof_epoch':issued,'evaluated_at_epoch':now,
        'status':status,'reason':reason,'player_flight_seconds':player_flight_seconds,
        'target_quantity':30,'depletion_stock_quantity':0,
        'restock_timer_anchor':'physical_zero','arrival_grace_seconds':10,
        'estimated_departure_epoch':chosen,
        # A point forecast supplies no safe interval for shifting departure.
        'estimated_departure_deadline_epoch':chosen,
        'estimated_arrival_epoch':chosen+flight+10 if chosen is not None else None,
        'departure_countdown_seconds':chosen-now if chosen is not None else None,
        'selected_restock_event_index':None,'forecast_events':[],
        'prediction_calibrated':False,'verified_arrival_stock_success_probability':None,
        'departure_recommendation_is_estimate':True,'no_automated_gameplay':True,
        'departure_model_name':record['model_name'],'departure_policy':record['policy'],
        'event_timing_prediction_supported':False,
        'valid_until_epoch':min(issued+299,now+180-poll_age_seconds)
            if type(poll_age_seconds) is int and 0<=poll_age_seconds<=180 else issued-1}
