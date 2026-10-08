# V21 results review and unified two-layer predictor contract — 2026-10-08

## Scope and frozen datasets
User uploaded:
- `corrected_master.json` — schema `remaining-item-v21-corrected-challenger-v1`, 10 targeted complete results
- `truth_audit.json` — independently corrected V19 labels, snapshot SHA256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`
These are based on the **older original frozen DB**. Japan/UK/Canada specialist Xanax research has a newer separate VM snapshot; do not mix mismatched periods without matched reevaluation.

## Corrected audit baseline
- 134 V19 evaluated items; 27,654 sessions; 46 items with repaired labels
- 1,172 actual stock-on-arrival successes had been marked false negative; 0 false positives in this audit
- >=80% V19 items: 48 reported, 62 corrected
- Only arrival-success *labels* were repaired. Model selection originally trained on the flawed labels.

## Targeted V21: scores versus corrected V19
Not a matched test cohort. V21 and V19 have different holdout populations and V21 allows up to 12h departure wait. V21 training-only selector uses corrected quantity-at-arrival scoring, but output must still be judged for travel usability.

| Item | Corrected V19 hits | V21 hits | V21 median wait | Forced-at-12h sessions |
|---|---:|---:|---:|---:|
| uni:Shrooms | 90/90 (100%) | 83/83 (100%) | 0.25h | 0/83 |
| can:Vicodin | 92/92 (100%) | 89/89 (100%) | 12h | 54/89 |
| swi:Ketamine | 88/88 (100%) | 84/84 (100%) | 12h | 58/84 |
| chi:Ecstasy | 89/89 (100%) | 85/85 (100%) | 12h | 60/85 |
| arg:Patagonian Fossil | 86/97 (88.7%) | 64/79 (81.0%) | 3.25h | 12/79 |
| chi:Printing Paper | 80/88 (90.9%) | 69/85 (81.2%) | 4h | 14/85 |
| arg:Meteorite Fragment | 131/212 (61.8%) | 117/122 (95.9%) | 4.875h | 17/122 |
| arg:Tear Gas | 63/248 (25.4%) | 40/163 (24.5%) | 2.5h | 26/163 |
| chi:Fireworks | 108/237 (45.6%) | 43/150 (28.7%) | 4.25h | 15/150 |
| haw:Large Suitcase | 97/223 (43.5%) | 94/136 (69.1%) | 3.25h | 5/136 |

V21 completes all 10 with nominal 100% recommendation coverage; session-weighted success 768/1076 ~=71.4%, but these repeated half-hour sessions are correlated and the sample is targeted rather than representative of 236 items.

**Critical new finding:** Canada Vicodin, Switzerland Ketamine and China Ecstasy all report 100% with a **12-hour median wait**; 172 of their combined 258 holdout sessions were forced at the 12-hour cap. Their corrected V19 output *already* attained 100% on separate sessions. Do not promote V21 there or interpret 100% as better travel guidance. It is a strong example of why delay cost and cap rate must be part of champion selection.

**Meteorite:** V21 95.9% is promising vs corrected V19 61.8% and currently-running V20 raw 89.3%, but V21 waits ~4h53m median, and those challengers lack matched same-session evaluation. Retain all as candidates; do not unilaterally replace V20 or legacy.

**Scarce items:** Arg Tear Gas 24.5%, China Fireworks 28.7% under V21 corrected scorer; still genuinely difficult. Hawaii Large Suitcase 69.1% is improved relative to the previously corrected V19 reported rate but requires a matched test.

## Architecture confirmed with user
Unify the two research goals without throwing out any successful model:

1. **Stock forecast layer**: observed-stock current state; next drop estimate and start/end confidence window; next/estimated depletion; second projected cycle if reachable; timing-model ID; evidence tier; calibrated window-coverage probability only when demonstrated.
2. **Travel layer**: country/airstrip flight, acceptable user wait budget, recommended leave time and leave interval, ETA, target stock event, historical arrival-success by grace (+0, +10 sec, +1m, +3m), calibrated *per-flight* success probabilities only after separate calibration, time cost, plan reliability.
3. **Data quality**: provider bounce and collector outage handling, staleness, quantity feasibility, sparse/persistent item support, status that differentiates observed stock now vs projected future restock. Offer the best supported forecast for all items without inventing timing precision.
4. **Champion selection**: compare legacy V9/V10, V19, V20, V21, flower/plushie specialist and Xanax specialist per item on **matched decision timestamps and equivalent wait caps**; prioritize arrival success and timely travel as distinct metrics; preserve highest actual performance and never promote by version number.

The planned contract code is isolated:
- `services/dual_layer_prediction_contract.py`
- `tests/test_dual_layer_prediction_contract.py`

This module **does not connect to the live application**. It provides the shared schema for the future website/Discord and blocks publication of uncalibrated probability numbers. Legacy `services.prediction_v2_live.build_live_prediction_v2` already produces stock window and leave-by fields; the future adapter should reuse those until specialist engines are ready. No website/Discord modifications now.

## Implementation sequence
1. Finish user-run V20; audit it with corrected scorer.
2. Create matched-cohort research evaluator: identical decision starts, 30+ or requested quantity, gap clean, comparable travel wait cap and departure-grid/replan settings, clock-vs-cycle holdout counts; report exact/+10s/+1m/+3m, restock MAE and p90, predicted-interval coverage, time-to-leave cost, forced-cap %, and stock-on-arrival calibration.
3. Develop robust scarcity and sparse-availability models only for items with genuine failures, plus restock forecast specialists for UK/Canada Xanax and others. Keep Japan V7/V8 regime research isolated.
4. Freeze per-item dual-layer champion registry, shadow run, then unified site/Discord cutover *only when whole system is ready*.

## Explicit cautions
- Do not turn V21's uncalibrated `final_probability` into the website confidence percentage.
- Do not claim 100% availability prediction if forced 12h waits.
- Do not infer a restock-window forecast from an arrival-only model.
- Do not deploy automatically.


## First offline implementation checkpoint
New files on main (offline research/adapter only, not imported by production routes):
- `services/dual_layer_prediction_contract.py`: pure shared result schema for current stock, multi-cycle restock/depletion windows, evidence/confidence, leave time/window/leave-by, flight time, arrival, optional calibrated odds, quality warnings and historical accuracy.
- `services/dual_layer_prediction_legacy_adapter.py`: transforms existing V2 forecast objects into that schema **without** misrepresenting V2's `recommended_leave_by_timestamp` as an optimized leave time. Both first and second projected cycle fields are preserved.
- `tests/test_dual_layer_prediction_contract.py`: planned unit checks for stock state, active vs below requested, window order, flight-time consistency, probability-calibration guardrails, staleness and wait budget.
- `tests/test_dual_layer_prediction_legacy_adapter.py`: planned V2 compatibility checks.

Code authored and committed, but Python tests have **not yet been run in the repo runtime**. From local venv after `git pull` when convenient, run:
```powershell
python -m unittest discover -s tests -p "test_dual_layer_prediction_*.py" -v
```

No production `prediction_v2_live`, API route, Discord command, or dashboard has been changed.


## Essential correction: do NOT penalize natural restock waiting
The user clarified that long waits are often correct because a country/item may take hours to restock. A generic short wait-cap or penalty proportional to absolute hours would bias model selection against slow and rare items. **Historical arrival success is scored the same whether the legitimate target occurs in 5 minutes or 8 hours.**

Separate:
1. **Actual on-arrival availability** for desired quantity and +10s/+1m/etc (primary measure).
2. **Natural/unavoidable opportunity wait**: in a hindsight benchmark, departure delay from session start until the earliest quantity-qualified, flight-reachable stock window. This duration incurs **no predictor penalty**, and no prediction should be judged a failure just because the next real restock is beyond an arbitrary global cap.
3. **Avoidable delay/opportunity regret**: when a successful recommended departure occurs *after* an earlier actual feasible departure, optionally measure this as excess wait in seconds. Report skipped earlier opportunities, and separate early misses. Use future realized stock only for retrospective evaluation, never as a live feature.
4. **User patience/travel constraint**: configurable as UI preference, not universal scoring constant; if no viable chance exists within that constraint, display the next expected stock window and clearly label the guidance as outside the user budget. Stock forecast must still be shown.
5. **Forced wait cap**: track diagnostic status, but do not equate a 12-hour cap with bad accuracy unless earlier feasible opportunities were actually missed.

On the original V21 10-item corrected holdouts, I rechecked historical first feasible opportunities (quantity >=30, 10s grace, airstrip flight and collector gaps), using the original frozen stock DB. Note first feasible time is hindsight/oracle, not known by the model at prediction time:

| Item | V21 median wait | Hindsight earliest feasible median | Median hindsight excess wait (successful sessions only) |
|---|---:|---:|---:|
| arg:Meteorite Fragment | 292.5m | 153.1m | 40.7m |
| haw:Large Suitcase | 195m | 150.9m | 101.7m |
| can:Vicodin | 720m | 0m | 720m |
| swi:Ketamine | 720m | 0m | 720m |
| chi:Ecstasy | 720m | 0m | 720m |

- 17 Meteorite sessions hit the 12h cap; among those, 12 had a hindsight earliest feasible departure >=9 hours after the session started. Much of this long wait is genuinely due to stock timing, not an inefficiency.
- Conversely, all three capped high-stock drug models had a median earliest feasible departure of **immediately**. For those, waiting 12 hours really is avoidable under this quantity target.
- Historical earliest viable departure can be earlier than the model could reliably infer; measure regret separately rather than using oracle hindsight to contaminate causal predictions.
- Future stock windows crossing collector gaps/uncertain observations must be excluded as before.

Implemented reusable pure offline scorer: `services/next_opportunity_evaluation.py`, with tests `tests/test_next_opportunity_evaluation.py`. The six local unit tests passed covering natural long waits, unnecessary 12h waits, multiple opportunities, out-of-budget windows, missed arrivals, invalid inputs. No production integration.

**Next matched champion tournament should optimize arrival success FIRST. Report natural wait separately, and compare avoidable opportunity delay only after matching accuracy; never subtract arbitrary hours of necessary restock waiting from accuracy.**
