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
from research.departure_reconfirmation import evaluate as evaluate_reconfirmation
from research.depletion_timing_audit import observed_depletions, predicted_depletions, count_events
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
            ("phase_recent64_current_quarter", None, "current_quarter"))
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
           journal=None, model_sha="unversioned", progress=None):
    if type(days) is not int or not 1<=days<=7:
        raise ValueError("days must be 1..7")
    if type(limit_items) is not int or not 1<=limit_items<=24:
        raise ValueError("invalid roster limit")
    path = Path(source).resolve(strict=True)
    results = {}
    totals = {p:Counter() for p,_,_ in POLICIES}
    depletion_totals={p:Counter() for p in ('v163','daily_template','phase_analogs','phase_recent64')}
    event_totals={p:Counter() for p in ('v163','daily_template','phase_analogs','phase_recent64')}
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
            evidence = ArrivalEvidence(obs,polls,gaps,now)
            template_model=DailyTemplate(obs,crosses)
            phases = model._ReplayPhases(crosses)
            analogs = PhaseAnalogs(crosses)
            recent_analogs = PhaseAnalogs(crosses,capacity=64)
            cursor = 0
            plans = {p:[] for p,_,_ in POLICIES}
            stats = {p:Counter() for p,_,_ in POLICIES}
            episode_stats = {p:Counter() for p,_,_ in POLICIES}
            seen = {p:set() for p,_,_ in POLICIES}
            landed_episodes = {p:set() for p,_,_ in POLICIES}
            reasons = {p:Counter() for p,_,_ in POLICIES}
            chronological = {p:[Counter() for _ in range(days)] for p,_,_ in POLICIES}
            paired = {p:Counter() for p,_,_ in POLICIES if p!="v166_all_history"}
            event_stats={p:Counter() for p in event_totals}
            depletion_stats={p:Counter() for p in depletion_totals}
            for issued in issues:
                while cursor<len(obs) and obs[cursor].epoch<=issued:
                    phases.add(obs[cursor]); analogs.add(obs[cursor]); recent_analogs.add(obs[cursor]); cursor+=1
                state = phases.asof()
                analog_events = analogs.forecast(key, state, asof=issued)
                recent_events = recent_analogs.forecast(key, state, asof=issued)
                pi = bisect.bisect_right(polls,issued)-1
                age = issued-polls[pi] if pi>=0 else None
                if crosses(issued,issued):
                    age = None  # Known collection outage at issuance.
                baseline = evidence.score(issued+model.TRAVEL_SECONDS[country])
                forecasts = {}
                template=template_model.plan(issued,model.TRAVEL_SECONDS[country]) if age is not None and age<=180 else None
                template_events=template_model.event_forecast(issued,key,model.TRAVEL_SECONDS[country])
                v151=stable_earliest_departure(key,state,asof=issued,scenarios=48) if age is not None and age<=180 else None
                if (issued-issues.start)%(4*3600)==0:
                    # Comparable, nonoverlapping four-hour EVENT studies,
                    # independently of whether a departure is proposed.
                    forecasts[None]=model.predict_events(key,state,asof=issued)
                    end=min(issued+4*3600,now)
                    truths=clean[bisect.bisect_right(clean,issued):bisect.bisect_right(clean,end)]
                    for family,stream in (('v163',forecasts[None]),('daily_template',template_events),('phase_analogs',analog_events),('phase_recent64',recent_events)):
                        predictions=[e['predicted_restock_epoch'] for e in stream['restock_events']
                                     if issued<e['predicted_restock_epoch']<=end
                                     and age is not None and age<=180]
                        count_events(event_stats[family],predictions,truths)
                        depletion_truth=depleted[bisect.bisect_right(depleted,issued):bisect.bisect_right(depleted,end)]
                        depletion_predictions=(predicted_depletions(stream,start=issued,end=end)
                            if age is not None and age<=180 else [])
                        count_events(depletion_stats[family],depletion_predictions,depletion_truth)
                issued_outcomes = {}
                for policy, window, kind in POLICIES:
                    if window not in forecasts:
                        forecasts[window] = model.predict_events(key,state,asof=issued,recent_cycles=window)
                    forecast = (recent_events if policy.startswith("phase_recent64_") else
                                analog_events if policy.startswith("phase_analog_") else
                                template_events if policy.startswith("daily_event_") else forecasts[window])
                    decision = choose(forecast,issued,age,kind,template,v151)
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
                    actual = clean[bisect.bisect_right(clean,issued):bisect.bisect_right(clean,end)]
                    predicted = [e["predicted_restock_epoch"] for e in forecast["restock_events"]
                                 if issued<e["predicted_restock_epoch"]<=end
                                 and age is not None and age<=180]
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
                        anchor = (state["phase"],state["phase_onset"])
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
                                "source_poll_age_seconds":age,"issue_phase":state["phase"],
                                "forecast_status":forecast["status"],
                                "event_model_name":forecast.get("model_name","v163"),
                                "observed_current_quantity":state["last_observation"].quantity if state["last_observation"] else None,
                                "modeled_current_stock_window":forecast["current_stock_window"],
                                "issue_phase_onset":state["phase_onset"],
                                "status":decision["status"],"departure_epoch":dep,
                                "template_evidence":decision.get("template_evidence"),
                                "uncalibrated_scenario_support":decision.get("scenario_support"),
                                "arrival_epoch":arrival,"grace_seconds":model.GRACE,
                                "selected_event_index":decision["selected_restock_event_index"],
                                "forecast_events":[dict(e,event_id=f"{identity}:{e['index']}") for e in decision["forecast_events"]],
                                "outcome":outcome,"outcome_reason":reason,"evidence":proof,
                                "leave_now_outcome":baseline[0]}
                        journal.write(json.dumps(record,sort_keys=True)+"\n")
                incumbent=issued_outcomes["v166_all_history"]
                for p,c in paired.items():
                    challenger=issued_outcomes[p]
                    if incumbent in ("SUCCESS","FAILURE") and challenger in ("SUCCESS","FAILURE"):
                        c["matched_issues"]+=1
                        c["challenger_only_success"]+=challenger=="SUCCESS" and incumbent=="FAILURE"
                        c["v166_only_success"]+=challenger=="FAILURE" and incumbent=="SUCCESS"
            results[key]={"player_flight_seconds":model.TRAVEL_SECONDS[country],"policies":{p:dict(summarize(stats[p]),
                first_proposal_per_issue_phase=summarize(episode_stats[p]),
                replanned_hourly_starts=evaluate_reconfirmation(plans[p],cutoff=now,
                    flight_seconds=model.TRAVEL_SECONDS[country],score=evidence.score),
                distinct_observed_stock_episodes_reached=len(landed_episodes[p]),
                chronological_day_slices=[summarize(c) for c in chronological[p]],
                outcome_reasons=dict(reasons[p])) for p,_,_ in POLICIES},
                "matched_v166_comparisons":{p:dict(c) for p,c in paired.items()}}
            results[key]['event_models_fixed_four_hour']= {p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in event_stats.items()}
            results[key]['depletion_models_fixed_four_hour']={p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in depletion_stats.items()}
            results[key]['completed_phase_diagnostics']={
                field:{'count':len(state[field]),'all_median_seconds':model.quantile(state[field],.5) if state[field] else None,
                       'recent8_median_seconds':model.quantile(state[field][-8:],.5) if state[field] else None}
                for field in ('stocked_durations','depleted_durations')}
            for p,c in depletion_stats.items():depletion_totals[p].update(c)
            for p,c in event_stats.items():event_totals[p].update(c)
            for p in totals:
                totals[p].update(stats[p])
            if progress:
                progress(key,len(results),limit_items)
    return {"status":"CONTINUOUS_AS_ISSUED_HISTORICAL_REPLAY",
            "version":VERSION,"model_sha":model_sha,"asof_epoch":now,"days":days,
            "issue_step_seconds":300,"items_evaluated":len(results),
            "policies":{p:summarize(c) for p,c in totals.items()},"items":results,
            "event_models_fixed_four_hour":{p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in event_totals.items()},
            "depletion_models_fixed_four_hour":{p:dict(c,
                recall_10m=rate(c['matched_600s'],c['observed']),
                precision_10m=rate(c['matched_600s'],c['forecast'])) for p,c in depletion_totals.items()},
            "depletion_definition":"Observed >=30 to <30 crossing; not necessarily zero stock",
            "chronological_slices_policy":"Equal consecutive 24h issue slices; all policies fixed before replay. Latest day is a diagnostic holdout, not pristine lockbox after inspection.",
            "future_truth_selects_issue_times":False,"genuine_live_issuance":False,
            "source_written":False,"poll_backed_arrival_availability_measured":True,
            "per_country_provider_freshness_verified":False,
            "actual_player_flights_measured":False,
            "warning":"Historical reconstructed issues; frozen planned trips, not re-confirmed WATCH execution. Global heartbeats and change-only stock are sampled availability evidence, not exact-second or purchase certification. Repeated issues are correlated. V151 independent is included; daily-template adaptation is a challenger, not certified archived-specialist parity."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--days",type=int,default=2)
    parser.add_argument("--model-sha",default="unversioned")
    parser.add_argument("--journal",type=Path)
    args=parser.parse_args()
    if args.journal and args.journal.resolve()==args.source.resolve():
        raise SystemExit("journal must differ from source database")
    def progress(key,n,total):
        print(f"Continuous replay {n}/{total}: {key}",file=sys.stderr,flush=True)
    if args.journal:
        # Exclusive creation prevents replacing prior frozen evidence.
        with args.journal.open("x",encoding="utf8") as stream:
            result=replay(source=args.source,days=args.days,journal=stream,
                          model_sha=args.model_sha,progress=progress)
    else:
        result=replay(source=args.source,days=args.days,model_sha=args.model_sha,progress=progress)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
