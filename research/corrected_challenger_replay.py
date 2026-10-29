"""Resumable single-config replay; use --pilot before a seven-day run.

300s is an issuance sampling cadence, NEVER a departure eligibility filter.
Every issued future departure is scored. First issue per observed ordinal
opportunity is frozen; later forecasts cannot replace its result.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from research.causal_replay_slice import CausalReplaySlice
from research.corrected_challengers import MODELS, POLICY, forecast
from services.first_release_evidence import grade, TargetIndex


def readonly(path):
    con = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    return con


def country_state(con, country, epoch):
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone()
    if not exists:
        return 'UNVERIFIED'
    r = con.execute('''SELECT received_epoch,country_update_epoch,clock_status
        FROM country_stock_observations WHERE country=? AND received_epoch<=?
        ORDER BY received_epoch DESC,id DESC LIMIT 1''', (country,epoch)).fetchone()
    if not r:
        return 'UNVERIFIED'
    return 'FRESH' if r[2]=='REPORTED' and r[1] is not None and 0<=epoch-r[0]<=180 and 0<=epoch-r[1]<=180 else 'STALE'


def run(source, output, *, days=7, step=300, pilot=False, timeout=30, items=None, max_seconds=1800):
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if output == source or output in source.parents:
        raise ValueError('output must be a separate directory')
    output.mkdir(parents=True, exist_ok=True)
    def sha(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    digest = sha(source)
    root=Path(__file__).resolve().parents[1]
    code_paths=[__file__,root/'research/corrected_challengers.py',root/'research/causal_replay_slice.py',
        root/'services/first_release_schedule.py',root/'services/first_release_evidence.py',
        root/'services/travel_decision_contract_v166.py',root/'services/history_service.py',
        root/'services/plushie_flower_dynamic_planner_v19.py',root/'services/plushie_flower_dynamic_planner_v20.py',
        root/'deploy/scripts/v163_readonly_event_first_preview.py',root/'research/v145_provider_continuous_phases.py']
    fingerprints={str(Path(p).relative_to(root)):sha(p) for p in code_paths}
    started=time.monotonic()
    with closing(readonly(source)) as truth:
        truth.execute('BEGIN')
        polls = [r[0] for r in truth.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 ORDER BY timestamp")]
        if not polls:
            raise ValueError('no successful poll evidence')
        end = polls[-1]//step*step
        start = end-days*86400
        if polls[0] > start-7*86400:
            raise ValueError('need seven days of pre-test warmup plus the complete replay week; refresh snapshot')
        gaps = truth.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps').fetchall()
        identities = {'source_sha256':digest, 'code_sha256':fingerprints, 'policy':POLICY, 'start':start,
            'end':end, 'step':step, 'pilot':pilot, 'models':dict(MODELS),
            'score_rule':'stock >30 at exact calculated arrival; zero grace',
            'training_policy':'ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK',
            'issuance_cadence_is_not_departure_filter':True,
            'production_modified':False}
        manifest = output/'manifest.json'
        if manifest.exists() and json.loads(manifest.read_text()) != json.loads(json.dumps(identities)):
            raise ValueError('output belongs to a different source or replay contract')
        manifest.write_text(json.dumps(identities, indent=2)+'\n')
        for key in items or MODELS:
            if key not in MODELS:
                raise ValueError('unknown challenger')
            country, item = key.split(':',1)
            rows = truth.execute('''SELECT timestamp,quantity,source FROM stock_history
                WHERE country=? AND lower(item_name)=lower(?) ORDER BY timestamp,id''',(country,item)).fetchall()
            if not rows or rows[0][0] > start-7*86400:
                raise ValueError('missing training history for '+key)
            index = TargetIndex(rows,gaps)
            path = output/(key.replace(':','__').replace(' ','_')+'.jsonl')
            records = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
            done = {r['issued'] for r in records}
            clocks = [start] if pilot else range(start,end+1,step)
            with tempfile.TemporaryDirectory() as td, CausalReplaySlice(source,Path(td)/'causal.sqlite') as mirror:
                for issued in clocks:
                    if issued in done:
                        continue
                    if time.monotonic()-started>=max_seconds:
                        print(json.dumps({'status':'PAUSED_AT_RUNTIME_BUDGET','resume':'rerun the identical command','item':key}),flush=True)
                        return
                    db = mirror.advance(issued)
                    began = time.monotonic()
                    r = {'item':key, 'issued':issued, 'country_freshness':country_state(truth,country,issued)}
                    if r['country_freshness']=='STALE':
                        r.update(status='STALE_COUNTRY_DATA', outcome={'status':'NO_RECOMMENDATION'})
                    else:
                        try:
                            child = subprocess.run([sys.executable,'-m',__name__ if __name__!='__main__' else 'research.corrected_challenger_replay',
                                '--worker',str(db),'--item',key,'--issued',str(issued)],
                                capture_output=True,text=True,timeout=timeout,check=True)
                            row = json.loads(child.stdout)
                            d = row.get('decision') or {}
                            r.update(status=d.get('status',row.get('status')), row=row)
                            arrival = d.get('estimated_arrival_epoch')
                            r['outcome'] = grade(arrival,rows,polls,gaps,cutoff=end) if type(arrival) is int else {'status':'NO_RECOMMENDATION'}
                            if type(arrival) is int and r['outcome']['status'] in ('SUCCESS','FAILURE'):
                                if country_state(truth,country,arrival)!='FRESH':
                                    r['outcome']={'status':'UNKNOWN','reason':'COUNTRY_FRESHNESS_UNVERIFIED_AT_ARRIVAL'}
                            target = index.target(row)
                            r['observed_target'] = target
                            if target and type(arrival) is int:
                                r['arrival_minus_opening_minutes']=(arrival-target['epoch'])/60
                                selected = next((e for e in d.get('forecast_events',[]) if e['index']==d.get('selected_restock_event_index')),None)
                                if selected:
                                    r['predicted_minus_observed_opening_minutes']=(selected['predicted_restock_epoch']-target['epoch'])/60
                            # Preserve issued selected windows, not 64 duplicated
                            # future windows at every issue throughout the week.
                            selected_index=d.get('selected_restock_event_index')
                            if 'forecast_events' in d:
                                d['forecast_events']=[e for e in d['forecast_events'] if e['index']==selected_index]
                            for name in ('restock_events','true_restock_events'):
                                if name in row.get('forecast',{}):
                                    row['forecast'][name]=[e for e in row['forecast'][name] if e.get('event_index')==selected_index]
                        except (subprocess.TimeoutExpired,subprocess.CalledProcessError,ValueError) as exc:
                            r.update(status='MODEL_ERROR',error_type=type(exc).__name__,
                                detail=str(getattr(exc,'stderr','') or str(exc))[-1500:],outcome={'status':'ERROR'})
                    r['seconds']=round(time.monotonic()-began,3)
                    with path.open('a') as f:
                        f.write(json.dumps(r,sort_keys=True)+'\n');f.flush()
                    records.append(r)
                    print(json.dumps({'item':key,'issued':issued,'seconds':r['seconds'],'status':r['status']}),flush=True)
            groups = {}; unmatched = Counter()
            for r in sorted(records,key=lambda r:r['issued']):
                if r.get('observed_target') and (r.get('row',{}).get('decision') or {}).get('estimated_departure_epoch') is not None:
                    groups.setdefault(r['observed_target']['epoch'],r)
                else:
                    unmatched[r['outcome']['status']]+=1
            counts=Counter(r['outcome']['status'] for r in groups.values())
            known=counts['SUCCESS']+counts['FAILURE']
            unsafe=unmatched['FAILURE']+unmatched['UNKNOWN']+unmatched['ERROR']
            report={'item':key,'model':MODELS[key],'pilot':pilot,'issue_rows':len(records),
                'seconds':sum(r['seconds'] for r in records),'distinct_opportunity_counts':dict(counts),
                'estimated_full_week_model_seconds':sum(r['seconds'] for r in records)/len(records)*(days*86400//step+1) if records else None,
                'success_fraction':counts['SUCCESS']/known if known and not unsafe else None,
                'unmatched_issue_counts':dict(unmatched),'raw_issue_counts':dict(Counter(r['outcome']['status'] for r in records)),
                'observed_openings_in_test':sum(start<=t<=end for t in index.times),
                'observed_openings_without_matched_forecast':sum(start<=t<=end and t not in groups for t in index.times),
                'first_forecasts_per_opportunity':list(groups.values()),
                'live_accuracy_certified':False,'production_modified':False}
            (output/(path.stem+'.summary.json')).write_text(json.dumps(report,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source');p.add_argument('--output');p.add_argument('--days',type=int,default=7,choices=[7])
    p.add_argument('--step',type=int,default=300,choices=[300,900,1800,3600])
    p.add_argument('--pilot',action='store_true');p.add_argument('--item',choices=tuple(MODELS))
    p.add_argument('--max-seconds',type=int,default=1800)
    p.add_argument('--worker');p.add_argument('--issued',type=int)
    a=p.parse_args()
    if a.worker:
        print(json.dumps(forecast(a.worker,a.item,a.issued)));return
    if not a.source or not a.output:
        p.error('--source and --output are required')
    if a.max_seconds<=0:p.error('--max-seconds must be positive')
    run(a.source,a.output,days=a.days,step=a.step,pilot=a.pilot,items=[a.item] if a.item else None,max_seconds=a.max_seconds)


if __name__=='__main__':main()
