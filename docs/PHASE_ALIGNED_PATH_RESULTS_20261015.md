# Japan-priority phase-aligned trajectory results — 2026-10-15 UTC

Numerical source `634fd14522121cb26ef39350c4ea9b516632bf69`; private [run38675572102](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38675572102). CI passed89 replay tests, Chromium and all compatibility workflows.

Four variants were fixed before results: analog70, analog50, analog_peak and recent_peak. Whole observed futures are aligned to the same elapsed age after an observed physical restock/zero event; all subsequent cycles remain together. Training requires the entire aligned8h+flight+minute-bin+maturity horizon to finish before each issue. Zero means exactly0, not below30. Sampled transition anchors are not exact game-event seconds.

All rates below are historical resolved-arrival stock>=30 proxies, not actual purchases, live flights or calibrated future probabilities. All five-minute starts overlap heavily. A higher rate with lower coverage or excessive waiting is not automatically better. The peak variants are explicitly low-support diagnostics (minimum uncalibrated support0.15); support thresholds50/70 are not success guarantees. Existing event timing scores are not assigned to these departure-only models.

Reference policies were fixed from the preceding all-start report before retrieving this experiment's results, retaining useful coverage rather than simply the highest conditional score. They are research comparisons, not production assignments. All comparisons here use the SAME current snapshot; do not interpret changes versus an earlier snapshot as isolated model gains.

Snapshot cutoff1792033919 (2026-10-15 03:11:59 UTC / October14 23:11:59 EDT). Seven-day issue window,2016 five-minute starts per item/policy. All24 rows verified. Entire private run SUCCESS; future protocol correctly reported ready=False and retained its original source/window.

## Japan: reject this approach as an improvement

| Variant | Successes / resolved | Arrival success | Departure coverage | Wait min | Worst resolved day |
|---|---|---|---|---|---|
| zero_rate_current_quarter | 679/1858 | 36.54% | 98.81% | 71 | 8.68% |
| zero_path_aligned_analog70 | 0/96 | 0.00% | 4.76% | 240 | 0.00% |
| zero_path_aligned_analog50 | 126/349 | 36.10% | 22.12% | 216 | 0.00% |
| zero_path_aligned_analog_peak | 338/1334 | 25.34% | 67.46% | 173 | 0.00% |
| zero_path_aligned_recent_peak | 525/1726 | 30.42% | 100.00% | 76 | 15.97% |

The existing rate reference scored36.54%. Aligned50 matched roughly that conditional score but offered only22.12% coverage with216min waits; on matched resolved starts it won5/lost23 against rate. Analog peak25.34% and recent peak30.42% lost125/277 and134/288 respectively. Aligned70 resolved only96 correlated starts, all failures, with4.76% coverage; this is sparse episode exposure, NOT96 independent failed trips. Do not promote any aligned Japan variant or interpret support70 as70% future success. Exact phase alignment alone has not solved long-lead uncertainty. The next Japan direction needs independently evaluated long-lead forecast-error/clock-drift conditioning; no accuracy gain is claimed for that unimplemented hypothesis.

## Useful findings elsewhere

- **Chamois aligned analog70**:1327/1880=70.59% vs65.44% shared-regime70. Coverage100% vs91.07%, mean wait36vs90min, worst day55.59% vs45.42%; paired303 wins/221 losses on1534 matched starts. Starting-minute scores67.95–73.86%. Strongest balanced lead this round, still well below the reliability goal.
- **Camel aligned analog50**:66.21% vs65.85% local70, full coverage, wait4vs24min, worst day61.79% vs51.11%. Paired296/300: no matched accuracy improvement. Retain as a speed/day-floor tradeoff, not an accuracy breakthrough.
- **Lion aligned analog50**:67.36% vs69.14% shared-regime70, full coverage, wait4vs17min, worst day64.17% vs55.99%; paired248/256. More even sampled days and shorter waits, lower average success. Recent peak81.02% has84.03% coverage,117min wait and58.66% worst day; paired366/167 but many baseline successes become abstentions. A separate slower-trip research option, not a universal replacement.
- **Nessie analog peak**:88.52% vs77.07% shared-regime70, but80.70% vs99.55% coverage and131vs36min wait; worst day48.80% vs61.83%; paired213/107. Its attractive average does not meet the day-to-day consistency objective. Recent peak84.90% also has lower coverage78.57% and56.03% worst day.
- **Red Fox analog peak**:82.40% vs73.58% hybrid;88.94% vs99.55% coverage,109vs10min wait,57.29% vs66.42% worst day; paired263/137. Keep as an explicit accuracy/wait tradeoff, not a faster or more consistent policy.
- Monkey analog peak74.23% vs72.07% local70, with lower coverage90.03% vs96.58%,112vs66min wait,40% vs56.02% worst day. Panda's existing shared-regime80 remains86.36%; aligned variants do not improve it. Strong existing local/rate candidates remain preferred overall.

## All24 fixed comparisons

Each cell is resolved historical arrival success / departure coverage. The reference column names the policy fixed from the previous report. Exact counts, waits, all days (including no resolved arrivals), offset counts and paired results appear in [the companion scorecard](PHASE_ALIGNED_PATH_RESULTS_20261015.json).

| Item | Reference policy | Reference | Aligned70 | Aligned50 | Analog peak | Recent peak |
|---|---|---|---|---|---|---|
| arg:Ceibo Flower | zero_path_analog80 | 99.45% / 98.96% | 93.60% / 95.09% | 90.44% / 97.02% | 99.81% / 84.13% | 99.40% / 91.47% |
| arg:Monkey Plushie | zero_path_analog70 | 72.07% / 96.58% | 68.50% / 99.85% | 64.06% / 100.00% | 74.23% / 90.03% | 63.80% / 88.54% |
| can:Crocus | zero_rate_current_quarter | 100.00% / 91.07% | 96.46% / 66.52% | 95.99% / 66.52% | 98.10% / 64.14% | 97.68% / 88.84% |
| can:Wolverine Plushie | zero_path_analog80 | 96.69% / 100.00% | 85.31% / 100.00% | 72.37% / 100.00% | 96.96% / 100.00% | 93.61% / 99.95% |
| can:Xanax | zero_hybrid_current_rate_current_quarter | 96.39% / 99.80% | 79.36% / 48.76% | 72.95% / 49.95% | 77.24% / 48.26% | 89.25% / 99.75% |
| cay:Banana Orchid | zero_path_analog80 | 99.84% / 95.68% | 97.24% / 89.19% | 94.04% / 89.29% | 100.00% / 79.76% | 98.48% / 93.06% |
| cay:Stingray Plushie | zero_path_analog80 | 98.23% / 99.95% | 88.30% / 100.00% | 83.56% / 100.00% | 98.07% / 99.95% | 98.30% / 99.90% |
| chi:Panda Plushie | zero_path_regime80 | 86.36% / 96.03% | 70.15% / 99.95% | 64.79% / 100.00% | 72.10% / 79.32% | 65.42% / 62.30% |
| chi:Peony | zero_hybrid_current_rate_current_quarter | 96.41% / 100.00% | 90.98% / 86.86% | 92.53% / 87.50% | 97.96% / 70.04% | 96.98% / 98.51% |
| haw:Orchid | zero_hybrid_current_rate_current_quarter | 99.79% / 97.82% | 93.51% / 85.86% | 87.62% / 89.73% | 86.30% / 79.66% | 100.00% / 96.08% |
| jap:Cherry Blossom | zero_path_analog80 | 96.67% / 98.56% | 85.06% / 95.78% | 76.17% / 97.57% | 95.43% / 68.50% | 96.57% / 96.83% |
| jap:Xanax | zero_rate_current_quarter | 36.54% / 98.81% | 0.00% / 4.76% | 36.10% / 22.12% | 25.34% / 67.46% | 30.42% / 100.00% |
| mex:Dahlia | zero_rate_current_quarter | 100.00% / 98.96% | 94.58% / 94.74% | 94.41% / 94.74% | 98.14% / 93.50% | 98.53% / 98.91% |
| mex:Jaguar Plushie | zero_path_analog80 | 98.81% / 100.00% | 97.63% / 100.00% | 96.24% / 100.00% | 99.02% / 100.00% | 97.19% / 100.00% |
| sou:African Violet | zero_path_analog80 | 98.80% / 96.28% | 95.01% / 80.80% | 94.81% / 80.90% | 100.00% / 52.83% | 99.72% / 91.17% |
| sou:Lion Plushie | zero_path_regime70 | 69.14% / 100.00% | 63.37% / 99.85% | 67.36% / 100.00% | 69.90% / 96.13% | 81.02% / 84.03% |
| swi:Chamois Plushie | zero_path_regime70 | 65.44% / 91.07% | 70.59% / 100.00% | 61.98% / 100.00% | 73.00% / 93.70% | 55.79% / 54.17% |
| swi:Edelweiss | zero_path_analog80 | 97.52% / 100.00% | 84.54% / 100.00% | 80.14% / 100.00% | 97.72% / 100.00% | 97.42% / 99.31% |
| uae:Camel Plushie | zero_path_analog70 | 65.85% / 100.00% | 63.93% / 99.90% | 66.21% / 100.00% | 65.00% / 88.49% | 65.26% / 77.38% |
| uae:Tribulus Omanense | zero_path_analog80 | 99.63% / 100.00% | 96.79% / 72.42% | 94.06% / 72.42% | 100.00% / 45.59% | 96.41% / 97.27% |
| uni:Heather | zero_path_analog80 | 99.72% / 97.32% | 89.80% / 95.73% | 86.84% / 96.18% | 98.15% / 92.66% | 99.83% / 91.91% |
| uni:Nessie Plushie | zero_path_regime70 | 77.07% / 99.55% | 67.55% / 99.95% | 71.86% / 99.95% | 88.52% / 80.70% | 84.90% / 78.57% |
| uni:Red Fox Plushie | zero_hybrid_current_rate_current_quarter | 73.58% / 99.55% | 68.40% / 99.85% | 67.88% / 99.85% | 82.40% / 88.94% | 74.54% / 96.38% |
| uni:Xanax | zero_hybrid_current_rate_current_quarter | 99.94% / 88.89% | 72.43% / 50.35% | 46.03% / 83.33% | 51.02% / 9.72% | 100.00% / 18.50% |

## Decision and remaining limits

Retain Chamois aligned70 as a new validation lead; keep Camel/Lion50 as explicit speed/day-floor alternatives and Lion/Nessie/RedFox peak variants as slower-trip tradeoffs. Do not broadly replace strong references. Japan remains unresolved, with this entire new family rejected as an improvement there. Inspected historical lead selection needs fresh validation; none of these rates is a calibrated future probability, deployment approval or independent-flight certification.

The predeclared fixed_forward_v1_20261015 remains source87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04, October14 22:30 EDT–October15 22:30 EDT. Its earliest mature snapshot isOctober16 09:55:10 EDT; snapshot availability, scheduling and replay runtime can delay results. It tests the earlier frozen family, NOT these new aligned variants. Any validation for the new family needs a separate future protocol. No production route, publisher assignment, collector access or frozen-window source changed.
