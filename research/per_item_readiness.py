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
            if (type(n) is not int or type(hits) is not int or not 0<=hits<=n
                or n<500 or phase.get('scored',0)<20 or coverage is None or coverage<.6
                or latest is None or proposals<=0):
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
                'mean_planned_wait_seconds':v.get('wait_seconds_sum',0)/proposals}
            if hits/n>=.9 and latest>=.9:qualified.append(candidate)
            elif hits/n>=.8 and latest>=.8:promising.append(candidate)
        eligible=qualified or promising
        # Earliest useful travel is an objective. Prefer the smaller
        # observed waiting cost among candidates clearing the same gate.
        chosen=min(eligible,key=lambda r:(r['mean_planned_wait_seconds'],-r['historical_fraction'],r['policy'])) if eligible else None
        rows.append({'item_key':key,'status':
            'HISTORICAL_TARGET_MET_NEEDS_FORWARD_VALIDATION' if qualified else
            'PROMISING_BELOW_TARGET' if promising else 'MORE_RESEARCH_REQUIRED',
            'research_candidate':chosen,'qualified_candidate_count':len(qualified),
            'production_model_changed':False})
    return {'status':'PER_ITEM_RESEARCH_READINESS','model_sha':report.get('model_sha'),
            'asof_epoch':report.get('asof_epoch'),'days':report.get('days'),
            'target_arrival_success_fraction':.9,'minimum_proposal_coverage':.6,
            'minimum_resolved_arrivals':500,'minimum_scored_issue_phase_proposals':20,
            'rows':rows,'automatic_model_promotion':False,
            'genuine_prospective_validation':False,
            'evidence_unit':'Correlated historical issues and first proposals per known issue phase, not independent player flights',
            'selection_warning':'Candidates selected from inspected history; fresh forward validation required. Event-stream compatibility excludes detached daily-target and V151 policies until their integration is complete.'}


if __name__=='__main__':
    with open(sys.argv[1],encoding='utf8') as stream:r=json.load(stream)
    print(json.dumps(readiness(r),sort_keys=True))
