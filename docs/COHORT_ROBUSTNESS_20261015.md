# Cohort robustness correction — 2026-10-15 UTC

The legacy hourly replanning metric selected the first five-minute issue after the snapshot-relative seven-day boundary, then every twelfth issue. A snapshot shift of thirty minutes therefore changed nearly every hourly start. Large changes between successive snapshots can reflect this phase sensitivity, alongside new evidence and maturation. Earlier reports describe their sampled cohorts; they do not establish reliability across starting times.

The primary diagnostic now pools **every five-minute start** over the issue window. It also reports the twelve UTC-minute offsets separately and a fixed UTC top-of-hour series. Legacy source-relative hourly results remain for audit compatibility. Counts, coverage, unresolved outcomes, wait sums, chronological day slices and matched comparisons against the same local paths and established rate references remain visible. A higher conditional success rate with low departure coverage is not accepted as an improvement.

These starts overlap heavily: one stock episode and one recommended departure can serve many cohorts. They are not independent flights, player executions, calibrated future probabilities or confidence certification. Offset variability is sensitivity analysis, not twelve independent replications. Never directly compare the old hourly percentage with the new pooled percentage as a model gain.

Forecast generation is unchanged by this evaluator correction. Source truth is memoized only within an item's immutable replay snapshot. Tests verify canonical UTC starts, complete nonduplicated five-minute starts, fixed issue-window boundaries, unchanged pre-cutoff decisions under future-truth mutation, and full/focused replay equality.

The fixed future-window experiment separately freezes source and issue window before fresh data arrives. Reconstructed outcomes remain distinct from actual live issuance and purchases. Physical depletion continues to require positive stock to exactly zero; stock below thirty is buying availability, not depletion.
