# Restore the item-specific incumbent roster before choosing any model

**2026-10-21; research-only.** The owner correctly distinguishes
(1) **true physical restock timing** from (2) **the flight that can actually
buy >=30 units at landing and landing+10s**. They are separate prediction
problems. Do not collapse them into a single number or replace the
existing specialist champions with one generic pooled model.

## Frozen incumbent roster

`research/v38_roster.json` already pins 22 of the 24 item-specific
champions, their model families, configuration names, source paths and
the then-current source-verification status. The two additional
`can:Xanax` and `uni:Xanax` mappings are supplied by the pinned
`EXTRA_XANAX` in `research/v128_full24_earliest_shadow.py`.

Archived named families:

- **Flowers + several plushies:** per-item V18/V19/V20 with explicitly
  frozen `dynN` and `trajN` configurations.
- **Monkey and Chamois:** `checkpoint4_online_selector.py`.
- **Panda:** `panda_pair_selector_ml.py`.
- **Lion:** `lion_pair_selector_ml.py`.
- **Camel:** `camel_fast_selector.py`.
- **Nessie:** `recent_phase_select.py`.
- **Red Fox:** `rf_localgrid.py`.
- **Japan Xanax:** separate specialist research
  `research/japan_xanax/renewal_shadow.py`, with pinned roster source
  unverified; never silently substitute the generic flower/plushie clock.

The last seven named specialist paths are not currently certified as
available through this public checkout. The original V18/V19/V20
planner files are in `services/`, but their original training/evaluation
loader uses `history_service`. The special planners likewise require
verifying source and historical-only inputs. **Do not point these scripts
at the live production DB** to compare them. Adapt them to the
**read-only sanitized snapshot**, honor historical as-of training
boundaries, compare identical time windows, and reject unavailable
source/adapters rather than silently falling back to a generic model.

The four physical clocks in `research/restock_event_clock.py` are a
**research baseline**, not a rerun of any of the item-specific champion
roster. The export in `scripts/run_pc_historical_sixcore.py` now
includes `incumbent_family`, `incumbent_config`, and
`incumbent_evaluated_in_this_tournament=false` for every policy.

## Exactly what to score

For every item and physical event ordinal:

1. **Restock accuracy**: issue timestamp, physical restock ordinal, model
   source and forecast `predicted_restock_epoch`. Independently identify
   the ordinal 0->positive event from later polls. Report first-observed
   timestamp, possible poll-bracket range, signed forecast minus
   first-observed restock time (**negative = predicted early; positive =
   predicted late**), absolute timing error, within ±5m and ±10m, no
   prediction/unknown cases, and first-issued-per-distinct-restock
   denominators. A first-observed positive is not the exact server
   restock second. Timing between successful polls remains uncertain.
2. **Chosen physical restock accuracy**: when an earlier drop is not
   reachable, do not relabel the chosen later drop as the first. Score
   its own ordinal and signed error as well. A model can predict the
   next drop accurately but fail to predict a *later chosen drop*.
3. **Flight success**: at each 300s simulated issue, choose earliest
   credible arrival window based only on observations available then.
   Honor actual travel time and +10s grace, model expiry, and final
   as-issued departure confirmation. Score `SUCCESS` only where
   observed stock >=30 is continuous through arrival+10s, otherwise
   `FAILURE` or `UNKNOWN` (provider gap/insufficient polls). Report
   successes / known outcomes, departure coverage, waiting time,
   matched leave-now comparisons, and distinct underlying stock windows.
   Separately report *landing minus observed chosen restock*: negative
   means landed early (could fail); positive means landed late (could
   sell out). Do not confuse lateness with failure itself.
4. **Already stocked**: if quantity >=30 **now**, this is a genuine
   candidate window. The player can depart **immediately** and arrive
   while stock is still there, especially for long-lived flowers.
   Evaluate observed remaining stock through arrival+10s, with
   uncertainty about depletion. Do **not** require another restock.
   Report current-stock departures separately from predicted future
   event departures. Abstain if arrival survival is uncertain; do not
   assume stocked now implies safe purchase.
5. **Model selection**: compare each original item-specific incumbent
   (when its safe read-only adapter is present) against improved
   restock and arrival/flight models on the same later held-out dates.
   Keep one champion **per item**, no global forced winner. Freeze
   selection on an earlier development period; evaluate on an
   untouched later period; prospectively verify on the isolated VM
   before requesting promotion.

## Baseline evidence motivating the design

The owner's PC artifact `30day-laggrid.zip` completed 24 items, 30
historical days, four generic clocks, 0/60/180/300/600-second arrival
offsets. Example of the **later** 15-day half using
`phase_empirical_expected` (proxy hourly cohorts):

| Item | First-next physical restock MAE | Flight known success |
|------|---------------------------------|----------------------|
| Camel | 2.85 min | 68.4% |
| Red Fox | 4.90 min | 69.5% |
| Nessie | 4.63 min | 70.1% |
| Panda | 4.62 min | 61.4% |
| Japan Xanax | 5.83 min | 22.6% |

A good first-event timing error does **not** establish that the selected
*later* reachable restock was accurate. For example the artifact had
many selected later-event identities marked unknown continuity, and
Ceibo's selected physical event error averaged ~65min among only 24
scored selected-event cases, despite next-event MAE ~5.35min on 52
hourly issues. These are **not equivalent denominators**, and
none of these rates is real-player flight proof.

This document records the restored design; **no incumbent scores
have been rerun from their original specialist code yet**. Keep that
gap visible. The user must not be asked to repeat generic 30-day
history until incumbents and the full scorecard are ready.
