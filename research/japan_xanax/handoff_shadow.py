"""Additional paired Japan handoff shadow; keep full-roster recorder running."""
import argparse
import json
import os
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,STEP,WAIT,ROOT,source_data,rate_plan
from research.japan_xanax.zero_handoff import ZeroAnchor

MODES=('sequence_blocks_peak','zero_handoff180','rate_current_quarter','leave_now_control')


def issued_plans(source,issued):
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    rows,polls,crosses,evidence,cutoff=source_data(source,now=issued,item_key=KEY)
    age=issued-cutoff
    if not 0<=age<=180:raise ValueError('Source heartbeat stale')
    h=History(crosses);anchor=ZeroAnchor(crosses,180);rate=QuantityRateCycles(crosses)
    for row in rows:h.add(row);anchor.add(row);rate.add(OBS(*row))
    baseline=h.plans(issued,poll_age=age);view,borrowed=anchor.phase_view(h)
    alternate=view.plans(issued,poll_age=age)['sequence_blocks_peak'] if borrowed else baseline['sequence_blocks_peak']
    return {m:dict(v) for m,v in [('sequence_blocks_peak',baseline['sequence_blocks_peak']),
        ('zero_handoff180',dict(alternate,borrowed_zero_phase=borrowed,provider_handoff_max_seconds=180)),
        ('rate_current_quarter',rate_plan(rate,KEY,issued,age)),('leave_now_control',baseline['leave_now_control'])]},cutoff


def record(source,journal,*,model_sha,duration=28800):
    if not 60<=duration<=86400:raise ValueError('Bounded recording duration required')
    source=Path(source).resolve(strict=True);journal=Path(journal).resolve()
    if journal.exists() or journal.suffix!='.sqlite' or journal.is_symlink() or journal==source:raise ValueError('New separate journal required')
    os.umask(0o077)
    with closing(sqlite3.connect(journal)) as db:
        db.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE plans(issued INTEGER,item_key TEXT,mode TEXT,record TEXT,PRIMARY KEY(issued,item_key,mode));')
        db.execute('INSERT INTO metadata VALUES(?,?)',('model_sha',model_sha));db.commit()
        deadline=time.monotonic()+duration
        while time.monotonic()<deadline:
            began=time.monotonic();issued=int(time.time())
            try:
                selected,cutoff=issued_plans(source,issued);published=int(time.time())
                if not 0<=published-issued<=30 or published-cutoff>180:raise ValueError('Stale or delayed publication')
                if set(selected)!=set(MODES):raise ValueError('Paired model roster mismatch')
                with db:
                    for mode,p in selected.items():
                        dep=p['departure'];dep=max(dep,issued+15,published) if dep is not None else None
                        if dep is not None and dep>issued+WAIT:
                            p=dict(p,status='ABSTAIN_OUTSIDE_EIGHT_HOUR_HORIZON');dep=None
                        r=dict(p,departure=dep,published=published,issued=issued,item_key=KEY,mode=mode,
                            model_sha=model_sha,source_cutoff=cutoff,poll_age_seconds=issued-cutoff,
                            arrival=dep+FLIGHT if dep is not None else None,flight_seconds=FLIGHT,
                            target_quantity=30,depletion_stock_quantity=0,grace_seconds=10,
                            website_publication=False,actual_gameplay=False,
                            execution='FROZEN_SHADOW_PLAN_FUTURE_RECONFIRMATION_UNTESTED')
                        db.execute('INSERT INTO plans VALUES(?,?,?,?)',(issued,KEY,mode,json.dumps(r,sort_keys=True)))
                print(json.dumps(dict(status='JAPAN_PAIRED_HANDOFF_RECORDED',issued=issued,models=len(selected),publication_seconds=published-issued)),flush=True)
            except (OSError,ValueError,sqlite3.Error) as e:
                print(json.dumps(dict(status='JAPAN_PAIRED_HANDOFF_UNAVAILABLE',issued=issued,error=str(e)[:160])),flush=True)
            elapsed=time.monotonic()-began;time.sleep(min(max(0,deadline-began-elapsed),max(1,STEP-elapsed)))


def score(source,journal,*,model_sha):
    from research.shadow_scorecard import report
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    result=report(source,journal,expected_model_sha=model_sha)
    with closing(sqlite3.connect(Path(journal).resolve(strict=True).as_uri()+'?mode=ro',uri=True)) as db:
        records=[json.loads(r[0]) for r in db.execute('SELECT record FROM plans ORDER BY issued,item_key,mode LIMIT 100001')]
    if len(records)>100000:raise ValueError('Journal cap exceeded')
    if result['records']!=len(records):raise ValueError('Journal changed during scoring; retry')
    _,_,_,evidence,cutoff=source_data(source,item_key=KEY)
    modes={r['mode'] for r in records};cohorts={};replanned={}
    for mode in sorted(modes):
        values=[(r['issued'],r['departure'],r['poll_age_seconds']) for r in records if r['mode']==mode]
        followup=min(cutoff,values[-1][0]+STEP-1)
        c=[];replanned[mode]=evaluate_all_starts(values,cutoff=followup,flight_seconds=FLIGHT,score=evidence.score,cohorts=c);cohorts[mode]=c
    result['replanned_five_minute_starts']=replanned
    if 'sequence_blocks_peak' in cohorts:
        result['replanned_paired_vs_sequence']={m:compare_cohorts(cohorts['sequence_blocks_peak'],c) for m,c in cohorts.items() if m!='sequence_blocks_peak'}
    result['replanned_limitation']='Recorded advice replay only, no actual flights. Incomplete recorded 8h follow-up remains pending even when later truth is mature; source freshness enforced at simulated departure. Frozen and replanned metrics are separate. Only successfully recorded issue starts are scored; capture outages are logged separately.'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('record','score'))
    p.add_argument('--source',required=True);p.add_argument('--journal',required=True);p.add_argument('--model-sha',required=True)
    p.add_argument('--duration-seconds',type=int,default=28800);a=p.parse_args()
    sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    if sha!=a.model_sha:raise ValueError('Pinned checkout mismatch')
    if a.action=='record':record(a.source,a.journal,model_sha=sha,duration=a.duration_seconds)
    else:print(json.dumps(score(a.source,a.journal,model_sha=sha),indent=2,sort_keys=True))


if __name__=='__main__':main()
