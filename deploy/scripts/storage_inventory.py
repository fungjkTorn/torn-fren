#!/usr/bin/env python3
"""Bounded read-only storage inventory. Never deletes, rotates or vacuums data."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import time

PATHS=('/opt/torn-fren','/var/lib/torn-fren','/var/lib/torn-fren-live-beta',
       '/var/lib/torn-fren-research','/var/lib/torn-fren-v38',
       '/var/backups/torn-fren-ops','/home/ubuntu','/var/log','/var/cache/apt')


def inventory(verify_latest=False):
    usage=shutil.disk_usage('/')
    report={'generated_epoch':int(time.time()),'read_only':True,'deleted_files':0,
        'disk':{'used_bytes':usage.used,'free_bytes':usage.free,'total_bytes':usage.total,
                'used_percent':round(100*usage.used/usage.total,2)},'directories':[]}
    for name in PATHS:
        path=Path(name)
        if not path.exists():continue
        try:
            r=subprocess.run(['du','-x','-B1','--max-depth=1','--exclude=.ssh',name],
                capture_output=True,text=True,timeout=8,check=True)
            sizes=[]
            for line in r.stdout.splitlines():
                size,folder=line.split('\t',1);sizes.append({'path':folder,'bytes':int(size)})
            report['directories'].extend(sorted(sizes,key=lambda r:r['bytes'],reverse=True)[:20])
        except (subprocess.SubprocessError,ValueError,OSError) as e:
            report['directories'].append({'path':name,'status':'INCOMPLETE','error_type':type(e).__name__})
    backups=[]
    for path in Path('/var/lib/torn-fren/backups').glob('stock_history-*.db.gz'):
        if len(backups)>=2000:break
        if path.is_symlink():continue
        s=path.stat();backups.append({'name':path.name,'bytes':s.st_size,'modified_epoch':int(s.st_mtime)})
    backups.sort(key=lambda r:r['modified_epoch'])
    report['backups']={'files':backups,'count':len(backups),'total_bytes':sum(r['bytes'] for r in backups),
        'retention_not_changed':True,'inventory_cap':2000}
    if verify_latest and backups:
        path=Path('/var/lib/torn-fren/backups')/backups[-1]['name']
        count=0;deadline=time.monotonic()+15
        try:
            with gzip.open(path,'rb') as f:
                while True:
                    block=f.read(1024*1024)
                    if not block:break
                    count+=len(block)
                    if count>2*1024**3 or time.monotonic()>deadline:raise TimeoutError('backup verification limit')
            report['backups']['latest_gzip_integrity']='PASS'
        except (OSError,EOFError,TimeoutError):report['backups']['latest_gzip_integrity']='FAILED_OR_LIMIT_EXCEEDED'
        report['backups']['sqlite_restore_verified']=False
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify-latest-gzip',action='store_true')
    print(json.dumps(inventory(p.parse_args().verify_latest_gzip),indent=2))
