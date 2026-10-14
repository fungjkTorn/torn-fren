"""Prepare one coherent shared event snapshot; no deployment or model promotion.

Explicit assignments only. Runs separately from web requests and never writes
the source database. The operator chooses an output JSON path and cadence.
"""
import argparse
import json
import os
import re
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

from deploy.scripts import v163_readonly_event_first_preview as model
from research.causal_phase_analogs import PhaseAnalogs
from research.true_zero_cycles import ZeroCycles
from services.travel_read_model import MAX_BYTES, build_board
from services.travel_window_policy import POLICIES


def prepare(source, *, model_sha, assignments=None, now=None, allow_legacy_availability_baselines=False):
    if not re.fullmatch('[0-9a-f]{40}', model_sha):
        raise ValueError('exact source SHA required')
    clock = int(time.time()) if now is None else now
    if type(clock) is not int or clock <= 0:
        raise ValueError('invalid issue clock')
    roster = set(model.exact_roster())
    assignments = assignments or {}
    if not isinstance(assignments,dict) or set(assignments)-roster:
        raise ValueError('assignment outside verified roster')
    for config in assignments.values():
        if (not isinstance(config,dict) or config.get('event_history') not in
            ('all_history','recent_8','phase_analogs_18','true_zero_all') or config.get('flight_adapter') not in POLICIES):
            raise ValueError('invalid explicit model assignment')
        if config['event_history']!='true_zero_all' and not allow_legacy_availability_baselines:
            raise ValueError('legacy availability clocks require explicit research-only opt-in')
    path = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=12)) as db:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        heartbeat = model.read_heartbeat(db)
        age = clock-heartbeat if type(heartbeat) is int else None
        if age is None or not 0 <= age <= 180:
            raise ValueError('source heartbeat too old for a current event snapshot')
        gaps = db.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?',
                          (clock,model.MAX_GAPS+1)).fetchall()
        if len(gaps)>model.MAX_GAPS:
            raise ValueError('collection gap cap exceeded')
        crosses = model._gap_index(gaps,clock)
        if crosses(clock,clock):
            raise ValueError('active collection outage')
        items={}; policies={}
        for key in sorted(roster):
            country,name=key.split(':',1)
            raw=db.execute('SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?',
                           (country,name,clock,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS:
                raise ValueError('stock history cap exceeded')
            phase=model._ReplayPhases(crosses)
            config=assignments.get(key,{'event_history':'true_zero_all','flight_adapter':'median'})
            analog=PhaseAnalogs(crosses) if config['event_history']=='phase_analogs_18' else None
            zero=ZeroCycles(crosses) if config['event_history']=='true_zero_all' else None
            for t,q,s in raw:
                if type(t) is not int or type(q) is not int or q<0 or not s:
                    raise ValueError('invalid stock history')
                obs=model.OBS(t,q,s); phase.add(obs)
                if analog is not None: analog.add(obs)
                if zero is not None: zero.add(obs)
            state=phase.asof()
            forecast=(zero.forecast(key,asof=clock) if zero is not None else
                      analog.forecast(key,state,asof=clock) if analog is not None else
                      model.predict_events(key,state,asof=clock,recent_cycles=8 if config['event_history']=='recent_8' else None))
            items[key]=forecast; policies[key]=config['flight_adapter']
    snapshot={'asof_epoch':clock,'source_heartbeat_age_seconds':age,
              'model_sha':model_sha,'model_version':'Explicit per-item research event policies',
              'items':items,'item_policies':policies,'item_assignments':assignments,
              'production_model_promoted':False,'calibration_state':'UNCALIBRATED'}
    build_board(snapshot,now=clock)  # Validate the exact consumer contract.
    return snapshot


def publish(snapshot, destination, *, source):
    output=Path(destination)
    if output.suffix!='.json' or output.is_symlink() or output.resolve()==Path(source).resolve():
        raise ValueError('output must be a separate non-symlink JSON snapshot')
    data=json.dumps(snapshot,sort_keys=True).encode()
    if len(data)>MAX_BYTES:
        raise ValueError('event snapshot cap exceeded')
    fd,tmp=tempfile.mkstemp(prefix='.event-snapshot-',dir=output.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,output)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--model-sha',required=True)
    parser.add_argument('--assignments',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-legacy-availability-baselines',action='store_true',help='Research-only comparison; default snapshots use physical zero clocks')
    args=parser.parse_args()
    assignments=json.loads(args.assignments.read_text()) if args.assignments else None
    snapshot=prepare(args.source,model_sha=args.model_sha,assignments=assignments,
                     allow_legacy_availability_baselines=args.allow_legacy_availability_baselines)
    publish(snapshot,args.output,source=args.source)
    print(json.dumps({'status':'RESEARCH_EVENT_SNAPSHOT_PREPARED','item_count':len(snapshot['items']),
                      'asof_epoch':snapshot['asof_epoch'],'deployment_performed':False}))
