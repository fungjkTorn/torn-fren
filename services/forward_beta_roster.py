"""Explicitly approved second cohort; do not import a tournament selection."""
from types import MappingProxyType

CHALLENGER_MODELS=MappingProxyType({
    'arg:Monkey Plushie':('v20','traj3'),
    'can:Wolverine Plushie':('v20','traj12'),
    'cay:Stingray Plushie':('v20','traj5'),
    'chi:Peony':('v20','traj12'),
    'sou:African Violet':('v20','traj11'),
    'sou:Lion Plushie':('v20','traj12'),
})

# All six retain the evaluated full-history override. In particular Lion's
# former @48h variant is not restored when it becomes a forward beta.
FULL_HISTORY=True

NEXT_SIX_MODELS=MappingProxyType({
 'uae:Camel Plushie':('v19','dyn3'),'uni:Nessie Plushie':('v19','dyn8'),
 'uni:Red Fox Plushie':('v18','dyn1'),'chi:Panda Plushie':('v19','dyn1'),
 'uni:Xanax':('v19','dyn8'),'sou:Xanax':('v19','dyn6'),
})

def forecast_next_six(source,key,*,now,flight_seconds):
 from services.first_release_schedule import forecast_first_release_item
 from research.current_stock_continuation import extend_current_stock
 return forecast_first_release_item(source,key,now=now,flight_seconds=flight_seconds,
  model_roster=NEXT_SIX_MODELS,timing_full_history=True,current_stock_leave_now=True,
  forecast_transform=extend_current_stock if key=='uni:Xanax' else None)
