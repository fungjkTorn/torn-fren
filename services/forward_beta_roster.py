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
