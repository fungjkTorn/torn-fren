"""Admin-only guarded deployment for the audited ten-item live beta package.

Preserve the collector, bot, arbitrage, current local changes and old jobs.
Stage one bounded publisher run, validate systemd, smoke-test an owned local
server, then switch the website. Any deployment error restores the web app.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

BASE=Path('/var/lib/torn-fren-live-beta')
APP=Path('/opt/torn-fren/web/app.py')
EXPECTED_APP='86e84488655ab8e83fc86965c846f13ff17da27b0f8edbeac3bf5f3e583a2657'
WEB='torn-fren-web.service'
SERVICE='torn-fren-first-ten-beta.service'
TIMER='torn-fren-first-ten-beta.timer'
PYTHON=Path('/home/ubuntu/torn-fren-v38-probe/.venv/bin/python')
WEB_PYTHON=Path('/opt/torn-fren/venv/bin/python')
SOURCE=Path('/var/lib/torn-fren-research/stock_history_forward.db')
DROPIN=Path('/etc/systemd/system/torn-fren-web.service.d/90-first-ten-beta.conf')
HOOK=b'\n# First ten live beta bridge (guarded owner deployment).\nfrom web.first_release_bridge import install_first_release\ninstall_first_release(app)\n'


def digest(data):return hashlib.sha256(data).hexdigest()


def run(args,timeout=30,env=None):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout,env=env)
    if p.returncode:
        raise RuntimeError('command failed ('+str(p.returncode)+'): '+' '.join(args[:3])+'\n'+p.stderr[-2500:])
    return p.stdout


def health(port,expected_sha=None):
    result={}
    for path in ('/','/experimental','/travel-decisions','/api/first-release'):
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=10) as r:
            raw=r.read(8*1024*1024)
            if r.status!=200:raise ValueError('HTTP smoke failure: '+path)
        if path=='/api/first-release':
            board=json.loads(raw)
            if board['status']!='LIVE_BETA' or len(board['rows'])!=10:
                raise ValueError('beta feed is not fresh and complete')
            if expected_sha is not None and board['model_sha']!=expected_sha:
                raise ValueError('website is serving a different model revision')
            available=[r for r in board['rows'] if r['decision'].get('estimated_departure_epoch') is not None]
            if not available:raise ValueError('all ten forecasts are unavailable; refuse rollout')
            result['available_recommendations']=len(available)
            result['unavailable_items']=[r['item_key'] for r in board['rows'] if r not in available]
            result['model_sha']=board['model_sha'];result['items']=len(board['rows'])
        elif b'beta.js' not in raw:
            raise ValueError('view is not connected to the beta feed: '+path)
        result[path]='PASS'
    return result


def service_text(release,sha):
    return f'''[Unit]
Description=Torn Fren ten-item live beta publisher and forward evidence
After=local-fs.target
ConditionPathExists={SOURCE}
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
ExecStart=/usr/bin/flock -n {BASE}/publisher.lock {PYTHON} -B -m services.first_release_live publish --source {SOURCE} --state {BASE} --model-sha {sha}
Nice=19
CPUQuota=50%
MemoryMax=1024M
TimeoutStartSec=58
TimeoutStopSec=15
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths={BASE}
UMask=0022
'''


TIMER_TEXT='''[Unit]
Description=Refresh Torn Fren ten-item live beta every minute
[Timer]
OnCalendar=*-*-* *:*:20 UTC
AccuracySec=1s
Persistent=false
Unit=torn-fren-first-ten-beta.service
[Install]
WantedBy=timers.target
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',required=True)
    args=p.parse_args()
    if os.geteuid()!=0:raise PermissionError('admin sudo session required')
    if digest(APP.read_bytes())!=EXPECTED_APP:
        raise ValueError('website source changed since preflight; refusing to overwrite it')
    if BASE.is_symlink() or DROPIN.exists():raise ValueError('existing beta deployment requires review')
    for path in (PYTHON,WEB_PYTHON,SOURCE):
        if not path.is_file():raise ValueError('required runtime/source missing: '+str(path))
    web_props=run(['systemctl','show',WEB,'--property=User,WorkingDirectory,ActiveState'])
    if not all(x in web_props for x in ('User=ubuntu','WorkingDirectory=/opt/torn-fren','ActiveState=active')):
        raise ValueError('website service no longer matches preflight')
    with zipfile.ZipFile(args.package) as z:
        manifest=json.loads(z.read('manifest.json'))
        sha=manifest['model_sha']
        if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('invalid source pin')
        files={}
        for name,expected in manifest['files'].items():
            relative=Path(name)
            if not name.startswith('source/') or relative.is_absolute() or '..' in relative.parts:
                raise ValueError('unsafe release member')
            raw=z.read(name)
            if digest(raw)!=expected:raise ValueError('release checksum mismatch: '+name)
            files[name.removeprefix('source/')]=raw
    if len(files)>1500 or sum(map(len,files.values()))>100*1024*1024:
        raise ValueError('release package exceeds reviewed bounds')
    account=pwd.getpwnam('ubuntu')
    BASE.mkdir(mode=0o755,parents=True,exist_ok=True);os.chown(BASE,account.pw_uid,account.pw_gid)
    release=BASE/'releases'/sha
    if release.exists():
        if release.is_symlink() or any(not (release/name).is_file() or digest((release/name).read_bytes())!=digest(raw) for name,raw in files.items()):
            raise ValueError('existing staged release does not match this package')
    else:
        release.mkdir(parents=True)
        for name,raw in files.items():
            target=release/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw);os.chmod(target,0o644)
    for d in release.rglob('*'):
        if d.is_dir():os.chmod(d,0o755)
    parent=Path('/var/backups/torn-fren-ops');parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-first-ten-',dir=parent))
    original=APP.read_bytes();(backup/'app.py.original').write_bytes(original)
    changes=[]
    result={'status':'DEPLOYING','backup_directory':str(backup),'release_sha':sha,
            'production_collector_modified':False,'old_jobs_retired':False,'github_actions_used':False}
    def save(): (backup/'deployment.json').write_text(json.dumps(result,indent=2))
    def restore_files():
        for path,before,installed in reversed(changes):
            if path.exists() and digest(path.read_bytes())!=digest(installed):
                raise ValueError('rollback refuses to overwrite newer work: '+str(path))
            if before is None:path.unlink(missing_ok=True)
            else:path.write_bytes(before)
    def install(path,raw):
        path.parent.mkdir(parents=True,exist_ok=True)
        old=path.read_bytes() if path.exists() else None
        if old is not None and path!=APP:raise ValueError('existing target requires review: '+str(path))
        changes.append((path,old,raw));path.write_bytes(raw);os.chmod(path,0o644)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',TORNFREN_REPLAY_PINNED_RESEARCH=str(BASE/'no-legacy-stage'))
    web_changed=False
    try:
        print('Preparing the first fresh ten-item forecast and evidence log…',file=sys.stderr,flush=True)
        cmd=['runuser','-u','ubuntu','--','env','PYTHONDONTWRITEBYTECODE=1','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1','TORNFREN_REPLAY_PINNED_RESEARCH='+str(BASE/'no-legacy-stage'),str(PYTHON),'-B','-m','services.first_release_live','publish','--source',str(SOURCE),'--state',str(BASE),'--model-sha',sha]
        # The immutable checkout, not the production tree, supplies model code.
        old_cwd=Path.cwd();os.chdir(release)
        try:result['first_publication']=json.loads(run(cmd,timeout=60,env=env))
        finally:os.chdir(old_cwd)
        for name in ('web/first_release_bridge.py',):
            compile(files[name],name,'exec')
            install(Path('/opt/torn-fren')/name,files[name])
        for name,raw in files.items():
            if name.startswith('web/first_release_assets/'):
                install(Path('/opt/torn-fren')/name,raw)
        install(APP,original+HOOK);web_changed=True
        service_path=Path('/etc/systemd/system')/SERVICE
        timer_path=Path('/etc/systemd/system')/TIMER
        install(service_path,service_text(release,sha).encode())
        install(timer_path,TIMER_TEXT.encode())
        install(DROPIN,('[Service]\nEnvironment=TORN_FREN_V40_LIGHT_GRAPH=1\nEnvironment=TORN_FREN_FIRST_RELEASE_SNAPSHOT='+str(BASE/'latest.json')+'\n').encode())
        run(['systemd-analyze','verify',str(service_path),str(timer_path)])
        # Explicit rollback artifact, including guards against newer app edits.
        rollback=backup/'rollback.py'
        meta=[]
        for idx,(path,before,installed) in enumerate(changes):
            saved=backup/('original-'+str(idx))
            if before is not None:saved.write_bytes(before)
            meta.append({'path':str(path),'before':str(saved) if before is not None else None,'installed_sha':digest(installed)})
        (backup/'rollback-files.json').write_text(json.dumps(meta))
        rollback.write_text('''import hashlib,json,pathlib,subprocess
base=pathlib.Path(__file__).parent
subprocess.run(['systemctl','disable','--now','torn-fren-first-ten-beta.timer'],check=False)
subprocess.run(['systemctl','stop','torn-fren-first-ten-beta.service'],check=False)
for r in reversed(json.loads((base/'rollback-files.json').read_text())):
 p=pathlib.Path(r['path'])
 if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()!=r['installed_sha']:raise SystemExit('Refuse newer work: '+str(p))
 if r['before'] is None:p.unlink(missing_ok=True)
 else:p.write_bytes(pathlib.Path(r['before']).read_bytes())
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','restart','torn-fren-web.service'],check=True)
print('FIRST_TEN_BETA_ROLLED_BACK; evidence preserved')
''')
        result['rollback_command']='sudo python3 '+str(rollback)
        save()
        # Owned local smoke server; always terminated, never left detached.
        with (backup/'staging.log').open('wb') as log:
            process=subprocess.Popen(['runuser','-u','ubuntu','--','env','TORN_FREN_V40_LIGHT_GRAPH=1',str(WEB_PYTHON),'-B','-m','uvicorn','web.app:app','--host','127.0.0.1','--port','18020'],cwd='/opt/torn-fren',stdout=log,stderr=log,start_new_session=True)
            try:
                for attempt in range(20):
                    if process.poll() is not None:raise RuntimeError('staging web process exited; inspect '+str(backup/'staging.log'))
                    try:
                        result['staging_views']=health(18020,sha);break
                    except (OSError,ValueError):time.sleep(1)
                else:raise RuntimeError('staging website did not pass its route/feed checks')
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        run(['systemctl','daemon-reload'])
        print('Checking one real systemd publisher invocation…',file=sys.stderr,flush=True)
        run(['systemctl','start',SERVICE],timeout=65)
        result['publisher_service']=run(['systemctl','show',SERVICE,'--property=Result,ExecMainStatus,CPUUsageNSec,MemoryPeak'])
        run(['systemctl','enable','--now',TIMER])
        run(['systemctl','restart',WEB])
        for attempt in range(15):
            try:result['live_views']=health(8000,sha);break
            except (OSError,ValueError):time.sleep(1)
        else:raise RuntimeError('live website checks failed')
        with urllib.request.urlopen('http://127.0.0.1:8000/api/history?country=mex&item=Dahlia&minutes=5',timeout=15) as r:
            graph=json.load(r)
        if graph.get('analysis',{}).get('first_release',{}).get('item_key')!='mex:Dahlia':
            raise ValueError('live graph is not reading the beta feed')
        result['graph_api_bridge']='PASS'
        result['timer']=run(['systemctl','show',TIMER,'--property=ActiveState,UnitFileState,NextElapseUSecRealtime'])
        result['status']='FIRST_TEN_BETA_LIVE_INITIAL_CHECKS_PASSED'
        result['scheduled_cadence_verified']=False
        result['accuracy_verified']=False
        result['url']='https://tornfren.duckdns.org/experimental'
    except Exception as error:
        result['status']='DEPLOYMENT_STOPPED';result['error']=str(error)
        subprocess.run(['systemctl','disable','--now',TIMER],capture_output=True)
        subprocess.run(['systemctl','stop',SERVICE],capture_output=True)
        try:
            restore_files();run(['systemctl','daemon-reload'])
            if web_changed:run(['systemctl','restart',WEB])
            result['web_changes_rolled_back']=True
        except Exception as rollback_error:
            result['rollback_error']=str(rollback_error)
    finally:
        save();print(json.dumps(result,indent=2))
    return 0 if result['status']=='FIRST_TEN_BETA_LIVE_INITIAL_CHECKS_PASSED' else 1


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print(json.dumps({'status':'PREFLIGHT_STOPPED','error':str(e)}));sys.exit(1)
