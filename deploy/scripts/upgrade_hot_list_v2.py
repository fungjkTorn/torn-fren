"""Pinned, hash-guarded Hot List upgrade. Standard library; preflight by default."""
import argparse
import ast
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

ROOT=Path('/opt/torn-fren')
BACKUPS=Path('/var/backups/torn-fren-ops')
SERVICE='torn-fren-web.service'
REVISION='1c2b8f3bf85ac8d58bf0e18fc5b7208e92eba122'
BASE='https://raw.githubusercontent.com/fungjkTorn/torn-fren/'+REVISION+'/'
MODULE='web/beanstalk_hot_list.py'
BRIDGE='web/first_release_bridge.py'
CORE='web/first_release_assets/hotlist-core.js'
EXPECTED={MODULE:'e251b5491fe323db44c0f00a122c51bfdbaee30b52e5da99c5749bf3aa99c93f',BRIDGE:'0af648371bf8ea0042c3e6c487d1dbcc51a6c84edd14e8306a83d3c43f59e5f5',CORE:'95d6c6281f32383d5759086b9c22e4ed6215157bb61c5e9e5aa116b191eebcd7'}
BLOBS={MODULE:'ca8b4c3ecdf6f64d4a3964f423922593b00df981',BRIDGE:'14c14fbf4ff32ed842b466e385bdbb32e99684fc',CORE:'0b891571e10dbe8a37bb81237b4eccc101dc35b0'}
START='            if path=="/api/beanstalk-hot-list":'
END='            if path=="/api/first-release/history-summary":'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def fetch(url):
    request=urllib.request.Request(url,headers={'Cache-Control':'no-cache','User-Agent':'TornFREN-HotList-Upgrade/2'})
    with urllib.request.urlopen(request,timeout=15) as r:
        raw=r.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise RuntimeError('Oversized response')
    return raw

def stage():
    old={};new={};stats={}
    for name,digest in EXPECTED.items():
        p=ROOT/name
        if p.is_symlink() or not p.is_file():raise RuntimeError('Not a regular file: '+name)
        old[name]=p.read_bytes();stats[name]=p.stat()
        if sha(old[name])!=digest:raise RuntimeError('Installed file changed since audit: '+name)
        raw=fetch(BASE+name)
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if blob!=BLOBS[name]:raise RuntimeError('Download failed pinned Git blob check: '+name)
        new[name]=raw
    original=old[BRIDGE].decode();target=new[BRIDGE].decode()
    if original.count(START)!=1 or original.count(END)!=1:raise RuntimeError('Ambiguous live handler')
    a=original.index(START);b=original.index(END,a)
    ta=target.index(START);tb=target.index(END,ta)
    legacy=original[a:b]
    if 'payload=await run_in_threadpool(public_hot_list)\n' not in legacy:raise RuntimeError('Unexpected live handler')
    new[BRIDGE]=(original[:a]+target[ta:tb]+original[b:]).encode()
    for name in (MODULE,BRIDGE):ast.parse(new[name].decode(),filename=name)
    return old,new,stats

def atomically(path,raw,st):
    fd,temp=tempfile.mkstemp(prefix='.hot-list-v2-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(temp,st.st_mode & 0o7777);os.chown(temp,st.st_uid,st.st_gid)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def restart():
    subprocess.run(['systemctl','restart',SERVICE],check=True,timeout=45)

def verify():
    last=None
    for attempt in range(20):
        try:
            if subprocess.run(['systemctl','is-active','--quiet',SERVICE]).returncode:raise RuntimeError('Web service inactive')
            v1=json.loads(fetch('http://127.0.0.1:8000/api/beanstalk-hot-list'))
            v2=json.loads(fetch('http://127.0.0.1:8000/api/beanstalk-hot-list?version=2'))
            now=time.time()
            for body,count,schema in [(v1,7,'v1'),(v2,8,'v2')]:
                picks=body.get('picks',[])
                if body.get('schema')!='torn-fren-beanstalk-hot-list-'+schema or body.get('status')!='OK' or len(picks)!=count:raise RuntimeError('Wrong live '+schema+' response')
                if len({p['item_key'] for p in picks})!=count:raise RuntimeError('Duplicate picks')
                expected={'xanax':count-6,'plushie':2,'flower':2,'nikeh':2}
                if any(sum(p['category']==k for p in picks)!=n for k,n in expected.items()):raise RuntimeError('Wrong category counts')
                if abs(now-body['generated_epoch'])>120:raise RuntimeError('Stale live feed')
            if v2.get('inventory_slots')!=15 or not v2.get('valid_until'):raise RuntimeError('Missing v2 metadata')
            for p in v2['picks']:
                if 'source_checked_at' not in p or 'departure_valid_until' not in p:raise RuntimeError('Missing timing metadata')
            catalog=json.loads(fetch('http://127.0.0.1:8000/api/catalog'))
            board=json.loads(fetch('http://127.0.0.1:8000/api/first-release'))
            if not catalog.get('countries') or not board.get('rows'):raise RuntimeError('Catalog or existing board unavailable')
            fetch('http://127.0.0.1:8000/experimental')
            served=fetch('http://127.0.0.1:8000/first-release-assets/hotlist-core.js')
            if "'uni:Xanax'" in served.decode().split('const HOT_EXCLUSIONS=new Set(',1)[1].split(';',1)[0]:raise RuntimeError('UK remains excluded in served browser asset')
            return {'v1_picks':7,'v2_picks':8,'generated_at':v2['generated_at'],'xanax':[{k:p[k] for k in ('destination','estimated_round_trip_profit_per_hour')} for p in v2['picks'] if p['category']=='xanax']}
        except Exception as e:
            last=e
            if attempt<19:time.sleep(2)
    raise RuntimeError('Live verification failed: '+str(last))

def install(apply=False):
    if os.geteuid()!=0:raise RuntimeError('Run through sudo python3')
    old,new,stats=stage()
    if not apply:return {'status':'PREFLIGHT_PASSED','revision':REVISION,'changed_files':list(new)}
    BACKUPS.mkdir(parents=True,exist_ok=True)
    saved=Path(tempfile.mkdtemp(prefix='hot-list-v2-',dir=BACKUPS));os.chmod(saved,0o700)
    manifest=[]
    for i,name in enumerate(new):
        backup=str(i)+'.bin';(saved/backup).write_bytes(old[name])
        manifest.append({'path':str(ROOT/name),'backup':backup,'installed_sha256':sha(new[name])})
    (saved/'rollback.json').write_text(json.dumps(manifest,indent=2))
    # Rollback uses this same pinned script and verifies no newer file exists.
    (saved/'upgrade.py').write_bytes(Path(__file__).read_bytes())
    report={'backup_directory':str(saved),'rollback_command':'sudo python3 '+str(saved/'upgrade.py')+' --rollback '+str(saved)}
    done=[]
    try:
        for name in (MODULE,CORE,BRIDGE):
            p=ROOT/name
            if p.is_symlink() or sha(p.read_bytes())!=sha(old[name]):raise RuntimeError('Concurrent edit: '+name)
            atomically(p,new[name],stats[name]);done.append(name)
        restart();report.update(status='DEPLOYED',live=verify())
    except Exception as e:
        report.update(status='ROLLED_BACK',error=str(e));failures=[]
        for name in reversed(done):
            try:
                p=ROOT/name
                if p.is_symlink() or sha(p.read_bytes())!=sha(new[name]):raise RuntimeError('Newer file detected')
                atomically(p,old[name],stats[name])
            except Exception as recovery:failures.append(name+': '+str(recovery))
        try:restart()
        except Exception as recovery:failures.append(str(recovery))
        if failures:report.update(status='MANUAL_RECOVERY_REQUIRED',rollback_errors=failures)
    (saved/'report.json').write_text(json.dumps(report,indent=2));return report

def rollback(saved):
    saved=Path(saved);rows=json.loads((saved/'rollback.json').read_text())
    for row in rows:
        p=Path(row['path'])
        if p.is_symlink() or sha(p.read_bytes())!=row['installed_sha256']:raise RuntimeError('Newer file detected: '+str(p))
    for row in reversed(rows):
        p=Path(row['path']);atomically(p,(saved/row['backup']).read_bytes(),p.stat())
    restart();return {'status':'ROLLBACK_COMPLETE'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback');args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run through sudo python3')
    with open('/run/lock/torn-fren-hot-list-v2.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=rollback(args.rollback) if args.rollback else install(args.apply)
        print(json.dumps(result,indent=2))
        raise SystemExit(0 if result['status'] in ('DEPLOYED','PREFLIGHT_PASSED','ROLLBACK_COMPLETE') else 1)
