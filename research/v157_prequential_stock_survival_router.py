"""V157 research-only prequential selector for V151 pair versus independent.

At issue T, consume ONLY V145 completed adjacent LOW->HIGH episodes ending
no later than T. Every validation episode is scored against forecasts fit to
STRICTLY EARLIER completed episodes, not the episode being predicted.

The probability target here is >=30 stock at three *within-first-cycle*
elapsed horizons after a depleted phase begins. It is a proper-score proxy
for joint LOW/HIGH phase modeling, NOT an actual user's landing prediction
for a multi-cycle flight, and NOT calibrated stock certainty.

Freeze eligibility rules before the live historical comparison:
  >=9 directly bounded pairs, >=5 training pairs, >=4 held-out pairs;
  both phase types need at least two distinct durations;
  positive paired-vs-independent mean Brier improvement >=0.02;
  >=3 held-out episodes must individually improve (no cherry-picked bin).
Fail closed to independent otherwise, leaving all V151 arrival support
checks, flight times, and website code untouched.
"""
from __future__ import annotations

import statistics

from research.v151_stable_earliest_departure import _paired_complete_cycles

MIN_DIRECT_PAIRS = 9
TRAIN_PAIRS = 5
MIN_VALIDATION_PAIRS = 4
MIN_MEAN_BRIER_LIFT = 0.02
MIN_BETTER_EPISODES = 3
MAX_PAIRS_USED = 48
HORIZON_FRACTIONS = (0.25, 0.5, 0.75)


def _probabilities(train, elapsed):
    low=[x for x,_ in train]
    high=[y for _,y in train]
    paired=sum(x<=elapsed<x+y for x,y in train)/len(train)
    independent=sum(x<=elapsed<x+y for x in low for y in high)/(
        len(low)*len(high))
    return paired,independent


def _validate_pairs(pairs):
    if type(pairs) is not list:
        raise ValueError("missing complete cycle pairs")
    for entry in pairs:
        if (not isinstance(entry,tuple) or len(entry)!=2 or
            type(entry[0]) is not int or type(entry[1]) is not int or
            min(entry)<=0):
            raise ValueError("invalid bounded phase duration")
    return pairs[-MAX_PAIRS_USED:]


def cross_validate_cycle_survival(pairs):
    """Deterministic chronological held-out Brier comparison; no outcomes outside pairs."""
    pairs=_validate_pairs(pairs)
    result={
        "direct_pairs":len(pairs),
        "heldout_episodes":0,
        "heldout_scores":0,
        "paired_mean_brier":None,
        "independent_mean_brier":None,
        "paired_brier_improvement":None,
        "paired_better_episodes":0,
        "independent_better_episodes":0,
        "equal_episodes":0,
        "selected_sampling":"independent",
        "reason":"INSUFFICIENT_DIRECTLY_BOUNDED_PAIRS",
        "not_calibrated_probability":True,
        "real_flight_success_verified":False,
        "asof_research_only":True,
        "validation_target":"FIRST_COMPLETED_LOW_HIGH_EPISODE_STOCK30",
    }
    if len(pairs)<MIN_DIRECT_PAIRS:
        return result
    low_values=[a for a,_ in pairs]
    high_values=[b for _,b in pairs]
    if len(set(low_values))<2 or len(set(high_values))<2:
        result["reason"]="NONIDENTIFIABLE_CONSTANT_PHASE_DURATION"
        return result
    if len(pairs)-TRAIN_PAIRS<MIN_VALIDATION_PAIRS:
        return result
    loss_p=[]
    loss_i=[]
    episodes_better=episodes_worse=episodes_equal=0
    for pos in range(TRAIN_PAIRS,len(pairs)):
        train=pairs[:pos]
        true_low,true_high=pairs[pos]
        # Per-issue horizon anchors derive ONLY from preceding completed
        # pairs. No future duration or learned best-bin selection.
        median_cycle=statistics.median([a+b for a,b in train])
        horizons=sorted(set(max(1,round(f*median_cycle))
                            for f in HORIZON_FRACTIONS))
        episodic_p=episodic_i=0.
        for elapsed in horizons:
            prob_p,prob_i=_probabilities(train,elapsed)
            actual=float(true_low<=elapsed<true_low+true_high)
            lp=(prob_p-actual)**2
            li=(prob_i-actual)**2
            episodic_p+=lp
            episodic_i+=li
            loss_p.append(lp)
            loss_i.append(li)
        diff=episodic_i-episodic_p
        if diff>1e-12:
            episodes_better+=1
        elif diff< -1e-12:
            episodes_worse+=1
        else:
            episodes_equal+=1
    n=len(loss_p)
    lift=(sum(loss_i)-sum(loss_p))/n
    result.update({
        "heldout_episodes":len(pairs)-TRAIN_PAIRS,
        "heldout_scores":n,
        "paired_mean_brier":round(sum(loss_p)/n,6),
        "independent_mean_brier":round(sum(loss_i)/n,6),
        "paired_brier_improvement":round(lift,6),
        "paired_better_episodes":episodes_better,
        "independent_better_episodes":episodes_worse,
        "equal_episodes":episodes_equal,
    })
    # The item/flight's previously observed arrival outcomes are not used.
    if lift>=MIN_MEAN_BRIER_LIFT and episodes_better>=MIN_BETTER_EPISODES:
        result["selected_sampling"]="paired_complete"
        result["reason"]="PREQUENTIAL_FIRST_CYCLE_SURVIVAL_IMPROVEMENT"
    else:
        result["reason"]="PAIRED_NOT_PROVEN_BETTER_PREQUENTIALLY"
    return result


def prequential_item_route(item_key, phases, *, asof):
    if (not isinstance(item_key,str) or item_key.count(":")!=1
        or type(asof) is not int or asof<=0
        or not isinstance(phases,dict)):
        raise ValueError("invalid item or issue clock")
    last=phases.get("last_observation")
    if last is not None and (type(last.epoch) is not int or last.epoch>asof):
        raise ValueError("future observation leaked into router")
    pairs=_paired_complete_cycles(phases,asof)
    answer=cross_validate_cycle_survival(pairs)
    answer["item_key"]=item_key
    answer["issued_epoch"]=asof
    answer["history_pinned_to_issue"]=True
    answer["departure_advice_published"]=False
    return answer
