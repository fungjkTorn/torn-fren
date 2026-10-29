"""Install the reviewed freshness repair from an immutable Git commit.

Keep frozen model identity and the existing append-only evidence series. Only
publisher code, its service command and two website files are updated. No
collector changes, new jobs, GitHub Actions or model tournament.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

MODEL_SHA='45d14b5e931458e41dc31e551310994caf4f8a1d'
BASE=Path('/var/lib/torn-fren-live-beta')
SERVICE='torn-fren-first-ten-beta.service'
TIMER='torn-fren-first-ten-beta.timer'
WEB='torn-fren-web.service'
SERVICE_PATH=Path('/etc/systemd/system')/SERVICE
BRIDGE=Path('/opt/torn-fren/web/first_release_bridge.py')
JS=Path('/opt/torn-fren/web/first_release_assets/beta.js')
PYTHON=Path('/home/ubuntu/torn-fren-v38-probe/.venv/bin/python')
HISTORY=Path('/var/lib/torn-fren-research/stock_history_forward.db')
COLLECTOR=Path('/opt/torn-fren/data/stock_history.db')
BACKUPS=Path('/var/backups/torn-fren-ops')
EXPECTED={
 SERVICE_PATH:'597c08317097f5a95c2a3abcc39e44adfb9fcc3aa17c822fec4ea775a67add1b',
 BRIDGE:'8efb480cdab52a35f491db28daed8f8dfc6609c6b0536e206fea874268123cb3',
 JS:'f5032a800f29c0f52fa8c0280c14a1b549644aba8f52d6a5e77f4e14c73b492a'}


def digest(raw):return hashlib.sha256(raw).hexdigest()


def run(args,*,timeout=30,cwd=None,binary=False):
    result=subprocess.run(args,cwd=cwd,capture_output=True,timeout=timeout,text=not binary)
    if result.returncode:
        error=result.stderr.decode(errors='replace') if binary else result.stderr
        raise RuntimeError('command failed: '+' '.join(map(str,args[:3]))+'\n'+error[-6000:])
    return result.stdout


def atomic(path,raw):
    stat=path.stat();fd,tmp=tempfile.mkstemp(prefix='.refresh-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,stat.st_mode&0o777);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def stage(repo,commit):
    raw=run(['runuser','-u','ubuntu','--','git','-C',str(repo),'archive',commit],timeout=60,binary=True)
    if len(raw)>100*1024*1024:raise ValueError('Git archive exceeds reviewed bounds')
    files={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive:
            p=Path(member.name)
            if p.is_absolute() or '..' in p.parts or member.issym() or member.islnk():raise ValueError('unsafe Git archive path')
            if member.isdir():continue
            if not member.isfile():raise ValueError('unsupported Git archive member')
            files[member.name]=archive.extractfile(member).read()
    if len(files)>1500:raise ValueError('too many release files')
    original=BASE/'releases'/MODEL_SHA
    # The timing engines, event scheduler and historical input processing must
    # be byte-identical to the approved model source. Only delivery is repaired.
    frozen=[p for folder in ('services','research') for p in (original/folder).rglob('*.py')
            if p.relative_to(original).as_posix()!='services/first_release_live.py']
    frozen.append(original/'deploy/scripts/v163_readonly_event_first_preview.py')
    if not frozen:raise ValueError('approved frozen source unavailable')
    for p in frozen:
        name=p.relative_to(original).as_posix()
        if files.get(name)!=p.read_bytes():raise ValueError('frozen model source changed: '+name)
    release=BASE/'releases'/commit
    if release.is_symlink():raise ValueError('symlinked release refused')
    release.mkdir(parents=True,exist_ok=True)
    for name,raw in files.items():
        p=release/name
        if p.exists():
            if p.is_symlink() or not p.is_file() or p.read_bytes()!=raw:raise ValueError('existing staged code differs: '+name)
        else:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);os.chmod(p,0o644)
    os.chmod(release,0o755)
    for p in release.rglob('*'):
        if p.is_dir():os.chmod(p,0o755)
    return release,files,len(frozen)


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=12) as response:return response.read(8*1024*1024)


def health(commit):
    feed=json.loads(get('/api/first-release'))
    if feed.get('model_sha')!=MODEL_SHA or feed.get('publisher_sha')!=commit or feed.get('status')!='LIVE_BETA':
        raise ValueError('fresh reviewed publisher is not being served')
    refresh=feed.get('source_refresh') or {}
    if refresh.get('status')!='READ_ONLY_COLLECTOR_TAIL_APPLIED' or refresh.get('collector_written') is not False:
        raise ValueError('fresh read-only tail provenance missing')
    for route in ('/','/experimental','/travel-decisions'):
        if b'/first-release-assets/beta.js' not in get(route):raise ValueError('website route check failed: '+route)
    js=get('/first-release-assets/beta.js')
    if b'Stock data delayed' not in js or b'feedError=true' not in js:raise ValueError('refresh continuity UI not served')
    return {'status':feed['status'],'model_sha':feed['model_sha'],'publisher_sha':commit,
            'source_age_seconds':int(time.time())-feed['source_heartbeat_epoch'],
            'available_items':sum(r['decision'].get('estimated_departure_epoch') is not None for r in feed['rows']),
            'source_refresh':refresh,'recent_publications':feed.get('recent_publications',[])}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',required=True);parser.add_argument('--commit',required=True)
    args=parser.parse_args();changes=[];backup=None;paused=False;result={}
    try:
        if os.geteuid()!=0:raise PermissionError('sudo admin session required')
        if not re.fullmatch('[0-9a-f]{40}',args.commit):raise ValueError('full immutable Git commit required')
        repo=Path(args.repo).resolve(strict=True)
        if BASE.is_symlink():raise ValueError('ordinary live state directory required')
        for p,expected in EXPECTED.items():
            if p.is_symlink() or digest(p.read_bytes())!=expected:raise ValueError('installed file differs; preserve newer work: '+str(p))
        timer=run(['systemctl','show',TIMER,'--property=ActiveState,UnitFileState'])
        if 'ActiveState=active' not in timer or 'UnitFileState=enabled' not in timer:raise ValueError('existing publisher timer is not enabled and active')
        release,files,frozen_count=stage(repo,args.commit)
        print('Reviewed Git source staged; checking a fresh read-only publication...',file=sys.stderr,flush=True)
        parent=BACKUPS;parent.mkdir(parents=True,exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-refresh-',dir=parent))
        result={'status':'INSTALLING_REFRESH_REPAIR','publisher_sha':args.commit,'model_sha':MODEL_SHA,
                'evidence_series_preserved':True,'collector_modified':False,'github_actions_used':False,
                'frozen_model_files_verified':frozen_count,'backup_directory':str(backup),'old_jobs_retired':False}
        for p in EXPECTED:(backup/p.name).write_bytes(p.read_bytes())
        run(['systemctl','stop',TIMER]);paused=True
        run(['systemctl','stop',SERVICE],timeout=20)
        cmd=['flock','-w','10',str(BASE/'publisher.lock'),'runuser','-u','ubuntu','--','env',
             'PYTHONDONTWRITEBYTECODE=1','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',
             'TORNFREN_REPLAY_PINNED_RESEARCH='+str(BASE/'no-legacy-stage'),str(PYTHON),'-B','-m','services.first_release_live','publish',
             '--source',str(HISTORY),'--live-source',str(COLLECTOR),'--state',str(BASE),'--model-sha',MODEL_SHA,'--publisher-sha',args.commit]
        result['first_publication']=json.loads(run(cmd,timeout=65,cwd=release))
        sys.path.insert(0,str(release))
        from deploy.scripts.install_first_ten_beta import service_text
        service=service_text(release,MODEL_SHA).replace('--model-sha '+MODEL_SHA,
            '--model-sha '+MODEL_SHA+' --live-source '+str(COLLECTOR)+' --publisher-sha '+args.commit).encode()
        after={SERVICE_PATH:service,BRIDGE:files['web/first_release_bridge.py'],JS:files['web/first_release_assets/beta.js']}
        for p,raw in after.items():
            before=p.read_bytes();atomic(p,raw);changes.append((p,before,raw))
        run(['systemd-analyze','verify',str(SERVICE_PATH)])
        records={str(p):digest(raw) for p,raw in after.items()}
        rollback='''import hashlib,os,pathlib,subprocess
root=pathlib.Path(__file__).parent
records=RECORDS
if os.geteuid()!=0:raise SystemExit('Run with sudo')
for name,expected in records.items():
 p=pathlib.Path(name)
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise SystemExit('Refuse newer work: '+name)
subprocess.run(['systemctl','stop','TIMER'],check=True)
subprocess.run(['systemctl','stop','SERVICE'],check=True)
for name in records:
 p=pathlib.Path(name);s=p.stat();tmp=p.with_name('.rollback-'+p.name);tmp.write_bytes((root/p.name).read_bytes());os.chmod(tmp,s.st_mode&0o777);os.chown(tmp,s.st_uid,s.st_gid);os.replace(tmp,p)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','restart','WEB'],check=True)
subprocess.run(['systemctl','start','TIMER'],check=True)
print('REFRESH_REPAIR_ROLLED_BACK; evidence records preserved')
'''.replace('RECORDS',repr(records)).replace("'TIMER'",repr(TIMER)).replace("'SERVICE'",repr(SERVICE)).replace("'WEB'",repr(WEB))
        (backup/'rollback.py').write_text(rollback)
        result['rollback_command']='sudo python3 '+str(backup/'rollback.py')
        run(['systemctl','daemon-reload'])
        run(['systemctl','start',SERVICE],timeout=65)
        result['publisher_service']=run(['systemctl','show',SERVICE,'--property=Result,ExecMainStatus'])
        run(['systemctl','restart',WEB])
        for attempt in range(12):
            try:result['live_checks']=health(args.commit);break
            except Exception:
                if attempt==11:raise
                time.sleep(1)
        run(['systemctl','start',TIMER]);paused=False
        result['status']='REFRESH_REPAIR_INITIAL_CHECKS_PASSED'
        result['scheduled_cadence_verified']=False
    except Exception as error:
        result.update(status='REFRESH_REPAIR_STOPPED',error=str(error),collector_modified=False)
        try:
            for p,before,after in reversed(changes):
                if digest(p.read_bytes())!=digest(after):raise ValueError('rollback refuses newer changes: '+str(p))
                atomic(p,before)
            if changes:
                run(['systemctl','daemon-reload']);run(['systemctl','restart',WEB])
            result['code_rolled_back']=bool(changes)
        except Exception as restore_error:result['rollback_error']=str(restore_error)
    finally:
        if paused:
            try:run(['systemctl','start',TIMER])
            except Exception as restart_error:result['timer_restart_error']=str(restart_error)
        if backup:(backup/'refresh-repair.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    return 0 if result['status']=='REFRESH_REPAIR_INITIAL_CHECKS_PASSED' else 1

if __name__=='__main__':raise SystemExit(main())
