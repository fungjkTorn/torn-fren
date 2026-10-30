"""Rescore saved challenger advice with the exact live simulated-trip policy.

No model inference, synthetic refreshes, changed departures or source writes.
The original 300-second grid is the only available publication stream.
"""
import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from research.nearest_stock_boundary_misses import boundary_index,classify,summarize
from services.first_release_evidence import connect,record
from services.simulated_trip_evidence import POLICY,summary,history
from services.restock_signatures import events


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def load_archive(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest.get('pilot') or manifest.get('policy')!='CORRECTED_CHALLENGERS_FIRST_REACHABLE_V1':
        raise ValueError('expected completed corrected challenger week')
    if manifest.get('training_policy')!='ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK':
        raise ValueError('unexpected original training restriction')
    clocks=list(range(manifest['start'],manifest['end']+1,manifest['step']))
    records={};files={'manifest.json':digest(directory/'manifest.json')}
    for key in manifest['models']:
        name=key.replace(':','__').replace(' ','_')+'.jsonl';path=directory/name
        rows=sorted([json.loads(line) for line in path.read_text().splitlines() if line],key=lambda r:r['issued'])
        if [r['issued'] for r in rows]!=clocks:raise ValueError('missing or duplicate clock: '+key)
        for r in rows:
            if r['item']!=key or r.get('status')=='MODEL_ERROR':raise ValueError('invalid saved forecast: '+key)
            if 'row' not in r and r['status']!='STALE_COUNTRY_DATA':raise ValueError('unexplained missing forecast: '+key)
            if 'row' in r and (r['row']['asof_epoch']!=r['issued'] or r['row']['item_key']!=key):
                raise ValueError('saved row identity differs: '+key)
        records[key]=rows;files[name]=digest(path)
    return manifest,records,files


def rescore(source,archive,output):
    source=Path(source).resolve(strict=True);archive=Path(archive).resolve(strict=True);output=Path(output)
    manifest,records,files=load_archive(archive)
    if digest(source)!=manifest['source_sha256']:raise ValueError('stock source differs from original replay')
    if output.exists():raise ValueError('choose a new output directory; prior results are preserved')
    output.mkdir(parents=True)
    identity=hashlib.sha256(json.dumps({'source':manifest['source_sha256'],'models':manifest['models'],
        'training':manifest['training_policy'],'native_code':manifest['code_sha256']},sort_keys=True).encode()).hexdigest()[:40]
    result={'status':'SAVED_CHALLENGERS_RESCORED','evidence_policy':POLICY,'research_identity':identity,
        'start_epoch':manifest['start'],'cutoff_epoch':manifest['end'],'source_sha256':manifest['source_sha256'],
        'saved_forecast_hashes':files,'original_models':manifest['models'],'training_policy':manifest['training_policy'],
        'sampling_seconds':manifest['step'],'publication_clock':'SAMPLED_ISSUE_TIME_NO_MEASURED_SERVER_LATENCY',
        'advice_expiry_preserved':True,'unrecorded_refreshes_assumed':False,'model_inference_run':False,
        'production_modified':False,'arrival_timing_changed':False,'items':{}}
    root=Path(__file__).resolve().parents[1]
    result['scoring_code_sha256']={str(p.relative_to(root)):digest(p) for p in [Path(__file__).resolve(),root/'services/simulated_trip_evidence.py',root/'services/restock_signatures.py',root/'research/nearest_stock_boundary_misses.py']}
    with closing(connect(output/'rescore.sqlite')) as db, closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as stock:
        stock.execute('PRAGMA query_only=ON');stock.execute('BEGIN')
        for key,rows in records.items():
            for r in rows:
                # Explicit stale/no-advice clocks must withdraw an outstanding
                # recommendation, rather than disappear from the chronology.
                row=deepcopy(r.get('row') or {'item_key':key,'asof_epoch':r['issued'],'decision':{},'status':r['status']})
                row['published_epoch']=r['issued']
                record(db,row,model_sha=identity)
        for t in range(manifest['start'],manifest['end']+1,manifest['step']):
            db.execute('INSERT INTO publications VALUES(?,?,?)',(t,t,'RESEARCH_SAMPLED_ISSUE_CLOCK'))
        db.commit()
        all_trips=[]
        for key in records:
            metric=summary(db,stock,item_key=key,model_sha=identity,cutoff=manifest['end'])
            if metric['target_identity_audit']['duplicate_target_groups']:raise ValueError('duplicate target identity: '+key)
            states=json.loads(db.execute('SELECT payload FROM simulation_cursors WHERE item=? AND model_sha=? AND policy=?',(key,identity,POLICY)).fetchone()[0])
            targets={p['id']:p.get('resolved_opening',p.get('restock_anchor')) for p in states['completed']}
            item_rows,gaps=history(stock,key,manifest['end'])
            zeros,_,conflicts=boundary_index(item_rows,gaps)
            qualified=events(item_rows,gaps,metric['restock_profile'])
            # A small sellback is not the next normal restock for early/late
            # classification. Preserve unknowns when a qualified boundary lacks.
            boundaries=(zeros,[(e['epoch'],e['previous_epoch']) for e in qualified],conflicts)
            item_trips=[];misses=[]
            for entry in db.execute('''SELECT t.id,t.payload,o.payload FROM simulated_trips t JOIN simulated_trip_outcomes o
                ON o.item=t.item AND o.model_sha=t.model_sha AND o.policy=t.policy AND o.id=t.id
                WHERE t.item=? AND t.model_sha=? AND t.policy=? AND o.cutoff=? ORDER BY json_extract(t.payload,'$.departure_epoch')''',
                (key,identity,POLICY,manifest['end'])).fetchall():
                trip=json.loads(entry[1]);trip['outcome']=json.loads(entry[2]);trip['item_key']=key
                trip['resolved_target_epoch']=targets[entry[0]]
                original=json.loads(db.execute('SELECT payload FROM issues WHERE item=? AND issued=?',(key,trip['issued_epoch'])).fetchone()[0])
                if (trip['departure_epoch'],trip['arrival_epoch'])!=(original['decision']['estimated_departure_epoch'],original['decision']['estimated_arrival_epoch']):
                    raise ValueError('frozen geometry differs from saved recommendation')
                if trip['outcome']['status']=='FAILURE':
                    trip['miss']=classify(trip['arrival_epoch'],trip['outcome'],item_rows,gaps,index=boundaries);misses.append(trip['miss'])
                item_trips.append(trip)
            counts=Counter(t['outcome']['status'] for t in item_trips);known=counts['SUCCESS']+counts['FAILURE']
            result['items'][key]={'model':manifest['models'][key],'issue_clocks':len(records[key]),
                'advice_issue_clocks':sum(type((r.get('row',{}).get('decision') or {}).get('estimated_departure_epoch')) is int for r in records[key]),
                'simulated_trips':len(item_trips),'successes':counts['SUCCESS'],'failures':counts['FAILURE'],
                'known':known,'unknown':counts['UNKNOWN'],'pending':counts['PENDING'],
                'known_success_fraction':counts['SUCCESS']/known if known else None,
                'target_identity_audit':metric['target_identity_audit'],'restock_profile':metric['restock_profile'],
                'qualified_restocks':metric['observed_restocks_since_start'],'revision_counts':metric['revision_counts'],
                'no_advice_clock_statuses':dict(Counter(r['status'] for r in records[key] if type((r.get('row',{}).get('decision') or {}).get('estimated_departure_epoch')) is not int)),
                'nearest_qualified_boundary_misses':summarize(misses),
                'latest_ten':{k:metric[k] for k in ('known','successes','failures','unknown','pending','success_fraction')},
                'active_recommendation_at_cutoff':metric['active_recommendation']}
            # Idempotency is part of the audit, not a new forecast/retest.
            if summary(db,stock,item_key=key,model_sha=identity,cutoff=manifest['end'])!=metric:raise ValueError('non-idempotent rescore')
            all_trips.extend(item_trips);db.commit()
            print(json.dumps({'item':key,'trips':len(item_trips),'successes':counts['SUCCESS'],'known':known,'misses':summarize(misses)}),flush=True)
        if db.execute('SELECT COUNT(*) FROM issues').fetchone()[0]!=sum(len(r) for r in records.values()):raise ValueError('missing archived clocks')
        result['idempotency_verified']=True;result['saved_geometry_preserved']=True
    # Original files and the sealed source must remain byte-identical.
    if digest(source)!=manifest['source_sha256'] or any(digest(archive/name)!=value for name,value in files.items()):
        raise ValueError('original evidence changed')
    result['original_inputs_unchanged']=True
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'trips.json').write_text(json.dumps(all_trips,indent=2)+'\n')
    fields=('item_key','id','issued_epoch','departure_epoch','arrival_epoch','resolved_target_epoch','status','pre_quantity','post_quantity','classification','minutes_after_zero','minutes_before_restock')
    with (output/'trips.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for trip in all_trips:
            flat={**trip,**trip['outcome'],**trip.get('miss',{})};writer.writerow({k:flat.get(k) for k in fields})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--archive',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();rescore(a.source,a.archive,a.output)
