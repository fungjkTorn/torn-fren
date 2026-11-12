"""Guarded assets-only update for an already installed first-ten beta.

No web Python, publisher, database, model, timer or service changes.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request
import zipfile

ASSETS=Path('/opt/torn-fren/web/first_release_assets')
BACKUPS=Path('/var/backups/torn-fren-ops')
NAMES=frozenset(('beta.css','beta.js','board.html'))
REVISION='compact-planner-v1'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def atomic_write(path,raw,stat):
    fd,tmp=tempfile.mkstemp(prefix='.ui-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,stat.st_mode & 0o777)
        os.chown(tmp,stat.st_uid,stat.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=15) as response:
        return response.read(8*1024*1024)


def health(files,model_sha):
    for name in NAMES-{'board.html'}:
        if digest(get('/first-release-assets/'+name))!=digest(files[name]):
            raise ValueError('website is serving a different asset: '+name)
    for path in ('/experimental','/travel-decisions'):
        if digest(get(path))!=digest(files['board.html']):
            raise ValueError('website is serving a different planner: '+path)
    if b'/first-release-assets/beta.js' not in get('/'):
        raise ValueError('stock graph bridge is not installed')
    feed=json.loads(get('/api/first-release'))
    if feed['model_sha']!=model_sha or len(feed['rows'])!=10:
        raise ValueError('running model feed changed during the UI update')
    return {'planner_routes':'PASS','stock_graph_bridge':'PASS',
            'assets':'PASS','model_sha':feed['model_sha'],'forecast_items':len(feed['rows'])}


def install(package):
    if os.geteuid()!=0:raise PermissionError('run through sudo')
    if ASSETS.is_symlink() or not ASSETS.is_dir():raise ValueError('ordinary installed asset directory required')
    with zipfile.ZipFile(package) as archive:
        if sum(i.file_size for i in archive.infolist())>2*1024*1024:
            raise ValueError('UI package exceeds bounds')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('ui_revision')!=REVISION or set(manifest['files'])!=NAMES:
            raise ValueError('wrong UI package')
        files={name:archive.read('assets/'+name) for name in NAMES}
        for name,raw in files.items():
            if digest(raw)!=manifest['files'][name]['sha256']:
                raise ValueError('package checksum mismatch: '+name)
    if any((ASSETS/name).is_symlink() or not (ASSETS/name).is_file() for name in NAMES):
        raise ValueError('ordinary installed assets required')
    before={name:(ASSETS/name).read_bytes() for name in NAMES}
    if before==files:
        return {'status':'UI_ALREADY_INSTALLED','ui_revision':REVISION,
                'health':health(files,manifest['expected_model_sha'])}
    for name,raw in before.items():
        if digest(raw)!=manifest['files'][name]['expected_installed_sha256']:
            raise ValueError('installed UI changed; refusing to overwrite '+name)
    feed=json.loads(get('/api/first-release'))
    if feed.get('model_sha')!=manifest['expected_model_sha']:
        raise ValueError('running model release differs from this update')
    BACKUPS.mkdir(mode=0o700,parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-ui-',dir=BACKUPS))
    stats={name:(ASSETS/name).stat() for name in NAMES}
    for name,raw in before.items():(backup/name).write_bytes(raw)
    rollback='''import hashlib,os,pathlib,sys
if os.geteuid()!=0:raise SystemExit('Run with sudo')
root=pathlib.Path(__file__).parent
records=RECORDS
for path,sha in records.items():
 p=pathlib.Path(path)
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise SystemExit('Refuse newer work: '+path)
for path in records:
 p=pathlib.Path(path);s=p.stat();tmp=p.with_name('.rollback-'+p.name)
 tmp.write_bytes((root/p.name).read_bytes());os.chmod(tmp,s.st_mode&0o777);os.chown(tmp,s.st_uid,s.st_gid);os.replace(tmp,p)
print('UI_ROLLBACK_COMPLETE')
'''.replace('RECORDS',repr({str(ASSETS/name):digest(raw) for name,raw in files.items()}))
    (backup/'rollback.py').write_text(rollback)
    result={'status':'UPDATING_UI','ui_revision':REVISION,'backup_directory':str(backup),
            'models_changed':False,'evidence_database_changed':False,
            'services_restarted':False,'old_jobs_retired':False,'github_actions_used':False,
            'rollback_command':'sudo python3 '+str(backup/'rollback.py')}
    changed=[]
    try:
        for name in ('beta.css','board.html','beta.js'):
            atomic_write(ASSETS/name,files[name],stats[name]);changed.append(name)
        result['health']=health(files,manifest['expected_model_sha'])
        result['status']='UI_UPDATE_CHECKS_PASSED'
    except Exception as error:
        result['status']='UI_UPDATE_STOPPED';result['error']=str(error)
        restored=[]
        for name in reversed(changed):
            if digest((ASSETS/name).read_bytes())!=digest(files[name]):
                raise RuntimeError('rollback refuses newer UI changes: '+name) from error
            atomic_write(ASSETS/name,before[name],stats[name]);restored.append(name)
        result['ui_rolled_back']=len(restored)==len(changed)
    (backup/'update.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',required=True)
    try:
        result=install(parser.parse_args().package)
    except Exception as error:
        result={'status':'UI_PREFLIGHT_STOPPED','error':str(error),'models_changed':False}
    print(json.dumps(result,indent=2))
    return 0 if result['status'] in ('UI_UPDATE_CHECKS_PASSED','UI_ALREADY_INSTALLED') else 1

if __name__=='__main__':raise SystemExit(main())
