# Corrected seven-challenger replay

Historical evaluation preserved below. The same saved forecasts have since been rescored with the live V5 freeze-at-recommended-departure policy; see [the V5 rescore](CHALLENGER_V5_RESCORE_20261029.md). Its frozen-trip rates and miss counts use a different evaluation unit.

Window: Oct 21, 2026 11:20 PM ET to Oct 28, 2026 11:20 PM ET.

All seven items completed all 2,017 issue clocks: 14,119 item evaluations in total, with no native model errors. Every clock is present exactly once. Source hash and complete first-forecast chronology were checked independently.

The existing live first-reachable-window scheduler was used, followed by one native timing configuration per item. There is no five-minute departure eligibility filter or agreement gate. A five-minute issuance grid samples forecasts. Full available causal history is retained, with no 48-hour or point-count lookback restrictions.

## Observed-opportunity results

These are the first issued forecasts for matched observed opportunities, not repeated five-minute rows. Percentages below are conditional on known matched outcomes. Unmatched failures/unknowns remain separately visible and prevent these from being advertised as overall success rates. Pending/unknown opportunities are excluded only from the conditional known denominator.

The primary identity audit preserves buying-window continuity across provider changes when both observations agree on >30 availability. Conflicting switches, ambiguous boundaries and collection gaps still prevent a match. The original live matcher rejects every provider switch and can thereby exclude earlier failures; its counts are retained in RESULTS.json as the conservative-reference view. Saved forecasts and landing grades are unchanged.

| Item | Matched success / known | Unknown | Pending | Advice issue clocks / 2,017 |
| --- | ---: | ---: | ---: | ---: |
| arg:Monkey Plushie | 55/75 (73.3%) | 9 | 0 | 1666 |
| can:Wolverine Plushie | 120/153 (78.4%) | 7 | 0 | 1817 |
| cay:Stingray Plushie | 127/149 (85.2%) | 14 | 0 | 1754 |
| chi:Peony | 18/19 (94.7%) | 1 | 0 | 1785 |
| sou:African Violet | 13/13 (100.0%) | 1 | 1 | 1277 |
| sou:Lion Plushie | 66/87 (75.9%) | 7 | 0 | 1837 |
| uni:Xanax | 1/1 existing stock period; no independent rate | 0 | 0 | 460 |

## Coverage and unmatched evidence

The advice counts measure how often an issue produced advice, not distinct trips. No-advice causes and all unmatched issue outcomes follow. An unmatched failure is retained; it cannot be silently removed to improve a percentage.

| Item | Unmatched success rows | Unmatched failure rows | Unmatched unknown rows | No-advice rows |
| --- | ---: | ---: | ---: | ---: |
| arg:Monkey Plushie | 528 | 175 | 42 | 351 |
| can:Wolverine Plushie | 161 | 50 | 21 | 200 |
| cay:Stingray Plushie | 122 | 18 | 10 | 263 |
| chi:Peony | 146 | 0 | 3 | 232 |
| sou:African Violet | 199 | 26 | 1 | 740 |
| sou:Lion Plushie | 542 | 144 | 53 | 180 |
| uni:Xanax | 42 | 0 | 0 | 1557 |

### arg:Monkey Plushie

Configuration: v20 traj3, full-history override. No-advice causes: `{"CURRENT_PHASE_UNKNOWN": 184, "STALE_COUNTRY_DATA": 167}`.

Matched failure timing: `{"AFTER_OBSERVED_STOCK_LOSS": 6, "EARLY_WHILE_UNSTOCKED": 13, "OTHER_OR_UNCERTAIN": 1}`. Median minutes from the relevant observed boundary: `{"AFTER_OBSERVED_STOCK_LOSS": 10.783333333333333, "EARLY_WHILE_UNSTOCKED": 76.26666666666667}`.

### can:Wolverine Plushie

Configuration: v20 traj12, full-history override. No-advice causes: `{"CURRENT_PHASE_UNKNOWN": 150, "STALE_COUNTRY_DATA": 50}`.

Matched failure timing: `{"AFTER_OBSERVED_STOCK_LOSS": 13, "EARLY_WHILE_UNSTOCKED": 19, "OTHER_OR_UNCERTAIN": 1}`. Median minutes from the relevant observed boundary: `{"AFTER_OBSERVED_STOCK_LOSS": 4.116666666666666, "EARLY_WHILE_UNSTOCKED": 5.766666666666667}`.

### cay:Stingray Plushie

Configuration: v20 traj5, full-history override. No-advice causes: `{"CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS": 22, "CURRENT_PHASE_UNKNOWN": 154, "STALE_COUNTRY_DATA": 87}`.

Matched failure timing: `{"AFTER_OBSERVED_STOCK_LOSS": 4, "EARLY_WHILE_UNSTOCKED": 16, "OTHER_OR_UNCERTAIN": 2}`. Median minutes from the relevant observed boundary: `{"AFTER_OBSERVED_STOCK_LOSS": 5.233333333333333, "EARLY_WHILE_UNSTOCKED": 3.866666666666667}`.

### chi:Peony

Configuration: v20 traj12, full-history override. No-advice causes: `{"CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS": 85, "CURRENT_PHASE_UNKNOWN": 76, "STALE_COUNTRY_DATA": 71}`.

Matched failure timing: `{"EARLY_WHILE_UNSTOCKED": 1}`. Median minutes from the relevant observed boundary: `{"EARLY_WHILE_UNSTOCKED": 50.61666666666667}`.

### sou:African Violet

Configuration: v20 traj11, full-history override. No-advice causes: `{"CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS": 135, "CURRENT_PHASE_UNKNOWN": 563, "STALE_COUNTRY_DATA": 42}`.

Matched failure timing: `{}`. Median minutes from the relevant observed boundary: `{}`.

### sou:Lion Plushie

Configuration: v20 traj12, full-history override. No-advice causes: `{"CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS": 28, "CURRENT_PHASE_UNKNOWN": 110, "STALE_COUNTRY_DATA": 42}`.

Matched failure timing: `{"AFTER_OBSERVED_STOCK_LOSS": 7, "EARLY_WHILE_UNSTOCKED": 14}`. Median minutes from the relevant observed boundary: `{"AFTER_OBSERVED_STOCK_LOSS": 2.283333333333333, "EARLY_WHILE_UNSTOCKED": 44.38333333333333}`.

### uni:Xanax

Configuration: v19 dyn8, full-history override. No-advice causes: `{"CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS": 1489, "STALE_COUNTRY_DATA": 68}`.

Matched failure timing: `{}`. Median minutes from the relevant observed boundary: `{}`.

## Interpretation limits

Stock >30 at calculated arrival is success, with zero grace; exactly 30 is failure. Successful arrival after a restock is still success. Early/late minutes are reported only for failed matched arrivals and use observed threshold boundaries, which have polling uncertainty. Historical replay is not prospective accuracy certification.

A shared event-calendar limitation can withhold all advice before the native timing model runs: unknown current phase onset, or a current stock period longer than every historical survivor. UK Xanax is a prominent example. Those are coverage limitations to investigate rather than evidence that selectively issued advice is sufficient.

All source reads and native inputs were causal at each issue. Sealed outcome data was used only to score saved predictions and retrospectively identify observed opportunities. Country freshness is required for known arrival outcomes. No actual player departure or purchase is required.

The cache acceleration was checked against complete original forecast payloads at 21 issue/item pairs, all identical. It reuses already closed collection checks and imports, not predictions. A brief runner overlap produced identical duplicate rows; originals and migration audits were retained, duplicates were removed only after equality checks, and final scoring sorts by issued timestamp and independently requires the full unique grid. The first forecast, never the best revision, remains the evaluation record.

## Follow-up work prepared

The admin-health update is staged in Git, not deployed. It reports live publisher, country clocks, evidence ledger, model and publisher identities, and labels legacy counters. Fifty-two regression/unit tests passed; desktop/mobile UI checks passed. The user can deploy later using deploy/Update_Admin_Health.ps1. Its default is a deployment plan; -Apply installs only three health/UI files and restarts only the web service, with rollback on failed API checks.

The screenshot showed 31.1% disk used and about 30GB free; 59 backups occupied 4.3GB. The read-only storage inventory is prepared, but no host inventory or deletion has been performed. Review retention and verify backups before choosing cleanup targets. Collector history, active model releases and forecast evidence remain preserved.

Production models, publisher, collector, timers and website remain unchanged by this replay. No additional item has been deployed. Code: https://github.com/fungjkTorn/torn-fren/commit/96a336685de17b9e16923b321d526d30417a927a . No GitHub Actions runs were triggered.

## Recommended discussion order

1. Peony is the clearest next candidate to prepare for labelled live forward testing: 18/19 known matched opportunities, with one unknown. African Violet is also promising at 13/13 known, but has one unknown, one pending, and advice on only 63.3% of issue clocks. Investigate its phase-onset/overrun withholding before presenting it as broadly reliable.
2. Stingray has a larger matched sample (127/149 known, 85.2%). Its matched failures include 16 early arrivals (median 3.9 minutes before the observed opening) and four after observed stock loss (median 5.2 minutes). This warrants timing diagnostics, not a blanket offset chosen on this same test week.
3. Wolverine is 120/153 known (78.4%), with 19 early and 13 late matched failures. A single later/earlier shift would trade one problem for the other.
4. Monkey is 55/75 known (73.3%); Lion is 66/87 known (75.9%). Some early misses are much larger than a few minutes: median 76.3 minutes for Monkey and 44.4 minutes for Lion among matched early failures. Inspect projected restock/calendar alignment over their long flights before tuning only the departure refinement. These are observed-target diagnostics, not proof that a single fixed timing correction will work.
5. UK Xanax has one matched pre-existing stocked period and no new clean buying-window openings in the test week. It issued advice on only 460/2,017 clocks (22.8%); 1,489 clocks were withheld because the phase outlasted historical survivors. Do not advertise a 100% independent-event success rate. Current-stock continuation/long-stock handling needs its own change and test.

These are priorities for review and preparation, not production promotions. Remaining unmatched failures and unknowns mean every overall success percentage is withheld. The original strict-provider matched subset was more favorable because it excluded some earlier failures; those conditional reference numbers must not be used as headline accuracy.
