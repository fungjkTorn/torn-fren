"""Compare actual frozen outcomes and exact observed opportunity identities."""
from collections import Counter
import argparse,json
from pathlib import Path
from statistics import median
from research.corrected_challengers import NEXT_SIX_MODELS

def identity(trip):
    value=trip.get('resolved_target_epoch')
    if type(value) is int and value>0:return value
    anchor=trip.get('episode_anchor')
    if isinstance(anchor,str):
        epoch=int(anchor.split(':',1)[1]);return epoch if epoch>0 else None
    return None

def advice_behavior(directory,key):
    path=Path(directory)/'archive'/(key.replace(':','__').replace(' ','_')+'.jsonl')
    waits=[];c=Counter()
    for line in path.read_text().splitlines():
        r=json.loads(line);row=r.get('row') or {};d=row.get('decision') or {};dep=d.get('estimated_departure_epoch')
        if type(dep) is not int:continue
        waits.append((dep-r['issued'])/60);c['leave_now_clocks']+=dep==r['issued']
        c['current_stock_advice_clocks']+=d.get('selected_restock_event_index')==0
        placement=d.get('arrival_placement')
        if placement:
            c['future_placement_clocks']+=1;c['uncertainty_core_overlaps']+=placement['core_overlaps']
            c['arrival_actually_adjusted']+=d['estimated_arrival_epoch']!=placement['native_arrival_epoch']
        rates=(row.get('forecast') or {}).get('net_stock_rates')
        if rates:c['recent_rate_exceeded_historical_upper']+=rates.get('arrival_loss_rate_upper',0)>max(0,rates['upper'])
    return {'median_wait_minutes':median(waits) if waits else None,'counts':dict(c)}

def compare(baseline,directories,output):
    baseline=Path(baseline);b=json.loads((baseline/'scored/results.json').read_text());bt=json.loads((baseline/'scored/trips.json').read_text())
    out={'source_sha256':b['source_sha256'],'start_epoch':b['start_epoch'],'cutoff_epoch':b['cutoff_epoch'],
        'baseline':b['items'],'baseline_advice_behavior':{k:advice_behavior(baseline,k) for k in NEXT_SIX_MODELS},'variants':{},'actual_test_data_only':True,'baseline_modified':False,
        'limitation':'Retrospective already-inspected week; five-minute historical issuance; forward confirmation required.'}
    for directory in map(Path,directories):
        r=json.loads((directory/'scored/results.json').read_text());trips=json.loads((directory/'scored/trips.json').read_text())
        for k in ('source_sha256','start_epoch','cutoff_epoch'):assert r[k]==b[k],k
        manifest=json.loads((directory/'archive/manifest.json').read_text());variant=manifest['cleanup_variant'];item_results={}
        for key in NEXT_SIX_MODELS:
            old=b['items'][key];new=r['items'][key];left=[t for t in bt if t['item_key']==key];right=[t for t in trips if t['item_key']==key]
            def index(rows):
                d={}
                for t in rows:
                    target=identity(t)
                    if target is None:continue
                    if target in d:raise ValueError('duplicate observed opportunity: '+key)
                    d[target]=t
                return d
            x,y=index(left),index(right);common=x.keys()&y.keys();paired=Counter()
            for target in common:
                a=x[target]['outcome']['status'];c=y[target]['outcome']['status'];paired['shared_observed_opportunities']+=1
                if a not in ('SUCCESS','FAILURE') or c not in ('SUCCESS','FAILURE'):
                    paired['shared_but_not_both_known']+=1;continue
                paired['both_known']+=1
                if a=='SUCCESS' and c=='SUCCESS':paired['both_success']+=1
                elif a=='FAILURE' and c=='FAILURE':paired['both_failure']+=1
                elif c=='SUCCESS':paired['candidate_only_success']+=1
                else:paired['baseline_only_success']+=1
            paired['baseline_only_observed_opportunities']=len(x.keys()-y.keys());paired['candidate_only_observed_opportunities']=len(y.keys()-x.keys())
            statuses=Counter(t['outcome']['status'] for t in right)
            assert statuses['SUCCESS']==new['successes'] and statuses['FAILURE']==new['failures']
            shifts=[(y[t]['departure_epoch']-x[t]['departure_epoch'])/60 for t in common]
            item_results[key]={'advice_behavior':advice_behavior(directory,key),'paired_median_departure_shift_minutes':median(shifts) if shifts else None,
                'metrics':new,'paired_observed_opportunities':dict(paired),
                'known_success_rate_delta_pp':100*(new['known_success_fraction']-old['known_success_fraction']) if new['known'] and old['known'] else None,
                'advice_clock_change':new['advice_issue_clocks']-old['advice_issue_clocks'],'frozen_trip_change':new['simulated_trips']-old['simulated_trips'],
                'lower_rate':new['known_success_fraction']<old['known_success_fraction'] if new['known'] and old['known'] else None}
        out['variants'][variant]={'items':item_results,'research_identity':r['research_identity'],
            'idempotency_verified':r['idempotency_verified'],'original_inputs_unchanged':r['original_inputs_unchanged']}
    Path(output).write_text(json.dumps(out,indent=2)+'\n');return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);p.add_argument('--variants',nargs='+',required=True);p.add_argument('--output',required=True);a=p.parse_args();compare(a.baseline,a.variants,a.output)
