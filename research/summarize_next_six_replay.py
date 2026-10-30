"""Describe every frozen miss and daily outcomes without changing saved forecasts."""
from collections import Counter,defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

TZ=ZoneInfo('America/New_York')


def stamp(epoch):return datetime.fromtimestamp(epoch,TZ).isoformat() if epoch is not None else ''


def analyze(directory):
    directory=Path(directory)
    result=json.loads((directory/'scored/results.json').read_text())
    trips=json.loads((directory/'scored/trips.json').read_text())
    from research.rescore_saved_challengers import load_archive
    from research.corrected_challengers import NEXT_SIX_MODELS
    manifest,records,_=load_archive(directory/'archive')
    audit={'issue_clocks':0,'advice_clocks':0,'current_stock_leave_now_clocks':0,
        'future_advice_clocks':0,'model_errors':0,'geometry_mismatches':0,
        'training_override_missing':0,'wrong_model_identity':0,'wrong_threshold_or_grace':0}
    for key,rows in records.items():
        for record in rows:
            audit['issue_clocks']+=1
            if record['status']=='MODEL_ERROR':audit['model_errors']+=1
            row=record.get('row')
            if row is None:continue
            d=row.get('decision') or {}
            if not row.get('timing_full_history_override'):audit['training_override_missing']+=1
            if (d.get('timing_model_generation'),d.get('timing_model_config'))!=NEXT_SIX_MODELS[key]:audit['wrong_model_identity']+=1
            dep=d.get('estimated_departure_epoch')
            if type(dep) is not int:continue
            audit['advice_clocks']+=1
            if d.get('arrival_grace_seconds')!=0 or d.get('target_quantity')!=31:audit['wrong_threshold_or_grace']+=1
            if d['estimated_arrival_epoch']!=dep+d['player_flight_seconds'] or dep<record['issued']:audit['geometry_mismatches']+=1
            if d['selected_restock_event_index']==0:
                if dep!=record['issued']:audit['geometry_mismatches']+=1
                audit['current_stock_leave_now_clocks']+=1
            else:audit['future_advice_clocks']+=1
    if any(audit[k] for k in ('model_errors','geometry_mismatches','training_override_missing','wrong_model_identity','wrong_threshold_or_grace')):
        raise ValueError('policy audit failed: '+str(audit))
    audit['all_checks_passed']=True
    (directory/'policy-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    analyses={};miss_rows=[]
    for key,item in result['items'].items():
        selected=[t for t in trips if t['item_key']==key]
        failures=[t for t in selected if t['outcome']['status']=='FAILURE']
        if len(failures)!=item['failures']:raise ValueError('missing failure record')
        days=defaultdict(Counter);classes=Counter();near_early=[];near_late=[]
        for t in selected:days[stamp(t['departure_epoch'])[:10]][t['outcome']['status']]+=1
        for t in failures:
            m=t['miss'];classes[m['classification']]+=1
            if m['classification']=='EARLY':near_early.append(m['minutes_before_restock'])
            if m['classification']=='LATE':near_late.append(m['minutes_after_zero'])
            miss_rows.append({'item':key,'trip_id':t['id'],'departure_eastern':stamp(t['departure_epoch']),
                'arrival_eastern':stamp(t['arrival_epoch']),'classification':m['classification'],
                'minutes_after_zero':m.get('minutes_after_zero'),'minutes_before_restock':m.get('minutes_before_restock'),
                'previous_zero_eastern':stamp(m.get('previous_zero_epoch')),'next_normal_restock_eastern':stamp(m.get('next_restock_epoch')),
                'pre_quantity':t['outcome'].get('pre_quantity'),'post_quantity':t['outcome'].get('post_quantity'),
                'selected_event_index':t['selected_event_index'],'predicted_window_start_eastern':stamp(t['window_start']),
                'predicted_window_end_eastern':stamp(t['window_end']),'classification_reason':m.get('reason',''),
                'zero_boundary_interval':json.dumps(m.get('zero_boundary_interval')),
                'restock_boundary_interval':json.dumps(m.get('restock_boundary_interval'))})
        if sum(classes.values())!=item['failures']:raise ValueError('failure classifications do not reconcile')
        withheld=Counter((r.get('row',{}).get('forecast') or {}).get('status',r['status']) for r in records[key] if type((r.get('row',{}).get('decision') or {}).get('estimated_departure_epoch')) is not int)
        analyses[key]={'withheld_forecast_reasons':dict(withheld),'daily_frozen_outcomes':{k:dict(v) for k,v in sorted(days.items())},
            'miss_classes':dict(classes),'early_within_2_minutes':sum(x<=2 for x in near_early),
            'early_within_5_minutes':sum(x<=5 for x in near_early),'late_within_2_minutes':sum(x<=2 for x in near_late),
            'late_within_5_minutes':sum(x<=5 for x in near_late),
            'median_early_minutes':median(near_early) if near_early else None,
            'median_late_minutes':median(near_late) if near_late else None}
    (directory/'miss-analysis.json').write_text(json.dumps(analyses,indent=2)+'\n')
    fields=['item','trip_id','departure_eastern','arrival_eastern','classification','minutes_after_zero','minutes_before_restock',
        'previous_zero_eastern','next_normal_restock_eastern','pre_quantity','post_quantity','selected_event_index',
        'predicted_window_start_eastern','predicted_window_end_eastern','classification_reason','zero_boundary_interval','restock_boundary_interval']
    with (directory/'all-misses.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(miss_rows)
    return analyses


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');a=p.parse_args();print(json.dumps(analyze(a.directory),indent=2))
