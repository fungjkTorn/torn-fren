"""Retain first-observed canary plans; score sampled arrivals, never purchases.

Recorder is stdlib-only and independent of the running canary. Scoring reuses
ArrivalEvidence and reads the collector in one read-only transaction. A frozen
future plan is evaluated without pretending a later reconfirmation occurred.
"""
import argparse
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

ROOT=Path(__file__).resolve().parents[1]
MAX_RECORDS=250000
MAX_BYTES=2_000_000


def sha_check(sha):
    if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha):
        raise ValueError('exact canary SHA required')


def open_journal(path,sha):
    sha_check(sha)
    path=Path(path)
    if path.suffix!='.sqlite' or path.is_symlink():raise ValueError('separate .sqlite journal required')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as check:
            row=check.execute("SELECT value FROM audit_metadata WHERE key='canary_sha'").fetchone()
            if row!=(sha,):raise ValueError('journal belongs to another canary')
    db=sqlite3.connect(path,timeout=5)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS audit_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS issues(
        issued INTEGER NOT NULL,item_key TEXT NOT NULL,captured INTEGER NOT NULL,
        record TEXT NOT NULL,PRIMARY KEY(issued,item_key));
    ''')
    db.execute("INSERT OR IGNORE INTO audit_metadata VALUES('canary_sha',?)",(sha,))
    db.commit()
    return db


def capture(db,board,*,received):
    if not isinstance(board,dict):raise ValueError('board object required')
    issued=board.get('asof_epoch');evaluated=board.get('evaluated_at_epoch')
    rows=board.get('rows');age=board.get('source_poll_age_seconds')
    if (type(issued) is not int or type(evaluated) is not int or type(received) is not int
        or not issued<=evaluated<=received or received-issued>=300
        or received-evaluated>10 or type(age) is not int or not 0<=age+received-evaluated<=180
        or not isinstance(rows,list) or len(rows)!=24 or not all(isinstance(r,dict) for r in rows)
        or board.get('item_count')!=24):
        raise ValueError('fresh 24-item board required')
    keys=[r.get('item_key') for r in rows]
    if len(set(keys))!=24 or any(not isinstance(k,str) or ':' not in k for k in keys):
        raise ValueError('invalid roster identities')
    records=[]
    for row in rows:
        d=row['decision'];dep=row['departure_epoch'];arrival=row['arrival_epoch']
        flight=d['player_flight_seconds'];deadline=row['departure_deadline_epoch']
        if (not isinstance(d,dict) or row.get('departure_source')!='explicit_recommendation' or d.get('asof_epoch')!=issued
            or d.get('target_quantity')!=30 or d.get('depletion_stock_quantity')!=0
            or d.get('arrival_grace_seconds')!=10 or type(flight) is not int or not 60<=flight<=86400
            or d.get('execution_policy') not in ('strict_point_v1','publication_delay_30s_v1')):
            raise ValueError('unexpected canary contract')
        if dep is not None and (type(dep) is not int or not issued<=dep<=issued+28800
                               or arrival!=dep+flight or type(deadline) is not int):
            raise ValueError('invalid departure or landing')
        actionable=(dep is not None and received<=deadline
                    and received<=d['valid_until_epoch'] and row['policy']!='disabled')
        frozen=max(dep,received) if actionable else None
        record=dict(item_key=row['item_key'],issued=issued,captured=received,
            policy=row['policy'],model_name=row['model_name'],execution_policy=d['execution_policy'],
            model_departure_epoch=d.get('model_departure_epoch'),published_departure_epoch=dep,
            departure_epoch=frozen,arrival_epoch=frozen+flight if frozen is not None else None,
            flight_seconds=flight,target_quantity=30,arrival_grace_seconds=10,
            status=d['status'],actionable_at_capture=actionable,
            plan_kind=('immediate' if frozen==received else 'future') if actionable else 'abstain',
            capture_latency_seconds=received-issued)
        records.append((issued,row['item_key'],received,json.dumps(record,sort_keys=True)))
    before=db.total_changes
    with db:db.executemany('INSERT OR IGNORE INTO issues VALUES(?,?,?,?)',records)
    return db.total_changes-before


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def fetch(path):
    with build_opener(ProxyHandler({}),NoRedirect()).open('http://127.0.0.1:8770'+path,timeout=5) as r:
        data=r.read(MAX_BYTES+1)
        if r.status!=200 or len(data)>MAX_BYTES:raise ValueError('canary unavailable')
        return json.loads(data)


def record(path,sha,*,duration=28800,interval=2):
    if not 60<=duration<=86400 or not 1<=interval<=10:raise ValueError('invalid recorder bounds')
    os.umask(0o077)
    with closing(open_journal(path,sha)) as db:
        until=time.monotonic()+duration
        while time.monotonic()<until:
            try:
                health=fetch('/health')
                if not isinstance(health,dict) or health.get('source_sha')!=sha or health.get('status')!='PRIVATE_CANARY_READY':
                    raise ValueError('unexpected canary source or health')
                board=fetch('/api/travel-decisions');count=capture(db,board,received=int(time.time()))
                if count:print(json.dumps({'status':'PLANS_RECORDED','issue':board['asof_epoch'],'rows':count}),flush=True)
            except (OSError,ValueError,KeyError,TypeError) as error:
                print(json.dumps({'status':'CAPTURE_UNAVAILABLE','at':int(time.time()),'error':str(error)[:150]}),flush=True)
            time.sleep(interval)


def summarize(records,score):
    def group(selected):
        groups=defaultdict(Counter)
        for r in selected:
            c=groups[r['item_key']];c['issues']+=1
            if not r['actionable_at_capture']:c['abstain']+=1;continue
            c['proposals']+=1;c[r['plan_kind']+'_plans']+=1
            outcome,reason,_=score(r['item_key'],r['arrival_epoch'])
            c[outcome]+=1
            c[r['plan_kind']+'_'+outcome]+=1
            if outcome=='UNKNOWN':c['unknown_'+reason]+=1
        result={}
        for key,c in sorted(groups.items()):
            known=c['SUCCESS']+c['FAILURE']
            result[key]=dict(c,known=known,success_fraction=c['SUCCESS']/known if known else None,
                proposal_fraction=c['proposals']/c['issues'])
        return result
    # Select first observed issue BEFORE filtering actionable/outcome; no cherry-picking.
    first={}
    for r in sorted(records,key=lambda r:(r['issued'],r['captured'],r['item_key'])):
        first.setdefault((r['item_key'],r['issued']//3600),r)
    return {'primary_first_observed_item_utc_hour':group(first.values()),
            'all_observed_publications_diagnostic':group(records),
            'metric':'Frozen first-observed plan sampled arrival stock >=30 through +10sec',
            'actual_flights_or_purchases_verified':False,
            'future_plan_reconfirmation_verified':False,
            'independent_trials':False,'missed_publications_count_known':False}


def score_journal(source,journal,*,now=None):
    source=Path(source).resolve(strict=True);journal=Path(journal).resolve(strict=True)
    if source==journal or os.path.samefile(source,journal):raise ValueError('collector and journal must differ')
    # Prevent the VM's staged import default from changing the evidence implementation.
    os.environ['TORNFREN_REPLAY_WORK']=str(ROOT)
    os.environ['TORNFREN_REPLAY_PINNED_RESEARCH']=str(ROOT/'research')
    from research.continuous_departure_replay import ArrivalEvidence,model,MAX_POLLS
    clock=int(time.time()) if now is None else now
    with closing(sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True)) as ledger:
        sha=ledger.execute("SELECT value FROM audit_metadata WHERE key='canary_sha'").fetchone()[0]
        sha_check(sha)
        raw=ledger.execute('SELECT record FROM issues ORDER BY issued,item_key LIMIT ?',(MAX_RECORDS+1,)).fetchall()
    if len(raw)>MAX_RECORDS:raise ValueError('journal scoring cap exceeded; use a shorter collection run')
    records=[json.loads(r[0]) for r in raw]
    if any(r['item_key'] not in model.exact_roster() for r in records):raise ValueError('unverified roster identity')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=12)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        heartbeat=model.read_heartbeat(db)
        if heartbeat is None:raise ValueError('missing source heartbeat')
        cutoff=min(clock,heartbeat)
        polls=[r[0] for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp LIMIT ?",(cutoff,MAX_POLLS+1))]
        gaps=db.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?',(cutoff,model.MAX_GAPS+1)).fetchall()
        if len(polls)>MAX_POLLS or len(gaps)>model.MAX_GAPS:raise ValueError('source evidence cap exceeded')
        evidence={}
        for key in sorted({r['item_key'] for r in records if r['actionable_at_capture']}):
            country,name=key.split(':',1)
            rows=db.execute('SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?',(country,name,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(rows)>model.MAX_ITEM_CHANGE_ROWS:raise ValueError('item history cap exceeded')
            if any(type(t) is not int or type(q) is not int or q<0 or not s for t,q,s in rows):raise ValueError('invalid stock history')
            evidence[key]=ArrivalEvidence([model.OBS(*r) for r in rows],polls,gaps,cutoff)
        report=summarize(records,lambda key,arrival:evidence[key].score(arrival))
    return dict(report,canary_sha=sha,scored_at=clock,truth_cutoff=cutoff,record_count=len(records))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    r=sub.add_parser('record');r.add_argument('--journal',type=Path,required=True)
    r.add_argument('--expected-sha',required=True);r.add_argument('--duration-seconds',type=int,default=28800)
    s=sub.add_parser('score');s.add_argument('--journal',type=Path,required=True);s.add_argument('--source',type=Path,required=True)
    s.add_argument('--compact',action='store_true')
    a=p.parse_args()
    if a.mode=='record':record(a.journal,a.expected_sha,duration=a.duration_seconds)
    else:
        report=score_journal(a.source,a.journal)
        if not a.compact:print(json.dumps(report,sort_keys=True,indent=2));return
        print('Sampled arrival availability; frozen plans, not actual flights or verified probability.')
        print('Primary: first observed issue per item/UTC hour; future plans not reconfirmed.')
        print('Item | issues | proposals | success/known | unknown | pending | proposal %')
        for key,r in report['primary_first_observed_item_utc_hour'].items():
            print(f"{key} | {r['issues']} | {r.get('proposals',0)} | {r.get('SUCCESS',0)}/{r['known']} | {r.get('UNKNOWN',0)} | {r.get('PENDING',0)} | {r['proposal_fraction']:.1%}")
        print(json.dumps({k:report[k] for k in ('canary_sha','truth_cutoff','record_count')},sort_keys=True))


if __name__=='__main__':main()
