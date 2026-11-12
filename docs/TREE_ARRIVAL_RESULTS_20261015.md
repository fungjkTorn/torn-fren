# Fixed nonlinear arrival-model results — 15 October 2026

Exploratory historical reconstruction on seven days; not actual flights or a blind holdout. All2016 five-minute starts/item are pooled and highly correlated. Success means sampled stock≥30 at simulated arrival; true physical depletion remains exactly zero.

Source `9525422fff28521536d8a5bc6ceab9b7fe510269`; cutoff 1792106705. Both schedules, capacity and departure rules were fixed before replay. Models use only individually mature labels before canonical12-hour refits, including retained pre-window history.

Cells: success among resolved outcomes / departure coverage / mean wait in minutes. Full raw counts, twelve UTC-minute offsets, UTC hourly, chronological slices, training maturity and paired outcomes are in JSON. Peony and Jaguar are controls with strong fixed regime80 comparators.

| Item | Existing reference | Stable70 | Stable peak | Recent70 | Recent peak |
|---|---|---|---|---|---|
| arg:Monkey Plushie | 72.98% / 96.58% / 61.1 | 56.30% / 58.73% / 141.0 | 60.70% / 85.71% / 96.4 | 78.77% / 72.37% / 118.6 | 67.27% / 83.73% / 89.6 |
| chi:Panda Plushie | 87.11% / 95.63% / 135.4 | 67.71% / 74.85% / 111.5 | 65.15% / 84.38% / 100.4 | 62.24% / 79.76% / 109.8 | 77.81% / 86.06% / 108.8 |
| chi:Peony | 93.81% / 99.75% / 65.2 | 86.73% / 95.83% / 35.0 | 91.74% / 85.17% / 122.4 | 85.88% / 100.00% / 32.6 | 85.98% / 88.10% / 135.8 |
| jap:Xanax | 43.37% / 98.76% / 69.2 | unscored / 0.00% / 0.0 | 21.93% / 69.59% / 124.0 | unscored / 0.00% / 0.0 | 17.72% / 87.10% / 149.9 |
| mex:Jaguar Plushie | 98.19% / 99.95% / 13.5 | 72.32% / 75.79% / 108.6 | 76.44% / 80.80% / 89.0 | 83.17% / 83.43% / 100.9 | 77.43% / 81.99% / 94.1 |
| sou:Lion Plushie | 69.71% / 99.75% / 10.6 | 76.32% / 65.53% / 134.1 | 67.38% / 90.38% / 101.0 | 66.36% / 96.58% / 59.6 | 58.43% / 91.96% / 102.4 |
| swi:Chamois Plushie | 69.57% / 100.00% / 35.8 | 75.67% / 41.82% / 141.1 | 57.79% / 87.30% / 99.7 | 77.20% / 68.65% / 129.3 | 65.16% / 85.32% / 116.1 |
| uae:Camel Plushie | 66.21% / 100.00% / 4.1 | 83.35% / 51.88% / 136.0 | 82.61% / 85.17% / 100.5 | 67.07% / 64.73% / 129.9 | 73.78% / 84.42% / 103.5 |
| uni:Nessie Plushie | 73.46% / 100.00% / 28.3 | 74.98% / 70.39% / 116.1 | 69.61% / 77.93% / 106.0 | 73.61% / 76.93% / 113.9 | 73.24% / 88.05% / 106.9 |
| uni:Red Fox Plushie | 74.16% / 99.90% / 10.5 | 81.36% / 67.56% / 121.5 | 57.42% / 79.41% / 104.0 | 66.16% / 87.85% / 98.9 | 58.02% / 82.69% / 104.9 |

Run `38829022013` succeeded. Artifact `12017050676`, ZIP557460bytes, SHA256 `b5195a4341a64e384c89e67f07eb8b29991b3e26eba264fcf0c436a7972d69fc` verified. Numerical source CI passed136 tests plus Chromium and all three compatibility workflows.

**Decision:** no default replacements. A stable-tree Camel patient policy is the useful follow-up lead. Other apparent weak-item gains generally lose substantial coverage or add long waits. The tree family also degrades strong controls, so it must not be promoted universally.

**Camel, comparable patient strategies:** stable tree peak82.61% versus earlier inventory-flow peak77.39%; coverage85.17% versus82.84%; meanwait100.5 versus102.6min. Worst-day success79.47% versus55.05%. All seven new daily success fractions are79.47–88.56%, although daily coverage ranges74.65–96.18%. Raw new counts1354SUCCESS/285FAILURE/36UNKNOWN/42PENDING/299ABSTAIN; earlier patient counts1215/355/1/103/342. Extra UNKNOWN mass is1.74 percentage points across2016 starts. These aggregate results are promising, but the first numerical source did not emit matched tree-versus-flow-peak pairs; a reporting-only follow-up adds that pair to the separate future protocol.

Against Camel's FAST aligned50 default, the new patient result is66.21→82.61% conditional success, but coverage100→85.17% and meanwait4.1→100.5min. On1569 matched resolved starts versus the fast reference it wins289/loses55; this does not remove the waiting tradeoff. The patient policy is not a faster recommendation or a calibrated82.61% guarantee. Keep the fast default and validate the patient alternative separately.

**Japan failed:** existing rate43.37%/98.76%coverage/69.2minwait. Tree stable peak21.93%/69.59%/124.0min; recent peak17.72%/87.10%/149.9min. Both strict70 variants have zero departures. Reject this family for Japan.

Monkey recent70 reaches78.77% versus72.98%, but coverage falls96.58→72.37% and wait61.1→118.6min. Lion stable70 reaches76.32% versus69.71%, but coverage99.75→65.53% and wait10.6→134.1min. Chamois recent70 reaches77.20% versus69.57%, but coverage100→68.65% and wait35.8→129.3min. RedFox stable70 reaches81.36% versus74.16%, but coverage99.90→67.56%, wait10.5→121.5min and its worst day is29.78%. These do not replace default references.

Panda and Nessie do not show a useful balanced gain. Strong controls also reject generalization: Jaguar regime80 reference98.19%/99.95%/13.5min versus best tree recent70 83.17%/83.43%/100.9min. Peony reference93.81%/99.75%/65.2min versus stable peak91.74%/85.17%/122.4min. Preserve their incumbents.

A separate Camel patient forward window is configured with primary tree_stable_peak versus inventory_flow_peak and secondary aligned50 for cost disclosure. It uses the same numerical models, fixed capacity and recency rules; helper/reporting changes do not retune the candidate. One24-hour future-period reconstruction will not establish long-term consistency or actual-flight accuracy. Original full-roster and Chamois protocol pins remain unchanged.

 Four fixed variants and all reference results are retained, including abstentions. A higher conditional success percentage is insufficient without coverage, wait and chronological consistency. Model scores are uncalibrated. Both existing frozen validation protocols remain unchanged.

Operational validation details: [CAMEL_PATIENT_FORWARD_STATUS_20261015.md](CAMEL_PATIENT_FORWARD_STATUS_20261015.md).
