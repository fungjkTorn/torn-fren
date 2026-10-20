"""Read existing decisions and original V2 archives; no prediction inference.

No live sampler, service restart, routing change, raw-stock export or deletion.
"""
import argparse
from collections import Counter,defaultdict
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import statistics
import shutil
import time
from urllib.request import build_opener,ProxyHandler
from urllib.error import URLError,HTTPError

ROOT=Path(__file__).resolve().parents[1]
os.environ['TORNFREN_REPLAY_WORK']=str(ROOT)
os.environ['TORNFREN_REPLAY_PINNED_RESEARCH']=str(ROOT/'research')


def timeline(records):
    groups=defaultdict(list)
    for r in records:groups[(r['item_key'],r['mode'])].append(r)
    output={}
    for (key,mode),rows in sorted(groups.items()):
        rows.sort(key=lambda r:(r['issued'],r['published']))
        waits=[];causes=Counter();moves=Counter();gaps=[];previous=None
        for r in rows:
            q,pub,dep=r['issued'],r['published'],r['departure']
            d=r.get('diagnostic',{})
            native=d.get('recommended_departure_timestamp',d.get('research_departure_timestamp'))
            if dep is None:
                causes['no_saved_departure']+=1
                causes[d.get('candidate_status',r['status'])]+=1
            else:
                waits.append(dep-q)
                if dep>=q+300:causes['target_after_next_model_recheck']+=1
                elif dep<pub:causes['target_passed_before_publication']+=1
                elif dep-r['source_cutoff']>180:causes['within_five_minutes_but_source_expires_before_target']+=1
                else:causes['near_term_eligible']+=1
                if dep>r.get('valid_until',q+300):causes['future_target_requires_reconfirmation']+=1
            if type(native) is int and native<q:causes['raw_target_precedes_query']+=1
            if previous is not None:
                gaps.append(q-previous['issued'])
                old=previous['departure']
                if old is not None and q<=old and dep is not None:
                    moves['postponed_before_old_target' if dep>old else 'advanced_before_old_target' if dep<old else 'unchanged_before_old_target']+=1
                if old is not None and previous['issued']<old<q:
                    moves['old_target_elapsed_between_captures']+=1
            previous=r
        output[key+'|'+mode]=dict(rows=len(rows),timed_proposals=len(waits),
            wait_minutes=dict(minimum=min(waits)/60,median=statistics.median(waits)/60,maximum=max(waits)/60) if waits else None,
            query_gap_seconds=dict(median=statistics.median(gaps),maximum=max(gaps),over_330_seconds=sum(g>330 for g in gaps)) if gaps else None,
            timing_causes=dict(causes),target_changes=dict(moves),
            statuses=dict(Counter(r['status'] for r in rows)))
    return output


def read_journal(path,sha):
    p=Path(path).expanduser().resolve(strict=True)
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=10)) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        if c.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()!=(sha,):raise ValueError('Wrong journal model pin')
        rows=c.execute('SELECT issued,item_key,mode,record FROM plans ORDER BY rowid LIMIT 100001').fetchall()
        attempts=c.execute('SELECT status,COUNT(*) FROM cycles GROUP BY status').fetchall()
    if len(rows)>100000:raise ValueError('Bounded journal required')
    records=[]
    for q,key,mode,encoded in rows:
        r=json.loads(encoded)
        if (r['issued'],r['item_key'],r['mode'],r['model_sha'])!=(q,key,mode,sha):raise ValueError('Journal identity mismatch')
        if (r.get('physical_depletion_quantity'),r.get('arrival_target'),r.get('grace_seconds'))!=(0,30,10):raise ValueError('Journal stock contract mismatch')
        records.append(r)
    return dict(model_sha=sha,records=len(records),capture_attempts=dict(attempts),models=timeline(records),
        restock_timing_accuracy=None,
        restock_timing_accuracy_unavailable_reason='This journal records arrival/departure candidates, not predicted next-restock events.',
        no_actual_flight_claim=True,
        interpretation='Future candidates require later reconfirmation. Target movement is observed movement, not proof that every postponement was wrong. Gaps over330 seconds diagnose cadence, not missing stock polls.')


def data_inventory(source):
    p=Path(source).expanduser().resolve(strict=True)
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=10)) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        rows=c.execute('SELECT country,item_name,COUNT(*),MIN(timestamp),MAX(timestamp),SUM(quantity=0) FROM stock_history GROUP BY country,item_name').fetchall()
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        archived_runs=c.execute('SELECT COUNT(*),MIN(created_at),MAX(created_at) FROM forecast_audit_runs').fetchone() if 'forecast_audit_runs' in tables else None
    return dict(stock_item_count=len(rows),items={country+':'+name:dict(change_rows=n,first_observation=first,last_observation=last,
        observed_span_days=(last-first)/86400 if last is not None and first is not None else None,zero_observations=zeros)
        for country,name,n,first,last,zeros in rows},original_v2_archive_inventory=archived_runs,
        table_names=[name for name in ('stock_history','poll_heartbeats','collection_gaps','forecast_audit_runs','forecast_audit_points') if name in tables],
        interpretation='Observed span is not continuous provider-certified coverage. No raw quantities, keys or unrelated tables exported.')


def recovery_inventory():
    """Bounded local page probes and shallow home inventory, never deletion."""
    opener=build_opener(ProxyHandler({}));pages=[]
    for port,path in ((8000,'/'),(8000,'/experimental'),(8000,'/travel-decisions'),
                      (8770,'/health'),(8770,'/'),(8770,'/experimental'),(8770,'/travel-decisions')):
        value=dict(port=port,path=path)
        try:
            with opener.open('http://127.0.0.1:'+str(port)+path,timeout=2) as response:
                body=response.read(4096);value['http_status']=response.status
                if path=='/health':
                    health=json.loads(body)
                    value['health']={k:health[k] for k in ('status','source_sha','item_count','source_poll_age_seconds','last_publish') if k in health}
        except HTTPError as e:value['http_status']=e.code
        except (OSError,URLError,ValueError) as e:value['error_type']=type(e).__name__
        pages.append(value)
    folders=[]
    for p in sorted(Path.home().glob('torn-fren*'))[:150]:
        if p.is_symlink() or not p.is_dir():continue
        databases=[f for pattern in ('*.sqlite','*.db') for f in p.glob(pattern) if f.is_file() and not f.is_symlink()]
        folders.append(dict(name=p.name,git_checkout=(p/'.git').is_dir(),
            shallow_database_bytes=sum(f.stat().st_size for f in databases),
            shallow_database_count=len(databases)))
    files=[dict(name=p.name,bytes=p.stat().st_size) for p in sorted(Path.home().glob('torn-fren*'))[:200]
           if p.is_file() and not p.is_symlink() and p.suffix in ('.sqlite','.db','.log','.json','.txt')]
    space=shutil.disk_usage(Path.home())
    return dict(local_pages=pages,home_project_directories=folders,home_project_files=files,
        home_filesystem_bytes=dict(total=space.total,used=space.used,free=space.free),
        cleanup_performed=False,
        limitation='Shallow inventory only. No directory is declared safe to remove; inactive services/timers may still reference it. HTTP200 checks page reachability, not prediction correctness.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--journal',required=True);p.add_argument('--model-sha',required=True)
    p.add_argument('--source',default='/opt/torn-fren/data/stock_history.db')
    p.add_argument('--out',required=True);p.add_argument('--days',type=int,default=30)
    p.add_argument('--with-stock-score',action='store_true')
    p.add_argument('--with-physical-identity',action='store_true',
                   help='Independently compare explicit Pn ordinals to all physical restocks')
    a=p.parse_args()
    if not 1<=a.days<=90:p.error('days must be 1..90')
    out=Path(a.out).expanduser().resolve()
    if out.exists():p.error('Use a new report path; existing evidence will not be overwritten')
    if Path.home().resolve() not in out.parents:p.error('Report must be under your home')
    result=dict(kind='SAVED_TIMELINE_AND_ORIGINAL_V2_AUDIT',read_only_sources=True,actual_flights=False,
                generated_at=int(time.time()),requested_original_days=a.days)
    def checkpoint():out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    result['timeline']=read_journal(a.journal,a.model_sha);checkpoint()
    print('SAVED_TIMELINE_READ',result['timeline']['records'],'rows',flush=True)
    print('Item | proposals/rows | min/median/max wait minutes | timing causes | target changes',flush=True)
    for identity,r in result['timeline']['models'].items():
        if not identity.endswith('|specialist_control'):continue
        w=r['wait_minutes'];wait='-' if w is None else '/'.join('%.1f'%w[k] for k in ('minimum','median','maximum'))
        print(identity.split('|')[0],str(r['timed_proposals'])+'/'+str(r['rows']),wait,
              json.dumps(r['timing_causes'],sort_keys=True),json.dumps(r['target_changes'],sort_keys=True),sep=' | ',flush=True)
    try:result['data_inventory']=data_inventory(a.source)
    except (OSError,ValueError,sqlite3.Error) as e:result['data_inventory']=dict(status='UNAVAILABLE',error_type=type(e).__name__)
    checkpoint()
    inventory=result['data_inventory']
    if 'items' in inventory:
        spans=[r['observed_span_days'] for r in inventory['items'].values() if r['observed_span_days'] is not None]
        print('DATA_INVENTORY',json.dumps(dict(stock_items=inventory['stock_item_count'],
            minimum_span_days=min(spans) if spans else None,maximum_span_days=max(spans) if spans else None,
            original_v2_archive_inventory=inventory['original_v2_archive_inventory'])),flush=True)
    result['recovery_inventory']=recovery_inventory();checkpoint()
    print('WEBSITE_REACHABILITY',json.dumps(result['recovery_inventory']['local_pages']),flush=True)
    print('PROJECT_DIRECTORY_COUNT',len(result['recovery_inventory']['home_project_directories']),'NO_DELETIONS',flush=True)
    from research.v134_original_graph_v2_audit import audit as archived_audit
    try:
        result['original_v2_archived']=archived_audit(collector=a.source,days=a.days)
        print('ORIGINAL_V2_ARCHIVED',json.dumps({k:v for k,v in result['original_v2_archived'].items() if k in ('status','overall','missing_tables')}),flush=True)
    except (OSError,ValueError,sqlite3.Error) as e:
        result['original_v2_archived']=dict(status='UNAVAILABLE',error_type=type(e).__name__,reason=str(e)[:180])
        print('ORIGINAL_V2_ARCHIVED',json.dumps(result['original_v2_archived']),flush=True)
    checkpoint()
    if a.with_stock_score:
        from research.v137_original_v2_stock_at_arrival_audit import audit as stock_audit
        try:result['original_v2_stock_score']=stock_audit(collector=a.source,days=a.days)
        except (OSError,ValueError,sqlite3.Error) as e:result['original_v2_stock_score']=dict(status='UNAVAILABLE',error_type=type(e).__name__,reason=str(e)[:180])
        checkpoint()
        print('ORIGINAL_V2_STOCK_SCORE',json.dumps({k:v for k,v in result['original_v2_stock_score'].items() if k in ('status','overall','missing_tables')}),flush=True)
    if a.with_physical_identity:
        from research.physical_restock_identity import archived_audit
        try:
            with closing(sqlite3.connect(Path(a.source).resolve().as_uri()+'?mode=ro',uri=True)) as db:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                result['physical_identity']=archived_audit(db,cutoff=result['generated_at'],days=a.days)
        except (OSError,ValueError,sqlite3.Error) as e:
            result['physical_identity']=dict(status='UNAVAILABLE',error_type=type(e).__name__,reason=str(e)[:180])
        checkpoint()
        print('PHYSICAL_IDENTITY',json.dumps(result['physical_identity']),flush=True)
    print('AUDIT_REPORT_SAVED',out,flush=True)


if __name__=='__main__':main()
