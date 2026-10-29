# Next items for live forward testing

The existing live set stays at ten. No website, publisher, timer or production
source is changed by this review. The planner layout is deliberately untouched.
There are fifteen remaining items in the verified 25-item checkpoint set.

## First next cohort

| Item | Preserved timing model | Old simulation reference | Current preparation |
| --- | --- | --- | --- |
| Stingray Plushie, Cayman Islands | V18 dyn7 | 521/593, 87.9% | Shared operation-sequence and actual native-engine tests pass |
| African Violet, South Africa | V19 dyn7 | 468/524, 89.3% | Shared operation-sequence and actual native-engine tests pass |
| Peony, China | V20 traj12 | 359/400, 89.8% | Gap-aware V20 path added for explicit candidate previews; tests pass |
| Xanax, UK | V19 dyn3 | 427/476, 89.7% | Native path tests pass; current long-stock handling needs a separate source preflight |

The old references use pre-update correlated issue rows, >=30 and the old
10-second bracket. They are not independent trips, current >30/no-grace results,
or forecasts of the new cohort's live accuracy. Do not copy them to the live
last-ten display. They prioritize investigation, rather than act as an admission
threshold or justify selecting different models on holdout results.

## New observations, not model scores

Seven-day public chart histories were read for those four items, Wolverine,
Canada Xanax and Japan Xanax, with at most two concurrent ordinary history reads.
No inference tournament or full historical replay was run.

Recent completed chart-stock intervals for Peony were about 12.3–16.5 hours;
African Violet about 12.7–15.7 hours. Stingray's last three were about 54–61
minutes, separated by roughly 16–17-minute below-threshold intervals. These
support investigating the first three now, while recognizing changed conditions.
The public chart alone cannot certify every poll/gap boundary; these summaries
are descriptive and are not accuracy scores.

UK Xanax never fell to <=30 in the retrieved seven days: its sampled minimum was
1,443. Continuous stocked history is not proof of no replenishments or a 100%
forecast rate. A boundary/duration forecaster can reject an unusually long phase
or fail to identify its start. Check its current-stock survival path against the
full causal VM history before adding it. Do not invent a restock time, count
phantom cycles or replace it with an unreviewed generic model to force advice.

## Scheduling and source audit

The older routed_champion_plan loop could move to a later physically reachable
restock if its timing scorer returned no recommendation. That is incompatible
with the requested operation sequence. The next cohort therefore uses the same
corrected policy as the ten: enumerate restocks, select the first physically
reachable opportunity, and only then refine timing within that event. A low or
missing timing score cannot skip it. Current stock is checked first when a
supported surviving window exists. The >30 threshold is 31, with no arrival grace
and no eight-hour calendar cap.

The shared scheduler now accepts an explicitly supplied immutable roster for
research previews; all production defaults and CLI choices remain the same ten.
The V20 path uses its gap-aware Timeline and completed-cycle features, rather
than treating Peony as V18. Every underlying timing engine/config remains the
preserved incumbent; no new model was selected or fitted. Existing ten-item
regressions pass alongside the four candidate engine tests.

research.next_forward_cohort is a read-only, one-item preview command. It does
not record prospective outcomes, publish advice, expand source-tail coverage,
change website allowlists or install a timer. Synthetic execution establishes
adapter/sequence behavior only. It does not establish current VM execution cost,
current data sufficiency or forward accuracy.

## Remaining fifteen, accounted for

The three above are the next source-preflight group. UK Xanax has the continuous
current-stock check. Wolverine Plushie (V18 dyn8, old 77.7%) and South Africa
Xanax (V19 dyn1, old 67.5%) are the following diagnostic candidates. Their lower
old rates are not grounds to prohibit labelled forward testing.

Monkey and Chamois retain checkpoint4 templates; Panda and Lion retain their
pair analog selectors; Camel retains its template bank; Nessie retains its
recent-phase template; Red Fox retains its analog model. Those seven require
an explicit event-first adapter review, pinned artifact/cache checks and bounded
VM execution checks. Do not replace their specialist identities with a simpler
V18/V19 model for convenience.

Canada Xanax and Japan Xanax remain the separate waiting-window workstream.
Record exact landing success separately from additional 5/10-minute Canada
windows and 10/20/30-minute Japan windows. Waiting-credit results are cumulative,
not additive. Record signed minutes early/late only with known observed
boundaries; stock already available at landing remains success even if the
restock timer prediction was off. V174 checkpoint summaries do not contain the
per-execution signed-error records required to reconstruct that breakdown.

## Before enabling the next cohort

Run a bounded single-issue preflight on a private consistent VM snapshot with
current stock, poll/gap evidence and country clocks for the candidate countries.
The present fresh-tail reader covers the existing ten: extending only an advice
allowlist would falsely imply current evidence for the new items. Explicitly
extend tail/item/country coverage, snapshot schema/roster checks, prospective
recording and website labels together. Benchmark the complete batch inside the
existing resource budget, then enable the three as labelled forward tests.
Keep all existing ten-item issue/outcome records. Group new outcomes by distinct
physical opportunity and show last ten; no real player flight is required.

This is preparation and review, not an assertion that any new item is live.
