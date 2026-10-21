# Cycle-conditioned departure replay — 15 October 2026

Exploratory historical reconstruction, not actual flights or a blind holdout. Primary result pools all five-minute starts. The 12 offsets are highly correlated. Success means sampled stock ≥30 at simulated arrival; physical depletion remains exactly zero.

Source `01a4c9001a6e8505912163bfafaa74a70c95ab1d`; cutoff 1792103062. Four policies fixed before replay; no retrospective item-level model selection. Each historical stock trajectory is completely mature before issue; cycle-fit errors are from predictions made at each cycle’s birth.

Each row shows success among resolved departures / departure coverage / mean wait in minutes. References are the previously selected weak-item references; controls show labeled fixed comparators. Full daily and offset sensitivities, raw counts and paired outcomes are in the accompanying JSON.

| Item | Reference | Ridge70 | Ridge peak | Median70 | Median peak |
|---|---|---|---|---|---|
| arg:Monkey Plushie | 72.98% / 96.58% / 61.1 | 65.58% / 99.95% / 22.0 | 77.61% / 81.00% / 115.3 | 63.02% / 99.90% / 25.2 | 67.38% / 68.80% / 112.3 |
| chi:Panda Plushie | 86.96% / 96.28% / 134.9 | 60.78% / 100.00% / 21.8 | 56.63% / 43.85% / 146.9 | 60.64% / 100.00% / 22.0 | 60.82% / 54.41% / 173.9 |
| chi:Peony | 85.95% / 96.03% / 57.3 | 87.73% / 91.27% / 66.8 | 86.64% / 41.22% / 213.9 | 83.57% / 94.69% / 80.1 | 84.09% / 32.54% / 178.4 |
| jap:Xanax | 43.07% / 99.40% / 69.5 | unscored / 0.00% / 0.0 | 19.02% / 83.28% / 134.9 | unscored / 0.00% / 0.0 | 25.26% / 97.92% / 81.1 |
| mex:Jaguar Plushie | 98.19% / 100.00% / 13.5 | 96.09% / 99.80% / 19.1 | 97.74% / 99.70% / 23.7 | 95.05% / 100.00% / 15.5 | 96.09% / 100.00% / 17.6 |
| sou:Lion Plushie | 69.55% / 99.65% / 10.5 | 68.87% / 99.65% / 16.5 | 62.52% / 71.18% / 135.9 | 67.99% / 99.65% / 15.3 | 60.96% / 93.11% / 108.5 |
| swi:Chamois Plushie | 69.57% / 100.00% / 35.9 | 66.06% / 96.97% / 30.8 | 52.25% / 73.12% / 112.6 | 71.97% / 100.00% / 18.0 | 54.43% / 75.10% / 105.4 |
| uae:Camel Plushie | 66.28% / 100.00% / 4.1 | 60.14% / 98.26% / 29.6 | 59.67% / 64.68% / 127.1 | 56.68% / 98.56% / 33.0 | 59.73% / 52.93% / 128.5 |
| uni:Nessie Plushie | 73.68% / 100.00% / 28.4 | 71.44% / 99.90% / 22.0 | 78.73% / 78.08% / 131.7 | 70.29% / 99.90% / 31.3 | 62.98% / 78.47% / 94.5 |
| uni:Red Fox Plushie | 74.15% / 99.95% / 10.5 | 70.81% / 99.95% / 28.3 | 68.23% / 96.53% / 124.8 | 73.10% / 100.00% / 33.2 | 86.66% / 49.36% / 130.1 |

Run `38820127841` completed successfully using private controls commit `3e183304bfda721b11aea2e5fcc7433211b94607`. Artifact `12012677605` (395611-byte ZIP) SHA256 `cc8768405df5264ad2b8df42f411c8a6dcf13fa4c0cacd6302929b33b6984c3b` verified before analysis. Source CI passed 124 tests, Chromium UI and all three compatibility workflows.

**Decision:** retain existing references. Chamois median70 is the one useful next-validation lead: +2.40 percentage points, 100% coverage for both, mean wait 35.86→18.02 minutes. On matched resolved starts it wins 316 and loses 284 (1772 pairs); all 12 UTC-minute offsets improve. Day-floor success rises 53.15→63.97%, but the last day falls 85.10→72.62%. Known outcomes fall from 1883 to 1859; UNKNOWN rises 105→129, with 28 PENDING for both. This is a modest exploratory gain with incomplete consistency, not promotion evidence.

Monkey ridge peak rises 72.98→77.61%, but coverage falls 96.58→81.00% and wait grows 61.14→115.26 minutes; its day floor falls 58.67→45.49%. Nessie ridge peak rises 73.68→78.73%, but coverage falls 100→78.08%, wait grows 28.38→131.72 minutes, and day 0 has no departures. Red Fox median peak rises 74.15→86.66%, but coverage falls 99.95→49.36%, wait grows 10.46→130.07 minutes, and two entire days have no departures. These are unsuitable replacements.

Panda, Lion, Camel, Jaguar control and the ridge version of Chamois do not improve the existing balance. Peony ridge70 gains only 1.78 points (85.95→87.73%) while losing 4.76 coverage points and adding 9.5 minutes; its cycle-timing sample also failed the minimum-size screen. Japan strict policies abstain on every start; ridge peak achieves 19.02% at 83.28% coverage and median peak 25.26% at 97.92% coverage, versus reference 43.07% at 99.40% coverage and a shorter wait. Reject this family for Japan.

The cycle MAE improvement therefore does not generally translate into useful flight decisions. Keep the timing signal as a diagnostic, reject the universal ridge/path replacement, and test any Chamois candidate on a separately fixed future window before considering a change. The original forward window does not validate this new family.

All four policies remain research challengers. A better conditional success percentage is insufficient if coverage collapses or waits increase. Daily floors and matched outcomes must support any next-step decision. No production deployment or model promotion occurred. Original frozen forward protocol remains source `87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04`, truth-ready no earlier than 16 October 2026 09:55:10 EDT plus snapshot and scheduling lag.
