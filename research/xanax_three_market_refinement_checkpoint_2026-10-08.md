# Three-market Xanax refinement checkpoint — 2026-10-08

**No production deployment.** Continue concurrently with user-run all-item V20/V21; no changes to running tournaments.

## Dataset
- Latest user-uploaded VM snapshot `torn-fren-stock-history-latest.db`
- SHA256: `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`
- Overall stock_history: 916,510 rows
- Japan Xanax: 8,609 rows; UK/uni Xanax: 12,336; Canada/can Xanax: 12,404
- Historical Japan old cutoff Unix `1791241426`.
- Exact target is at least 30 Xanax on arrival; supplemental +10s, +1m, +3m.
- UK/Canada flight: UK 106 min; Canada 27 min. Japan 149 min.

## Japan reproducible causal study
A *separate independent implementation* of the recorded V7 observation-lag and V8 timing-Ridge research was exercised on the uploaded snapshot with suppressed one-poll provider bounces and known collector gaps:
- 248 observed completed Japan windows, 177 strict clean P2 samples, 21 post-cutoff decision samples.
- V7 post-cutoff: exact 7/21 = 33.3%; +10s 8/21; +1m 8/21; +3m 10/21; reproduces prior reported frozen V7 precisely.
- Independent 60-resolved-sample standardized rolling Ridge, timing features with historical width and cooldown lags, alpha=1, training weights half-life 40 resolved samples:
  - Post-cutoff exact 13/21 = 61.9%
  - +10s 14/21 = 66.7%
  - +1m 14/21 = 66.7%
  - +3m 16/21 = 76.2%
- These are *not* the previously reported 16/21 = 76.2% exact result. That more favorable experiment was not yet reproduced using this independent feature implementation. Treat earlier 76.2% exact as an unverified development challenger, not the sole deployable benchmark.
- Across 95 pre-cutoff causal opportunities where both models were available, V7 49/95 exact vs rolling Ridge 37/95 exact. Ridge's improvement is therefore regime-specific, not universal.
- Simple causal recent-lifetime ratio switch at threshold 0.90 chooses Ridge in all 21 new samples, leading to the Ridge's 13/21 exact; on the 95 pre-cutoff samples it drops to 42/95 exact vs 49/95 V7. **Hard threshold 0.90 does not preserve old-regime accuracy in independent reproduction.**
- The same switch at threshold 0.70 gets 47/95 old exact but just 9/21 new exact. This shows a real stability/adaptation trade-off. Do not promote the simple switch without stronger selection validation.
- Future strict-P2 screening needs care: the 90–150-minute two-gap filter is evaluated retrospectively and relies on future gaps. Thus "100% clean P2 coverage" does NOT mean 100% of every possible live decision state. Extend prospectively to all causally identifiable opportunities before confident production deployment.

## UK / Canada availability-planner wait-budget sensitivity
Using the existing rolling nearest-neighbor planner, 30-minute uniformly sampled decision sessions on the same chronological final 25% test cohort for each country, with training-only configuration choice for each cap, full gap-free flight/wait horizon. All tested states produce a plan (no abstention). **The departure cap is exploratory and has now been examined on holdout, so the best cap is not a pristine final selection.**

Country UK (`uni`):
| Maximum wait | Holdout successes | Holdout accuracy | Mean departure wait |
|---|---:|---:|---:|
| 0m (depart now) | 178/216 | 82.4% | 0m |
| 60m | 185/216 | 85.6% | 6.7m |
| 120m | 195/216 | 90.3% | 15.3m |
| 180m | 203/216 | 94.0% | 45.7m |
| 240m | 206/216 | 95.4% | 36.2m |
| 360m | 204/216 | 94.4% | 55.8m |

Canada (`can`):
| Maximum wait | Holdout successes | Holdout accuracy | Mean departure wait |
|---|---:|---:|---:|
| 0m (depart now) | 171/219 | 78.1% | 0m |
| 60m | 195/219 | 89.0% | 13.2m |
| 90m | 206/219 | 94.1% | 18.4m |
| 120m | 206/219 | 94.1% | 21.0m |
| 180m | 212/219 | 96.8% | 27.3m |
| 240m | 211/219 | 96.3% | 32.2m |
| 360m | 210/219 | 95.9% | 31.4m |

On less-correlated first-one-per-4h checks:
- UK 240m: 27/28 (96.4%) vs depart-now 23/28 (82.1%).
- Canada 180m: 28/28 (100%) vs depart-now 21/28 (75%).
- UK first decision per live/empty run: 16/18 (88.9%) vs immediate 10/18 (55.6%).
- Canada first decision per run: 24/25 (96.0%) vs immediate 13/25 (52.0%).
These small groups are not enough to call the 100% figure a prospective guarantee.

## Recommendation
- Japan: Keep V8 recency-weighted rolling timing model as regime-specific challenger; preserve V7 fallback. Reproduce prior best executable recipe, then validate on genuinely future cycles. Don't assume a simple lifetime-ratio hard switch is already proven across historical regimes.
- UK: Availability-aware model with around 120–240m permitted delay is promising. Prefer showing the availability/time tradeoff, not a single inflated accuracy.
- Canada: Availability-aware model with around 90–180m permitted delay is promising. A 90-minute cap already gets ~94% at much lower wait.
- All markets: report exact, +10s, +1m, +3m, **average/quantile departure wait**, availability/coverage and sample independence. Require matched-cohort incumbent comparisons before promotion.

Saved research artifacts in conversation runtime include:
- `japan_xanax_regime_sensitivity_2026-10-08.json`
- `xanax_wait_budget_2026-10-08.json`
- `uk_can_wait_robustness_2026-10-08.json`
- `japan_xanax_v8_repro.py`, `japan_xanax_regime_switch_compare.py`, `uk_can_xanax_wait_budget_research.py`

No website, Discord bot, production registry, V20 or V21 output changed.
