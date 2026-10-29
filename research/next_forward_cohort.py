"""Read-only next-cohort preview; does not expand the live ten-item roster.

Keep exact incumbent timing configs and apply the same >30, zero-grace,
first-reachable-event contract. This module is preparation for prospective
capture, not evidence of live accuracy or a production publisher.
"""
import argparse
import json
import time
from types import MappingProxyType
from services.first_release_schedule import forecast_first_release_item
from research.plushie_champions.common import TRAVEL_SECONDS

CANDIDATE_MODELS=MappingProxyType({
    'cay:Stingray Plushie':('v18','dyn7'),
    'sou:African Violet':('v19','dyn7'),
    'chi:Peony':('v20','traj12'),
    'uni:Xanax':('v19','dyn3'),
})
PRIORITY_COHORT=('cay:Stingray Plushie','sou:African Violet','chi:Peony')


def preview(source,key,*,issued=None):
    if key not in CANDIDATE_MODELS:raise ValueError('item is outside the reviewed candidate cohort')
    issued=int(time.time()) if issued is None else issued
    result=forecast_first_release_item(source,key,now=issued,
        flight_seconds=TRAVEL_SECONDS[key.split(':')[0]],model_roster=CANDIDATE_MODELS)
    result.update(cohort='NEXT_COHORT_READ_ONLY_PREVIEW',live_roster_changed=False,
        historical_percentages_do_not_transfer=True,accuracy_evidence=False,
        production_deployed=False,actual_player_trips_required=False)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--item',required=True,choices=tuple(CANDIDATE_MODELS));p.add_argument('--issued',type=int)
    a=p.parse_args();print(json.dumps(preview(a.source,a.item,issued=a.issued),sort_keys=True))

if __name__=='__main__':main()
