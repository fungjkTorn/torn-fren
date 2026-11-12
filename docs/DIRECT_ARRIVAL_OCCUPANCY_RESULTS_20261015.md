# Direct arrival occupancy results — October 15, 2026

No general replacement passed. The direct classifier failed Japan and most weak plushies. Lion and Panda show selective tradeoffs worth recording, not automatic promotion.

Private run **38740796747**, source `ee4235c488cba45dd9b6b8e81f9dfc900f90564b`, sanitized snapshot **2026-10-15 12:47:58 UTC**. Eight selected items, seven days, **2,016 five-minute starts per policy per item**. This is exploratory historical reconstruction of sampled stock >=30 at arrival, not purchases, actual flights, calibrated probabilities, or independent trials. Reference rates below are rerun on the same snapshot; they must not be compared with earlier snapshot rates as evidence of model improvement.

## Fixed model comparison

Each cell shows conditional success / departure coverage / mean wait. Day floors are also conditional, with all seven daily counts retained in the companion JSON. No departure means undefined accuracy, not 0% accuracy.

| Item | Established reference | Direct 70 gate | Reference → direct worst day |
|---|---|---|---|
| arg:Monkey Plushie | 71.34% / 96.38% / 64m | 63.81% / 71.33% / 120m | 53.16% → 30.39% |
| chi:Panda Plushie | 85.53% / 94.39% / 131m | 84.34% / 71.18% / 115m | 55.73% → 73.98% |
| jap:Xanax | 39.48% / 99.95% / 71m | — / 0.00% / — | 17.77% → — |
| sou:Lion Plushie | 70.41% / 100.00% / 11m | 78.85% / 68.75% / 115m | 59.61% → 60.63% |
| swi:Chamois Plushie | 69.59% / 99.36% / 32m | 56.76% / 58.93% / 142m | 55.00% → 22.73% |
| uae:Camel Plushie | 65.81% / 100.00% / 4m | 61.73% / 66.91% / 126m | 62.23% → 34.57% |
| uni:Nessie Plushie | 77.27% / 99.95% / 33m | 60.45% / 76.59% / 106m | 52.79% → 30.91% |
| uni:Red Fox Plushie | 74.21% / 99.95% / 10m | 77.95% / 78.17% / 106m | 66.17% → 46.55% |

## Diagnostic peak policy

The peak policy is deliberately permissive and does not claim a calibrated chance of success. It is not a recommended fallback when the 70 gate abstains.

| Item | Success | Coverage | Mean wait | Worst day |
|---|---:|---:|---:|---:|
| arg:Monkey Plushie | 63.65% | 76.98% | 108m | 35.18% |
| chi:Panda Plushie | 77.23% | 76.39% | 110m | 36.77% |
| jap:Xanax | 37.49% | 80.95% | 139m | 1.12% |
| sou:Lion Plushie | 70.34% | 83.83% | 96m | 53.25% |
| swi:Chamois Plushie | 52.92% | 75.99% | 110m | 36.19% |
| uae:Camel Plushie | 56.96% | 76.93% | 110m | 32.58% |
| uni:Nessie Plushie | 70.65% | 74.85% | 111m | 36.62% |
| uni:Red Fox Plushie | 52.11% | 75.69% | 109m | 32.68% |

## Interpretation

- **Japan:** rate reference 732/1,854 =39.48%, 99.95% departure coverage, 71-minute wait. Direct peak 592/1,579 =37.49%, 80.95% coverage, 139-minute wait; worst day 1.12%. Strict direct70 made no departures. Reject both as replacements. The peak variant does win 227 versus lose 192 on 1,476 jointly resolved starts against rate, but omits 178 starts where rate succeeded. Its positive matched subset does not rescue its worse overall behavior.

- **Lion:** direct70 reaches 1,066/1,352 =78.85%, versus 1,299/1,845 =70.41% for the recent rate-correction reference. Coverage falls from 100% to 68.75%, waiting rises from 11 to 115 minutes, and the worst-day gain is only 59.61% to 60.63%. A selective experimental option, not a balanced winner. Reported paired comparisons are against rate and hybrid, not the stronger recent-correction reference.

- **Panda:** direct70 has a better conditional day floor (73.98% vs 55.73%) and slightly shorter wait, but lower average success (84.34% vs 85.53%) and much lower coverage (71.18% vs 94.39%). Retain as a selective diagnostic, not a demonstrated overall improvement.

- **Red Fox:** 77.95% conditional average versus 74.21% hides coverage falling to 78.17%, wait increasing from 10 to 106 minutes and worst day falling from 66.17% to 46.55%. Keep the reference. Monkey, Chamois, Camel and Nessie also keep their references.

Japan has a **149-minute modeled flight** versus a **12-minute median completed buying window**. Median positive physical phases are 722 seconds and median empty phases 7,178 seconds. These are separate marginal medians, not paired future cycle predictions or a proven predictability ceiling.

The classifier had substantial mature history: Japan’s final fit used 443 distinct hourly origins and 13,831 known horizon labels, with 29 canonical refits. The family was warmed from pre-window data; missing initial training is not a plausible explanation for this rejection. Origins and overlapping horizon labels remain correlated.

As-issued proposal rates and replanned departure rates differ substantially for some plushies, but their selected populations differ. That gap does not establish a causal benefit from freezing a departure. A separate paired execution ablation was completed with unchanged model coefficients (see `DEPARTURE_COMMITMENT_ABLATION_20261015.md`): first healthy proposal, fixed target, fresh heartbeat at departure, same starts, same eight-hour deadline. Later stock/model advice is intentionally ignored only in this diagnostic.

## Validation and boundaries

98 CI tests, Chromium interface checks and compatibility workflows passed for the direct classifier source. Future mutation, shorter snapshot, arbitrary replay warmup and true-zero tests passed. A periodic synthetic check recovered 8/8 target arrivals; this validates plumbing, not real accuracy.

Artifact 11976127804 (`direct-arrival-occupancy-v1`), 264,846 bytes, SHA256 `3be2c15017b338b8c35b66dbc4c128bf0b804c070cd66e2e3ee35cdb2a4ef22a`, verified before extraction. Companion JSON contains all selected-policy counts, UTC offsets, day slices, training maturity diagnostics, paired comparisons and physical/availability phase summaries.

No production promotion. Routine approved source remains a73adb6d786e0e7e710fcc99ec8c70e9e8319885; existing frozen forward protocol retains 87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04 and original dates. Global heartbeats still do not verify per-country upstream freshness.

## Data quality finding

`services/stock_provider.py` exposes each country's provider `update` clock.
The stock table and `save_snapshot_from_export` in `services/history_service.py`
store local collection time, quantity, cost and source. The sanitized research
export likewise contains no country update clock. Thus a successful collector
heartbeat cannot establish the age of the provider's country observation.
This is a verified measurement limitation, **not proof that stale reports
caused Japan's errors**. Historical per-country freshness cannot be recovered
from these fields alone. Future instrumentation should preserve provider and
country update clocks alongside local receipt time, including unchanged-stock
polls, before changing freshness-based labels or making stronger accuracy
claims. No collector or production schema was modified in this experiment.
