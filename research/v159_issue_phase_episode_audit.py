"""V159: clustered retrospective disagreement audit, NOT a new router.

First-issued item/UTC-hour checks can share the same observed as-issued
HIGH or LOW phase (same item, phase, phase onset). Counts of 20 hourly
predictions are not 20 independent restock events.

Collapse *mature*, same-issued independent V151 vs paired-cycle V151 and
V158 flight-horizon choices by the actual phase known AT ISSUE. Report
distinct clustered wins/losses and choice-regret cases. Future outcomes
are read only by the scoring step and cannot influence model routing.

A source phase episode is not guaranteed an independent future arrival
restock episode; this audit provides a stricter diagnostic grouping, not
a statistically certified independent-game-event result.
"""
from __future__ import annotations

from collections import defaultdict

VALID=("HIT","MISS")
MAX_ROWS=20000


def _exclusive(old,new):
    if old not in VALID or new not in VALID:
        return None
    if old==new:
        return 0
    return 1 if new=="HIT" else -1


def episode_audit(rows):
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:
        raise ValueError("unbounded invalid episode audit rows")
    groups=defaultdict(list)
    unknown_phase=0
    eligible=0
    paired_only=independent_only=0
    routed_lifts=0
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("invalid record")
        item=row.get("item_key")
        issued=row.get("issued_epoch")
        phase=row.get("issue_phase")
        onset=row.get("issue_phase_onset")
        if not isinstance(item,str) or not item or type(issued) is not int:
            # SOURCE_HISTORY_LIMIT records have no issue epoch; they
            # cannot anchor an as-of episode and do not count as losses.
            unknown_phase+=1
            continue
        if (phase not in ("HIGH","LOW") or type(onset) is not int
            or not 0<onset<=issued):
            unknown_phase+=1
            continue
        old=row.get("stable_outcome")
        new=row.get("paired_outcome")
        route=row.get("flight_horizon_outcome")
        raw_delta=_exclusive(old,new)
        routed_delta=_exclusive(old,route)
        if raw_delta is None and routed_delta is None:
            continue
        eligible+=1
        if raw_delta==1:
            paired_only+=1
        elif raw_delta==-1:
            independent_only+=1
        if routed_delta is not None:
            routed_lifts+=routed_delta
        # A selector can request paired but fall back to independent if
        # the paired model has no supported departure. Attribute actual
        # landed-stock outcomes to the model USED, not the desired route.
        used=row.get("flight_horizon_actual") or row.get(
            "flight_horizon_selection")
        groups[(item,phase,onset)].append(
            (raw_delta,routed_delta,used)
        )
    items=defaultdict(lambda:{
        "mature_issued_comparisons":0,
        "distinct_issue_phase_episodes":0,
        "raw_scorable_phase_episodes":0,
        "v158_scorable_phase_episodes":0,
        "raw_paired_winning_episodes":0,
        "raw_independent_winning_episodes":0,
        "raw_tied_or_mixed_episodes":0,
        "v158_winning_episodes":0,
        "v158_losing_episodes":0,
        "v158_tied_or_mixed_episodes":0,
        "raw_paired_exclusive_issues":0,
        "raw_independent_exclusive_issues":0,
        "v158_paired_chosen_issues":0,
        "raw_paired_only_missed_by_v158":0,
        "raw_independent_only_harmed_by_v158":0,
    })
    for (item,phase,onset),members in groups.items():
        v=items[item]
        v["distinct_issue_phase_episodes"]+=1
        v["mature_issued_comparisons"]+=len(members)
        raw=[x for x,_,_ in members if x is not None]
        chosen=[x for _,x,_ in members if x is not None]
        def bucket(score_list,prefix):
            if not score_list:
                return
            value=sum(score_list)
            if value>0:
                v[prefix+"_winning_episodes"]+=1
            elif value<0:
                v[prefix+"_losing_episodes"]+=1
            else:
                v[prefix+"_tied_or_mixed_episodes"]+=1
        # For raw independent advantage use unambiguous naming in output.
        if raw:
            v["raw_scorable_phase_episodes"]+=1
            raw_sum=sum(raw)
            if raw_sum>0:
                v["raw_paired_winning_episodes"]+=1
            elif raw_sum<0:
                v["raw_independent_winning_episodes"]+=1
            else:
                v["raw_tied_or_mixed_episodes"]+=1
        if chosen:
            v["v158_scorable_phase_episodes"]+=1
        bucket(chosen,"v158")
        for raw_delta,chosen_delta,selection in members:
            v["raw_paired_exclusive_issues"]+=int(raw_delta==1)
            v["raw_independent_exclusive_issues"]+=int(raw_delta==-1)
            v["v158_paired_chosen_issues"]+=int(selection=="paired_complete")
            v["raw_paired_only_missed_by_v158"]+=int(
                raw_delta==1 and selection!="paired_complete")
            v["raw_independent_only_harmed_by_v158"]+=int(
                raw_delta==-1 and selection=="paired_complete")
    totals={
        "eligible_mature_issue_rows":eligible,
        "unknown_or_unsupportable_issue_phase_rows":unknown_phase,
        "distinct_asof_phase_episodes":len(groups),
        "raw_scorable_phase_episodes":sum(x["raw_scorable_phase_episodes"] for x in items.values()),
        "v158_scorable_phase_episodes":sum(x["v158_scorable_phase_episodes"] for x in items.values()),
        "raw_paired_exclusive_issue_wins":paired_only,
        "raw_independent_exclusive_issue_wins":independent_only,
        "v158_net_exclusive_issue_wins":routed_lifts,
        "raw_paired_winning_episodes":sum(
            x["raw_paired_winning_episodes"] for x in items.values()),
        "raw_independent_winning_episodes":sum(
            x["raw_independent_winning_episodes"] for x in items.values()),
        "v158_winning_episodes":sum(
            x["v158_winning_episodes"] for x in items.values()),
        "v158_losing_episodes":sum(
            x["v158_losing_episodes"] for x in items.values()),
        "raw_paired_only_missed_by_v158":sum(
            x["raw_paired_only_missed_by_v158"] for x in items.values()),
        "raw_independent_only_harmed_by_v158":sum(
            x["raw_independent_only_harmed_by_v158"] for x in items.values()),
    }
    return {
        "method":"GROUP_BY_ASISSUED_STOCK_PHASE_EPISODE",
        "unit":"item+asissued_phase+asissued_phase_onset",
        "not_independent_future_restock_proof":True,
        "historical_backfill_provenance_unfrozen":True,
        "totals":totals,
        "items":dict(sorted(items.items())),
    }
