# Actual VM V139 prediction evidence — 12 October 2026

**Source:** User-run completed V139 pinned read-only audit; final marker AUDIT DONE, SSH exit code 0. No production, DB, collector, website, or timer mutations. **These are poll-state >=30-stock-at-arrival proxies, NOT player arrivals/purchases.** Per-country provider freshness is not proven. First item UTC hour reduces repeated five-minute issues, but does not create independent restock cycles. The three systems are on DIFFERENT issue cohorts, so direct accuracy ranking would be invalid.

## Matched comparisons, each against leave-now from SAME issue

| Model | Hourly starts | Valid proposals | Matched model and leave-now | Model proxy >=30 | Leave-now proxy >=30 | Model-only minus now-only | Mean wait |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original V2 graph earliest UI departure | 2,803 | 2,797 valid under 8h | 2,013 | 65.57% | 61.50% | +82 (423 vs 341) | 79.3 min |
| Existing V75 incumbents | 1,044 | 1,028 (98.5%) | 814 | 86.73% (706/814) | 76.29% (621/814) | +85 (152 vs 67) | not in excerpt |
| V128 generic 24-item challenger | 504 | 198 (39.3%) | 160 | 72.50% (116/160) | 71.25% (114/160) | +2 (14 vs 12) | 6.62 min |

Additional denominators:
- V75's 1,028 proposed flights: **761 stock>=30 proxy successes**, 111 misses, 156 unknown/pending; 16 absent/invalid departures; all-start conservative proxy hit lower bound 761/1044 = 72.89%.
- V128's 198 proposed flights: **122 proxy successes**, 47 misses, 29 unknown/pending; **306 abstentions**; all-start conservative proxy hit lower bound 122/504 = 24.21%. Conditional on its 169 known outcomes, 122/169 = 72.19%, DISTINCT from the matched 116/160 = 72.50%.
- V2 UI had 1,558 successful and 808 failed proxy arrivals among 2,366 scorable UI proposals; only 2,013 paired cases had both leave-now and model known.
- Both V75 and V128 matched vs-now differences are *within* each cohort; do not generalize V75 superiority to an unrun same-issue head-to-head.

## V2 restock forecast is a critical bottleneck

- Original V2 mean absolute next-restock timing error = **130.05 minutes**.
- True restock inside V2 predicted restock window = **778/2,159 = 36.04%**.
- Recommended arrival inside actual restock-to-depletion interval = **661/2,159 = 30.62%**; not a >=30-stock guarantee.
- The historical V137 audit could not perfectly reconstruct old browser latest-safe departure; avoid claiming a complete new-browser evaluation from these past scores.
- The new V2-to-P2 departure bridge already solves selecting a subsequent reachable cycle, but is not a fix for predicting the next restock two hours off.

## V128 coverage, instability and watch reconfirmations

- 5,736 five-minute issued records: 3,386 abstentions/unsupported; only 2,350 proposals (~40.97%).
- 504 hourly starts: **306 abstentions (60.7%)**, 198 proposals (39.3%). Live logs also showed 17–20 ABSTAIN_CURRENT_PHASE_ONSET_UNKNOWN in several complete 24-row batches.
- Among 835 adjacent unchanged-collector-state pairs with *two departure recommendations*, **277 changed by >5 minutes (~33.2%)**, **70 by >15 minutes (~8.4%)**. These are conditional adjacent-issue statistics, not independent cycles.
- Future WATCH first-hour rechecks: 31 near-departure reconfirmations, 12 later abstentions, 8 still WATCH, one with no reconfirmation. Never present far-future WATCH as a certified instruction to fly.
- Recorder was successfully producing 24-row batches but once failed with sqlite3.OperationalError: unable to open database file, then recovered. Monitor without touching the collector prematurely.

## Highest-priority item problems

| Item | V128 >=30 / known proxy | Additional concern |
| --- | ---: | --- |
| Camel Plushie | 5/12 = 41.7% | Original V2 restock window hit only 18.56% on 97 valid cycles |
| Stingray Plushie | 6/14 = 42.9% | V2 matched departure worse than leave-now: net -9 |
| Nessie Plushie | 6/12 = 50.0% | Original V2 restock hit only 25.89% on 282 cycles |
| Chamois Plushie | 5/9 = 55.6% | V75 matched net -6/26; V2 window hit 25.64% |
| Panda Plushie | 6/10 = 60.0% | Three-preview cohort only; no V75 matched baseline |
| Monkey Plushie | 7/10 = 70.0% | V2 window hit 26.56%; instability/arrival timing |
| Lion Plushie | 10/14 = 71.4% | Three-preview cohort only; source/model still provisional |
| Red Fox Plushie | 9/12 = 75.0% | V2 window hit 29.56% on 203 cycles |
| Canada Xanax | 5/6 = 83.3% | V75 matched net +23/43: preserve existing incumbent |
| Jaguar Plushie | 16/16 = 100% | Encouraging but too small and correlated to certify |
| Peony, Edelweiss, Japan Xanax, UK Xanax | 0 scored V128 proposals | **NO EVIDENCE**, not 0% observed accuracy |

Per-item V128 scored samples total 169: 122 hits and 47 misses. No item has the requested demonstration of >=30 independent restock events. Original V2 valid targeted cycles were missing for Crocus, Peony, Hawaii Orchid, Dahlia, Edelweiss and Tribulus; this means **zero SCORABLE archive target cycles**, not that the live page cannot display those items.

## Immediate product decisions

1. Preserve BOTH existing views: original V2 graph and already-deployed 24-row /experimental. Current API had 21 V75 incumbent models and provisional Panda/Lion/Japan Xanax rows. Do NOT replace these with V128.
2. V128 remains private research challenger until it demonstrates reliable coverage, lower miss rates, stable time-to-leave, watch reconfirmation and a matched cohort advantage. Its internal 0.60 scenario fraction is not calibrated success probability.
3. Focus model work on original V2 depletion-to-restock anchors and stocked lifetime/quantity>=30 survival, particularly Camel, Nessie, Chamois, Monkey, Red Fox, and Japan Xanax. Do not make random new tournaments.
4. Verify existing V75 per-item live mapping and three provisional preview model provenance before any promotion. Its apparent higher matched proxy performance is encouraging but from a distinct cohort.
5. Conduct future exact matched (item, issuance time, observation maturity, source coverage) three-way replay on overlapping periods. Retain censored unknowns and absent proposals in denominators.
6. Do not enable the newly added research-only shared V2 timeline on public site until actual deployed source is captured/reconciled, rollback tested, and user approves rollout. Server and experimental page source differ from repository checkout.

## Repeatable checks and traceability

New research/v139_beta_evidence_summary.py can parse a complete V139 terminal text file without accessing VM data; it checks paired success arithmetic, 24 item counts, abstentions, unknowns, and explicitly labels every item's forward success UNVERIFIED for promotion. Tests live at tests/test_v139_beta_evidence_summary.py.

Deployed V2 and experimental routes returned HTTP 200; V41 API contained 24 expected unique records, zero duplicates. See docs/vm_observed_dual_view_probe_20261012.md for installed V87 flag, deployed source fingerprints and intermittent V128 DB error.

No real flight or purchase outcome, no country-specific provider update age, and no same-issue comparison between model families was established.
