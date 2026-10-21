"""Read-only owner preflight for country-clock logging and snapshot export.

Never imports collector code, performs network requests, applies a patch,
changes ACLs, installs files or controls a service. Values from application
secrets, environment files and heartbeat error strings are never read.
"""
import argparse
import ast
import hashlib
import json
import sqlite3
import subprocess
import time
from collections import Counter
from contextlib import closing
from pathlib import Path


def read_code(path):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>2000000:raise ValueError('Code file cap exceeded')
        tree=ast.parse(raw)
        return tree,dict(status='READABLE',sha256=hashlib.sha256(raw).hexdigest())
    except (OSError,SyntaxError,ValueError) as exc:
        return None,dict(status='UNAVAILABLE',error_type=type(exc).__name__)


def inspect_code(root,exporter):
    root=Path(root);history,h=read_code(root/'services/history_service.py')
    provider,p=read_code(root/'services/stock_provider.py')
    helper,f=read_code(root/'services/country_freshness.py')
    installed,e=read_code(exporter)
    def has_record(tree):
        if tree is None:return False
        functions=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='save_snapshot_from_export']
        return any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='record'
            and isinstance(n.func.value,ast.Name) and n.func.value.id=='country_freshness' for fn in functions for n in ast.walk(fn))
    def has_clock_schema(tree):
        return tree is not None and any(isinstance(n,ast.Constant) and isinstance(n.value,str)
            and 'CREATE TABLE' in n.value and 'country_stock_observations' in n.value for n in ast.walk(tree))
    def has_export_support(tree):
        if tree is None:return False
        constants={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        return 'country_clock_schema_available' in constants and 'country_clock_rows' in constants
    return dict(history=h,provider=p,clock_helper=f,installed_exporter=e,
        country_record_call_present=has_record(history),helper_schema_present=has_clock_schema(helper),
        exporter_clock_metadata_code_present=has_export_support(installed),
        limitation='Static code inspection cannot establish which process revision is currently loaded.')


def database_report(path,now,*,snapshot=False):
    report=dict(status='UNAVAILABLE')
    try:
        path=Path(path).resolve(strict=True)
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            report=dict(status='READABLE',clock_table_present='country_stock_observations' in tables)
            if 'poll_heartbeats' in tables:
                last=db.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=?",(now,)).fetchone()[0]
                report['last_successful_poll']=last
                report['successful_poll_age_seconds']=now-last if last is not None else None
            if report['clock_table_present']:
                required={'id','received_epoch','country','source','country_update_epoch','clock_status'}
                columns={r[1] for r in db.execute('PRAGMA table_info(country_stock_observations)')}
                report['clock_schema_supported']=required<=columns
                if required<=columns:
                    rows=db.execute('''SELECT received_epoch,source,country_update_epoch,clock_status
                        FROM country_stock_observations WHERE country='jap' AND received_epoch BETWEEN ? AND ?
                        ORDER BY received_epoch DESC,id DESC LIMIT 5001''',(now-86400,now)).fetchall()
                    report['japan_recent_sample_truncated']=len(rows)>5000
                    rows=rows[:5000];providers={}
                    for source in sorted({r[1] for r in rows}):
                        if source not in ('yata','prometheus','unknown'):
                            source_key='UNRECOGNIZED_PROVIDER'
                        else:source_key=source
                        selected=[r for r in rows if r[1]==source];ages=[];statuses=Counter()
                        for receipt,_,update,status in selected:
                            # Only approved statuses are exposed, not arbitrary DB strings.
                            approved={'REPORTED','MISSING','INVALID','FUTURE','EMPTY_PAYLOAD_REPORTED','EMPTY_PAYLOAD_MISSING','EMPTY_PAYLOAD_INVALID','EMPTY_PAYLOAD_FUTURE'}
                            statuses[status if status in approved else 'UNRECOGNIZED_STATUS']+=1
                            if type(update) is int and update<=receipt:ages.append(receipt-update)
                        providers[source_key]=dict(sampled_rows=len(selected),newest_receipt=max(r[0] for r in selected),
                            min_report_age_seconds=min(ages,default=None),max_report_age_seconds=max(ages,default=None),statuses=dict(statuses))
                    report['japan_sampled_rows']=len(rows);report['japan_providers']=providers
            if snapshot:
                meta=dict(db.execute('SELECT key,value FROM research_metadata')) if 'research_metadata' in tables else {}
                allowed=('source_cutoff_epoch','sanitized_stock_only','roster_size','country_clock_schema_available','country_clock_rows')
                report['metadata']={k:meta[k] for k in allowed if k in meta}
                report['clock_export_metadata_present']=all(k in meta for k in ('country_clock_schema_available','country_clock_rows'))
        return report
    except (OSError,sqlite3.Error,ValueError) as exc:
        return dict(status='UNAVAILABLE',error_type=type(exc).__name__)


def patch_check(root,payload):
    patch=Path(payload)/'deploy/research_runner/country_clock_activation.patch'
    try:
        raw=patch.read_bytes()
        if len(raw)>200000:raise ValueError('Patch cap exceeded')
        result=subprocess.run(['git','-C',str(root),'apply','--check','-'],input=raw,capture_output=True,timeout=15)
        status='APPLICABLE' if result.returncode==0 else 'DOES_NOT_APPLY' if result.returncode==1 else 'CHECK_UNAVAILABLE'
        return dict(status=status,
            patch_sha256=hashlib.sha256(raw).hexdigest(),returncode=result.returncode,
            limitation='Check only; already-applied or locally changed code can both fail this check. No patch applied.')
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        return dict(status='UNAVAILABLE',error_type=type(exc).__name__)


def preflight(*,collector_root,source,snapshot,exporter,payload_root,now=None):
    now=int(time.time()) if now is None else now
    code=inspect_code(collector_root,exporter)
    live=database_report(source,now) if source is not None else dict(status='NOT_REQUESTED')
    copy=database_report(snapshot,now,snapshot=True)
    if source is None:
        if copy['status']!='READABLE':diagnosis='SNAPSHOT_EVIDENCE_UNAVAILABLE'
        elif not copy.get('clock_export_metadata_present'):diagnosis='SNAPSHOT_CLOCK_EXPORT_INSTRUMENTATION_UNCONFIRMED'
        elif not copy.get('japan_sampled_rows'):diagnosis='NO_JAPAN_CLOCK_ROWS_VISIBLE_IN_SNAPSHOT_SAMPLE'
        else:diagnosis='SNAPSHOT_CLOCK_EVIDENCE_VISIBLE'
    elif live['status']!='READABLE':diagnosis='LIVE_EVIDENCE_UNAVAILABLE'
    elif not live['clock_table_present']:diagnosis='LIVE_CLOCK_TABLE_ABSENT'
    elif not live.get('clock_schema_supported'):diagnosis='LIVE_CLOCK_SCHEMA_UNSUPPORTED'
    elif not live.get('japan_sampled_rows'):diagnosis='NO_JAPAN_CLOCK_ROWS_IN_LAST_DAY'
    elif copy['status']!='READABLE':diagnosis='SNAPSHOT_EVIDENCE_UNAVAILABLE'
    elif not copy.get('clock_export_metadata_present'):diagnosis='CLOCK_ROWS_PRESENT_EXPORT_INSTRUMENTATION_UNCONFIRMED'
    elif not copy.get('japan_sampled_rows'):diagnosis='LIVE_CLOCK_ROWS_NOT_VISIBLE_IN_SNAPSHOT_SAMPLE'
    else:diagnosis='CLOCK_EVIDENCE_VISIBLE_CHECK_COUNTRY_REPORT_AGES'
    return dict(kind='COUNTRY_CLOCK_OWNER_READONLY_PREFLIGHT',asof=now,diagnosis=diagnosis,
        scope='LIVE_DB_AND_SNAPSHOT' if source is not None else 'SNAPSHOT_AND_STATIC_CODE_ONLY',
        collector_code=code,live_database=live,research_snapshot=copy,patch_check=patch_check(collector_root,payload_root),
        production_modified=False,service_restarted=False,provider_freshness_certified=False,
        limitation='Recent collector heartbeat is not country/item freshness. Reported country clocks do not prove exact game-event timing. Missing exporter metadata cannot establish absence of logging on the live collector.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collector-root',required=True)
    p.add_argument('--source',help='Owner-only live DB check. Omit to inspect only snapshot and static code.')
    p.add_argument('--snapshot',required=True);p.add_argument('--exporter',required=True)
    p.add_argument('--payload-root',required=True)
    a=p.parse_args()
    print(json.dumps(preflight(collector_root=a.collector_root,source=a.source,snapshot=a.snapshot,
        exporter=a.exporter,payload_root=a.payload_root),indent=2,sort_keys=True))


if __name__=='__main__':main()
