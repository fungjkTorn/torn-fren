"""Run isolated next-six weekly replays, merge archives, and apply live V5 scoring."""
import argparse
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from research.corrected_challengers import NEXT_SIX_MODELS
from research.rescore_saved_challengers import rescore,load_archive


def run(source,output,workers=3):
    source=Path(source).resolve(strict=True);output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    started=time.monotonic()
    def worker(key):
        name=key.replace(':','__').replace(' ','_');directory=output/'items'/name
        directory.mkdir(parents=True,exist_ok=True)
        pilot=output/'pilots'/name
        with (directory/'pilot.log').open('w') as log:
            subprocess.run([sys.executable,'-m','research.corrected_challenger_replay',
                '--source',str(source),'--output',str(pilot),'--item',key,'--pilot'],
                cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
        entry=json.loads((pilot/(name+'.jsonl')).read_text().splitlines()[0])
        if entry['status']=='MODEL_ERROR':raise ValueError('pilot failed: '+key+' '+str(entry.get('detail')))
        print(json.dumps({'status':'PILOT_PASSED','item':key,'seconds':entry['seconds']}),flush=True)
        with (directory/'replay.log').open('a') as log:
            subprocess.run([sys.executable,'-m','research.cached_challenger_replay',
                '--source',str(source),'--output',str(directory),'--item',key,'--max-seconds','14400'],
                cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
        manifest,records,_=load_archive(directory)
        print(json.dumps({'status':'ITEM_COMPLETED','item':key,'clocks':len(records[key])}),flush=True)
        return directory,manifest
    completed=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(worker,key):key for key in NEXT_SIX_MODELS}
        while pending:
            done,_=wait(pending,timeout=45,return_when=FIRST_COMPLETED)
            if not done:
                counts={}
                for key in pending.values():
                    name=key.replace(':','__').replace(' ','_');path=output/'items'/name/(name+'.jsonl')
                    counts[key]=sum(1 for _ in path.open()) if path.exists() else 0
                print(json.dumps({'status':'REPLAY_PROGRESS','elapsed_seconds':round(time.monotonic()-started),'clocks':counts}),flush=True)
            for job in done:
                completed.append(job.result());del pending[job]
    archive=output/'archive';archive.mkdir(exist_ok=True)
    baseline=None;models={}
    for directory,manifest in completed:
        shared={k:v for k,v in manifest.items() if k!='models'}
        if baseline is None:baseline=shared
        if shared!=baseline:raise ValueError('individual replay contracts differ')
        for key,identity in manifest['models'].items():
            if key in models:raise ValueError('duplicate replay item')
            models[key]=identity;name=key.replace(':','__').replace(' ','_')+'.jsonl'
            shutil.copyfile(directory/name,archive/name)
    if set(models)!=set(NEXT_SIX_MODELS):raise ValueError('missing item archive')
    (archive/'manifest.json').write_text(json.dumps({**baseline,'models':models},indent=2)+'\n')
    load_archive(archive)
    result=rescore(source,archive,output/'scored')
    print(json.dumps({'status':'NEXT_SIX_WEEK_RESCORED','elapsed_seconds':round(time.monotonic()-started),'result':str(output/'scored/results.json')}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--workers',type=int,choices=(1,2,3),default=3);a=p.parse_args();run(a.source,a.output,a.workers)
