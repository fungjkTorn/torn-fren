# Publication-delay historical audit

A selected point departure can be missed before a page receives the snapshot. The current integration correctly clears a missed point. Before adding any execution tolerance, this fixed diagnostic measures publication delays of 0, 5, 15, 30, 60, 90, 120 and 180 seconds.

For each staged policy and fixed five-minute issue, the strict arm executes only a point still in the future when delivered, before the next original issue and while source age remains <=180 seconds. The late counterfactual shifts a missed point to its delivery time, subject to the same source/issue expiry, and scores the changed sampled arrival. That arm is experimental, not permission to execute late. It does not alter the deployed recommendation contract.

Outcomes retain ABSTAIN, FUTURE_RECHECK, MISSED_POINT, STALE, UNKNOWN and PENDING separately. Success is conditional on known arrivals; actionable fraction uses every issue. Paired late-versus-zero-delay wins/losses, UTC days and twelve minute offsets remain visible. These are issued-plan diagnostics, NOT full trip-start/replanning cohorts or independent flights; their percentages must not replace the original all-start trip success metrics.

The audit uses the staged 14-candidate assignments, existing causal numerical path model, mature training paths and exact physical-zero state. Source stock is read in one SQLite read-only transaction. Every plan is issued using past observations; later observations are used only to score arrival. The latest issue window ends early enough to mature all scored before-next-issue arrivals. No model is selected, retrained differently or promoted from this report. Active Camel and Chamois protocols stay frozen.

Four unit/integration tests passed locally, including exact delayed arrival scoring, lost strict actionability, explicit late failures, stale/future/unknown categories and an actual historical fixture replay with unchanged source bytes.

Historical runner status and results are recorded below once available. No VM commands are needed from the user to perform this research. Installing a fresh public feed and integrating the deployed experimental page remain separate release steps.
