# V28 all-item tournament — fixed-cutoff research checkpoint (2026-10-08)

**Status: research evidence assembled; NO new live champion has been certified. DO NOT MERGE TO MAIN OR ACTIVATE LIVE.**

## Inputs and method
- Frozen DB SHA256: `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`.
- Cutoff: `1791241486` (2026-10-05 23:04:46 UTC). All 54,007 stored V19/V20/V21 holdout recommendations predate this cutoff.
- Exactly **236 catalog items** tracked; **162** had complete V19/V20/V21 candidate configurations for local post-cutoff compatibility replay, **74** did not (including separately reserved Japan Xanax).
- First broad five-start sweep: **363 configurations, 1,815 model-level outcomes**; no item outcomes were substituted from archived holdouts.
- All 21 standard museum flowers/plushies: separate normalized eight-hour, five-minute replanning, quantity >=30 +10s, 12-start generic model comparison.
- All seven newly uploaded specialist plushie policies ran on the frozen newer snapshot using local transcriptions of committed source, on 5–12 fixed-cutoff starts. Direct matched comparisons use **identical session starts** within each item.

## Seven matched specialist comparisons

| Item | Specialist | Frozen generic V19 | V20 | V21 | Depart now | Hindsight 8h |
|---|---:|---:|---:|---:|---:|---:|
| Camel Plushie (UAE) | **8/8** | 3/8 | 4/8 | 4/8 | 3/8 | 8/8 |
| Chamois Plushie (Switzerland) | 4/5 | 3/5 | 4/5 | 4/5 | 1/5 | 5/5 |
| Lion Plushie (South Africa) | **9/12** | 10/12 | 11/12 | 11/12 | 5/12 | 12/12 |
| Monkey Plushie (Argentina) | 3/5 | 4/5 | 4/5 | 4/5 | 5/5 | 5/5 |
| Nessie Plushie (UK) | 9/12 | 10/12 | **11/12** | 7/12 | 6/12 | 12/12 |
| Panda Plushie (China) | 6/12 | 8/12 | **9/12** | 6/12 | 6/12 | 12/12 |
| Red Fox Plushie (UK) | 7/12 | 9/12 | 9/12 | 9/12 | 8/12 | 12/12 |

**These are compatibility-port research results, not native-certified predictions or statistically independent trip samples.** Overlapping session starts represent correlated stock cycles.

## Native parity + interpretation
- Diagnostic on five older-model item keys: exact departure reproduction **33/42** (V19 10/15; V20 8/12; V21 15/15). This is not sufficient parity to authorize a winner switch.
- The strongest emerging specialist is Camel, but 8/8 has a wide confidence interval and is insufficient proof of a >90% long-run success rate.
- On the newer cohort Nessie, Red Fox and Panda specialists underperformed a generic comparator, despite historical >90% development figures; investigate regime drift and code parity before replacing handoff incumbents.
- Lion/Panda selectors were rerun using the GitHub locked runner’s causally mature **320-start** pre-cutoff cap. Smaller 140-start refits initially scored Lion 11/12 and Panda 8/12; after correcting the cap those scores fell to 9/12 and 6/12. This training sensitivity reinforces the no-promotion decision.
- Historical success metrics were used extensively for model development; Oct 5–8 postcutoff snapshot is now also studied. A truly untouched future lockbox requires data collected later.

## Code status and release blockers
- Imported exact original six scripts and helper to `research/plushie_champions/`, fixed template tie-breaker crash, read-only SQLite access, and added `locked_replay.py` with a fixed cutoff and explicit all-start scoring. Native specialist code has not been run on the 134MB user-uploaded snapshot by GitHub Actions (CI uses synthetic fixtures only).
- Integrated GitHub CI passed **30** unit/synthetic tests (5 specialist/import, 3 fixed cutoff, 10 manifest, 12 release gates).
- All **236 incumbent selections** stay research-frozen, not deployed. The seven have diagnostic contender rankings only.
- Separate Japan Xanax specialist requires its own frozen-replay validation and tested live adapter. V2 remains fallback.
- Before any main merge or public guidance: run original native runner against stable new data; achieve full engine parity; independently validate across distinct resolved stock windows; verify prediction freshness, gap suppression, quantity and grace; build and test feature-flagged private shadow + rollback; avoid uncalibrated numeric chance claims.

**No database, API keys, live website changes or bot commands committed.** The full machine-readable 236-item audit and seven-comparison CSV were exported as user-facing files in the research chat; this markdown preserves the evidence summary without committing the large database.
