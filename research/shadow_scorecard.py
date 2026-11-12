"""Read-only, same-issue scorecards for full-roster frozen shadow predictions."""
import argparse
import json
import re
import sqlite3
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

OUTCOMES={'SUCCESS','FAILURE','UNKNOWN','PENDING','ABSTAIN'}


def summarize(rows,expected_issues):
    c=Counter(r['outcome'] for r in rows)
    known=c['SUCCESS']+c['FAILURE'];proposed=sum(r['departure'] is not None for r in rows)
    waits=[r['departure']-r['issued'] for r in rows if r['departure'] is not None]
    return dict(issues=expected_issues,observed_issues=len(rows),missing_issues=expected_issues-len(rows),proposals=proposed,successes=c['SUCCESS'],failures=c['FAILURE'],
        known=known,unknown=c['UNKNOWN'],pending=c['PENDING'],abstentions=c['ABSTAIN'],
        known_success_fraction=c['SUCCESS']/known if known else None,
        proposal_coverage=proposed/expected_issues if expected_issues else None,
        mean_wait_minutes=sum(waits)/len(waits)/60 if waits else None,
        immediate=summarize_subset(rows,'immediate'),future=summarize_subset(rows,'future'),
        status_counts=dict(Counter(r.get('status','UNSPECIFIED') for r in rows)),
        outcome_reasons=dict(Counter(r['reason'] for r in rows)))


def summarize_subset(rows,kind):
    values=[r for r in rows if r['kind']==kind];c=Counter(r['outcome'] for r in values)
    n=c['SUCCESS']+c['FAILURE']
    return dict(proposals=len(values),successes=c['SUCCESS'],failures=c['FAILURE'],
        known=n,unknown=c['UNKNOWN'],pending=c['PENDING'],
        known_success_fraction=c['SUCCESS']/n if n else None)


def paired(left,right):
    common=sorted(set(left)&set(right));win=loss=tie=unresolved=0
    for t in common:
        a=left[t]['outcome'];b=right[t]['outcome']
        if a not in ('SUCCESS','FAILURE') or b not in ('SUCCESS','FAILURE'):unresolved+=1
        elif a==b:tie+=1
        elif b=='SUCCESS':win+=1
        else:loss+=1
    return dict(same_issued_samples=len(common),both_known=win+loss+tie,
        challenger_wins=win,challenger_losses=loss,ties=tie,unresolved=unresolved,
        baseline_only_samples=len(set(left)-set(right)),challenger_only_samples=len(set(right)-set(left)))


def build(records,score):
    identities=set();first={}
    for r in records:
        identity=(r['issued'],r['item_key'],r['mode'])
        if identity in identities:raise ValueError('Duplicate issued item/model')
        identities.add(identity)
        if type(r['issued']) is not int or type(r['published']) is not int or r['published']<r['issued']:raise ValueError('Invalid publication clock')
        if r['departure'] is not None:
            if type(r['departure']) is not int or not r['published']<=r['departure']<=r['issued']+28800:raise ValueError('Invalid departure clock')
            if r['arrival']!=r['departure']+r['flight_seconds']:raise ValueError('Mixed arrival/flight identity')
        bucket=(r['item_key'],r['issued']//3600)
        first[bucket]=min(first.get(bucket,r['issued']),r['issued'])
    groups=defaultdict(list);indexed=defaultdict(dict)
    for r in sorted(records,key=lambda r:(r['issued'],r['item_key'],r['mode'])):
        if r['issued']!=first[(r['item_key'],r['issued']//3600)]:continue
        if r['departure'] is None:outcome,reason='ABSTAIN',r.get('status','NO_PLAN')
        else:outcome,reason,_=score(r['item_key'],r['arrival'])
        if outcome not in OUTCOMES:raise ValueError('Unsupported outcome')
        kind='abstain' if r['departure'] is None else ('immediate' if r['departure']==r['published'] else 'future')
        value=dict(r,outcome=outcome,reason=reason,kind=kind)
        groups[(r['item_key'],r['mode'])].append(value);indexed[(r['item_key'],r['mode'])][r['issued']]=value
    items={}
    for key in sorted({k for k,_ in groups}):
        modes=sorted({r['mode'] for r in records if r['item_key']==key})
        expected_issues=sum(k==key for k,hour in first)
        items[key]=dict(models={m:summarize(groups[(key,m)],expected_issues) for m in modes},
            paired_vs_controls={base:{m:paired(indexed[(key,base)],indexed[(key,m)]) for m in modes if m!=base}
                for base in ('leave_now_control','rate_current_quarter') if base in modes})
    return dict(records=len(records),items=items,item_count=len(items),
        sample='First issue per item/UTC hour; every model uses that same issue',
        calibrated_probability=False,actual_flights=False,automatic_promotion=False,
        future_departure_reconfirmation=False,
        limitation='Frozen shadow arrivals only. Correlated hourly samples; pending/unknown/abstentions are not failures or successes. No restock/depletion timing accuracy inferred.')


def report(source,journal,*,expected_model_sha):
    if not re.fullmatch('[0-9a-f]{40}',expected_model_sha):raise ValueError('Exact recorded model SHA required')
    source=Path(source).resolve(strict=True);journal=Path(journal).resolve(strict=True)
    if source.samefile(journal):raise ValueError('Separate source and shadow journal required')
    with closing(sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        sha=db.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()
        if sha!=(expected_model_sha,):raise ValueError('Journal model differs from expected pin')
        rows=db.execute('SELECT issued,item_key,mode,record FROM plans ORDER BY issued,item_key,mode LIMIT 100001').fetchall()
    if len(rows)>100000:raise ValueError('Journal record cap exceeded')
    records=[]
    for issued,key,mode,raw in rows:
        r=json.loads(raw)
        if (r['issued'],r['item_key'],r['mode'],r['model_sha'])!=(issued,key,mode,expected_model_sha):raise ValueError('Journal record identity mismatch')
        records.append(r)
    from research.japan_xanax.renewal_shadow import source_data
    cache={}
    def score(key,arrival):
        if key not in cache:cache[key]=source_data(source,item_key=key)[3]
        return cache[key].score(arrival)
    return dict(build(records,score),model_sha=expected_model_sha,
        truth_cutoffs={k:v.cutoff for k,v in cache.items()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--journal',required=True)
    p.add_argument('--expected-model-sha',required=True)
    a=p.parse_args();print(json.dumps(report(a.source,a.journal,expected_model_sha=a.expected_model_sha),indent=2,sort_keys=True))


if __name__=='__main__':main()
