# UK / Canada Xanax availability-aware research — 2026-10-07

## Snapshot
- DB: `torn-fren-stock-history-latest.db`
- SHA256 `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`
- UK (`uni`) Xanax raw observations 12,336; 6 provider bounces suppressed; 70 completed >=30 observed windows.
- Canada (`can`) Xanax raw observations 12,404; 4 provider bounces suppressed; 110 completed >=30 observed windows.
- Median observed window: UK 142.2 minutes, Canada 77.7 minutes. Most recent 20 medians UK 290.4m, Canada 240.0m.
- Strongly unlike Japan Xanax (~10.8m observed median); reuse Japan's P2-only Ridge is not justified.

## Benchmark definition
- User decisions sampled uniformly every 30 minutes over the collected timeline.
- Filter decisions whose *full* flight + max-departure-wait window intersects recorded collection gaps.
- UK airstrip flight 6,360 sec (106m); Canada 1,620 sec (27m), from Torn Fren's travel constants.
- Success means >=30 Xanax in stock at arrival or within a 10-second arrival grace.
- Candidate waits 0..360 minutes in 30-minute steps (13 choices). Delayed departure allowed, no abstention.
- Chronological first 75% model development, final 25% holdout. Configuration selected on validation within earlier 75%; holdout was not used for selection.
- Labels for training analogs must have fully resolved before each decision time, including its largest candidate departure delay.

## Model
A causal rolling weighted nearest-neighbor planner on current available stock, normalized stock fraction, current stock/empty run age, recent 5/30/60-minute trends, and time-of-day. Training candidates are sampled decision states from the last 200 resolved starts, choose 16 nearest neighbors, reciprocal-distance exponent 2, wait penalty 0.05 estimated success probability per hour. Model uses observed quantity and past timeline only. No recommendation abstention.

## Holdout results
| Country | N 30-minute decisions | Depart-now success | Rolling planner success | Gain |
|---|---:|---:|---:|---:|
| UK | 216 | 178/216 = 82.41% | 201/216 = 93.06% | +10.65 pp |
| Canada | 219 | 171/219 = 78.08% | 210/219 = 95.89% | +17.81 pp |

All sessions qualify for a recommendation. No 10-second near-threshold increment happened to change these coarse 30-minute outcomes.

### Outcome by current stock state
| Country | State | N | Depart now | Planner |
|---|---|---:|---:|---:|
| UK | currently live >=30 | 175 | 149/175 = 85.14% | 162/175 = 92.57% |
| UK | currently below30 | 41 | 29/41 = 70.73% | 39/41 = 95.12% |
| Canada | currently live >=30 | 171 | 159/171 = 92.98% | 163/171 = 95.32% |
| Canada | currently below30 | 48 | 12/48 = 25.00% | 47/48 = 97.92% |

Paired outcomes:
- UK 23 improved by planner, 0 worsened, 15 planner failures, 38 depart-now failures.
- Canada 39 improved, 0 worsened, 9 planner failures, 48 depart-now failures.

### Departure wait tradeoff
- UK: 70.83% depart immediately; median wait all sessions 0; median when waiting 180m; mean across all sessions 48.1m.
- Canada: 73.52% depart immediately; median wait all sessions 0; median when waiting 90m; mean across all sessions 31.4m.

### Robustness: less-correlated subsamples
30-minute sessions are **not** statistically independent; long stock windows contribute many outcomes. As a check:
- First decision per distinct live/empty-state episode: UK 16/18 = 88.9% versus depart-now 10/18=55.6%; Canada 24/25=96.0% versus depart-now 13/25=52.0%.
- One decision per 4-hour bin: UK 25/28 = 89.3% versus 23/28 = 82.1%; Canada 27/28 = 96.4% versus 21/28 = 75%.
- Four chronological holdout quarters for UK planner: 50/54, 51/54, 47/54, 53/54.
- Four chronological holdout quarters for Canada planner: 51/54, 54/55, 53/55, 52/55.

Simple model ablation:
- 120-minute cooldown heuristic (depart now if live, otherwise wait toward zero-start+120m minus flight duration): UK 183/216 = 84.7%; Canada 203/219 = 92.7%. Better than depart now but worse than rolling nearest-neighbor.

## Interpretation
This is a separate research backtest, **not** the existing V18/V19 exact code running on a matched cohort. Earlier broad V19 registry gives UK Xanax 91.96% (206/224) and Canada Xanax 78.69% (192/244) on a different simulated departure-start methodology. Do **not** directly use the cross-benchmark percentage gaps as proof that one system beats the other.
UK/Canada stocks persist for hours; availability-on-arrival / adaptive waiting is a better modeling formulation than Japan's short-lived P2-timing model.

## Next
1. Compare the candidate and current V18/V19 winner on exactly matched times and horizons.
2. Evaluate departure penalty and user time-cost rather than maximizing availability alone.
3. Stress-test on newly collected independent cycles before production winner designation.
4. Japan Xanax retains separately selected regime-adaptive V8; avoid blind sharing.
5. Preserve these models as specialist challenger candidates for production registry integration.
