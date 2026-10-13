"""V158 research-only flight-horizon, completed-cycle prequential V151 router.

V157's single-cycle 25/50/75%-of-cycle Brier target was too distant from
the actual decision. V158 simulates paired-vs-independent LOW/HIGH cycles
over the ACTUAL item's flight +10s, plus 5 and 15 minutes of departure
delay. Chronological held-out validation origins are completed LOW onset
boundaries. Every forecast trains on the STRICTLY preceding completed
adjacent LOW->HIGH episodes; scoring uses only future fully observed,
contiguous complete cycles. Unknown future periods ABSTAIN, never become
MISS or fictitious future-stock evidence.

No live collector/network calls. The chosen mode is frozen as of the
original issue time, before the real historical stock outcome is read.
The score is a historical proxy, not calibrated game stock probability.
"""
from __future__ import annotations

import hashlib
import random
import statistics
from functools import lru_cache

from research.plushie_champions.common import TRAVEL_SECONDS

THRESHOLD=30
GRACE=10
MIN_TRAIN_PAIRS=6
MIN_VALID_ORIGINS=4
MAX_VALID_ORIGINS=12
MAX_HIST_PAIRS=128
SIMS=40
DEPARTURE_DELAYS=(0,300,900)
MIN_BRIER_LIFT=.015
MIN_BETTER_ORIGINS=3
MAX_SIM_TRANSITIONS=128


def _fully_bounded_episodes(phases,asof):
    lows=phases.get("observed_bounded_depleted_windows",[])
    highs=phases.get("observed_bounded_stocked_windows",[])
    if not isinstance(lows,list) or not isinstance(highs,list):
        raise ValueError("invalid completed cycle windows")
    if len(lows)+len(highs)>20000:
        raise ValueError("unbounded complete history")
    right={}
    for start,end in highs:
        if (type(start) is not int or type(end) is not int or
            not 0<start<end<=asof or start in right):
            raise ValueError("invalid stocked episode")
        right[start]=end
    episodes=[]
    prev_start=0
    for start,end in lows:
        if (type(start) is not int or type(end) is not int or
            not 0<start<end<=asof or start<=prev_start):
            raise ValueError("invalid depleted episode")
        prev_start=start
        high_end=right.get(end)
        if high_end is not None:
            episodes.append((start,end,high_end))
    return tuple(episodes[-MAX_HIST_PAIRS:])


def _origin_future_states(episodes,idx,horizons):
    """Truth for a LOW onset; require no gap through each scored horizon."""
    first_start=episodes[idx][0]
    result={}
    pos=idx
    known_until=first_start
    for horizon in sorted(horizons):
        absolute=first_start+horizon
        while known_until<=absolute and pos<len(episodes):
            low_start,high_start,high_end=episodes[pos]
            if low_start!=known_until:
                break
            known_until=high_end
            pos+=1
        if known_until<=absolute:
            result[horizon]=None
            continue
        # Need to locate the exact complete cycle covering absolute time.
        # Actual high starts are observed threshold crossings.
        result[horizon]=any(
            start<=absolute<end
            for low, start,end in episodes[idx:pos])
    return result


def _simulator_probability(train,horizons,*,paired,seed):
    lows=[low for low,high in train]
    highs=[high for low,high in train]
    rng=random.Random(seed)
    scores={h:0 for h in horizons}
    for _ in range(SIMS):
        transitions=[]
        pos=0
        for step in range(MAX_SIM_TRANSITIONS):
            if paired:
                lo,hi=rng.choice(train)
            else:
                lo=rng.choice(lows)
                hi=rng.choice(highs)
            transitions.append((pos+lo,pos+lo+hi))
            pos+=lo+hi
            if pos>max(horizons):
                break
        if pos<=max(horizons):
            raise RuntimeError("unsupported multi-cycle simulation horizon")
        for h in horizons:
            scores[h]+=int(any(start<=h<end for start,end in transitions))
    return {h:scores[h]/SIMS for h in horizons}


@lru_cache(maxsize=384)
def _score_complete_episodes(item_key, episodes):
    country=item_key.split(":",1)[0]
    flight=TRAVEL_SECONDS[country]
    horizons=tuple(flight+GRACE+d for d in DEPARTURE_DELAYS)
    n=len(episodes)
    base={
        "completed_episode_count":n,
        "validation_origin_count":0,
        "scored_arrivals":0,
        "paired_brier":None,
        "independent_brier":None,
        "paired_brier_lift":None,
        "paired_better_origins":0,
        "independent_better_origins":0,
        "equal_origins":0,
        "selected_sampling":"independent",
        "reason":"INSUFFICIENT_COMPLETE_EPISODES",
        "arrival_horizons_seconds":horizons,
        "historical_proper_score_only":True,
        "game_stock_arrival_confirmed":False,
    }
    if n<MIN_TRAIN_PAIRS+MIN_VALID_ORIGINS:
        return base
    start=max(MIN_TRAIN_PAIRS,n-MAX_VALID_ORIGINS)
    paired_loss=independent_loss=0.
    scored=valid=better=worse=ties=0
    for idx in range(start,n):
        # Exclude later pairs from the prediction; they appear exclusively
        # in the post-hoc comparison to the actual heldout state.
        train=tuple((b-a,c-b) for a,b,c in episodes[:idx])
        truth=_origin_future_states(episodes,idx,horizons)
        supported=tuple(h for h in horizons if truth[h] is not None)
        if not supported:
            continue
        digest=hashlib.blake2b(
            repr((item_key,train)).encode(),digest_size=8).digest()
        seed=int.from_bytes(digest,"big")
        p=_simulator_probability(train,supported,paired=True,seed=seed)
        q=_simulator_probability(train,supported,paired=False,seed=seed)
        lp=sum((p[h]-int(truth[h]))**2 for h in supported)
        li=sum((q[h]-int(truth[h]))**2 for h in supported)
        paired_loss+=lp
        independent_loss+=li
        scored+=len(supported)
        valid+=1
        if li-lp>1e-12:
            better+=1
        elif lp-li>1e-12:
            worse+=1
        else:
            ties+=1
    base.update({
        "validation_origin_count":valid,
        "scored_arrivals":scored,
        "paired_better_origins":better,
        "independent_better_origins":worse,
        "equal_origins":ties,
    })
    if valid<MIN_VALID_ORIGINS:
        base["reason"]="INSUFFICIENT_CONTIGUOUS_HELDOUT_ARRIVALS"
        return base
    lift=(independent_loss-paired_loss)/scored
    base.update({
        "paired_brier":round(paired_loss/scored,6),
        "independent_brier":round(independent_loss/scored,6),
        "paired_brier_lift":round(lift,6),
    })
    if lift>=MIN_BRIER_LIFT and better>=MIN_BETTER_ORIGINS:
        base["selected_sampling"]="paired_complete"
        base["reason"]="PREQUENTIAL_FLIGHT_HORIZON_PAIRED_LIFT"
    else:
        base["reason"]="NO_VALIDATED_FLIGHT_HORIZON_PAIRED_LIFT"
    return base


def flight_horizon_item_route(item_key,phases,*,asof):
    if (not isinstance(item_key,str) or item_key.count(":")!=1
        or type(asof) is not int or asof<=0
        or not isinstance(phases,dict)):
        raise ValueError("invalid item issue")
    country,name=item_key.split(":",1)
    if country not in TRAVEL_SECONDS or not name:
        raise ValueError("unsupported item/country")
    last=phases.get("last_observation")
    if last is not None and (type(last.epoch) is not int or last.epoch>asof):
        raise ValueError("future observation reached prequential router")
    episodes=_fully_bounded_episodes(phases,asof)
    result=dict(_score_complete_episodes(item_key,episodes))
    result.update({
        "item_key":item_key,"issued_epoch":asof,
        "outcome_free_selection":True,"future_bounded_phases_not_used":True,
        "flight_seconds":TRAVEL_SECONDS[country],
        "publication_allowed":False,
        "forward_validated":False,
    })
    return result
