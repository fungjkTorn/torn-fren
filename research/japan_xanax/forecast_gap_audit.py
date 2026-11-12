"""Explain Japan forecast gaps without altering gates or production models."""
import bisect
from collections import Counter,defaultdict
from research.japan_xanax.renewal_shadow import History,KEY,STEP,source_data
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF


def prerequisite(history,issued,age):
    if history.last is not None and history.last[0]>issued:raise ValueError('Future observation')
    if age is None or not 0<=age<=180:return 'STALE_OR_MISSING_HEARTBEAT',{}
    if history.crosses(issued,issued):return 'ACTIVE_COLLECTION_GAP',{}
    cycles=[c for c in history.cycles if c.end<=issued][-96:]
    info=dict(completed_cycles=len(cycles),phase_known=history.phase_start is not None)
    if len(cycles)<16:return 'FEWER_THAN_16_CYCLES',info
    if history.phase_start is None:return 'UNKNOWN_PHYSICAL_PHASE',info
    if issued-history.last[0]>86400:return 'ITEM_STATE_OLDER_THAN_24H',info
    high=history.last[1]>0;phase_age=issued-history.phase_start
    durations=[c.end-c.restock if high else c.restock-c.zero for c in cycles]
    n=sum(d>phase_age for d in durations)
    info.update(phase='positive' if high else 'zero',phase_age_seconds=phase_age,
        survivors=n,longest_past_phase=max(durations),quantity=history.last[1])
    if n<4:return 'FEWER_THAN_4_PHASE_SURVIVORS',info
    return 'READY',info


def run(source,*,model_sha):
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);cursor=0;counts=Counter();days=defaultdict(Counter);details=defaultdict(Counter)
    examples=defaultdict(list);resets=Counter();last_reset='INITIAL_OR_LEFT_CENSORED';all_rows=[]
    for issued in range(ISSUE_START,ISSUE_END+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];previous=h.last
            if previous is None:reason='INITIAL'
            elif row[0]<=previous[0]:reason='NONINCREASING_TIME'
            elif row[2]!=previous[2]:reason='PROVIDER_SWITCH'
            elif crosses(previous[0],row[0]):reason='COLLECTION_GAP'
            elif row[1]>previous[1]>0:reason='POSITIVE_TOP_UP'
            else:reason=None
            if reason:
                last_reset=reason
                if ISSUE_START<=row[0]<=ISSUE_END:resets[reason]+=1
            h.add(row);cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        reason,info=prerequisite(h,issued,age)
        if reason=='READY':
            plan=h.plans(issued,poll_age=age)['sequence_blocks_peak']
            reason='FORECAST' if plan['departure'] is not None else 'LOW_SCENARIO_SUPPORT'
        counts[reason]+=1;days[(issued-ISSUE_START)//86400][reason]+=1
        if reason=='UNKNOWN_PHYSICAL_PHASE':details[reason][last_reset]+=1
        if 'survivors' in info:
            details[reason]['survivors_'+str(info['survivors'])]+=1
            details[reason]['phase_'+info['phase']]+=1
        if len(examples[reason])<3:examples[reason].append(dict(issued=issued,**info))
        all_rows.append(dict(issued=issued,reason=reason,**info))
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        issues=len(all_rows),reasons=dict(counts),daily_reasons={str(k):dict(v) for k,v in days.items()},
        reason_details={k:dict(v) for k,v in details.items()},examples=dict(examples),phase_resets=dict(resets),
        baseline_counts_reproduced=counts['FORECAST']==451 and len(all_rows)-counts['FORECAST']==413,
        issue_diagnostics=all_rows,development_window=True,automatic_promotion=False,
        limitation='Prerequisite and issued-plan audit only, not an accuracy test or evidence of regime change. No model gates changed.')
