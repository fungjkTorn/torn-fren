"""V167 event-candidate adapters for the current all-24 champion roster.

Legacy champion wrappers searched dense delay grids with short MAX_WAIT caps.
These adapters preserve each champion's scoring/configuration while replacing
that dense grid with event-derived candidate departure times. Thus calendar
lookahead is event-driven, not time-horizon-driven.

Research only. No production writes or automatic promotion.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from research.plushie_champions.common import (
    AnalogPlanner, ResearchContext, TemplatePlanner, TRAVEL_SECONDS, GRACE,
    gap_overlap,
)
from research.v38_v18_single_tick import V18_APPROVED
from research.v38_v19_single_tick import V19_APPROVED

V19_EXTRA={"can:Xanax":"dyn8","uni:Xanax":"dyn3"}
V20_EXTRA={"chi:Peony":"traj12"}

CHAMPION_KIND={
    **{k:"v18" for k in V18_APPROVED},
    **{k:"v19" for k in V19_APPROVED},
    **{k:"v19" for k in V19_EXTRA},
    **{k:"v20" for k in V20_EXTRA},
    "arg:Monkey Plushie":"checkpoint4_template",
    "swi:Chamois Plushie":"checkpoint4_template",
    "chi:Panda Plushie":"pair_analog",
    "sou:Lion Plushie":"pair_analog",
    "uae:Camel Plushie":"camel_template_bank",
    "uni:Nessie Plushie":"nessie_template",
    "uni:Red Fox Plushie":"redfox_analog",
    "jap:Xanax":"japan_quantity_rate",
}


def roster():
    if len(CHAMPION_KIND)!=24:
        raise ValueError(f"expected 24 champion identities, got {len(CHAMPION_KIND)}")
    return dict(CHAMPION_KIND)


def _candidate_delays(events,issued):
    rows=[]
    for e in events:
        dep=e.get("earliest_departure_epoch")
        if isinstance(dep,int) and dep>=issued:
            rows.append((dep-issued,e))
    rows.sort(key=lambda x:x[0])
    return rows


def _install_history(db):
    from services import history_service
    from services.frozen_candidate_worker_v31 import _install_frozen_readonly_history
    _install_frozen_readonly_history(history_service,db)
    return history_service


def _engine_choice(db,key,issued,events,generation,config_name):
    candidates=_candidate_delays(events,issued)
    if not candidates:
        return {"status":"NO_REACHABLE_EVENT_CANDIDATES","departure":None}
    country,item=key.split(":",1)
    history_service=_install_history(db)
    if generation=="v18":
        from services import plushie_flower_dynamic_planner_v18 as engine
        cleaned,cycles,_=engine.load_item(country,item,30)
        timeline=engine.Timeline(cleaned,cycles,30)
        deps,features=engine.completed_cycle_features(cycles)
    elif generation=="v19":
        from services import plushie_flower_dynamic_planner_v19 as engine
        cleaned,cycles,_bounces,gaps=engine.load_item(country,item,30)
        normalized=engine.normalize_gaps(history_service.get_collection_gaps())
        timeline=engine.Timeline(cleaned,cycles,30,gaps=normalized)
        deps,features=engine.completed_cycle_features(cycles,gaps=normalized)
    elif generation=="v20":
        from services import plushie_flower_dynamic_planner_v20 as engine
        cleaned,cycles,_bounces,gaps=engine.load_item(country,item,30)
        normalized=engine.normalize_gaps(history_service.get_collection_gaps())
        timeline=engine.Timeline(cleaned,cycles,30,gaps=normalized)
        deps,features=engine.completed_cycle_features(cycles,gaps=normalized)
    else:
        raise ValueError("unsupported dynamic generation")
    cfg=next((x for x in engine.configs() if x.name==config_name),None)
    if cfg is None:
        return {"status":"FROZEN_CONFIG_UNAVAILABLE","departure":None}
    points=engine.build_points(timeline,deps,features,600)
    if len(points)<60:
        return {"status":"INSUFFICIENT_HISTORICAL_FEATURES","departure":None}
    delays=[d for d,_ in candidates]
    proposal=engine.plan(
        float(issued),points,[p.t for p in points],timeline,deps,features,cfg,
        delays,int(TRAVEL_SECONDS[country]),10)
    if proposal is None:
        return {"status":"NO_RECOMMENDATION","departure":None}
    dep=int(proposal["departure_time"])
    event=min(candidates,key=lambda x:abs((issued+x[0])-dep))[1]
    return {
        "status":"EVENT_CANDIDATE_SELECTED",
        "departure":dep,
        "selected_event_index":event["event_index"],
        "score":proposal.get("probability"),
        "model_generation":generation.upper(),
        "model_config":config_name,
    }


def _template_probs(planner,q,candidates):
    refs=[]
    for d in planner.lags:
        fit,shift,raw=planner._best_ref(q,d)
        if fit>=planner.minfit:
            refs.append((d,shift,fit,raw))
    scored=[]
    for delay,event in candidates:
        arrival=q+planner.travel+delay
        num=den=0.0
        for d,shift,fit,raw in refs:
            z=planner._state(arrival-d*86400-shift)
            if z is None:
                continue
            w=fit*fit/d
            num+=w*int(z);den+=w
        if den:
            scored.append((delay,num/den,event))
    return scored,refs


def _template_choice(planner,q,candidates):
    scored,refs=_template_probs(planner,q,candidates)
    if not scored:
        return None
    best=max(x[1] for x in scored)
    # Same .04 near-best philosophy as TemplatePlanner, but candidate points
    # are restock events rather than every 5-minute delay.
    near=[x for x in scored if x[1]>=best-.04]
    delay,prob,event=min(near,key=lambda x:x[0])
    return delay,prob,event,refs


def _timeline_only(db,key):
    from research.plushie_champions.common import connect,load_gaps,Timeline
    country,item=key.split(":",1)
    con=connect(db)
    gs,ge=load_gaps(con)
    tl=Timeline(con,gs,ge,country,item)
    return con,SimpleNamespace(timelines={(country,item):tl})


def _checkpoint_choice(db,key,issued,events):
    from research.v166_seven_specialist_earliest_replay import _checkpoint4_single_tick
    picked=_checkpoint4_single_tick(db,key,issued)
    expert=picked.get("expert")
    if expert is None:
        return {"status":picked.get("status","CHECKPOINT4_NOT_READY"),"departure":None}
    candidates=_candidate_delays(events,issued)
    if not candidates:
        return {"status":"NO_REACHABLE_EVENT_CANDIDATES","departure":None}
    country,item=key.split(":",1)
    con,ctx=_timeline_only(db,key)
    try:
        p=TemplatePlanner(ctx,country,item,lags=expert[0],lookback=expert[1],
                          shift_range=expert[2])
        choice=_template_choice(p,issued,candidates)
    finally:
        con.close()
    if choice is None:
        return {"status":"CHECKPOINT4_EVENT_ABSTAIN","departure":None,
                "selected_expert":expert}
    delay,prob,event,_=choice
    return {"status":"EVENT_CANDIDATE_SELECTED","departure":issued+delay,
            "selected_event_index":event["event_index"],"score":prob,
            "selected_expert":expert,"model_generation":"CHECKPOINT4"}


def _nessie_choice(db,key,issued,events):
    from research.v38_nessie_single_tick import CONFIG
    candidates=_candidate_delays(events,issued)
    if not candidates:
        return {"status":"NO_REACHABLE_EVENT_CANDIDATES","departure":None}
    country,item=key.split(":",1)
    con,ctx=_timeline_only(db,key)
    try:
        p=TemplatePlanner(ctx,country,item,**CONFIG)
        choice=_template_choice(p,issued,candidates)
    finally:
        con.close()
    if choice is None:
        return {"status":"NESSIE_EVENT_ABSTAIN","departure":None}
    delay,prob,event,_=choice
    return {"status":"EVENT_CANDIDATE_SELECTED","departure":issued+delay,
            "selected_event_index":event["event_index"],"score":prob,
            "model_generation":"RECENT_PHASE_TEMPLATE"}


def _camel_choice(db,key,issued,events):
    from research.v38_camel_single_tick import EXPERTS
    candidates=_candidate_delays(events,issued)
    if not candidates:
        return {"status":"NO_REACHABLE_EVENT_CANDIDATES","departure":None}
    country,item=key.split(":",1)
    con,ctx=_timeline_only(db,key)
    try:
        choices=[]
        for expert in EXPERTS:
            p=TemplatePlanner(ctx,country,item,lags=expert[0],
                              lookback=expert[1],shift_range=expert[2])
            choice=_template_choice(p,issued,candidates)
            if choice is None:continue
            delay,prob,event,refs=choice
            maxfit=max((x[2] for x in refs),default=0.0)
            choices.append((prob,maxfit,-delay,expert,event))
    finally:
        con.close()
    if not choices:
        return {"status":"CAMEL_EVENT_ABSTAIN","departure":None}
    prob,maxfit,neg_delay,expert,event=max(choices,key=lambda x:(x[0],x[1],x[2]))
    delay=-neg_delay
    return {"status":"EVENT_CANDIDATE_SELECTED","departure":issued+delay,
            "selected_event_index":event["event_index"],"score":prob,
            "selected_expert":expert,
            "model_generation":"CAMEL_24_TEMPLATE_BANK"}


def _analog_with_delays(ctx,country,item,q,k,weight,candidates):
    planner=AnalogPlanner(ctx,country,item,k=k,global_weight=weight,cutoff=q)
    delays=np.array([d for d,_ in candidates],dtype=float)
    planner.delays=delays
    # AnalogPlanner's original path_ok was built for the legacy 8h grid.
    # Recompute it for the farthest event candidate so every historical
    # analogue has its complete candidate-arrival outcome resolved <= issue.
    max_delay=int(max(delays)) if len(delays) else 0
    planner.maxfuture=max_delay+planner.travel+GRACE
    planner.path_ok=np.array([
        not gap_overlap(ctx.gs,ctx.ge,t,t+planner.maxfuture)
        for t in ctx.grid
    ])
    result=planner.plan(float(q))
    if result is None:return None
    dep=int(result[0])
    event=min(candidates,key=lambda x:abs((q+x[0])-dep))[1]
    return dep,float(result[1]),event


def _redfox_choice(db,key,issued,events):
    candidates=_candidate_delays(events,issued)
    if not candidates:return {"status":"NO_REACHABLE_EVENT_CANDIDATES","departure":None}
    ctx=ResearchContext.build(db,asof=issued,readonly=True)
    try:
        result=_analog_with_delays(ctx,"uni","Red Fox Plushie",issued,18,.5,candidates)
    finally:
        ctx.con.close()
    if result is None:return {"status":"REDFOX_EVENT_ABSTAIN","departure":None}
    dep,score,event=result
    return {"status":"EVENT_CANDIDATE_SELECTED","departure":dep,
            "selected_event_index":event["event_index"],"score":score,
            "model_generation":"GLOBAL_REGIME_ANALOG"}


def _pair_choice(db,key,issued,events):
    from research.v49_lion_panda_pair_probe import TARGETS,original_features
    from research.v50_pair_selector_artifact import choose_from_features
    from research.v52_pair_trained_tick import load_pinned_artifact
    from research.v81_pair_forward_comparison import PINS
    candidates=_candidate_delays(events,issued)
    if not candidates:return {"status":"NO_REACHABLE_EVENT_CANDIDATES","departure":None}
    target="panda" if key.startswith("chi:") else "lion"
    artifact_root=Path(os.environ.get(
        "TORNFREN_SPECIALIST_ARTIFACTS","/home/ubuntu/torn-fren-private-models"))
    artifact=artifact_root/(target+"_selector_artifact.json")
    if not artifact.is_file():
        local=Path(__file__).resolve().parents[1]/"historical_pc_data"/(target+"_selector_artifact.json")
        artifact=local if local.is_file() else artifact
    if not artifact.is_file():
        return {"status":"MISSING_PINNED_SELECTOR_ARTIFACT","departure":None}
    model=load_pinned_artifact(artifact,PINS[target],target)
    config=TARGETS[target]
    country,item=config["key"].split(":",1)
    ctx=ResearchContext.build(db,asof=issued,readonly=True)
    try:
        original={}
        for name in ("a","b"):
            k,w=config["expert_"+name]
            original[name]=AnalogPlanner(ctx,country,item,k=k,global_weight=w,
                                         cutoff=issued).plan(float(issued))
        features=original_features(ctx,country,item,float(issued),
                                   original["a"],original["b"],target)
        selected="b" if choose_from_features(model,features) else "a"
        k,w=config["expert_"+selected]
        result=_analog_with_delays(ctx,country,item,issued,k,w,candidates)
    finally:
        ctx.con.close()
    if result is None:
        return {"status":"PAIR_EVENT_ABSTAIN","departure":None,
                "selected_expert":selected}
    dep,score,event=result
    return {"status":"EVENT_CANDIDATE_SELECTED","departure":dep,
            "selected_event_index":event["event_index"],"score":score,
            "selected_expert":selected,
            "model_generation":"PINNED_PAIR_SELECTOR"}


def choose_event(db,key,issued,events):
    """Return one champion-scored event candidate, with no calendar horizon."""
    kind=CHAMPION_KIND.get(key)
    if kind is None:return {"status":"NO_CHAMPION_IDENTITY","departure":None}
    if kind=="v18":
        return _engine_choice(db,key,issued,events,"v18",V18_APPROVED[key])
    if kind=="v19":
        config=V19_APPROVED.get(key) or V19_EXTRA.get(key)
        return _engine_choice(db,key,issued,events,"v19",config)
    if kind=="v20":
        return _engine_choice(db,key,issued,events,"v20",V20_EXTRA[key])
    if kind=="checkpoint4_template":
        return _checkpoint_choice(db,key,issued,events)
    if kind=="nessie_template":
        return _nessie_choice(db,key,issued,events)
    if kind=="camel_template_bank":
        return _camel_choice(db,key,issued,events)
    if kind=="redfox_analog":
        return _redfox_choice(db,key,issued,events)
    if kind=="pair_analog":
        return _pair_choice(db,key,issued,events)
    if kind=="japan_quantity_rate":
        # Japan Xanax uses the physical-zero quantity-rate event model itself.
        # Its candidate event list is already generated from that route by V167.
        event=next((e for e in events if e.get("reachable")),None)
        return {
            "status":"JAPAN_RATE_EVENT_SELECTED" if event else "JAPAN_RATE_EVENT_ABSTAIN",
            "departure":event.get("earliest_departure_epoch") if event else None,
            "selected_event_index":event.get("event_index") if event else None,
            "score":None,"model_generation":"JAPAN_QUANTITY_RATE",
        }
    raise ValueError("unsupported champion kind")
