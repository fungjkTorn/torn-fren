# Seven saved challengers rescored with V5

Window: October 21, 2026 11:20 PM ET through October 28, 2026 11:20 PM ET. All 14,119 original saved item/issue records were retained: 2,017 per item. No models were rerun, no departure or arrival was adjusted, and no production change was made. The original stock snapshot and forecast files remain byte-identical.

Policy: `RECOMMENDED_DEPARTURE_FREEZE_V5`, the same tracking implementation now deployed for the live ten. Each recommendation may revise before departure, then freezes with the exact saved departure and arrival. Unknown and pending arrivals are separate; stock >30 at calculated arrival is success, zero grace. All seven items have zero duplicate target identities, and repeating the summaries changes nothing.

## Whole-week frozen simulated trips

These are all frozen tests in the week, not just the last ten. The percentages use known results only; unknown/pending counts remain visible. They are historical sampled-stream outcomes, not prospective accuracy certification.

| Item | Frozen trips | Success / known | Unknown | Pending | Advice clocks / 2,017 |
| --- | ---: | ---: | ---: | ---: | ---: |
| arg:Monkey Plushie | 134 | 95/126 (75.4%) | 6 | 2 | 1666 |
| can:Wolverine Plushie | 163 | 155/161 (96.3%) | 2 | 0 | 1817 |
| cay:Stingray Plushie | 162 | 153/158 (96.8%) | 3 | 1 | 1754 |
| chi:Peony | 16 | 16/16 (100.0%) | 0 | 0 | 1785 |
| sou:African Violet | 13 | 13/13 (100.0%) | 0 | 0 | 1277 |
| sou:Lion Plushie | 141 | 103/134 (76.9%) | 5 | 2 | 1837 |
| uni:Xanax | 1 | 1/1; existing stocked period only | 0 | 0 | 460 |

UK Xanax has no qualified restocks in the replay week and only one frozen test during an existing stocked period. Its single success does not estimate independent-restock accuracy. African Violet has only 13 tests and advice on 63.3% of clocks; its phase-onset/overrun withholding remains a coverage question. Peony has 16 tests. Do not treat those clean but small samples as established 100% reliability.

## Failed-trip nearest-boundary audit

For a known failed arrival with zero stock, compare elapsed minutes since preceding clean depletion to zero against minutes until the next qualified normal restock. Assign whichever is closer. Qualified restocks use the V5 pre-test historical profile, excluding tiny sellbacks. Missing/conflicting boundaries, mixed zero/low-stock brackets and ties remain explicit. Boundary timestamps have polling uncertainty. A known purchase failure does not become an unknown arrival merely because its early/late boundary is uncertain.

| Item | Failures | Early | Late | Positive stock 1–30 | Uncertain / tie | Median early / late minutes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| arg:Monkey Plushie | 31 | 12 | 13 | 1 | 5 | 4.0 / 4.8 |
| can:Wolverine Plushie | 6 | 1 | 3 | 0 | 2 | 6.6 / 3.8 |
| cay:Stingray Plushie | 5 | 2 | 2 | 0 | 1 | 4.6 / 6.9 |
| chi:Peony | 0 | 0 | 0 | 0 | 0 | — / — |
| sou:African Violet | 0 | 0 | 0 | 0 | 0 | — / — |
| sou:Lion Plushie | 31 | 19 | 11 | 0 | 1 | 3.3 / 3.8 |
| uni:Xanax | 0 | 0 | 0 | 0 | 0 | — / — |

## Revisions, expiries and sampling limits

The archive contains forecasts at 300-second intervals and no measured server publication latency. For this rescore only, each recorded issue clock is its simulated publication clock. Missing stale-country forecasts become explicit no-advice clocks. No one-minute refreshes or extra forecasts were invented. Original validity deadlines remain unchanged, so a recommendation may expire before the next recorded clock. Those withdrawals are not failed arrivals, and their exclusion from frozen trips is exposed below. The result therefore does not establish what the same models would do under a live one-minute refresh stream.

| Item | Revisions before departure | Postponements (subset of revisions) | Expired before departure | Withdrawn: no advice | Withdrawn: changed target |
| --- | ---: | ---: | ---: | ---: | ---: |
| arg:Monkey Plushie | 741 | 409 | 19 | 55 | 4 |
| can:Wolverine Plushie | 871 | 554 | 26 | 13 | 3 |
| cay:Stingray Plushie | 937 | 645 | 10 | 35 | 1 |
| chi:Peony | 877 | 645 | 0 | 36 | 7 |
| sou:African Violet | 679 | 493 | 0 | 28 | 0 |
| sou:Lion Plushie | 940 | 558 | 15 | 24 | 38 |
| uni:Xanax | 197 | 132 | 0 | 1 | 0 |

## Interpretation and next decisions

- Wolverine (155/161 known) and Stingray (153/158) now have the strongest larger samples for discussion of labelled forward testing. The earlier lower matched-window percentages were computed from a different evaluation unit; this rescore does not demonstrate that their models were improved.
- Peony and African Violet remain promising, with small samples and the coverage limitations above.
- Monkey has 31 failures, split between 12 early, 13 late, five uncertain-boundary classifications and one positive-low-stock arrival. Lion also has 31 failures, including 19 early and 11 late. Diagnose timing/depletion before choosing an offset.
- UK Xanax remains a current-stock/long-phase handling problem. The native phase-overrun blocker is unchanged.
- Retain the earliest-reachable-window sequence and full available causal training history. Do not reintroduce rolling/48-hour restrictions or five-minute departure eligibility filters.
- Jonny’s deferred arrival-margin idea is recorded in `docs/TIMING_REFINEMENT_FOLLOWUP.md`. For long stocked windows, consider targeting slightly after predicted restock in a separately validated experiment. No such timing change was made here, and Crocus is left to collect more live evidence.

## Reproduction

```bash
PYTHONPATH=. python research/rescore_saved_challengers.py --source /path/to/torn-fren-challenger-history-20261029T032420Z.sqlite --archive /path/to/original-current-week --output /path/to/new-rescore-directory
```

The tool validates the original source hash, complete unique issue grid and full-history training metadata before scoring. It fails on duplicate target identities, checks frozen geometry against the original saved row, checks summary idempotency, and rechecks original input hashes. Output includes whole-week and last-ten results, per-trip records, early/late classifications and recommendation-change counts.
