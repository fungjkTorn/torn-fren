"""Owner-only clock activation. Default is a read-only plan; --apply is explicit.

Apply backs up only the three code files, preserves ownership/modes, restarts
only the poller, refreshes the existing research snapshot and verifies new
clock rows. On failure it restores changed code and restarts the old poller.
Clock rows already collected are retained. It never edits prediction models,
stock-history rows, web/bot services, ACLs or service/timer configuration.
"""
import argparse
import ast
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path

PAYLOAD='deploy/patches/country-clock-20261018'
POLLER='torn-fren-poller.service'
SNAPSHOT='torn-fren-research-snapshot.service'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def plan(root,exporter,payload_root):
    root=Path(root).resolve(strict=True);exporter=Path(exporter).resolve(strict=True);payload_root=Path(payload_root)
    manifest=json.loads((payload_root/PAYLOAD/'manifest.json').read_text())
    patch=(payload_root/PAYLOAD/'collector.patch').read_bytes()
    if digest(patch)!=manifest['patch_sha256']:raise ValueError('Payload patch hash mismatch')
    history=root/'services/history_service.py';helper=root/'services/country_freshness.py'
    if history.is_symlink() or helper.exists() or helper.is_symlink():raise ValueError('Unexpected existing helper or collector file symlink')
    old=history.read_bytes();old_exporter=exporter.read_bytes()
    if digest(old)!=manifest['base_history_sha256']:raise ValueError('Collector changed; regenerate and review patch')
    if digest(old_exporter)!=manifest['installed_exporter_base_sha256']:raise ValueError('Installed exporter changed; review deployment')
    for label,path in [('history',history),('installed_exporter',exporter)]:
        st=path.stat();expected=manifest[label+'_file_metadata']
        if (st.st_uid,st.st_gid,oct(st.st_mode&0o777))!=(expected['uid'],expected['gid'],expected['mode']):
            raise ValueError('Installed file ownership or permissions changed')
    with tempfile.TemporaryDirectory(prefix='torn-clock-stage-') as td:
        stage=Path(td);(stage/'services').mkdir();(stage/'services/history_service.py').write_bytes(old)
        result=subprocess.run(['git','-C',str(stage),'apply','--unidiff-zero','-'],input=patch,capture_output=True,timeout=15)
        if result.returncode:raise ValueError('Isolated patch application failed')
        modified=(stage/'services/history_service.py').read_bytes()
    if digest(modified)!=manifest['proposed_history_sha256']:raise ValueError('Proposed collector hash mismatch')
    helper_bytes=(payload_root/'services/country_freshness.py').read_bytes()
    exporter_bytes=(payload_root/'deploy/research_runner/export_snapshot.py').read_bytes()
    if digest(helper_bytes)!=manifest['helper_sha256'] or digest(exporter_bytes)!=manifest['exporter_sha256']:
        raise ValueError('Payload helper or exporter hash mismatch')
    for data in (modified,helper_bytes,exporter_bytes):ast.parse(data)
    hs=history.stat();es=exporter.stat()
    files=[dict(path=helper,new=helper_bytes,old=None,uid=hs.st_uid,gid=hs.st_gid,mode=0o644),
           dict(path=history,new=modified,old=old,uid=hs.st_uid,gid=hs.st_gid,mode=hs.st_mode&0o777),
           dict(path=exporter,new=exporter_bytes,old=old_exporter,uid=es.st_uid,gid=es.st_gid,mode=es.st_mode&0o777)]
    return files,dict(kind='COUNTRY_CLOCK_ACTIVATION_PLAN',production_modified=False,
        files=[dict(path=str(f['path']),old_sha256=digest(f['old']) if f['old'] is not None else None,
                    new_sha256=digest(f['new']),uid=f['uid'],gid=f['gid'],mode=oct(f['mode'])) for f in files],
        restart_service=POLLER,refresh_service=SNAPSHOT,export_epoch_forwarded=False,
        provider_freshness_certified=False,rollback_retains_collected_clock_rows=True)


def atomic_write(path,data,uid,gid,mode):
    fd,name=tempfile.mkstemp(prefix='.country-clock-',dir=Path(path).parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),mode)
            if (os.fstat(f.fileno()).st_uid,os.fstat(f.fileno()).st_gid)!=(uid,gid):os.fchown(f.fileno(),uid,gid)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def service(action,unit):
    if (action,unit) not in (('restart',POLLER),('start',SNAPSHOT)):raise ValueError('Unexpected service operation')
    subprocess.run(['systemctl',action,unit],check=True,capture_output=True,timeout=90)


def verify_collector(source,since,timeout=100):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
                db.execute('PRAGMA query_only=ON')
                n=db.execute("SELECT COUNT(DISTINCT received_epoch) FROM country_stock_observations WHERE country='jap' AND received_epoch>=?",(since,)).fetchone()[0]
                heartbeat=db.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
            if n>=2 and heartbeat is not None and heartbeat>=since:
                return dict(japan_new_receipts=n,latest_successful_poll=heartbeat)
        except sqlite3.Error:pass
        time.sleep(3)
    raise RuntimeError('New Japan clock receipts and collector heartbeats not verified')


def verify_snapshot(snapshot,since):
    with closing(sqlite3.connect(Path(snapshot).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.execute('PRAGMA query_only=ON');meta=dict(db.execute('SELECT key,value FROM research_metadata'))
    if (meta.get('country_clock_schema_available')!='true' or int(meta.get('country_clock_rows','0'))<=0
            or int(meta.get('source_cutoff_epoch','0'))<since):raise RuntimeError('Fresh exported clock metadata not verified')
    return dict(country_clock_rows=int(meta['country_clock_rows']),snapshot_cutoff=int(meta['source_cutoff_epoch']))


def apply(files,summary,*,backup_root,source,snapshot,run_service=service,collector_check=verify_collector,snapshot_check=verify_snapshot):
    # Recheck immediately before making any changes, even if a plan was cached.
    for f in files:
        if f['path'].is_symlink():raise ValueError('Installed code became a symlink since planning')
        if f['old'] is None:
            if f['path'].exists() or f['path'].is_symlink():raise ValueError('New helper appeared since planning')
        else:
            st=f['path'].stat()
            if (st.st_uid,st.st_gid,st.st_mode&0o777)!=(f['uid'],f['gid'],f['mode']):
                raise ValueError('Installed permissions changed since planning')
            if digest(f['path'].read_bytes())!=digest(f['old']):raise ValueError('Installed code changed since planning')
    backup_root=Path(backup_root);backup_root.mkdir(parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%dT%H%M%SZ-',time.gmtime()),dir=backup_root));backup.chmod(0o700)
    index=[]
    for i,f in enumerate(files):
        if f['old'] is not None:(backup/str(i)).write_bytes(f['old'])
        index.append(dict(path=str(f['path']),uid=f['uid'],gid=f['gid'],mode=f['mode'],
            original_present=f['old'] is not None,old_sha256=digest(f['old']) if f['old'] is not None else None,new_sha256=digest(f['new'])))
    (backup/'index.json').write_text(json.dumps(index,indent=2,sort_keys=True)+'\n')
    changed=[];since=int(time.time());failure=None
    try:
        for f in files:
            atomic_write(f['path'],f['new'],f['uid'],f['gid'],f['mode']);changed.append(f)
        run_service('restart',POLLER)
        health=collector_check(source,since)
        run_service('start',SNAPSHOT)
        exported=snapshot_check(snapshot,since)
        return dict(kind='COUNTRY_CLOCK_ACTIVATED',backup_directory=str(backup),**health,**exported,
            prediction_models_changed=False,provider_freshness_certified=False,export_epoch_forwarded=False)
    except Exception as exc:
        failure=type(exc).__name__
        try:
            for f in reversed(changed):
                if digest(f['path'].read_bytes())!=digest(f['new']):raise RuntimeError('Concurrent code change prevents automatic rollback')
                if f['old'] is None:f['path'].unlink()
                else:atomic_write(f['path'],f['old'],f['uid'],f['gid'],f['mode'])
            if changed:run_service('restart',POLLER)
        except Exception as rollback:
            raise RuntimeError('Activation failed; rollback requires manual review; backups at '+str(backup)) from rollback
        raise RuntimeError('Activation failed ('+failure+'); original code restored; backups at '+str(backup)) from exc


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true')
    p.add_argument('--collector-root',default='/opt/torn-fren');p.add_argument('--exporter',default='/usr/local/lib/torn-fren-research/export_snapshot.py')
    p.add_argument('--snapshot',default='/var/lib/torn-fren-research/stock_history_research.db')
    p.add_argument('--backup-root',default='/var/backups/torn-fren-country-clocks')
    p.add_argument('--payload-root',default=str(Path(__file__).resolve().parents[2]));a=p.parse_args()
    if a.apply and os.geteuid()!=0:p.error('--apply must be explicitly run by the owner with sudo')
    files,summary=plan(a.collector_root,a.exporter,a.payload_root)
    if not a.apply:print(json.dumps(summary,indent=2,sort_keys=True));return
    result=apply(files,summary,backup_root=a.backup_root,source=Path(a.collector_root)/'data/stock_history.db',snapshot=a.snapshot)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':main()
