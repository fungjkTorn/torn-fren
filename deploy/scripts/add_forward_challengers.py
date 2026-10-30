"""Stage six approved challengers, then atomically expose their separate feed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import zipfile

BASE=Path('/var/lib/torn-fren-live-beta')
STATE=BASE/'challengers'
ROOT=Path('/opt/torn-fren')
COLLECTOR=ROOT/'data/stock_history.db'
PYTHON=Path('/home/ubuntu/torn-fren-v38-probe/.venv/bin/python')
UNIT=Path('/etc/systemd/system/torn-fren-challengers-beta.service')
TIMER=UNIT.with_suffix('.timer')
PRIMARY=Path('/etc/systemd/system/torn-fren-first-ten-beta.service')
WEB='torn-fren-web.service'
BACKUPS=Path('/var/backups/torn-fren-ops')
EXPECTED={
    'web/first_release_bridge.py':'c3569fd86315cc11efea6402aeefbc187977e33c376759546f2969a30836fa59',
    'web/first_release_assets/beta.js':'d2d856f07d181854738ad66096f541edcc1d27e15ff694b785c3e039d9859276',
}
CONFIGS={'arg:Monkey Plushie':('v20','traj3'),'can:Wolverine Plushie':('v20','traj12'),
    'cay:Stingray Plushie':('v20','traj5'),'chi:Peony':('v20','traj12'),
    'sou:African Violet':('v20','traj11'),'sou:Lion Plushie':('v20','traj12')}
ADDED=frozenset(CONFIGS)


def run(args,timeout=30):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(p.stderr[-3000:] or p.stdout[-3000:])
    return p.stdout


def atomic(path,raw):
    st=path.stat();fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.forward-beta-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw)
        os.chmod(temp,st.st_mode&0o777);os.chown(temp,st.st_uid,st.st_gid);os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)


def service(release,sha):
    return f'''[Unit]
Description=Torn Fren six approved challengers and forward evidence
After=local-fs.target
ConditionPathExists={STATE / 'stock_history.sqlite'}
[Service]
Type=oneshot
User=ubuntu
Group=ubuntu
WorkingDirectory={release}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=OMP_NUM_THREADS=1
Environment=MKL_NUM_THREADS=1
Environment=TORNFREN_REPLAY_PINNED_RESEARCH={BASE}/no-legacy-stage
ExecStart=/usr/bin/flock -n {STATE}/publisher.lock {PYTHON} -B -m services.challenger_live --collector {COLLECTOR} --state {STATE} --model-sha {sha}
Nice=19
CPUQuota=75%
MemoryMax=1024M
TimeoutStartSec=140
TimeoutStopSec=15
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths={STATE}
UMask=0022
'''


TIMER_TEXT='''[Unit]
Description=Refresh the six forward challengers each minute
[Timer]
OnCalendar=*-*-* *:*:50 UTC
AccuracySec=1s
Persistent=false
Unit=torn-fren-challengers-beta.service
[Install]
WantedBy=timers.target
'''


def validate_snapshot(data,sha):
    if data.get('model_sha')!=sha or set(data.get('items',{}))!=ADDED:raise ValueError('wrong challenger snapshot identity')
    if data.get('historical_accuracy_included') is not False:raise ValueError('historical accuracy must not be seeded')
    if int(time.time())>data['valid_until_epoch']:raise ValueError('challenger snapshot already expired')
    if set(data.get('live_metrics',{}))!=ADDED:raise ValueError('missing challenger evidence metrics')
    for key,row in data['items'].items():
        if not row.get('timing_full_history_override'):raise ValueError('full-history override missing: '+key)
        d=row.get('decision') or {}
        if (d.get('timing_model_generation'),d.get('timing_model_config'))!=CONFIGS[key]:raise ValueError('wrong native configuration: '+key)
        m=data['live_metrics'][key]
        if m.get('evidence_policy')!='RECOMMENDED_DEPARTURE_FREEZE_V5':raise ValueError('V5 evidence required')
        if m.get('target_identity_audit',{}).get('duplicate_target_groups',1):raise ValueError('duplicate or missing target audit')


def verify_web(sha,primary_sha):
    last=None
    for _ in range(15):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/api/first-release',timeout=4) as r:data=json.load(r)
            rows=data.get('rows',[])
            if len(rows)!=16 or data.get('status')!='LIVE_BETA':raise ValueError('combined feed not fresh and complete')
            added={r['item_key'] for r in rows if r.get('cohort')=='challengers'}
            if added!=ADDED:raise ValueError('challenger roster differs')
            if any(r['model_sha']!=(sha if r['item_key'] in ADDED else primary_sha) for r in rows):raise ValueError('item model identity changed')
            if data.get('cohorts',{}).get('challengers',{}).get('status')!='LIVE_BETA':raise ValueError('challenger feed is stale')
            return {'items':16,'new_items':sorted(added),'primary_model_sha':primary_sha,'challenger_model_sha':sha}
        except (OSError,ValueError,KeyError) as exc:last=exc;time.sleep(.5)
    raise RuntimeError('combined website feed failed verification: '+str(last))


def deploy(archive,sha,apply=False):
    if os.geteuid()!=0:raise PermissionError('sudo required for guarded deployment')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('exact Git release SHA required')
    if UNIT.exists() or TIMER.exists():raise ValueError('challenger units already exist; inspect before replacing')
    primary_unit=PRIMARY.read_bytes();primary=json.loads((BASE/'latest.json').read_text())
    if len(primary.get('items',{}))!=10:raise ValueError('original ten-item snapshot required')
    if int(time.time())>primary['valid_until_epoch']:raise ValueError('original feed is delayed; resolve before rollout')
    old={}
    for name,expected in EXPECTED.items():
        old[name]=(ROOT/name).read_bytes()
        if hashlib.sha256(old[name]).hexdigest()!=expected:raise ValueError('website changed; refuse overwrite: '+name)
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>2000 or sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('oversized release')
        files={}
        for info in z.infolist():
            if info.is_dir():continue
            p=Path(info.filename)
            if p.is_absolute() or '..' in p.parts or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('unsafe release member')
            if p.parts[0] not in ('services','research','deploy') and info.filename not in EXPECTED:raise ValueError('unexpected release member')
            files[info.filename]=z.read(info)
    if not all(name in files for name in EXPECTED):raise ValueError('website files missing')
    release=BASE/'releases'/(sha+'-challengers');release.mkdir(parents=True,exist_ok=True)
    for name,raw in files.items():
        path=release/name;path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.read_bytes()!=raw:raise ValueError('immutable release differs')
        path.write_bytes(raw);path.chmod(0o644)
    for path in [release]+[p for p in release.rglob('*') if p.is_dir()]:path.chmod(0o755)
    account=pwd.getpwnam('ubuntu');STATE.mkdir(mode=0o755,exist_ok=True);os.chown(STATE,account.pw_uid,account.pw_gid)
    source=STATE/'stock_history.sqlite'
    seed_needed=not source.exists()
    if not seed_needed:
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
            hb=db.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
        seed_needed=hb is None or time.time()-hb>600
    if seed_needed:
        seed=source.with_name('stock-history-bootstrap-'+str(time.time_ns())+'.sqlite')
        command="from services.challenger_live import bootstrap; import json; print(json.dumps(bootstrap("+repr(str(COLLECTOR))+","+repr(str(seed))+")))"
        run(['runuser','-u','ubuntu','--',PYTHON,'-B','-c',"import os; os.chdir("+repr(str(release))+"); "+command],timeout=90)
        if source.exists():source.rename(source.with_name('stock-history-previous-'+str(time.time_ns())+'.sqlite'))
        seed.rename(source)
    # The private preflight cannot seed the public cohort's forward-trip ledger.
    with tempfile.TemporaryDirectory(prefix='.challenger-preview-',dir=STATE) as td:
        os.chown(td,account.pw_uid,account.pw_gid)
        transient='torn-fren-challengers-preview-'+str(int(time.time()))
        raw=run(['systemd-run','--quiet','--wait','--pipe','--collect','--unit='+transient,
            '--uid=ubuntu','--property=WorkingDirectory='+str(release),'--property=CPUQuota=75%',
            '--property=Nice=19','--property=MemoryMax=1024M','--property=RuntimeMaxSec=135',
            '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=OPENBLAS_NUM_THREADS=1','--setenv=OMP_NUM_THREADS=1','--setenv=MKL_NUM_THREADS=1',
            '--setenv=TORNFREN_REPLAY_PINNED_RESEARCH='+str(BASE/'no-legacy-stage'),
            PYTHON,'-B','-m','services.challenger_live','--collector',COLLECTOR,'--source',source,'--state',td,'--model-sha',sha],timeout=145)
        preflight=json.loads(raw);snapshot=json.loads((Path(td)/'latest.json').read_text());validate_snapshot(snapshot,sha)
        if preflight['elapsed_seconds']>55:raise ValueError('challenger batch exceeds the one-minute cadence budget; original deployment unchanged')
        result={'status':'SIX_CHALLENGER_PLAN','release_sha':sha,'preflight':preflight,
            'new_items':sorted(ADDED),'resulting_items':16,'primary_publisher_modified':False,
            'collector_modified':False,'historical_results_seeded':False,'raw_evidence_deleted':False}
    if not apply:return result
    backup_root=BACKUPS;backup_root.mkdir(parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix='six-challengers-',dir=backup_root));backup.chmod(0o700)
    for name,raw in old.items():(backup/Path(name).name).write_bytes(raw)
    (backup/'primary.service').write_bytes(primary_unit)
    result['backup_directory']=str(backup)
    try:
        UNIT.write_text(service(release,sha));TIMER.write_text(TIMER_TEXT)
        run(['systemd-analyze','verify',UNIT,TIMER]);run(['systemctl','daemon-reload'])
        run(['systemctl','start',UNIT.name],timeout=145)
        validate_snapshot(json.loads((STATE/'latest.json').read_text()),sha)
        for name in EXPECTED:atomic(ROOT/name,files[name])
        run(['systemctl','restart',WEB])
        result['verification']=verify_web(sha,primary['model_sha'])
        if PRIMARY.read_bytes()!=primary_unit:raise ValueError('original publisher unit changed')
        run(['systemctl','enable','--now',TIMER.name])
        result['status']='SIX_CHALLENGERS_APPLIED'
    except Exception as exc:
        cleanup_errors=[]
        for args in (['systemctl','stop',TIMER.name,UNIT.name],['systemctl','disable',TIMER.name]):
            try:run(args)
            except Exception as cleanup:cleanup_errors.append(str(cleanup))
        for name,raw in old.items():
            try:atomic(ROOT/name,raw)
            except Exception as cleanup:cleanup_errors.append(str(cleanup))
        try:run(['systemctl','restart',WEB])
        except Exception as cleanup:cleanup_errors.append(str(cleanup))
        UNIT.unlink(missing_ok=True);TIMER.unlink(missing_ok=True)
        try:run(['systemctl','daemon-reload'])
        except Exception as cleanup:cleanup_errors.append(str(cleanup))
        result.update(status='SIX_CHALLENGERS_ROLLED_BACK',error=str(exc),cleanup_errors=cleanup_errors)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True)
    p.add_argument('--sha',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    try:result=deploy(a.archive,a.sha,a.apply)
    except Exception as exc:
        result={'status':'SIX_CHALLENGERS_STOPPED','error_type':type(exc).__name__,'error':str(exc),
            'primary_publisher_modified':False,'collector_modified':False}
    print(json.dumps(result,indent=2))
    if result['status'] in ('SIX_CHALLENGERS_ROLLED_BACK','SIX_CHALLENGERS_STOPPED'):raise SystemExit(1)
