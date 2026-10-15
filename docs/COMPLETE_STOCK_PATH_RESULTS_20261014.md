# Complete stock path results — October14 evening,2026

Private [run38661757886](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38661757886) SUCCESS. Numerical source7dc462dd8a128df44407f5df7db05423225dbdc3; CI38661654234 passed75 tests plus Chromium and compatibility checks. Snapshot cutoff1792024856 (2026-10-15T00:40:56.000Z); seven days,24 verified items,23 focused policies,168 hourly starts/item.

Historical sampled stock>=30 at simulated arrival, with five-minute replanning,180s source expiry and8h maximum wait. Not actual player flights, exact game-event timing, calibrated success probability, or earliest-optimal departure accuracy. These data overlap inspected history. Support thresholds70/80 are empirical path votes, not success probabilities.

## Useful signals and limitations

- Monkey analog70:125/155=80.65% versus baseline68.35%,162/168 departures. Matched31 gains/13 losses versus baseline,43/16 versus current-rate hybrid,42/14 versus full rate. Mean wait~13->68min; latest and worst sampled days66.67%. Useful but NOT consistently reliable90% behavior.
- Chamois analog70:93/137=67.88% versus58.55%,153/168 departures.33/20 versus baseline,33/19 versus current-rate hybrid. Mean wait~12->100min; worst sampled day26.09%. Reject as a general reliability improvement despite pooled gain.
- Stingray analog80:156/160=97.5%, all168 depart;13/0 matched versus baseline,6/0 versus hybrid,9/0 versus rate. Worst sampled day91.67%; mean wait~13min. Strong historical validation lead.
- Wolverine analog80:146/153=95.42%, all168 depart;12/4 versus rate. Worst sampled day82.61%; no claim of consistent90%-every-day performance.
- Ceibo analog80:153/154=99.35%, all168 depart;23/0 versus each prior hybrid and rate reference; worst sampled day95.24%.
- Edelweiss analog80:158/162=97.53%, all168 depart;16/1 versus hybrid,28/1 versus rate; worst sampled day90.91%.
- Tribulus analog80:157/157 sampled successes, all168 depart;22/0 versus hybrid,6/0 versus rate. Finite historical100% is NOT a guarantee.
- Several flowers already tie strong rate/hybrid references: do not call Crocus/Orchid/Dahlia ties new gains just because they beat the weaker all-history baseline.
- UK Xanax analog70 loses45 matched successes versus each strong hybrid/rate reference (0 gains); reject. Japan Xanax all three paths produce no departures: no accuracy rate and no solution.
- Panda/Lion/Nessie/RedFox are not generally improved. Increasing support70->80 often worsens actual replanned outcomes and greatly increases waits. recent70's uniform trajectories often never execute or have inadequate coverage; reject blanket use.

## All24 fixed comparisons

Every cell lists resolved successes/denominator, departure coverage over168 starts, and mean wait among departed cohorts. Unknown and pending arrivals are excluded from resolved success, abstentions remain in coverage. Comparisons here always use current-quarter zero baseline; mutually resolved outcome pairs below avoid conflating denominator changes with gains.

| Item | Zero baseline | Condition analog70 | Condition analog80 |
|---|---|---|---|
| arg:Ceibo Flower | 138/149 (92.6%) | 153/156 (98.1%); 100.0% coverage; 46min wait | 153/154 (99.4%); 100.0% coverage; 54min wait |
| arg:Monkey Plushie | 108/158 (68.3%) | 125/155 (80.7%); 96.4% coverage; 68min wait | 92/118 (78.0%); 79.8% coverage; 121min wait |
| can:Crocus | 145/149 (97.3%) | 147/149 (98.7%); 91.1% coverage; 57min wait | 147/147 (100.0%); 89.9% coverage; 59min wait |
| can:Wolverine Plushie | 139/153 (90.8%) | 145/155 (93.5%); 100.0% coverage; 11min wait | 146/153 (95.4%); 100.0% coverage; 15min wait |
| can:Xanax | 139/160 (86.9%) | 152/165 (92.1%); 99.4% coverage; 59min wait | 152/165 (92.1%); 99.4% coverage; 64min wait |
| cay:Banana Orchid | 151/158 (95.6%) | 157/158 (99.4%); 96.4% coverage; 51min wait | 158/158 (100.0%); 96.4% coverage; 57min wait |
| cay:Stingray Plushie | 143/160 (89.4%) | 151/157 (96.2%); 100.0% coverage; 10min wait | 156/160 (97.5%); 100.0% coverage; 13min wait |
| chi:Panda Plushie | 102/155 (65.8%) | 98/154 (63.6%); 100.0% coverage; 21min wait | 98/138 (71.0%); 84.5% coverage; 131min wait |
| chi:Peony | 145/160 (90.6%) | 139/149 (93.3%); 93.5% coverage; 51min wait | 145/152 (95.4%); 92.9% coverage; 65min wait |
| haw:Orchid | 140/160 (87.5%) | 156/158 (98.7%); 98.8% coverage; 59min wait | 158/158 (100.0%); 98.8% coverage; 65min wait |
| jap:Cherry Blossom | 134/162 (82.7%) | 144/159 (90.6%); 100.0% coverage; 42min wait | 148/153 (96.7%); 100.0% coverage; 60min wait |
| jap:Xanax | 52/152 (34.2%) | no resolved arrivals; 0.0% coverage; — | no resolved arrivals; 0.0% coverage; — |
| mex:Dahlia | 144/151 (95.4%) | 151/151 (100.0%); 95.2% coverage; 58min wait | 151/151 (100.0%); 95.2% coverage; 58min wait |
| mex:Jaguar Plushie | 150/155 (96.8%) | 158/159 (99.4%); 100.0% coverage; 7min wait | 158/159 (99.4%); 100.0% coverage; 10min wait |
| sou:African Violet | 139/151 (92.0%) | 150/155 (96.8%); 96.4% coverage; 61min wait | 151/153 (98.7%); 96.4% coverage; 80min wait |
| sou:Lion Plushie | 102/152 (67.1%) | 103/155 (66.5%); 100.0% coverage; 22min wait | 97/149 (65.1%); 92.9% coverage; 104min wait |
| swi:Chamois Plushie | 89/152 (58.6%) | 93/137 (67.9%); 91.1% coverage; 100min wait | 62/99 (62.6%); 61.9% coverage; 144min wait |
| swi:Edelweiss | 145/164 (88.4%) | 156/164 (95.1%); 100.0% coverage; 28min wait | 158/162 (97.5%); 100.0% coverage; 36min wait |
| uae:Camel Plushie | 97/159 (61.0%) | 102/159 (64.1%); 100.0% coverage; 24min wait | 52/98 (53.1%); 60.7% coverage; 163min wait |
| uae:Tribulus Omanense | 146/158 (92.4%) | 147/157 (93.6%); 100.0% coverage; 35min wait | 157/157 (100.0%); 100.0% coverage; 50min wait |
| uni:Heather | 137/156 (87.8%) | 153/157 (97.5%); 97.6% coverage; 52min wait | 149/150 (99.3%); 97.6% coverage; 61min wait |
| uni:Nessie Plushie | 110/150 (73.3%) | 104/146 (71.2%); 96.4% coverage; 57min wait | 83/118 (70.3%); 76.8% coverage; 119min wait |
| uni:Red Fox Plushie | 108/155 (69.7%) | 110/153 (71.9%); 100.0% coverage; 38min wait | 68/107 (63.5%); 73.2% coverage; 124min wait |
| uni:Xanax | 114/149 (76.5%) | 103/150 (68.7%); 94.6% coverage; 43min wait | 111/148 (75.0%); 92.9% coverage; 55min wait |

## Matched validation leads and weak-item caution

Gains/losses mean challenger-only successes / reference-only successes on the SAME clock-selected, mutually resolved starts. Full pair matrices include unknown/pending/abstention combinations in private report. Worst-day percentages have typically~20 resolved samples, sometimes fewer; they are noisy diagnostics.

| Item · fixed candidate | Worst sampled day | vs zero baseline | vs current-rate hybrid | vs full rate |
|---|---:|---:|---:|---:|
| arg:Monkey Plushie · zero_path_analog70 | 66.67% | 31/13 | 43/16 | 42/14 |
| swi:Chamois Plushie · zero_path_analog70 | 26.090000000000003% | 33/20 | 33/19 | 32/20 |
| arg:Ceibo Flower · zero_path_analog80 | 95.24000000000001% | 9/0 | 23/0 | 23/0 |
| cay:Stingray Plushie · zero_path_analog80 | 91.67% | 13/0 | 6/0 | 9/0 |
| can:Wolverine Plushie · zero_path_analog80 | 82.61% | 10/4 | 11/4 | 12/4 |
| sou:African Violet · zero_path_analog80 | 90.48% | 11/2 | 6/2 | 15/1 |
| swi:Edelweiss · zero_path_analog80 | 90.91% | 16/1 | 16/1 | 28/1 |
| uae:Tribulus Omanense · zero_path_analog80 | 100% | 11/0 | 22/0 | 6/0 |

## Timing-audit correction after this run

Focused mode originally omitted legacy daily-template departure fitting, which also left its optional event-audit reference empty. This does NOT affect ANY reported zero/path policy or its outcomes. Follow-up source restores that fit on the four-hour event cohorts only, skips unused legacy analog forecasts outside those cohorts, and adds full/focused equality checks for ALL event-audit sections as well as retained policy outcomes. First-run accuracy above remains pinned to the original SHA; do not relabel it as a fresh numerical result at a later source.

## Decision

Keep fixed per-item research leads for fresh validation; no automatic selector or blanket model replacement. Stronger-item gains exist, while Monkey's gain carries substantial waiting cost and remaining weak items are unresolved. No production model assignment or publisher whitelist change.

Next modeling target is demand/regime context, including causal activity across items, and persistent regime changes rather than chasing a retrospective winner. Source-country update timestamps also need verification/retention before exact-time live claims; inspected stock-history insertion uses collection time while the provider exposes a separate country update field. No collector deployment was performed.
