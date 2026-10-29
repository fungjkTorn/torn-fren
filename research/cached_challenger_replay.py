"""Exact-output acceleration of the corrected replay, Linux isolated item process.

The native forecast is recomputed every issue with the same causal mirror and
config. Reuse imported modules and closed-interval collector query results only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import traceback
from types import SimpleNamespace
from unittest.mock import patch

from research.corrected_challenger_replay import run
from research.corrected_challengers import forecast,MODELS
from research.replay_history_acceleration import cached_history


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--item',required=True,choices=tuple(MODELS));p.add_argument('--max-seconds',type=int,default=14400)
    a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    hashes={Path(f).name:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in (__file__,Path(__file__).with_name('replay_history_acceleration.py'))}
    (root/(a.item.replace(':','__').replace(' ','_')+'.acceleration.json')).write_text(json.dumps(hashes,indent=2)+'\n')
    def alarm(signum,frame):raise subprocess.TimeoutExpired('cached native forecast',30)
    old=signal.signal(signal.SIGALRM,alarm)
    try:
        with cached_history() as advance:
            def worker(args,**kw):
                source=args[args.index('--worker')+1]
                key=args[args.index('--item')+1];issued=int(args[args.index('--issued')+1])
                advance(source,issued)
                signal.setitimer(signal.ITIMER_REAL,kw['timeout'])
                try:return SimpleNamespace(stdout=json.dumps(forecast(source,key,issued)))
                except subprocess.TimeoutExpired:raise
                except Exception as exc:
                    raise subprocess.CalledProcessError(1,args,stderr=traceback.format_exc()) from exc
                finally:signal.setitimer(signal.ITIMER_REAL,0)
            with patch('research.corrected_challenger_replay.subprocess.run',side_effect=worker):
                run(a.source,a.output,items=[a.item],max_seconds=a.max_seconds)
    finally:
        signal.signal(signal.SIGALRM,old)


if __name__=='__main__':main()
