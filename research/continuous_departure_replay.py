"""Causal every-five-minute historical policy replay, never live issuance.

One read-only SQLite transaction; issue clocks do not depend on outcomes.
Global successful heartbeats corroborate carried-forward item deltas, but
cannot establish per-country upstream freshness or a successful purchase.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import sqlite3
import sys
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from deploy.scripts import v163_readonly_event_first_preview as model
from services.travel_decision_contract_v166 import build_item_travel_decision
from research.causal_daily_template import DailyTemplate
from research.causal_phase_analogs import PhaseAnalogs
from research.departure_reconfirmation import evaluate as evaluate_reconfirmation, compare as compare_reconfirmation
from research.depletion_timing_audit import (observed_depletions, predicted_depletions, observed_restocks,
    observed_availability_losses, predicted_availability_losses, count_events)
from research.true_zero_cycles import ZeroCycles
from research.quantity_rate_cycles import QuantityRateCycles
from research.zero_component_hybrids import ComponentHybrid
from research.causal_policy_selector import CausalPolicySelector
from research.causal_stock_paths import CausalStockPaths
from services.travel_window_policy import project_policy
from research.v151_stable_earliest_departure import stable_earliest_departure

POLICIES = (("v166_all_history", None, "median"),
            ("quarter_buffer_all_history", None, "quarter"),
            ("midpoint_all_history", None, "midpoint"),
            ("midpoint_recent_8", 8, "midpoint"),
            ("late_onset_all_history", None, "late"),
            ("quarter_with_current_stock", None, "current_quarter"),
            ("daily_template_earliest", None, "template_earliest"),
            ("daily_template_center", None, "template_center"),
            ("daily_template_first_window", None, "template_first_center"),
            ("daily_event_quarter", None, "quarter"),
            ("daily_event_current_quarter", None, "current_quarter"),
            ("v151_independent_48", None, "v151"),
            ("phase_analog_quarter", None, "quarter"),
            ("phase_analog_midpoint", None, "midpoint"),
            ("phase_analog_current_quarter", None, "current_quarter"),
            ("phase_recent64_quarter", None, "quarter"),
            ("phase_recent64_midpoint", None, "midpoint"),
            ("phase_recent64_current_quarter", None, "current_quarter"),
            ("zero_anchored_quarter", None, "quarter"),
            ("zero_anchored_midpoint", None, "midpoint"),
            ("zero_anchored_current_quarter", None, "current_quarter"),
            ("zero_rate_quarter", None, "quarter"),
            ("zero_rate_midpoint", None, "midpoint"),
            ("zero_rate_current_quarter", None, "current_quarter"))
HYBRID_FAMILIES=tuple("zero_hybrid_"+mode for mode in ComponentHybrid.MODES)
POLICIES += tuple((family+"_"+kind,None,kind) for family in HYBRID_FAMILIES
                  for kind in ("quarter","midpoint","current_quarter"))
SELECTOR_EXPERTS=("zero_anchored_current_quarter","zero_anchored_midpoint",
                  "zero_rate_current_quarter","zero_rate_midpoint")+tuple(
                  family+"_"+kind for family in HYBRID_FAMILIES
                  for kind in ("midpoint","current_quarter"))
POLICIES += (("zero_adaptive_selector",None,"selector"),)
POLICIES += tuple(("zero_path_"+mode,None,"path_"+mode) for mode in CausalStockPaths.MODES)
ZERO_COMPARATORS={p:("zero_anchored_midpoint" if p.endswith("_midpoint") else
                    "zero_anchored_quarter" if p.endswith("_quarter") and not p.endswith("_current_quarter") else
                    "zero_anchored_current_quarter")
                  for p,_,_ in POLICIES if p.startswith(("zero_rate_","zero_hybrid_","zero_adaptive_","zero_path_"))}
ZERO_FAMILIES=("zero_anchored","zero_rate")+HYBRID_FAMILIES
MAX_POLLS = 400000
VERSION = "continuous_departure_replay_v1"


class ArrivalEvidence:
    """Indexed poll-backed availability; reject hidden threshold excursions."""
    def __init__(self, observations, polls, gaps, cutoff):
        self.rows = observations
        self.times = [r.epoch for r in observations]
        self.polls = polls
        self.crosses = model._gap_index(gaps, cutoff)
        self.cutoff = cutoff

    def score(self, arrival):
        if self.cutoff < arrival + model.GRACE + 180:
            return "PENDING", "ARRIVAL_NOT_MATURE", None
        i = bisect.bisect_right(self.polls, arrival) - 1
        j = bisect.bisect_left(self.polls, arrival + model.GRACE)
        if i < 0 or j >= len(self.polls):
            return "UNKNOWN", "NO_POLL_BRACKET", None
        before, after = self.polls[i], self.polls[j]
        if arrival - before > 180 or after - arrival - model.GRACE > 180:
            return "UNKNOWN", "SPARSE_POLL_BRACKET", None
        if self.crosses(before, after):
            return "UNKNOWN", "COLLECTION_GAP", None
        a = bisect.bisect_right(self.times, before) - 1
        b = bisect.bisect_right(self.times, after) - 1
        if a < 0 or b < 0:
            return "UNKNOWN", "NO_STOCK_STATE", None
        if max(before-self.times[a], after-self.times[b]) > 86400:
            return "UNKNOWN", "STOCK_STATE_OLDER_THAN_24H", None
        segment = self.rows[a:b+1]
        if len({r.source for r in segment}) != 1:
            return "UNKNOWN", "ITEM_PROVIDER_SWITCH", None
        qualifying = {r.quantity >= 30 for r in segment}
        if len(qualifying) != 1:
            return "UNKNOWN", "THRESHOLD_TRANSITION_IN_BRACKET", None
        available = qualifying.pop()
        return ("SUCCESS" if available else "FAILURE"), "POLL_BACKED_DELTA_STATE", {
            "pre_poll": before, "post_poll": after,
            "pre_quantity": self.rows[a].quantity,
            "post_quantity": self.rows[b].quantity,
            "item_provider": self.rows[a].source,
        }


def choose(forecast, issued, poll_age, kind, template=None, v151=None):
    """Choose using issued events only; no truth or future stock argument."""
    decision = build_item_travel_decision(
        forecast, now=issued, poll_age_seconds=poll_age)
    healthy=poll_age is not None and 0<=poll_age<=180
    flight=decision["player_flight_seconds"]
    if kind=="v151":
        candidate=v151.get("first_reachable") if v151 and healthy else None
        departure=candidate.get("departure_epoch") if candidate else None
        return dict(decision,estimated_departure_epoch=departure,
                    estimated_arrival_epoch=departure+flight+model.GRACE if departure is not None else None,
                    selected_restock_event_index=None,
                    status=v151["status"] if v151 and healthy else "STALE_DATA",
                    scenario_support=candidate.get("scenario_stock_fraction") if candidate else None)
    if kind.startswith("template_"):
        departure=template.get(kind.split("_",1)[1]) if template and healthy else None
        return dict(decision,estimated_departure_epoch=departure,
                    estimated_arrival_epoch=departure+flight+model.GRACE if departure is not None else None,
                    selected_restock_event_index=None,
                    status=template["status"] if template and healthy else "STALE_DATA",
                    template_evidence=template)
    return project_policy(forecast,now=issued,poll_age_seconds=poll_age,kind=kind)


def rate(n, d):
    return round(n/d, 4) if d else None


def summarize(counts):
    scored = counts["SUCCESS"]+counts["FAILURE"]
    return dict(sorted(counts.items()), scored=scored,
                success_fraction=rate(counts["SUCCESS"], scored),
                proposal_fraction=rate(counts["proposals"], counts["issues"]))


def replay(*, source, days=2, asof=None, limit_items=24,
           journal=None, model_sha="unversioned", progress=None, focused_zero=False):
    policies=tuple(row for row in POLICIES if not focused_zero or row[0]=="v166_all_history" or row[0].startswith("zero_"))
    needs_template=any(kind.startswith("template_") for _,_,kind in policies)
    needs_v151=any(kind=="v151" for _,_,kind in policies)
    if type(days) is not int or not 1<=days<=7:
        raise ValueError("days must be 1..7")
    if type(limit_items) is not int or not 1<=limit_items<=24:
        raise ValueError("invalid roster limit")
    path = Path(source).resolve(strict=True)
    results = {}
    totals = {p:Counter() for p,_,_ in policies}
    depletion_totals={p:Counter() for p in ('v163','daily_template','phase_analogs','phase_recent64')+ZERO_FAMILIES}
    availability_totals={p:Counter() for p in depletion_totals}
    event_totals={p:Counter() for p in ('v163','daily_template','phase_analogs','phase_recent64')+ZERO_FAMILIES}
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE name='research_metadata'").fetchone()
        metadata = dict(db.execute("SELECT key,value FROM research_metadata")) if has_meta else {}
        cutoff = int(metadata["source_cutoff_epoch"]) if has_meta else int(time.time())
        now = cutoff if asof is None else asof
        if type(now) is not int or now<=days*86400 or now>cutoff:
            raise ValueError("invalid cutoff")
        start = now-days*86400
        issues = range((start//300+1)*300, now+1, 300)
        gaps = db.execute("SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp", (now,)).fetchall()
        polls = [int(r[0]) for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp LIMIT ?", (now, MAX_POLLS+1))]
        if len(polls)>MAX_POLLS:
            raise ValueError("heartbeat cap exceeded")
        for key in sorted(model.exact_roster())[:limit_items]:
            country, name = key.split(":",1)
            raw = db.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?", (country,name,now,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS:
                raise ValueError("stock change cap exceeded")
            if any(type(t) is not int or type(q) is not int or q<0 or not s for t,q,s in raw):
                raise ValueError("invalid stock row")
            obs = [model.OBS(t,q,s) for t,q,s in raw]
            crosses, clean, _ = model._replay_restock_index(obs,gaps,now)
            depleted = observed_depletions(obs,crosses)
            true_restocks = observed_restocks(obs,crosses)
            unavailable = observed_availability_losses(obs,crosses)
            evidence = ArrivalEvidence(obs,polls,gaps,now)
            path_model=CausalStockPaths(obs,polls,crosses,cutoff=now,
                                       flight_seconds=model.TRAVEL_SECONDS[country],score=evidence.score)
            template_model=DailyTemplate(obs,crosses)
            phases = model._ReplayPhases(crosses)
            analogs = PhaseAnalogs(crosses)
            recent_analogs = PhaseAnalogs(crosses,capacity=64)
            zero_cycles = ZeroCycles(crosses)
            rate_cycles = QuantityRateCycles(crosses)
            hybrids={"zero_hybrid_"+mode:ComponentHybrid(crosses,mode) for mode in ComponentHybrid.MODES}
            selector=CausalPolicySelector(SELECTOR_EXPERTS,"zero_anchored_current_quarter")
            selected_experts=Counter()
            cursor = 0
            plans = {p:[] for p,_,_ in policies}
            stats = {p:Counter() for p,_,_ in policies}
            episode_stats = {p:Counter() for p,_,_ in policies}
            seen = {p:set() for p,_,_ in policies}
            landed_episodes = {p:set() for p,_,_ in policies}
            reasons = {p:Counter() for p,_,_ in policies}
            chronological = {p:[Counter() for _ in range(days)] for p,_,_ in policies}
            zero_paired = {p:Counter() for p in ZERO_COMPARATORS}
            paired = {p:Counter() for p,_,_ in policies if p!="v166_all_history"}
            event_stats={p:Counter() for p in event_totals}
            depletion_stats={p:Counter() for p in depletion_totals}
            availability_stats={p:Counter() for p in availability_totals}
            for issued in issues:
                while cursor<len(obs) and obs[cursor].epoch<=issued:
                    phases.add(obs[cursor]); analogs.add(obs[cursor]); recent_analogs.add(obs[cursor]); zero_cycles.add(obs[cursor]); rate_cycles.add(obs[cursor])
                    for hybrid in hybrids.values():hybrid.add(obs[cursor])
                    cursor+=1
                state = phases.asof()
                analog_events = analogs.forecast(key, state, asof=issued)
                recent_events = recent_analogs.forecast(key, state, asof=issued)
                zero_events = zero_cycles.forecast(key,asof=issued)
                rate_events = rate_cycles.forecast(key,asof=issued)
                hybrid_events={family:hybrid.forecast(key,asof=issued) for family,hybrid in hybrids.items()}
                pi = bisect.bisect_right(polls,issued)-1
                age = issued-polls[pi] if pi>=0 else None
                if crosses(issued,issued):
                    age = None  # Known collection outage at issuance.
                path_plans=path_model.plans(issued,zero_cycles,poll_age=age)
                baseline = evidence.score(issued+model.TRAVEL_SECONDS[country])
                forecasts = {}
                template=template_model.plan(issued,model.TRAVEL_SECONDS[country]) if needs_template and age is not None and age<=180 else None
                template_events=template_model.event_forecast(issued,key,model.TRAVEL_SECONDS[country])
                v151=stable_earliest_departure(key,state,asof=issued,scenarios=48) if needs_v151 and age is not None and age<=180 else None
                if (issued-issues.start)%(4*3600)==0:
                    # Comparable, nonoverlapping four-hour EVENT studies,
                    # independently of whether a departure is proposed.
                    forecasts[None]=model.predict_events(key,state,asof=issued)
                    end=min(issued+4*3600,now)
                    truths=true_restocks[bisect.bisect_right(true_restocks,issued):bisect.bisect_right(true_restocks,end)]
                    for family,stream in (('v163',forecasts[None]),('daily_template',template_events),('phase_analogs',analog_events),('phase_recent64',recent_events),('zero_anchored',zero_events),('zero_rate',rate_events))+tuple(hybrid_events.items()):
                        predictions=[e['predicted_restock_epoch'] for e in stream.get('true_restock_events',stream['restock_events'])
                                     if issued<e['predicted_restock_epoch']<=end
                                     and age is not None and age<=180]
                        count_events(event_stats[family],predictions,truths)
                        depletion_truth=depleted[bisect.bisect_right(depleted,issued):bisect.bisect_right(depleted,end)]
                        depletion_predictions=(predicted_depletions(stream,start=issued,end=end)
                            if age is not None and age<=180 else [])
                        count_events(depletion_stats[family],depletion_predictions,depletion_truth)
                        unavailable_truth=unavailable[bisect.bisect_right(unavailable,issued):bisect.bisect_right(unavailable,end)]
                        unavailable_predictions=(predicted_availability_losses(stream,start=issued,end=end)
                            if age is not None and age<=180 else [])
                        count_events(availability_stats[family],unavailable_predictions,unavailable_truth)
                issued_outcomes = {}
                issued_decisions={}
                issued_forecasts={}
                for policy, window, kind in policies:
                    if window not in forecasts:
                        forecasts[window] = model.predict_events(key,state,asof=issued,recent_cycles=window)
                    forecast = (rate_events if policy.startswith("zero_rate_") else
                                zero_events if policy.startswith("zero_anchored_") else
                                recent_events if policy.startswith("phase_recent64_") else
                                analog_events if policy.startswith("phase_analog_") else
                                template_events if policy.startswith("daily_event_") else forecasts[window])
                    if policy.startswith("zero_hybrid_"):
                        forecast=hybrid_events[next(f for f in HYBRID_FAMILIES if policy.startswith(f+"_"))]
                    if kind.startswith("path_"):
                        forecast=zero_events
                        path_plan=path_plans[kind[5:]]
                        decision=build_item_travel_decision(forecast,now=issued,poll_age_seconds=age)
                        path_departure=path_plan["departure_epoch"]
                        decision=dict(decision,estimated_departure_epoch=path_departure,
                            estimated_arrival_epoch=path_departure+model.TRAVEL_SECONDS[country]+model.GRACE if path_departure is not None else None,
                            selected_restock_event_index=None,status=path_plan["status"],
                            estimated_departure_deadline_epoch=None,
                            departure_countdown_seconds=path_departure-issued if path_departure is not None else None,
                            path_evidence=path_plan,departure_model_name="causal_complete_stock_paths_v1")
                    elif kind=="selector":
                        selector.update(issued,{p:issued_decisions[p] for p in SELECTOR_EXPERTS},
                                        poll_age=age,flight_seconds=model.TRAVEL_SECONDS[country],score=evidence.score)
                        expert,selection=selector.select()
                        forecast=issued_forecasts[expert]
                        decision=dict(issued_decisions[expert],selected_expert=expert,selector_evidence=selection)
                        selected_experts[expert]+=1
                    else:
                        decision = choose(forecast,issued,age,kind,template,v151)
                    issued_decisions[policy]=decision
                    issued_forecasts[policy]=forecast
                    dep = decision["estimated_departure_epoch"]
                    plans[policy].append((issued, dep, age))
                    arrival = dep+model.TRAVEL_SECONDS[country] if dep is not None else None
                    # Freeze the decision before consulting any outcome evidence.
                    outcome, reason, proof = evidence.score(arrival) if arrival is not None else ("ABSTAIN",decision["status"],None)
                    c = stats[policy]
                    c["issues"]+=1; c["proposals"]+=dep is not None
                    c[outcome]+=1; reasons[policy][reason]+=1
                    issued_outcomes[policy]=outcome
                    day_index=min(days-1,(issued-start-1)//86400)
                    day=chronological[policy][day_index]
                    day["issues"]+=1; day["proposals"]+=dep is not None
                    day[outcome]+=1
                    # Nonoverlapping next-tick slices retain a true event
                    # denominator without counting the same future restock
                    # once for every earlier issue in its eight-hour horizon.
                    end = min(issued+300,now)
                    actual = true_restocks[bisect.bisect_right(true_restocks,issued):bisect.bisect_right(true_restocks,end)]
                    predicted = [e["predicted_restock_epoch"] for e in forecast.get("true_restock_events",forecast["restock_events"])
                                 if issued<e["predicted_restock_epoch"]<=end
                                 and age is not None and age<=180]
                    if not kind.startswith("path_"):
                        c["next_tick_observed_restocks"]+=len(actual)
                        c["next_tick_forecast_restocks"]+=len(predicted)
                        for tolerance in (15,60,600):
                            c[f"next_tick_matched_{tolerance}s"]+=model.match_events(
                                predicted,actual,tolerance=tolerance)["matched"]
                    c["leave_now_"+baseline[0]]+=1
                    if dep is not None:
                        c["wait_seconds_sum"]+=dep-issued
                        if outcome in ("SUCCESS","FAILURE") and baseline[0] in ("SUCCESS","FAILURE"):
                            c["matched_leave_now"]+=1
                            c["policy_only_success"]+=outcome=="SUCCESS" and baseline[0]=="FAILURE"
                            c["leave_now_only_success"]+=outcome=="FAILURE" and baseline[0]=="SUCCESS"
                        # First proposal per known ISSUE phase, not per winning outcome.
                        anchor = ((forecast.get("physical_inventory_phase"),forecast.get("physical_phase_onset_epoch"))
                                  if policy.startswith("zero_") else (state["phase"],state["phase_onset"]))
                        if anchor[1] is not None and anchor not in seen[policy]:
                            seen[policy].add(anchor)
                            ec=episode_stats[policy]
                            ec["issues"]+=1; ec["proposals"]+=1; ec[outcome]+=1
                        if outcome=="SUCCESS":
                            index=bisect.bisect_right(clean,arrival)-1
                            if index>=0:
                                landed_episodes[policy].add(clean[index])
                    if journal is not None:
                        identity=f"{VERSION}:{model_sha}:{key}:{issued}:{policy}"
                        record={"issue_id":hashlib.sha256(identity.encode()).hexdigest(),
                                "model_sha":model_sha,"item_key":key,"issued_epoch":issued,
                                "source_cutoff_epoch":issued,"policy":policy,
                                "source_poll_age_seconds":age,
                                "issue_phase":forecast.get("physical_inventory_phase",state["phase"]),
                                "issue_availability_phase":state["phase"],
                                "restock_timer_anchor":forecast.get("restock_timer_anchor","LEGACY_30_ITEM_AVAILABILITY_PHASE"),
                                "observed_zero_epoch":forecast.get("observed_zero_epoch"),
                                "observed_zero_onset_bracket":forecast.get("observed_zero_onset_bracket"),
                                "forecast_status":forecast["status"],
                                "selected_expert":decision.get("selected_expert"),
                                "selector_evidence":decision.get("selector_evidence"),
                                "path_evidence":decision.get("path_evidence"),
                                "departure_model_name":decision.get("departure_model_name"),
                                "event_model_name":forecast.get("model_name","v163"),
                                "observed_current_quantity":state["last_observation"].quantity if state["last_observation"] else None,
                                "modeled_current_stock_window":forecast["current_stock_window"],
                                "issue_phase_onset":forecast.get("physical_phase_onset_epoch",state["phase_onset"]),
                                "status":decision["status"],"departure_epoch":dep,
                                "template_evidence":decision.get("template_evidence"),
                                "uncalibrated_scenario_support":decision.get("scenario_support"),
                                "arrival_epoch":arrival,"grace_seconds":model.GRACE,
                                "selected_event_index":decision["selected_restock_event_index"],
                                "forecast_events":[dict(e,event_id=f"{identity}:{e['index']}") for e in decision["forecast_events"]],
                                "outcome":outcome,"outcome_reason":reason,"evidence":proof,
                                "leave_now_outcome":baseline[0]}
                        journal.write(json.dumps(record,sort_keys=True)+"\n")
                for p,c in zero_paired.items():
                    base=issued_outcomes[ZERO_COMPARATORS[p]]
                    challenger=issued_outcomes[p]
                    if base in ("SUCCESS","FAILURE") and challenger in ("SUCCESS","FAILURE"):
                        c["matched_issues"]+=1
                        c["challenger_only_success"]+=challenger=="SUCCESS" and base=="FAILURE"
                        c["zero_baseline_only_success"]+=challenger=="FAILURE" and base=="SUCCESS"
                incumbent=issued_outcomes["v166_all_history"]
                for p,c in paired.items():
                    challenger=issued_outcomes[p]
                    if incumbent in ("SUCCESS","FAILURE") and challenger in ("SUCCESS","FAILURE"):
                        c["matched_issues"]+=1
                        c["challenger_only_success"]+=challenger=="SUCCESS" and incumbent=="FAILURE"
                        c["v166_only_success"]+=challenger=="FAILURE" and incumbent=="SUCCESS"
            results[key]={"player_flight_seconds":model.TRAVEL_SECONDS[country],"policies":{p:dict(summarize(stats[p]),
                departure_only_model=p.startswith("zero_path_"),
                first_proposal_per_issue_phase=summarize(episode_stats[p]),
                replanned_hourly_starts=evaluate_reconfirmation(plans[p],cutoff=now,
                    flight_seconds=model.TRAVEL_SECONDS[country],score=evidence.score),
                distinct_observed_stock_episodes_reached=len(landed_episodes[p]),
                chronological_day_slices=[summarize(c) for c in chronological[p]],
                outcome_reasons=dict(reasons[p])) for p,_,_ in policies},
                "path_established_reference_comparisons":{p:{reference:compare_reconfirmation(
                    plans[reference],plans[p],cutoff=now,flight_seconds=model.TRAVEL_SECONDS[country],score=evidence.score)
                    for reference in ("zero_rate_current_quarter","zero_hybrid_current_rate_current_quarter")}
                    for p,_,_ in policies if p.startswith("zero_path_")},
                "adaptive_selector_expert_issue_counts":dict(selected_experts),
                "adaptive_selector_final_training":selector.select()[1],
                "matched_zero_replanned_comparisons":{p:compare_reconfirmation(
                    plans[ZERO_COMPARATORS[p]],plans[p],
                    cutoff=now,flight_seconds=model.TRAVEL_SECONDS[country],score=evidence.score)
                    for p in zero_paired},
                "matched_zero_baseline_comparisons":{p:dict(c) for p,c in zero_paired.items()},
                "matched_v166_comparisons":{p:dict(c) for p,c in paired.items()}}
            results[key]['event_models_fixed_four_hour']= {p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in event_stats.items()}
            results[key]['depletion_models_fixed_four_hour']={p:dict(c,
                prediction_supported=p in ZERO_FAMILIES,
                recall_10m=rate(c['matched_600s'],c['observed']) if p in ZERO_FAMILIES else None,
                precision_10m=rate(c['matched_600s'],c['forecast']) if p in ZERO_FAMILIES else None) for p,c in depletion_stats.items()}
            results[key]['availability_loss_models_fixed_four_hour']={p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in availability_stats.items()}
            results[key]['availability_phase_diagnostics']={
                field:{'count':len(state[field]),'all_median_seconds':model.quantile(state[field],.5) if state[field] else None,
                       'recent8_median_seconds':model.quantile(state[field][-8:],.5) if state[field] else None}
                for field in ('stocked_durations','depleted_durations')}
            z=zero_cycles.physical.asof()
            results[key]['true_zero_phase_diagnostics']={
                label:{'count':len(values),'all_median_seconds':model.quantile(values,.5) if values else None}
                for label,values in (('nonzero_durations',z['stocked_durations']),
                                     ('zero_durations',z['depleted_durations']),
                                     ('available_durations',zero_cycles.available_durations))}
            for p,c in availability_stats.items():availability_totals[p].update(c)
            for p,c in depletion_stats.items():depletion_totals[p].update(c)
            for p,c in event_stats.items():event_totals[p].update(c)
            for p in totals:
                totals[p].update(stats[p])
            if progress:
                progress(key,len(results),limit_items)
    return {"status":"CONTINUOUS_AS_ISSUED_HISTORICAL_REPLAY",
            "version":VERSION,"model_sha":model_sha,"focused_zero":focused_zero,"asof_epoch":now,"days":days,
            "issue_step_seconds":300,"items_evaluated":len(results),
            "policies":{p:summarize(c) for p,c in totals.items()},"items":results,
            "event_models_fixed_four_hour":{p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in event_totals.items()},
            "depletion_models_fixed_four_hour":{p:dict(c,
                prediction_supported=p in ZERO_FAMILIES,
                recall_10m=rate(c['matched_600s'],c['observed']) if p in ZERO_FAMILIES else None,
                precision_10m=rate(c['matched_600s'],c['forecast']) if p in ZERO_FAMILIES else None) for p,c in depletion_totals.items()},
            "availability_loss_models_fixed_four_hour":{p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in availability_totals.items()},
            "depletion_definition":"Observed positive stock to exactly zero",
            "restock_definition":"Observed exactly zero to positive stock",
            "availability_loss_definition":"Observed >=30 to <30; never the depletion timer anchor",
            "timing_protocol_changed":"True restock/depletion truth differs from earlier availability-threshold scorecards",
            "chronological_slices_policy":"Equal consecutive 24h issue slices; all policies fixed before replay. Latest day is a diagnostic holdout, not pristine lockbox after inspection.",
            "future_truth_selects_issue_times":False,"genuine_live_issuance":False,
            "source_written":False,"poll_backed_arrival_availability_measured":True,
            "per_country_provider_freshness_verified":False,
            "actual_player_flights_measured":False,
            "warning":"Historical reconstructed issues; frozen policy scores and separately labeled simulated replanning, not actual player execution. Global heartbeats and change-only stock are sampled availability evidence, not exact-second or purchase certification. Repeated issues are correlated. V151 independent is included; daily-template adaptation is a challenger, not certified archived-specialist parity."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--days",type=int,default=2)
    parser.add_argument("--model-sha",default="unversioned")
    parser.add_argument("--journal",type=Path)
    parser.add_argument("--focused-zero",action="store_true",help="Keep zero-clock/path policies and V166 comparator; skip unused legacy flight simulations")
    args=parser.parse_args()
    if args.journal and args.journal.resolve()==args.source.resolve():
        raise SystemExit("journal must differ from source database")
    def progress(key,n,total):
        print(f"Continuous replay {n}/{total}: {key}",file=sys.stderr,flush=True)
    if args.journal:
        # Exclusive creation prevents replacing prior frozen evidence.
        with args.journal.open("x",encoding="utf8") as stream:
            result=replay(source=args.source,days=args.days,journal=stream,
                          model_sha=args.model_sha,progress=progress,focused_zero=args.focused_zero)
    else:
        result=replay(source=args.source,days=args.days,model_sha=args.model_sha,progress=progress,focused_zero=args.focused_zero)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
