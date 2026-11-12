# Physical-cycle predictability results — 15 October 2026

Exploratory seven-day rolling replay. Each full physical cycle starts at observed zero→positive and ends at the next observed zero→positive, with a positive→exactly zero transition in between. Predictions use only already completed cycles at issue. These are cycle timing errors, not flight success rates. Unknown and pending cycles remain visible.

Source `e9401a759c6d61b546f199474c33f84c54186ed4`; isolated run `38818855993`; cutoff 1792103062. Artifact `12011373032`, ZIP SHA256 `4036e931ba2b9aad89785229ec3b908edc10b1745bced0cb080de0d13f9a031c` verified.

| Item | Closed / unknown / pending | Median MAE (min) | Ridge MAE (min) | MAE reduction | Timing screen |
|---|---:|---:|---:|---:|---|
| arg:Monkey Plushie | 169 / 27 / 1 | 8.69 | 5.95 | 31.5% | Pass |
| chi:Panda Plushie | 171 / 33 / 1 | 10.11 | 8.61 | 14.8% | Pass |
| chi:Peony | 26 / 4 / 1 | 138.51 | 103.17 | 25.5% | Fail |
| jap:Xanax | 62 / 11 / 1 | 8.81 | 15.81 | -79.5% | Fail |
| mex:Jaguar Plushie | 159 / 27 / 1 | 10.05 | 6.97 | 30.7% | Pass |
| sou:Lion Plushie | 181 / 27 / 1 | 11.23 | 7.97 | 29.0% | Pass |
| swi:Chamois Plushie | 179 / 31 / 1 | 9.83 | 7.58 | 22.8% | Pass |
| uae:Camel Plushie | 176 / 27 / 1 | 7.10 | 5.84 | 17.7% | Pass |
| uni:Nessie Plushie | 167 / 29 / 1 | 13.53 | 10.56 | 22.0% | Pass |
| uni:Red Fox Plushie | 158 / 25 / 1 | 14.41 | 9.24 | 35.9% | Pass |

Seven weak plushies improved mean timing error by 14.8–35.9%, with no worse 90th-percentile error under the predeclared screen. Jaguar, a control, also passed. Peony has only 26 closed comparisons, below the minimum of 30. Japan ridge timing was 79.5% worse; this rejects it as a universal clock model.

Clock-phase screening found no useful stable schedule: all 600–7200 second gates rejected; rare 300-second admissions did not beat poll-phase controls. No clock-lattice policy is promoted.

The next experiment tests four fixed cycle-conditioned stock-path departure policies (ridge and median, each strict 70% support and peak support). Both families are tested for every item; timing-screen outcomes do not select item policies. Same inspected history remains exploratory. The original frozen forward test and production models remain unchanged.
