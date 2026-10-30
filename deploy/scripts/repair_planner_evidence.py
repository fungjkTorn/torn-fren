"""Install a reporting-only publisher overlay; preserve native model files."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import types
import subprocess
import tempfile
import time
import zipfile

BASE=Path('/var/lib/torn-fren-live-beta')
UNIT=Path('/etc/systemd/system/torn-fren-first-ten-beta.service')
TIMER='torn-fren-first-ten-beta.timer'
JS=Path('/opt/torn-fren/web/first_release_assets/beta.js')
BACKUPS=Path('/var/backups/torn-fren-ops')
COLLECTOR=Path('/opt/torn-fren/data/stock_history.db')
ENTRY='''import importlib.util,os,pathlib,sys
sys.path.insert(0,os.getcwd())
from services import first_release_live as live
for name in ('restock_signatures','simulated_trip_evidence'):
    spec=importlib.util.spec_from_file_location('services.'+name,pathlib.Path(__file__).with_name(name+'.py'))
    child=importlib.util.module_from_spec(spec);sys.modules[spec.name]=child;spec.loader.exec_module(child)
spec=importlib.util.spec_from_file_location('corrected_live_evidence',pathlib.Path(__file__).with_name('evidence.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
live.evidence=module
live.main()
'''

def reconcile(folder,ledger,collector,model_sha):
    package=sys.modules.setdefault('services',types.ModuleType('services'))
    if not hasattr(package,'__path__'):package.__path__=[]
    for name in ('restock_signatures','simulated_trip_evidence'):
        spec=importlib.util.spec_from_file_location('services.'+name,folder/(name+'.py'))
        child=importlib.util.module_from_spec(spec);sys.modules[spec.name]=child;spec.loader.exec_module(child)
    spec=importlib.util.spec_from_file_location('repair_evidence',folder/'evidence.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    db=module.connect(ledger)
    src=sqlite3.connect(collector.resolve(strict=True).as_uri()+'?mode=ro',uri=True)
    try:
        src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
        hb=src.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
        if hb is None:raise ValueError('missing source heartbeat')
        cutoff=min(int(time.time()),hb)
        pairs=db.execute('SELECT DISTINCT item,model_sha FROM issues WHERE model_sha=?',(model_sha,)).fetchall()
        if len(pairs)!=10:raise ValueError('expected the active ten-item model ledger')
        result={}
        for item,sha in pairs:
            result[item]=module.summary(db,src,item_key=item,model_sha=sha,cutoff=cutoff)
        db.commit();return result
    finally:src.close();db.close()

def preview(folder,ledger,collector,model_sha):
    with tempfile.TemporaryDirectory(prefix='simulation-preview-',dir=BASE) as td:
        copy=Path(td)/'ledger.sqlite'
        src=sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(copy)
        try:src.backup(dst)
        finally:dst.close();src.close()
        return reconcile(folder,copy,collector,model_sha)

def run(args,timeout=30):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(p.stderr[-2000:])
    return p.stdout

def atomic(path,raw):
    stat=path.stat();fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.evidence-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw)
        os.chmod(tmp,stat.st_mode&0o777);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,path)
    finally:
        if Path(tmp).exists():Path(tmp).unlink()

def repair(archive,apply=False):
    with zipfile.ZipFile(archive) as z:
        evidence=z.read('services/first_release_evidence.py');js=z.read('web/first_release_assets/beta.js')
        board=z.read('web/first_release_assets/board.html')
        companions={name:z.read('services/'+name+'.py') for name in ('restock_signatures','simulated_trip_evidence')}
    compile(evidence,'evidence.py','exec');compile(ENTRY,'entry.py','exec')
    revision=hashlib.sha256(evidence+js+board+ENTRY.encode()+b''.join(companions.values())).hexdigest()[:20]
    board_path=JS.with_name('board.html')
    old_unit=UNIT.read_bytes();old_js=JS.read_bytes();old_board=board_path.read_bytes();old_snapshot=(BASE/'latest.json').read_bytes()
    commands=[b'-m services.first_release_live',str(BASE/'reporting'/'98ebf83b2b87555dfca1'/'entry.py').encode(),str(BASE/'reporting'/revision/'entry.py').encode()]
    found=[command for command in commands if old_unit.count(command)==1]
    if len(found)!=1:
        raise ValueError('publisher command differs; inspect active unit before applying overlay')
    old_command=found[0]
    before=json.loads(old_snapshot)
    result={'status':'EVIDENCE_REPAIR_PLAN','reporting_revision':revision,'model_sha':before['model_sha'],
        'evidence_policy':'RECOMMENDED_DEPARTURE_FREEZE_V5',
        'collector_modified':False,'native_models_modified':False,'raw_evidence_deleted':False}
    if os.geteuid()!=0:raise PermissionError('root required for private evidence preview')
    folder=BASE/'reporting'/revision;folder.mkdir(parents=True,exist_ok=True)
    for name,data in [('entry.py',ENTRY.encode()),('evidence.py',evidence)]+[(name+'.py',raw) for name,raw in companions.items()]:
        compile(data,name,'exec')
        p=folder/name
        if p.exists() and p.read_bytes()!=data:raise ValueError('reporting overlay identity collision')
        p.write_bytes(data);p.chmod(0o644)
    folder.chmod(0o755);folder.parent.chmod(0o755)
    began=time.monotonic()
    comparison=preview(folder,BASE/'forecasts.sqlite',COLLECTOR,before['model_sha'])
    result['preview_seconds']=round(time.monotonic()-began,2)
    fields=('simulated_trips_total','known','successes','failures','unknown','pending','observed_restocks_since_start','revision_counts','restock_profile','target_identity_audit')
    result['preview']={key:{f:m.get(f) for f in fields} for key,m in comparison.items()}
    if not apply:return result
    if any(m.get('target_identity_audit',{}).get('duplicate_target_groups',1) for m in comparison.values()):
        result.update(status='EVIDENCE_REPAIR_BLOCKED',error='duplicate or missing target identity audit; live service unchanged')
        return result
    backup_root=BACKUPS;backup_root.mkdir(exist_ok=True,parents=True)
    backup=Path(tempfile.mkdtemp(prefix='planner-evidence-',dir=backup_root));backup.chmod(0o700)
    (backup/'service').write_bytes(old_unit);(backup/'beta.js').write_bytes(old_js);(backup/'board.html').write_bytes(old_board);(backup/'latest.json').write_bytes(old_snapshot)
    result['backup_directory']=str(backup)
    paused=False
    try:
        run(['systemctl','stop',TIMER]);paused=True
        run(['systemctl','stop',UNIT.name])
        # SQLite backup API captures a consistent ledger including any WAL.
        src=sqlite3.connect((BASE/'forecasts.sqlite').as_uri()+'?mode=ro',uri=True)
        dst=sqlite3.connect(backup/'forecasts.sqlite')
        try:src.backup(dst)
        finally:dst.close();src.close()
        reconciled=reconcile(folder,BASE/'forecasts.sqlite',COLLECTOR,before['model_sha'])
        if any(m.get('target_identity_audit',{}).get('duplicate_target_groups',1) for m in reconciled.values()):
            raise ValueError('duplicate target identity during final reconciliation')
        new_unit=old_unit.replace(old_command,str(folder/'entry.py').encode())
        atomic(UNIT,new_unit);atomic(JS,js);atomic(board_path,board)
        run(['systemd-analyze','verify',str(UNIT)])
        run(['systemctl','daemon-reload'])
        run(['systemctl','start',UNIT.name],timeout=75)
        current=json.loads((BASE/'latest.json').read_text())
        if current['model_sha']!=before['model_sha'] or current['published_epoch']<=before['published_epoch']:
            raise ValueError('new publication identity/clock failed')
        if len(current['live_metrics'])!=10 or not all(m.get('evidence_policy')=='RECOMMENDED_DEPARTURE_FREEZE_V5' for m in current['live_metrics'].values()):
            raise ValueError('new evidence policy not active')
        if any(m.get('target_identity_audit',{}).get('duplicate_target_groups',1) for m in current['live_metrics'].values()):
            raise ValueError('duplicate target identity in new publication')
        result.update(status='EVIDENCE_REPAIR_APPLIED',published_epoch=current['published_epoch'],
            counts={k:{f:m.get(f) for f in fields} for k,m in current['live_metrics'].items()})
    except Exception as exc:
        atomic(UNIT,old_unit);atomic(JS,old_js);atomic(board_path,old_board);atomic(BASE/'latest.json',old_snapshot)
        run(['systemctl','daemon-reload'])
        result.update(status='EVIDENCE_REPAIR_ROLLED_BACK',error_type=type(exc).__name__,error=str(exc))
    finally:
        if paused:run(['systemctl','start',TIMER])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True);p.add_argument('--apply',action='store_true')
    a=p.parse_args();r=repair(a.archive,a.apply);print(json.dumps(r,indent=2))
    if r['status'] in ('EVIDENCE_REPAIR_ROLLED_BACK','EVIDENCE_REPAIR_BLOCKED'):raise SystemExit(1)
