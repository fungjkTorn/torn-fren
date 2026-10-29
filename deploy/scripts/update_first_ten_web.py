"""Guarded Git deployment for beta website files; publisher and models untouched."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

ROOT=Path('/opt/torn-fren')
BACKUPS=Path('/var/backups/torn-fren-ops')
ALLOWED=frozenset(('web/first_release_bridge.py','web/first_release_assets/beta.js','web/first_release_assets/beta.css'))
WEB='torn-fren-web.service'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def run(args,timeout=30):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    if p.returncode:raise RuntimeError('command failed: '+' '.join(args[:3])+'\n'+p.stderr[-3000:])
    return p.stdout


def git_file(repo,commit,name):
    raw=run(['runuser','-u','ubuntu','--','git','-C',str(repo),'show',commit+':'+name]).encode('utf-8')
    if len(raw)>1024*1024:raise ValueError('website source exceeds bounds')
    return raw


def load_release(repo,commit):
    manifest=json.loads(git_file(repo,commit,'deploy/first_ten_web_update.json'))
    if manifest.get('schema_version')!=1 or set(manifest['files'])!=ALLOWED:
        raise ValueError('unsupported website update manifest')
    for field in ('model_sha','expected_publisher_sha'):
        if not re.fullmatch('[0-9a-f]{40}',manifest[field]):raise ValueError('invalid model or publisher pin')
    files={name:git_file(repo,commit,name) for name in ALLOWED}
    for name,raw in files.items():
        if digest(raw)!=manifest['files'][name]['sha256']:raise ValueError('Git website checksum mismatch: '+name)
    compile(files['web/first_release_bridge.py'],'web/first_release_bridge.py','exec')
    return manifest,files


def atomic(path,raw):
    stat=path.stat();fd,tmp=tempfile.mkstemp(prefix='.web-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,stat.st_mode&0o777);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=12) as r:return r.read(8*1024*1024)


def health(manifest,files):
    feed=json.loads(get('/api/first-release'))
    if feed.get('ui_revision')!=manifest['ui_revision']:raise ValueError('updated graph bridge not loaded')
    if feed.get('model_sha')!=manifest['model_sha'] or feed.get('publisher_sha')!=manifest['expected_publisher_sha']:
        raise ValueError('model or publisher changed during website update')
    for name in ('beta.css','beta.js'):
        if digest(get('/first-release-assets/'+name))!=digest(files['web/first_release_assets/'+name]):
            raise ValueError('updated website asset not served: '+name)
    for route in ('/','/experimental','/travel-decisions'):
        if b'/first-release-assets/beta.js' not in get(route):raise ValueError('website route failed: '+route)
    return {'ui_revision':feed['ui_revision'],'publisher_sha':feed['publisher_sha'],
            'model_sha':feed['model_sha'],'routes':'PASS','assets':'PASS','feed_status':feed['status']}


def install(repo,commit):
    if os.geteuid()!=0:raise PermissionError('run through sudo')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('immutable Git commit required')
    manifest,files=load_release(repo,commit)
    for name in ALLOWED:
        if (ROOT/name).is_symlink() or not (ROOT/name).is_file():raise ValueError('ordinary installed website files required')
    before={name:(ROOT/name).read_bytes() for name in ALLOWED}
    if before==files:return {'status':'WEB_ALREADY_INSTALLED','checks':health(manifest,files)}
    for name,raw in before.items():
        if digest(raw)!=manifest['files'][name]['previous_sha256']:
            raise ValueError('website file changed; refusing to overwrite '+name)
    current=json.loads(get('/api/first-release'))
    if current.get('model_sha')!=manifest['model_sha'] or current.get('publisher_sha')!=manifest['expected_publisher_sha']:
        raise ValueError('running publisher differs from the reviewed deployment')
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-graph-windows-',dir=BACKUPS))
    for name,raw in before.items():(backup/Path(name).name).write_bytes(raw)
    records={str(ROOT/name):digest(raw) for name,raw in files.items()}
    rollback='''import hashlib,os,pathlib,subprocess
if os.geteuid()!=0:raise SystemExit('Run with sudo')
root=pathlib.Path(__file__).parent
records=RECORDS
for name,sha in records.items():
 p=pathlib.Path(name)
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise SystemExit('Refuse newer work: '+name)
for name in records:
 p=pathlib.Path(name);s=p.stat();tmp=p.with_name('.rollback-'+p.name);tmp.write_bytes((root/p.name).read_bytes());os.chmod(tmp,s.st_mode&0o777);os.chown(tmp,s.st_uid,s.st_gid);os.replace(tmp,p)
subprocess.run(['systemctl','restart','torn-fren-web.service'],check=True)
print('WEBSITE_ROLLED_BACK; publisher and evidence untouched')
'''.replace('RECORDS',repr(records))
    (backup/'rollback.py').write_text(rollback)
    result={'status':'UPDATING_WEBSITE','ui_revision':manifest['ui_revision'],'web_commit':commit,
            'backup_directory':str(backup),'rollback_command':'sudo python3 '+str(backup/'rollback.py'),
            'models_changed':False,'publisher_changed':False,'evidence_changed':False,'collector_changed':False,'github_actions_used':False}
    changed=[]
    try:
        for name in sorted(ALLOWED):atomic(ROOT/name,files[name]);changed.append(name)
        run(['systemctl','restart',WEB])
        for attempt in range(10):
            try:result['checks']=health(manifest,files);break
            except Exception:
                if attempt==9:raise
                time.sleep(1)
        result['status']='WEB_UPDATE_CHECKS_PASSED'
    except Exception as error:
        result.update(status='WEB_UPDATE_STOPPED',error=str(error))
        for name in reversed(changed):
            if digest((ROOT/name).read_bytes())!=digest(files[name]):raise ValueError('rollback refuses newer website work: '+name) from error
            atomic(ROOT/name,before[name])
        run(['systemctl','restart',WEB]);result['website_rolled_back']=True
    (backup/'website-update.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',required=True);p.add_argument('--commit',required=True);args=p.parse_args()
    try:result=install(Path(args.repo).resolve(strict=True),args.commit)
    except Exception as error:result={'status':'WEB_PREFLIGHT_OR_RECOVERY_STOPPED','error':str(error)}
    print(json.dumps(result,indent=2))
    return 0 if result['status'] in ('WEB_UPDATE_CHECKS_PASSED','WEB_ALREADY_INSTALLED') else 1

if __name__=='__main__':raise SystemExit(main())
