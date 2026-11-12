# Japan Xanax full-coverage research checkpoint — 2026-10-07

Clean benchmark:
- 154 strict clean P2 samples
- first 60 used as history
- 94 chronological evaluation opportunities
- 100% of valid opportunities must receive a recommendation
- Japan travel time = 149 minutes

Results from the latest causal model round:
- best stable exact-focused component model: 45.74% exact, 46.81% +10s, 48.94% +1m, 51.06% +3m
- earlier preserved static family remains slightly better overall at about 46.8% exact / 53.2% +3m
- new best full-coverage +3m model: 40.43% exact, 42.55% +10s, 44.68% +1m, 55.32% +3m, 56.38% +5m, 62.77% +10m

Additional rejected families:
- rolling direct estimators (~35% exact)
- Ridge regression (~37%)
- kNN interval optimizer (~35%)
- mechanistic empirical convolution (~35%)
- candidate boosted classifiers (~33-35%)
- autoregressive cooldown models (~39%)
- contextual expert routing
- time-of-day timer centers
- fixed-decision live censoring (best ~44.7% exact)
- conservative P1/P2 routing
- cross-item Japan timing proxies

Timer findings:
- clean cooldown mean is about 121 minutes, SD about 7.1 minutes
- G1/G2 correlation is about 0.05
- previous usable width vs future G2 is about 0.01
- current peak vs future G2 is about -0.02
- no tested causal feature reliably predicts the future cooldown draw

Structural timing issue:
- reachable P2 target is roughly 255 minutes after the current depletion
- departure is roughly 106 minutes after depletion because Japan flight time is 149 minutes
- the intervening P1 restock is usually around 121 minutes after depletion
- so the player normally leaves before P1 even appears
- the final G2 timer begins only after that future P1 batch later depletes

Using the actual later stock-window widths, an intentionally generous one-unresolved-timer idealization gives approximate maxima:
- exact 45.28%
- +10 seconds 45.93%
- +1 minute 49.18%
- +3 minutes 56.89%

The new 55.32% +3m model is therefore close to that idealized +3m information ceiling.

Interpretation:
>50% exact at 100% valid-opportunity coverage is no longer supported as a routine model-tuning target with current information. Continue looking for a genuine pre-departure signal for the future timer draw, preserve 100% valid coverage, calibrate per-cycle probabilities, and validate frozen candidates on new future data.
