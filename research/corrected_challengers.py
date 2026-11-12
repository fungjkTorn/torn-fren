"""Frozen V174 screen winners >75%, using the production operation sequence.

No legacy tournament event_departures/engine_issue_plans adapter is called.
Select the first reachable event BEFORE one native timing model sees delays.
This research roster is never imported by a production publisher.
"""
from types import MappingProxyType
from services.first_release_schedule import forecast_first_release_item
from research.plushie_champions.common import TRAVEL_SECONDS

# Selection fixed from development_selected_candidate, not best holdout finalist.
# Full-history overrides: Lion loses @48h, and all native point-count lookbacks
# are disabled. Old results do not transfer to these modified configurations.
# Strictly >75%; Camel and Nessie at exactly 75% are deliberately excluded.
MODELS = MappingProxyType({
    'arg:Monkey Plushie': ('v20', 'traj3'),
    'can:Wolverine Plushie': ('v20', 'traj12'),
    'cay:Stingray Plushie': ('v20', 'traj5'),
    'chi:Peony': ('v20', 'traj12'),
    'sou:African Violet': ('v20', 'traj11'),
    'sou:Lion Plushie': ('v20', 'traj12'),
    'uni:Xanax': ('v19', 'dyn8'),
})
POLICY = 'CORRECTED_CHALLENGERS_FIRST_REACHABLE_V1'
NEXT_MODELS = MappingProxyType({
    'uae:Camel Plushie': ('v19','dyn3'),
    'uni:Nessie Plushie': ('v19','dyn8'),
    'sou:Xanax': ('v19','dyn6'),
    'uni:Red Fox Plushie': ('v18','dyn1'),
    'chi:Panda Plushie': ('v19','dyn1'),
})
ALL_MODELS = MappingProxyType({**MODELS,**NEXT_MODELS})


def forecast(source, key, issued):
    if key not in ALL_MODELS:
        raise ValueError('item is outside frozen challenger roster')
    row = forecast_first_release_item(source, key, now=issued,
        flight_seconds=TRAVEL_SECONDS[key.split(':')[0]], model_roster=ALL_MODELS,
        timing_full_history=True)
    row.update(research_policy=POLICY, production_deployed=False,
               training_policy='ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK',
               original_tournament_percentages_do_not_transfer=True)
    return row
