# Torn Fren Model Sprint 2 — 2026-09-26

## Data basis
- Production snapshot: 386,553 stock-history rows.
- 104 recorded collection gaps.
- Event-aware boundary validation used.
- Travel Day separated from normal training: 2026-09-25 00:00 ET through 2026-09-28 00:00 ET.
- 61 country/item combinations have at least 30 fully usable normal cycles for walk-forward comparison.

## Main result
The data does not support one universal model.

### Restock timing
Best walk-forward family counts across 61 well-supported items:

best
median        17
tod           15
recent10      11
recent_tod    10
hybrid         8

Only 14/61 items improved restock median absolute error by at least 10% over the plain median. Keep restock timing simple by default and specialize only when item-specific evidence proves it helps.

### Stock lifetime / depletion
Best walk-forward family counts:

best
regression        24
qty_tod           20
qty_tod_recent    10
qty_recent         4
median             2
recent10           1

58/61 items improved lifetime median absolute error by at least 10% over a fixed median. Quantity + time-of-day is broadly useful; recent behavior helps a subset.

### Travel policy
Best travel-policy family counts under an early-arrival-heavy scoring rule:

best
midpoint         39
q925             11
adaptive_safe     7
tod_q925          4

Key examples:
- Japan Xanax: midpoint hit 53.2%, early 12.7%; q92.5 hit 57.0%, early 2.5%.
- Canada Xanax: q92.5 hit 97.1%, early 0.0%.
- Red Fox Plushie: midpoint hit 93.6%, early 0.0%.
- Camel Plushie: midpoint hit 93.0%, early 0.0%.

## Travel Day effect
68 items had enough normal and Travel Day observations for comparison.
- Median Travel Day sell-rate multiplier: 2.55x.
- 94.1% were at least 25% faster.
- 85.3% were at least 50% faster.

Examples:
country            item  normal_n  travel_n  normal_rate  travel_rate  rate_ratio  normal_life_min  travel_life_min
    jap           Xanax        99        12   131.658768   294.286133    2.235219        15.633333         4.350000
    uni Red Fox Plushie       302        54    88.136220   242.238043    2.748451        27.466667         7.883333
    uae   Camel Plushie       304        64    77.671960   157.264610    2.024728        30.550000        13.108333
    mex  Jaguar Plushie       300        57    81.397993   160.496760    1.971753        29.383333         7.183333

## Empirical projection-depth confidence
Normal-day resolved forecast audits:
- Japan Xanax: P1 56.5%; depth1 25.2%.
- Canada Xanax: P1 83.3%; depth1 30.0%.
- Red Fox Plushie: P1 98.7%; depth1 48.9%; depth2 35.4%.

## Patch behavior
- Empirical item + projection-depth confidence can downgrade live reliability when >=20 normal resolved audits exist.
- Travel Day outcomes are excluded from normal empirical confidence calibration.
- Two shadow-only travel challengers run for every item with a configured flight time and >=30 clean normal training cycles:
  - `safe_balanced_v1`: global clean-cycle stock-window optimizer with a 7.5% historical early-risk ceiling.
  - `safe_context_v1`: time-of-day + recency weighted stock-window optimizer with a 5% historical early-risk ceiling.
- Shadow models never change `/predict`, graph recommendations, or departure guidance.
- Shadow forecasts resolve against actual clean restock→depletion windows and record early/late seconds separately.

## Recommendation
Collect forward shadow outcomes for several normal days after Travel Day. Do not globally promote the new travel model. Promote per item only when forward evidence beats the live model on stock-at-arrival success while keeping early exposure within the chosen risk tolerance.