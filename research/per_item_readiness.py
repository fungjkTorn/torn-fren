"""Offline per-item research gates; never automatically promotes a model."""
import json
import sys

COHERENT_POLICIES={
    'v166_all_history':('all_history','median'),
    'quarter_buffer_all_history':('all_history','quarter'),
    'midpoint_all_history':('all_history','midpoint'),
    'midpoint_recent_8':('recent_8','midpoint'),
    'late_onset_all_history':('all_history','late'),
    'quarter_with_current_stock':('all_history','current_quarter'),
    'phase_analog_quarter':('phase_analogs_18','quarter'),
    'phase_analog_midpoint':('phase_analogs_18','midpoint'),
    'phase_analog_current_quarter':('phase_analogs_18','current_quarter'),
}


def arrival_evidence(policies):
    """Expose every measured departure policy without inventing event compatibility.

    This is evidence, not a ranking or assignment. In particular, a detached
    departure predictor cannot supply the graph's restock/depletion timeline.
    """
    rows=[]
    for name,policy in sorted(policies.items()):
        measured=policy.get('replanned_all_five_minute_starts')
        if not isinstance(measured,dict):
            continue
        departed=measured.get('departed',0)
        rows.append({'policy':name,
            'starts':measured.get('starts'),
            'successes':measured.get('SUCCESS',0),
            'failures':measured.get('FAILURE',0),
            'unknown':measured.get('UNKNOWN',0),
            'pending':measured.get('PENDING',0),
            'abstained':measured.get('ABSTAIN',0),
            'resolved_arrivals':measured.get('scored',0),
            'success_fraction':measured.get('success_fraction'),
            'departure_coverage':measured.get('departure_coverage'),
            'mean_wait_seconds':measured.get('wait_seconds_sum',0)/departed if departed else None,
            'chronological_day_slices':measured.get('chronological_start_day_slices',[]),
            'legacy_event_adapter_mapping_available':name in COHERENT_POLICIES,
            'departure_only_model':policy.get('departure_only_model',False),
            'restock_timing_accuracy_inferred':False,
            'depletion_timing_accuracy_inferred':False,
            'release_assignment_verified':False})
    return rows


def readiness(report):
    rows=[]
    for key,item in sorted(report['items'].items()):
        qualified=[];promising=[]
        for policy,(history,adapter) in COHERENT_POLICIES.items():
            v=item['policies'].get(policy,{})
            n=v.get('scored',0);hits=v.get('SUCCESS',0)
            phase=v.get('first_proposal_per_issue_phase',{})
            slices=v.get('chronological_day_slices') or []
            latest=slices[-1].get('success_fraction') if slices else None
            coverage=v.get('proposal_fraction');proposals=v.get('proposals',0)
            executed=v.get('replanned_hourly_starts') or {}
            executed_rate=executed.get('success_fraction')
            executed_coverage=executed.get('departure_coverage')
            if (type(n) is not int or type(hits) is not int or not 0<=hits<=n
                or n<500 or phase.get('scored',0)<20 or coverage is None or coverage<.6
                or latest is None or proposals<=0
                or executed.get('scored',0)<100 or executed_rate is None
                or executed_coverage is None or executed_coverage<.6):
                continue
            comparison=item.get('matched_v166_comparisons',{}).get(policy,{})
            if policy!='v166_all_history' and (
                comparison.get('matched_issues',0)<200 or
                comparison.get('challenger_only_success',0)<=comparison.get('v166_only_success',0)):
                continue
            candidate={'policy':policy,'event_history':history,'flight_adapter':adapter,
                'player_flight_seconds':item.get('player_flight_seconds'),
                'successes':hits,'resolved_arrivals':n,'historical_fraction':hits/n,
                'latest_day_fraction':latest,'proposal_coverage':coverage,
                'scored_issue_phase_proposals':phase['scored'],
                'replanned_historical_fraction':executed_rate,
                'replanned_departure_coverage':executed_coverage,
                'replanned_scored_arrivals':executed['scored'],
                'mean_planned_wait_seconds':v.get('wait_seconds_sum',0)/proposals}
            if hits/n>=.9 and latest>=.9 and executed_rate>=.9:qualified.append(candidate)
            elif hits/n>=.8 and latest>=.8 and executed_rate>=.8:promising.append(candidate)
        eligible=qualified or promising
        # Earliest useful travel is an objective. Prefer the smaller
        # observed waiting cost among candidates clearing the same gate.
        chosen=min(eligible,key=lambda r:(r['mean_planned_wait_seconds'],-r['historical_fraction'],r['policy'])) if eligible else None
        rows.append({'item_key':key,'status':
            'HISTORICAL_TARGET_MET_NEEDS_FORWARD_VALIDATION' if qualified else
            'PROMISING_BELOW_TARGET' if promising else 'MORE_RESEARCH_REQUIRED',
            'research_candidate':chosen,'qualified_candidate_count':len(qualified),
            'status_scope':'LEGACY_EVENT_ADAPTER_POLICIES_ONLY',
            'legacy_event_adapter_policy_coverage':{
                'evaluated':sorted(set(item['policies']) & set(COHERENT_POLICIES)),
                'missing':sorted(set(COHERENT_POLICIES)-set(item['policies'])),
                'outside_legacy_mapping':sorted(set(item['policies'])-set(COHERENT_POLICIES))},
            'arrival_policy_evidence':arrival_evidence(item['policies']),
            'production_model_changed':False})
    return {'status':'PER_ITEM_RESEARCH_READINESS','model_sha':report.get('model_sha'),
            'asof_epoch':report.get('asof_epoch'),'days':report.get('days'),
            'target_arrival_success_fraction':.9,'minimum_proposal_coverage':.6,
            'minimum_replanned_scored_arrivals':100,'minimum_replanned_departure_coverage':.6,
            'minimum_resolved_arrivals':500,'minimum_scored_issue_phase_proposals':20,
            'rows':rows,'automatic_model_promotion':False,
            'genuine_prospective_validation':False,
            'readiness_status_scope':'Legacy event/adapter assessment, not a complete arrival-policy ranking or release certification',
            'arrival_evidence_protocol':'All five-minute replanning starts; unknown and pending excluded from resolved success; correlated cohorts',
            'evidence_unit':'Correlated historical issues and first proposals per known issue phase, not independent player flights',
            'selection_warning':'Candidates selected from inspected history; fresh forward validation required. Event-stream compatibility excludes detached daily-target and V151 policies until their integration is complete.'}


if __name__=='__main__':
    with open(sys.argv[1],encoding='utf8') as stream:r=json.load(stream)
    print(json.dumps(readiness(r),sort_keys=True))
