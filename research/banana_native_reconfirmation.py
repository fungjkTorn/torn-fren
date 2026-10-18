"""Matched replanning validation of Banana's frozen earlier-window candidate.

Research only. Native model, raw-score .85 and leave-now controls use identical
issue clocks and source expiry. This is not a canary or a release qualification.
"""
import bisect
import json
import subprocess
import sys
from pathlib import Path

from research.matched_champion_audit import ISSUES,causal_copy,summarize
from research.execution_offset_study import bounded_departure,fixed_records,concentration
from research.japan_xanax.renewal_shadow import source_data,STEP,WAIT
from research.plushie_champions.common import TRAVEL_SECONDS


def run(source,out,*,model_sha):
    key='cay:Banana Orchid';out=Path(out)
    rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
    plans={};frozen=[]
    child="""import json,sys,types
provider=types.ModuleType('services.yata_api')
def forbidden(*a,**k):raise RuntimeError('HTTP forbidden in historical validation')
provider.get_country_stock=forbidden
sys.modules['services.yata_api']=provider
from research.template_window_study import strong_choices
print(json.dumps(strong_choices(sys.argv[1],'cay:Banana Orchid',int(sys.argv[2]))))
"""
    for i,issued in enumerate(range(ISSUES[0],ISSUES[-1]+WAIT+STEP,STEP)):
        db=out/'banana-causal.sqlite'
        try:
            causal_copy(source,db,issued)
            p=subprocess.run([sys.executable,'-B','-c',child,str(db),str(issued)],
                capture_output=True,text=True,timeout=20,check=True)
            choices=json.loads(p.stdout.strip().splitlines()[-1])
            # Include both screened thresholds; never hide the failed .70 arm.
            choices['leave_now_control']=issued+15
            pi=bisect.bisect_right(polls,issued)-1
            age=issued-polls[pi] if pi>=0 else None
            fresh=age is not None and 0<=age+15<=180 and not crosses(issued,issued)
            for mode,value in choices.items():
                dep=bounded_departure(issued,value) if fresh else None
                plans.setdefault(mode,[]).append((issued,dep,age))
                if issued in ISSUES:
                    outcome=evidence.score(dep+TRAVEL_SECONDS['cay'])[0] if dep is not None else 'ABSTAIN'
                    frozen.append(dict(issued=issued,mode=mode,departure=dep,outcome=outcome,status='FROZEN'))
            if i%24==0:print(json.dumps(dict(status='BANANA_REPLANNING',issued=issued,tick=i)),flush=True)
        finally:
            if db.exists():db.chmod(0o600);db.unlink()
    records=fixed_records(plans,ISSUES,cutoff,TRAVEL_SECONDS['cay'],evidence.score)
    return dict(item_key=key,model_sha=model_sha,truth_cutoff=cutoff,
        replanned=summarize(records),distinct=concentration(records),records=records,
        frozen=summarize(frozen),frozen_records=frozen,
        replan_seconds=STEP,source_expiry_seconds=180,maximum_wait_seconds=WAIT,
        physical_depletion_quantity=0,arrival_target=30,grace_seconds=10,
        automatic_promotion=False,independent_validation=False,
        limitation='Nine inspected historical starts; future-plan execution check only. Correlated simulations, not actual flights or calibrated probability.')
