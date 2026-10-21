# Quantity and consumption-rate challenger — October 14, 2026

## Corrected baseline

Private run [38620075037](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38620075037) completed successfully. Source `c3c493f1721ff50cb38cd77ebac5c835f03aad2f`. These are seven-day historical sampled-stock proxies, not prospective flights or purchase success. Baseline policy below is explicitly `zero_anchored_current_quarter`, not a per-item winner selected after seeing results.

| Item | Resolved simulated arrivals >=30 | Restock recall ±10m | True-zero depletion recall ±10m |
|---|---:|---:|---:|
| arg:Monkey Plushie | 100/157 (63.7%) | 44.7% | 43.4% |
| chi:Panda Plushie | 99/153 (64.7%) | 40.3% | 37.9% |
| jap:Xanax | 54/150 (36.0%) | 65.3% | 59.7% |
| sou:Lion Plushie | 101/154 (65.6%) | 49.0% | 49.8% |
| swi:Chamois Plushie | 84/146 (57.5%) | 51.4% | 47.7% |
| uae:Camel Plushie | 104/154 (67.5%) | 49.8% | 46.0% |
| uni:Nessie Plushie | 122/155 (78.7%) | 39.3% | 36.7% |
| uni:Red Fox Plushie | 116/158 (73.4%) | 49.5% | 47.7% |

All eight had 168/168 simulated departures. Unknown and pending arrivals are excluded from the resolved denominator. Timing recall uses fixed nonoverlapping four-hour cohorts; it is not precision or departure accuracy. This corrected baseline supersedes any interpretation of old <30 results as physical depletion accuracy.

## Fixed challenger before evaluation

`research/quantity_rate_cycles.py` uses:
- Physical positive→0 depletion and 0→positive restock only. The <30 buying threshold never starts the restock clock.
- Last64 clean completed physical batches: observed starting quantity divided by observed time to zero. Source switches, gaps and positive top-ups exclude rate training for that batch.
- Last64 completed zero waits; typical future batch quantity is the median last64 observed restock quantities. Current batch residual lifetime uses observed quantity, separately from typical future batch lifetime.
- When at least three observed declines cover180s in the last600s, blend the recent observed decline rate with the completed-cycle rate distribution. Fixed ratio cap0.25–4 and50% shrinkage; no per-item tuning.
- Separate zero and <30 endpoints. Counts below30 never create a current buying opportunity.
- Fallback to recent64 completed phase/lifetime history until three clean completed rate samples exist.

This constant-rate challenger is a bounded first experiment, not a claim that consumption is stationary. Change-only upstream data can miss top-ups, purchases and exact crossing instants. Rate estimates remain sampled stock decline, not certified demand. Future-cycle uncertainty still follows the existing quantile timeline; correlated scenario paths and causal regime specialists remain subsequent work.

## Comparison and gate

Three fixed arrival placements (quarter, midpoint, current-quarter) are compared with corresponding zero-clock baselines. Report includes same-issue frozen wins/losses and same-hourly-start replanning wins/losses, wait differences, every outcome-pair count, coverage, unknowns, pending and abstentions. All24 items replay to reveal regressions; the eight weak items are the priority review group.

No new policy enters the readiness whitelist or live publisher. Improvement and prospective rates are pending the runner results. Tests cover quantity-sensitive zero prediction, independent future batch lifetime, below30 separation, completed-sample causality, bounds, exclusions and matched comparisons.
