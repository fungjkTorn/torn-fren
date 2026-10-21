# Component and adaptive-selector results — October 14, 2026

Private [run38632606726](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38632606726) SUCCESS. Numerical source `81c1ffb3e570d104cc624e36a45a9e34e59d0954`; public CI38632425837 passed72 tests plus Chromium. All24 roster rows verified in retrieved output (strip log-chunk BOM before parsing timestamp prefixes). Source snapshot cutoff1792008529 (2026-10-14T20:08:49.000Z); seven-day replay,37 policies,168 hourly starts/item.

These are historical sampled stock>=30 arrival proxies under five-minute replanning. Not prospective/live flights, exact-second game truth, purchases, or earliest-optimal-departure accuracy. Physical depletion remains positive→exactly0, restock0→positive. Unknown and pending arrivals stay outside resolved percentages. Cohorts overlap and are correlated.

## What worked and failed

The selector is not a general release candidate: across eight priority weak items it produced23 matched gains versus35 losses. Japan Xanax dropped35.53%→27.92% with2 gains/13 losses on148 mutually resolved starts; Lion71.15%→67.72%,2 gains/7 losses on156. RedFox70.44%→71.61%,19 gains/15 losses on153. Changing experts can worsen the actual replanned stream even when each choice only uses matured past outcomes.

Across the other16 items, selector yielded117 gains versus7 losses on mutually resolved starts; pooled resolved counts2240/2499 baseline versus2323/2464 selector. These differing denominators are not themselves matched improvement proof. UAE Tribulus still regressed (2 gains/6 losses), so even this group cannot be promoted wholesale. Selection and design were inspected on overlapping history; no pristine holdout or live certification.

Static component hybrids have useful item-specific signals:
- RedFox current_rate/current_quarter:34 gains/22 losses on157 mutually resolved starts, all168 departed. Average wait18.1→10.0min; sampled worst day54.17%→63.64%. Positive but well below reliable90% performance.
- Panda current_rate/current_quarter:12 gains/9 losses on152 starts, all168 departed. Resolved success69.18%→70.32%; sampled worst day54.55%→63.64%. Small exploratory signal.
- Lion current_rate/current_quarter:25 gains/20 losses on150 starts, all168 departed. Better pooled accuracy but WORSE sampled worst day61.90%→59.09%; not a consistency improvement.
- Lion fast_wait/midpoint has a more even day profile but incurs longer waiting; its matched comparator is zero_anchored_midpoint, NOT current_quarter (28 gains/26 losses on152). Do not conflate the displayed current-quarter baseline with that matched comparator.

| Exploratory static candidate | Baseline current-quarter → candidate arrival success | Worst sampled START-day | Mean wait, all departed |
|---|---:|---:|---:|
| uni:Red Fox Plushie · zero_hybrid_current_rate_current_quarter | 112/159 (70.4%) → 125/160 (78.1%) | 54.2% → 63.6% | 18.1 → 10.0 min |
| chi:Panda Plushie · zero_hybrid_current_rate_current_quarter | 110/159 (69.2%) → 109/155 (70.3%) | 54.5% → 63.6% | 10.4 → 9.8 min |
| sou:Lion Plushie · zero_hybrid_current_rate_current_quarter | 111/156 (71.2%) → 116/156 (74.4%) | 61.9% → 59.1% | 8.5 → 9.6 min |
| sou:Lion Plushie · zero_hybrid_fast_wait_midpoint | 111/156 (71.2%) → 116/160 (72.5%) | 61.9% → 66.7% | 8.5 → 17.4 min |

Daily denominators are typically19–24 resolved starts; apparent worst-day gains are noisy exploratory diagnostics, not guarantees. Candidates above were highlighted after inspection and require fresh validation.

## Adaptive selector, all24 items

Baseline is always zero_anchored_current_quarter. Matched gains/losses are selector-only successes / baseline-only successes on mutually resolved fixed starts; percentages exclude unknown/pending/abstentions. Full outcome-pair matrices, counts, waits, day slices and expert choices are in the private artifact.

| Item | Baseline resolved arrivals | Adaptive resolved arrivals | Matched gains / losses | Adaptive departure coverage |
|---|---:|---:|---:|---:|
| arg:Ceibo Flower | 136/147 (92.5%) | 129/140 (92.1%) | 0 / 0 | 90.5% |
| arg:Monkey Plushie | 104/154 (67.5%) | 104/154 (67.5%) | 0 / 0 | 100.0% |
| can:Crocus | 137/150 (91.3%) | 146/150 (97.3%) | 8 / 0 | 90.5% |
| can:Wolverine Plushie | 142/154 (92.2%) | 142/154 (92.2%) | 0 / 0 | 100.0% |
| can:Xanax | 139/157 (88.5%) | 153/161 (95.0%) | 9 / 0 | 100.0% |
| cay:Banana Orchid | 148/159 (93.1%) | 148/159 (93.1%) | 0 / 0 | 97.6% |
| cay:Stingray Plushie | 142/157 (90.5%) | 150/161 (93.2%) | 4 / 0 | 100.0% |
| chi:Panda Plushie | 110/159 (69.2%) | 110/159 (69.2%) | 0 / 0 | 100.0% |
| chi:Peony | 150/162 (92.6%) | 155/163 (95.1%) | 4 / 0 | 98.2% |
| haw:Orchid | 137/160 (85.6%) | 147/154 (95.5%) | 15 / 0 | 98.2% |
| jap:Cherry Blossom | 136/163 (83.4%) | 149/161 (92.5%) | 15 / 0 | 98.8% |
| jap:Xanax | 54/152 (35.5%) | 43/154 (27.9%) | 2 / 13 | 98.2% |
| mex:Dahlia | 151/157 (96.2%) | 151/157 (96.2%) | 0 / 0 | 95.8% |
| mex:Jaguar Plushie | 151/158 (95.6%) | 151/158 (95.6%) | 0 / 0 | 100.0% |
| sou:African Violet | 138/148 (93.2%) | 142/149 (95.3%) | 3 / 0 | 95.8% |
| sou:Lion Plushie | 111/156 (71.2%) | 107/158 (67.7%) | 2 / 7 | 100.0% |
| swi:Chamois Plushie | 95/153 (62.1%) | 95/153 (62.1%) | 0 / 0 | 100.0% |
| swi:Edelweiss | 140/162 (86.4%) | 142/153 (92.8%) | 12 / 1 | 98.2% |
| uae:Camel Plushie | 106/157 (67.5%) | 106/157 (67.5%) | 0 / 0 | 100.0% |
| uae:Tribulus Omanense | 144/155 (92.9%) | 134/149 (89.9%) | 2 / 6 | 91.7% |
| uni:Heather | 135/157 (86.0%) | 145/150 (96.7%) | 16 / 0 | 94.0% |
| uni:Nessie Plushie | 116/154 (75.3%) | 116/154 (75.3%) | 0 / 0 | 100.0% |
| uni:Red Fox Plushie | 112/159 (70.4%) | 111/155 (71.6%) | 19 / 15 | 100.0% |
| uni:Xanax | 114/153 (74.5%) | 139/145 (95.9%) | 29 / 0 | 89.9% |

## Decision and next research

No production policy, readiness whitelist or publisher assignment changed. Reject blanket use of the adaptive selector and preserve static exploratory candidates for validation. Do not choose a hindsight winner per item and report its inspected-history rate as expected future performance.

Next priority for unresolved weak items is complete multi-cycle path forecasting and causal demand/regime context. The current forecasters still project repeated phase quantiles across long flights; a retrospective model switch does not remove that structural uncertainty. Compare against these pinned static baselines, retain matched starts/coverage/waits, and require fresh forward evidence before calling a model reliable.
