# Publication-delay historical audit

A selected point departure can be missed before a page receives the snapshot. The current integration correctly clears a missed point. Before adding any execution tolerance, this fixed diagnostic measures publication delays of 0, 5, 15, 30, 60, 90, 120 and 180 seconds.

For each staged policy and fixed five-minute issue, the strict arm executes only a point still in the future when delivered, before the next original issue and while source age remains <=180 seconds. The late counterfactual shifts a missed point to its delivery time, subject to the same source/issue expiry, and scores the changed sampled arrival. That arm is experimental, not permission to execute late. It does not alter the deployed recommendation contract.

Outcomes retain ABSTAIN, FUTURE_RECHECK, MISSED_POINT, STALE, UNKNOWN and PENDING separately. Success is conditional on known arrivals; actionable fraction uses every issue. Paired late-versus-zero-delay wins/losses, UTC days and twelve minute offsets remain visible. These are issued-plan diagnostics, NOT full trip-start/replanning cohorts or independent flights; their percentages must not replace the original all-start trip success metrics.

The audit uses the staged 14-candidate assignments, existing causal numerical path model, mature training paths and exact physical-zero state. Source stock is read in one SQLite read-only transaction. Every plan is issued using past observations; later observations are used only to score arrival. The latest issue window ends early enough to mature all scored before-next-issue arrivals. No model is selected, retrained differently or promoted from this report. Active Camel and Chamois protocols stay frozen.

Four unit/integration tests passed locally, including exact delayed arrival scoring, lost strict actionability, explicit late failures, stale/future/unknown categories and an actual historical fixture replay with unchanged source bytes.

Historical runner status and results are recorded below once available. No VM commands are needed from the user to perform this research. Installing a fresh public feed and integrating the deployed experimental page remain separate release steps.

Source `81df185d80226622ba5193975c1e47f05acea29e` passed public CI38931714824 (four tests), plus V35, profitability and V38 compatibility. Private request/control commit7779c059c766ddf29dcb10407630b00697834971 launched historical runner38931830035. It retains the existing isolated-research concurrency and sanitized read-only snapshot, with no extra collector permissions, production changes or frozen-protocol edits.

## Verified historical result

Runner38931830035 completed successfully. Artifact12058763021, ZIP59651bytes, SHA256 `e995a3c2d126e728747679c4dadfda29a50fe4adbbbf4549596d17dcc01a7c92` verified. Source cutoff1792166660; seven-day issue window1791549600→1792154100;2016issues/item. No deployment or permission changes.

Cells below describe per-issued-plan actionability and sampled outcomes, not full trip-start replanning success.

| Item | Strict actionability 0s → 30s | Zero-delay success → late30 success | Unknown 0s → late30 |
|---|---:|---:|---:|
| arg:Ceibo Flower | 54.71% → 0.40% | 99.53% → 99.63% | 30 → 29 |
| can:Crocus | 64.53% → 0.10% | 96.83% → 96.65% | 39 → 47 |
| can:Wolverine Plushie | 41.07% → 2.23% | 92.71% → 91.96% | 46 → 44 |
| cay:Banana Orchid | 53.08% → 0.05% | 98.94% → 98.94% | 29 → 36 |
| cay:Stingray Plushie | 47.72% → 2.83% | 95.50% → 95.08% | 50 → 47 |
| chi:Peony | 50.89% → 1.64% | 97.81% → 97.80% | 23 → 24 |
| haw:Orchid | 55.61% → 0.15% | 96.29% → 96.32% | 43 → 34 |
| jap:Cherry Blossom | 41.27% → 0.40% | 99.25% → 99.37% | 36 → 38 |
| mex:Dahlia | 58.18% → 0.00% | 99.38% → 99.38% | 49 → 47 |
| mex:Jaguar Plushie | 51.64% → 1.64% | 99.20% → 98.90% | 37 → 44 |
| sou:African Violet | 53.12% → 0.94% | 95.15% → 95.05% | 40 → 41 |
| swi:Edelweiss | 59.33% → 0.45% | 90.05% → 90.02% | 30 → 34 |
| uae:Tribulus Omanense | 60.71% → 0.55% | 95.94% → 95.96% | 43 → 36 |
| uni:Heather | 49.40% → 0.30% | 97.48% → 97.52% | 43 → 30 |

**Finding:** the current strict point contract is mathematically consistent but practically unusable for most immediate departures after publication latency. At30seconds strict actionability is0–2.83%of all issues, versus41.07–64.53%at zero delay. The remainder includes future rechecks/abstentions as well as missed points; do not call them all prediction failures.

**Short-tolerance candidate:** the fixed30second late arm preserves the baseline actionable fraction for all14items with similar conditional success. However unknown/resolved sets change. Zero matched30second exclusive losses does not mean zero added risk: observations previously unknown can become known failures, and marginal success fractions can fall. Poll-bracket resolution and highly correlated samples limit this inference.

Longer tolerance is less attractive: at120seconds Wolverine falls92.71→90.57%and Stingray95.50→93.12%on these issued-plan outcomes. At180seconds almost all potential executions are stale under the existing source-age limit, so residual high percentages are tiny-selected samples, not evidence of safety.

**Next implementation:** stage a separately identified <=30second execution-tolerance policy with cumulative source freshness, original issue expiry, exact delayed landing geometry, explicit missed-window cancellation, and evidence matched to that execution policy. Do not inherit the point-policy success fraction or change any active frozen model protocol. Validate the exact resulting consumer/publisher behavior before any owner-side deployment. The current integration still enforces strict points; this audit itself enables no late departure.
