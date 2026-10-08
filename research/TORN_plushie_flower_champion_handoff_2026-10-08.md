# TORN Plushie + Flower Prediction — Champion Finalization Handoff

Date: 2026-10-08
Scope: the 21 foreign museum-set flowers/plushies only. Japan Xanax remains a separate project/chat.

## Final product objective

For each item, use the model that is best for that item. Do **not** force one universal model.

Benchmark / live behavior:
- Success = quantity >= 30 at actual landing, or quantity reaches >= 30 within +10 seconds after landing.
- Planner starts from arbitrary historical website-open/check times.
- It must always maintain a future departure recommendation on valid data (essentially 100% recommendation coverage; no abstention gaming).
- Recalculate as new observations arrive; intended live cadence is every 5 minutes.
- Max planning wait used in current research: 8 hours.
- Known collection gaps and recovery-stamped fake transitions must not be used as training truth.
- User's original stretch goal: >90% for every individual item.
- Temporary acceptable floor for the three far/hard items (Camel, Monkey, Chamois): >=75%, but continue trying to push them to >90% if a causal method earns it.

## Critical benchmark warning

The Oct-02 to Oct-05-ish historical holdout has been inspected repeatedly during research. Treat all current scores as **development evidence**, not as a pristine final lockbox. The all-item finalization pass must preserve these champions, then validate them on a fresh chronological lockbox / newly collected future data before making a generalized live >90% claim.

Do not replace a strong existing item champion merely because a newer architecture exists. A challenger must beat the incumbent on the same causal benchmark.

## Current champion registry

| Country | Item | Champion / candidate | Development score | Coverage | Status |
|---|---|---|---:|---:|---|
| Mexico | Dahlia | V18 `dyn2` | 97.49% | 100% | LOCK candidate |
| Mexico | Jaguar Plushie | V18 `dyn3` | 98.39% | 100% | LOCK candidate |
| Cayman | Banana Orchid | V18 `dyn7` | 94.12% | 100% | LOCK candidate |
| Cayman | Stingray Plushie | V18 `dyn7` | 97.99% | 100% | LOCK candidate |
| Canada | Crocus | V18 `dyn5` | 95.67% | 100% | LOCK candidate |
| Canada | Wolverine Plushie | V18 `dyn8` | 97.58% | 100% | LOCK candidate |
| Hawaii | Orchid | V18 `dyn3` | 100.00% | 100% | LOCK candidate |
| UK | Heather | V18 `dyn3` | 99.13% | 100% | LOCK candidate |
| UK | Nessie Plushie | recent phase/template: `(2h lookback, lag 1d, +/-1h shift, minfit .5, recency_pow 1)` | 90.58% (125/138) | 100% | LOCK candidate, narrow margin |
| UK | Red Fox Plushie | global-regime analog planner `k=18`, global weight `.5` | 91.82% (101/110) | 100% | LOCK candidate |
| Argentina | Ceibo Flower | V18 `dyn3` | 95.38% | 100% | LOCK candidate |
| Argentina | Monkey Plushie | online template-expert selector, 2-day resolved-performance window | 76.15% (83/109) | 100% | BASE champion; stretch >90 unresolved |
| Switzerland | Edelweiss | V19 `dyn9` | 91.76% | 100% | LOCK candidate |
| Switzerland | Chamois Plushie | online template-expert selector, 3-day resolved-performance window | 77.98% (85/109) | 100% | BASE champion; stretch >90 unresolved |
| Japan | Cherry Blossom | V19 `dyn2` | 100.00% | 100% | LOCK candidate |
| China | Peony | V20 `traj12` | 100.00% | 100% | LOCK candidate |
| China | Panda Plushie | two-expert global-regime analog bank: A `(k16, gw=.15)`, B `(k18, gw=.75)` + ExtraTrees selector `depth=3, leaf=3` | 91.67% (99/108) | 100% | PROVISIONAL: weak selector validation, retest early |
| UAE | Tribulus Omanense | V18 `dyn3` | 96.62% | 100% | LOCK candidate |
| UAE | Camel Plushie | current-plan-probability selector across 24 template experts | 75.00% (81/108) | 100% | BASE champion; stretch >90 unresolved |
| South Africa | African Violet | V19 `dyn7` | 92.81% | 100% | LOCK candidate |
| South Africa | Lion Plushie | two-expert global-regime analog bank: A `(k14, gw=.35)`, B `(k18, gw=.5)` + logistic selector | 91.59% (98/107) | 100% | LOCK candidate / retest selector |

### Notes on the four newer >90 hard-item champions

**Nessie**
- Reproduced from `recent_phase_select.py`.
- Selector uses only the most recent 15% of pre-holdout history.
- Validation: 91.80%.
- Holdout: 90.58% = 125/138.
- Config: `(lookback_h=2, lags=(1,), shift_h=1, minfit=.5, recency_pow=1.0)`.

**Red Fox**
- Reproduced from `rf_localgrid.py`.
- Selected config `(k=18, global_regime_weight=.5)`.
- Validation: 93.94%.
- Holdout: 91.82% = 101/110.
- This is one of the cleaner newer champions because the same config is >90 on validation and holdout.

**Lion**
- Reproduced from `lion_pair_selector_ml.py`.
- Expert A `(14,.35)`, Expert B `(18,.5)`.
- Validation fixed experts: A 90.63%, B 78.13%; pair oracle 92.71%.
- Validation-selected selector: logistic, validation reward 89.58%.
- Holdout: 91.59% = 98/107; A 73.83%, B 90.65%, pair oracle 99.07%.
- This is causal but regime-sensitive; retest on fresh lockbox before production certainty.

**Panda**
- Reproduced from `panda_pair_selector_ml.py`.
- Expert A `(16,.15)`, Expert B `(18,.75)`.
- Selector: ExtraTrees `depth=3`, `min_samples_leaf=3`, selected on validation.
- Validation selector reward only 80.41%; holdout 91.67% = 99/108.
- Pair holdout ceiling 98.15%.
- Marked provisional because the holdout result is much better than validation; fresh lockbox is mandatory.

## Three remaining stretch items

### Camel Plushie
Current accepted base:
- `camel_fast_selector.py` current-plan-probability chooser across the 24 template experts.
- 81/108 = **75.00%** on the later segment.
- Simple fixed/template experts can reach ~75.9% diagnostically.
- Existing two-expert opportunity ceiling has been observed around **94-97%**, depending pair/search definition.
- Binary recent-performance selectors and probability-curve averaging failed to convert that ceiling causally.
- Strong regime shift around Sep-27/28 is the major problem.

### Monkey Plushie
Current accepted base:
- `checkpoint4_online_selector.py`, 2-day window.
- 83/109 = **76.15%**.
- Best single expert diagnostic ~77.98%.
- Two-expert opportunity ceiling ~95.4%.
- Per-trip classifier looked strong on validation and failed after regime switch; do not reuse that approach blindly.

### Chamois Plushie
Current accepted base:
- `checkpoint4_online_selector.py`, 3-day window.
- 85/109 = **77.98%**.
- Best fixed expert diagnostic ~80.73%.
- Two-expert opportunity ceiling ~95-96%.
- Curve averaging/fusion failed because complementary experts often represent different phases; averaging creates a bad middle phase.

## Strong research conclusions to preserve

1. **Per-item champions are correct.** There is no requirement for one universal model.
2. **Exact restock-second prediction is not necessary.** Landing safely inside the active stock window is what matters.
3. **Fixed 15-minute tick theory was rejected.** Median timing error ~225s; only ~20% within 90s.
4. **The hard long-flight items are primarily a multi-cycle phase/regime problem.** Independent lifetime recursion compounds error badly over 2-3+ hours.
5. **Active-window lifetime is the dominant missing signal.** Empty waits are much more stable (~15-16m for hard plushies in recent regimes).
6. **Future active lifetimes are causally predictable to a degree.** Recent-regime lifetime autocorrelation is meaningful for most hard plushies.
7. **Oracle lifetime tests prove structural headroom.** Camel re-check reached ~98.2% when future active lifetimes were supplied; earlier diagnostics for the hard plushies were mostly ~95-100%.
8. **Global/shared regime features help lifetime prediction**, but direct leave-now 3h occupancy classifiers are weak and should not become the main architecture.
9. **Regime changes are real and shared across items.** Sep-26 to Sep-28 had a dramatic short-lifetime demand shock, then recovery.
10. **Do not average conflicting expert phases.** Curve fusion was tested and rejected.
11. **Late binding / continual replan is still conceptually valid**, but it must be evaluated causally and must not become disguised abstention.
12. **No abstention gaming.** Missing a recommendation on otherwise-valid data counts against us.

## Data / important local research files

SQLite used in research:
- `/mnt/data/torn-fren-stock-history-fresh(3).db`
- ~121 MiB
- includes `stock_history`, `collection_gaps`, `prediction_audits`, `forecast_audit_points`, `forecast_audit_runs`, poll heartbeats, etc.

Baseline result files:
- `/mnt/data/plushie_flower_v18.json`
- `/mnt/data/plushie_flower_v19_targeted.json`
- `/mnt/data/plushie_flower_v20_targeted.json`

New champion / hard-item scripts:
- `/mnt/data/recent_phase_select.py` — Nessie recent-phase champion selection
- `/mnt/data/rf_localgrid.py` — Red Fox champion
- `/mnt/data/lion_pair_selector_ml.py` — Lion pair selector champion
- `/mnt/data/panda_pair_selector_ml.py` — Panda pair selector candidate
- `/mnt/data/checkpoint4_online_selector.py` — Monkey/Chamois online selector baselines
- `/mnt/data/camel_fast_selector.py` — Camel probability selector baseline
- `/mnt/data/curve_fusion_checkpoint.py` and related scripts — rejected curve-fusion family

Repo / workflow facts:
- GitHub main is source of truth.
- User prefers assistant pushes commits; user pulls.
- Old local stash from before V18 sync remains safe. **Never tell user to pop it.**
- Do not use VS Code Sync.
- Do not ship research scripts merely because they are newest.
- Production should use a champion manifest / registry to dispatch per-item winner models.

## Required all-item finalization pass in the continuation chat

The continuation chat should now stop broad invention and perform a **champion tournament/finalization**:

1. Reproduce every row in the 21-item registry above against a common benchmark harness.
2. Normalize all success accounting to the exact arrival/+10s rule and 100% coverage requirement.
3. Preserve each current champion as the incumbent.
4. For each item, compare only credible challengers from V18/V19/V20 plus the newer item-specific models.
5. Freeze `item -> champion model/config` into one machine-readable manifest.
6. Run an all-21 chronological simulation using that manifest.
7. Use a **fresh lockbox** not already optimized against. The current Oct holdout is development data now.
8. Report per-item success, successes/N, coverage, median wait, model family, and config. Never report only an average.
9. If fresh data confirms the champion registry, integrate that registry into the live planner and expose predicted stock windows + recommended leave time + expected arrival + success probability + backup opportunity.
10. Keep Camel/Monkey/Chamois current >=75% champions as the safe baseline, but run a final targeted stretch tournament for >90 using late-binding / regime-transition ideas. Do not hold up the first live base system indefinitely if the fresh lockbox confirms the >=75% floors and the other 18 items remain >90%.

## Travel times

- Mexico: 1020s
- Cayman: 1380s
- Canada: 1620s
- Hawaii: 5340s
- UK: 6360s
- Argentina: 6660s
- Switzerland: 6960s
- Japan: 8940s
- China: 9600s
- UAE: 10800s
- South Africa: 11820s

## Immediate next action

Build the common champion benchmark/manifest first. Do **not** begin another V22/V23 universal model. The goal now is to finalize and productionize the best per-item models we already discovered, while using the final tournament to identify any item whose purported champion does not reproduce.