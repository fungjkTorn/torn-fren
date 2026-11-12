# Inventory feature ablation results — 15 October 2026

Exploratory seven-day historical reconstruction, not actual flights or a blind holdout. All 2016 five-minute starts per item are pooled and highly correlated. Success means sampled stock ≥30 on simulated arrival; physical depletion remains exactly zero.

Source `235bb289e800d825ebeb7c013655b12ca4dee1a5`; cutoff 1792106705. All six policies were fixed before replay. Groups share candidate origins, past-only scaling, neighbor count, label maturity and support rules. Existing references remain visible; Jaguar and Peony are controls with fixed comparators.

Cells show success among resolved outcomes / departure coverage / mean wait in minutes. Full raw counts, UTC hourly and twelve offsets, chronological slices and matched outcomes are retained in JSON.

| Item | Existing reference | Phase70 | Quantity70 | Flow70 |
|---|---|---|---|---|
| arg:Monkey Plushie | 72.98% / 96.58% / 61.1 | 70.42% / 96.78% / 69.6 | 60.52% / 99.16% / 46.0 | 69.38% / 99.95% / 26.8 |
| chi:Panda Plushie | 87.11% / 95.63% / 135.4 | 70.52% / 99.85% / 50.3 | 68.63% / 100.00% / 28.2 | 65.74% / 100.00% / 16.9 |
| chi:Peony | 85.95% / 96.03% / 57.3 | 87.45% / 100.00% / 43.8 | 92.80% / 100.00% / 51.0 | 89.88% / 100.00% / 43.3 |
| jap:Xanax | 43.37% / 98.76% / 69.2 | unscored / 0.00% / 0.0 | unscored / 0.00% / 0.0 | unscored / 0.00% / 0.0 |
| mex:Jaguar Plushie | 98.19% / 99.95% / 13.5 | 98.09% / 99.95% / 10.1 | 97.87% / 100.00% / 8.2 | 98.04% / 99.95% / 8.0 |
| sou:Lion Plushie | 69.71% / 99.75% / 10.6 | 60.89% / 99.85% / 19.0 | 65.52% / 99.85% / 13.0 | 64.61% / 99.85% / 9.7 |
| swi:Chamois Plushie | 69.57% / 100.00% / 35.8 | 60.31% / 97.12% / 74.2 | 62.08% / 96.68% / 73.7 | 52.58% / 95.29% / 84.8 |
| uae:Camel Plushie | 66.21% / 100.00% / 4.1 | 65.94% / 99.80% / 23.6 | 62.64% / 99.85% / 20.9 | 63.78% / 99.95% / 16.7 |
| uni:Nessie Plushie | 73.46% / 100.00% / 28.3 | 76.89% / 100.00% / 30.8 | 70.01% / 100.00% / 25.3 | 69.94% / 100.00% / 18.0 |
| uni:Red Fox Plushie | 74.16% / 99.90% / 10.5 | 70.49% / 99.80% / 52.1 | 69.10% / 99.90% / 27.2 | 69.30% / 99.95% / 23.4 |

Diagnostic near-peak policies (same cell format):

| Item | Phase peak | Quantity peak | Flow peak |
|---|---|---|---|
| arg:Monkey Plushie | 80.08% / 74.95% / 108.0 | 75.66% / 81.99% / 115.3 | 69.15% / 91.57% / 129.0 |
| chi:Panda Plushie | 62.39% / 60.66% / 153.1 | 61.66% / 71.83% / 168.3 | 18.66% / 35.12% / 200.4 |
| chi:Peony | 99.34% / 98.16% / 126.7 | 100.00% / 98.51% / 104.0 | 100.00% / 94.94% / 99.6 |
| jap:Xanax | 43.87% / 50.69% / 178.1 | 52.84% / 42.71% / 197.3 | 22.80% / 38.14% / 176.4 |
| mex:Jaguar Plushie | 97.88% / 99.85% / 13.1 | 98.45% / 99.90% / 12.3 | 98.35% / 99.90% / 11.9 |
| sou:Lion Plushie | 85.71% / 66.07% / 151.9 | 87.54% / 72.87% / 134.5 | 81.34% / 71.43% / 120.2 |
| swi:Chamois Plushie | 60.42% / 73.21% / 147.7 | 76.75% / 75.10% / 145.2 | 92.18% / 56.60% / 153.7 |
| uae:Camel Plushie | 60.69% / 87.40% / 117.4 | 68.05% / 89.04% / 120.5 | 77.39% / 82.84% / 102.6 |
| uni:Nessie Plushie | 76.62% / 76.39% / 130.5 | 75.42% / 82.84% / 128.7 | 81.33% / 74.70% / 132.3 |
| uni:Red Fox Plushie | 94.63% / 62.50% / 163.1 | 87.04% / 84.38% / 159.9 | 82.93% / 59.72% / 137.2 |

Run `38826561576` succeeded; source CI passed133 tests plus Chromium and all three compatibility workflows. Artifact `12015970397`, ZIP478138bytes, SHA256 `1046fc84c6817662732b0ef3d40a722d1b85fdf33ea5a33e3b8cd9190dd2fec9` verified before analysis.

**Decision: no default model replacements.** The six fixed variants did not demonstrate a broadly useful improvement for the eight weak items. Added quantity and observed-flow features sometimes help their ablation control, but generally fail to beat the established references at useful coverage/waits. This tests these feature encodings and neighbor distances; it does not establish that inventory information is intrinsically useless.

Nessie phase70 is a follow-up lead: 73.46→76.89% resolved success, both100% departure coverage, mean wait28.34→30.78min. All12 UTC-minute offsets improve. On1713 matched resolved starts it wins198 and loses155 (matched success73.03→75.54%). Scored outcomes increase1786→1865 and UNKNOWN decreases208→129; PENDING22 both. Mean matched wait increases9.89min, versus2.44min across each policy's complete departed population. Daily consistency fails: worst day57.85→49.30%; it improves3 of7 days and regresses4. Latest day improves57.85→74.22%. Keep the incumbent and do not confuse average improvement with reliability.

The quantity70→flow70 primary comparison is mixed: Monkey wins289/loses145, Panda201/240, Lion152/152, Chamois126/265, Camel189/168, Nessie158/155, RedFox197/176; all strict Japan variants abstain. Quantity70 versus phase70 worsens Monkey, Panda, Camel, Nessie and RedFox; it helps Lion/Chamois but both remain below their established references. No universal “compound more inputs” gain appeared.

Japan: existing rate43.37% /98.76%coverage /69.2minwait. Best new conditional success is quantity_peak52.84% /42.71% /197.3min, with1058ABSTAIN and97PENDING starts and a0% daily floor. Phase_peak43.87% /50.69% /178.1min, flow_peak22.80% /38.14% /176.4min. All strict70 policies have zero departures. Reject these as default replacements.

High weak-item peak headlines are selective and slow: Lion quantity_peak87.54% /72.87%coverage /134.5minwait (worst day20.66%); Chamois flow_peak92.18% /56.60% /153.7min; Camel flow_peak77.39% /82.84% /102.6min; RedFox phase_peak94.63% /62.50% /163.1min. RedFox quantity_peak87.04% /84.38% /159.9min is another patient-policy diagnostic, not an improvement to the default10.5min reference wait. These may inform a separately validated patient preference later; they are not accurate leave-now recommendations.

Controls must also retain strong comparators: Peony quantity70 is92.80% /100% /51.0min versus phase70 87.45%, but existing regime80 is already93.81% /99.75% /65.2min. Quantity_peak reaches100% among1911 known arrivals, with70UNKNOWN,34PENDING,1ABSTAIN and104minmeanwait; not1911 independent trials or a calibrated100% guarantee. Jaguar reference98.19% remains strong; new quantity_peak98.45% is only a tiny exploratory difference. No control promotion.

Next research should test learned nonlinear interactions or learned feature weights against this fixed ablation, rather than assuming every extra feature or higher peak score improves the travel policy. Keep the original forward test and the separate Chamois median-cycle forward source/window unchanged.

 Higher conditional success must be assessed with departure coverage, waiting time, unknowns, daily consistency and paired outcomes. This inspected period cannot validate a future deployment. Existing original and Chamois frozen validation sources remain unchanged.
