#!/usr/bin/env python3
"""Install only admin-health files; default is a read-only deployment plan."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import urlopen
import zipfile

ROOT=Path('/opt/torn-fren')
BACKUP_ROOT=Path('/var/backups/torn-fren-ops')
FILES=('services/admin_health.py','services/admin_live_beta_health.py','web/static/admin.html')


def deploy(archive,apply=False,*,state=Path('/var/lib/torn-fren-live-beta')):
    with zipfile.ZipFile(archive) as z:
        content={name:z.read(name) for name in FILES}
    for name,data in content.items():
        if name.endswith('.py'):compile(data,name,'exec')
    if not (ROOT/'web/app.py').is_file():raise ValueError('unrecognized web installation')
    if 'build_admin_health' not in (ROOT/'web/app.py').read_text():raise ValueError('admin route unavailable')
    if any((ROOT/name).is_symlink() for name in FILES):raise ValueError('refuse symlinked deployment target')
    snapshot=state/'latest.json'
    expected=json.loads(snapshot.read_text())['model_sha']
    result={'status':'ADMIN_HEALTH_PLAN','files':list(FILES),'apply':apply,
        'collector_modified':False,'models_modified':False,'publisher_modified':False,
        'timers_modified':False,'disk_cleanup_performed':False,
        'sha256':{n:hashlib.sha256(b).hexdigest() for n,b in content.items()}}
    if not apply:return result
    if os.geteuid()!=0:raise PermissionError('root is required for the website files and restart')
    backup_root=BACKUP_ROOT;backup_root.mkdir(mode=0o700,parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%dT%H%M%SZ-',time.gmtime())+'admin-',dir=backup_root));backup.chmod(0o700)
    previous={n:(ROOT/n).read_bytes() if (ROOT/n).exists() else None for n in FILES}
    for name,data in previous.items():
        if data is not None:
            path=backup/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    result['backup_directory']=str(backup)
    def install(name,data):
        target=ROOT/name
        if data is None:
            if target.exists():target.unlink()
            return
        fd,path=tempfile.mkstemp(prefix='.admin-update-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data)
            os.chmod(path,0o644)
            if target.exists():
                s=target.stat();os.chown(path,s.st_uid,s.st_gid);os.chmod(path,s.st_mode&0o777)
            os.replace(path,target)
        finally:
            if Path(path).exists():Path(path).unlink()
    def restart():subprocess.run(['systemctl','restart','torn-fren-web.service'],check=True,capture_output=True,timeout=30)
    try:
        for name,data in content.items():install(name,data)
        restart();response=None
        for _ in range(10):
            try:
                with urlopen('http://127.0.0.1:8000/api/admin/health',timeout=4) as f:response=json.load(f)
                break
            except OSError:time.sleep(.5)
        if not response or response.get('live_beta',{}).get('model_sha')!=expected:
            raise ValueError('new admin API failed version/ledger snapshot preflight')
        if response.get('forecast_auditor',{}).get('scope')!='LEGACY_FORECAST_AUDITOR_NOT_CURRENT_LIVE_BETA':
            raise ValueError('new admin API marker missing')
        result.update(status='ADMIN_HEALTH_UPDATED',model_sha=expected,
            live_beta_status=response['live_beta']['status'],disk_health=response.get('disk_health'))
    except Exception as exc:
        for name,data in previous.items():install(name,data)
        restart();result.update(status='ADMIN_HEALTH_ROLLED_BACK',error_type=type(exc).__name__,error=str(exc))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True);p.add_argument('--apply',action='store_true')
    a=p.parse_args();r=deploy(a.archive,a.apply);print(json.dumps(r,indent=2))
    if r['status']=='ADMIN_HEALTH_ROLLED_BACK':raise SystemExit(1)
