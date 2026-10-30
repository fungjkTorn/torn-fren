"""Correctness checks using the supplied real collector data only."""
from pathlib import Path
import argparse,json,tempfile,time
from research.causal_replay_slice import CausalReplaySlice
from research.prelive_cleanup import forecast
from research.corrected_challengers import NEXT_SIX_MODELS
from services.first_release_schedule import build_first_release_decision


def run(source,output):
    records=[]
    for variant in ['clean-full','clean-recent7']:
        with tempfile.TemporaryDirectory() as td,CausalReplaySlice(source,Path(td)/'actual-history.sqlite') as mirror:
            for issued in [1792720800,1793023200,1793325600]:
                db=mirror.advance(issued)
                for key in NEXT_SIX_MODELS:
                    start=time.monotonic();row=forecast(db,key,issued,variant);d=row['decision'];f=row['forecast']
                    assert row['timing_full_history_override']
                    assert (d['timing_model_generation'],d['timing_model_config'])==NEXT_SIX_MODELS[key]
                    if type(d.get('estimated_departure_epoch')) is int:
                        assert d['estimated_arrival_epoch']==d['estimated_departure_epoch']+d['player_flight_seconds']
                        assert d['arrival_grace_seconds']==0 and d['target_quantity']==31
                        reachable=[e['index'] for e in d['forecast_events'] if e['flight_reachable']]
                        if d['selected_restock_event_index']!=0:assert d['selected_restock_event_index']==reachable[0]
                    rates=f.get('net_stock_rates');assert not rates or rates['last_label_epoch']<=issued-180
                    health=row.get('source') or {}
                    # Advance evaluation of this actual saved snapshot; no new
                    # observations are fabricated or passed into the forecast.
                    aged=build_first_release_decision(f,now=issued+301,flight_seconds=d['player_flight_seconds'],
                        poll_age_seconds=301,model_roster=NEXT_SIX_MODELS,current_stock_leave_now=True)
                    assert aged['estimated_departure_epoch'] is None
                    support=f.get('current_stock_arrival_support')
                    if key=='uni:Xanax' and support and support['lower_quantity_estimate']>=31:
                        assert d['selected_restock_event_index']==0 and d['estimated_departure_epoch']==issued
                        assert support['depletion_epoch'] is None and not support['restock_onset_inferred']
                        assert rates['flat_blocks']>0 and rates['rising_blocks']>0
                        replay=build_first_release_decision(f,now=issued+15,flight_seconds=d['player_flight_seconds'],
                            poll_age_seconds=30,model_roster=NEXT_SIX_MODELS,current_stock_leave_now=True)
                        if replay['estimated_departure_epoch'] is not None:assert replay['estimated_arrival_epoch']==replay['estimated_departure_epoch']+d['player_flight_seconds']
                    records.append({'variant':variant,'item':key,'issued':issued,'status':d['status'],
                        'selected_event':d['selected_restock_event_index'],'rate_samples':rates['samples'] if rates else 0,
                        'seconds':round(time.monotonic()-start,3),'checks_passed':True})
    Path(output).write_text(json.dumps({'source':str(Path(source).name),'actual_data_only':True,'checks':records},indent=2)+'\n')
    print(json.dumps({'status':'REAL_DATA_PILOTS_PASSED','cases':len(records)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.source,a.output)
