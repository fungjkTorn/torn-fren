# Cycle-conditioned stock-path departure experiment

The preceding physical-cycle audit found a past-only ridge timing signal in
seven weak plushies and Jaguar, but rejected that ridge signal for Japan.
Clock-period screening found no useful general pattern. Those timing results
do not establish arrival success, so this experiment tests the translation
to departures rather than promoting the cycle model.

Four fixed research policies combine two timing families (ridge and recent
median) with either a 0.70 agreement gate or a diagnostic peak gate. Both
families run on every item; no whole-evaluation-period signal flag chooses a
family at an earlier issue. The new scenarios remain departure-only and do
not inherit event-timing accuracy from another forecaster.

At a clean observed restock, freeze that cycle's feature vector and fit using
only previously completed cycles. For each historical completed cycle, keep
the error of the prediction made at its own birth. These are prequential
errors, not optimistic residuals from refitting the same target. Apply those
past errors to the current cycle clock, conditioning on no new restock yet.

Each error is coupled to its historical complete stock trajectory, aligned
at that historical cycle's next restock. Require the shifted historical issue
to lie within that cycle and match both the current positive/zero physical
phase and >=30 buying phase. Thus an error scenario that contradicts current
observations is rejected. Quantity 1–29 never means true depletion.

Future arrivals query the actual historical stock trajectory on a certified
one-minute grid. Future cycles and top-ups stay as observed, rather than
requiring invented future batch sizes or recursively treating predictions as
new training data. Each historical path must mature through the entire
eight-hour wait plus flight plus grid/evidence allowance BEFORE issuance.

Use the last 64 mature cases before matching. Require at least 24 cases, 16
matched scenarios, 12 known labels and 80% known mass. The strict policy takes
the first minute with >=0.70 smoothed agreement; the peak diagnostic takes
the first within 0.03 of the supported peak with a 0.15 floor. All scores are
uncalibrated. Thresholds and support rules are fixed before this replay.

When the current cycle becomes ambiguous after a gap or conflicting provider
transition, abstain until a clean observed restock establishes a new cycle.
Future invalidations cannot change earlier plans. At a new observed restock,
the cycle fit updates; survival and matching use currently available state.
This is not a blind first-proposal commitment strategy.

Run the same ten items as the audit: eight weak items plus Jaguar and Peony.
Compare all five-minute replanning starts, matched outcomes against prior
rate/hybrid/path references, coverage, waits, UTC offsets and daily floors.
Report all four policies and all unmatched outcomes. The data have already
been inspected, so this is exploratory reconstruction, not a pristine holdout.
The original frozen forward protocol remains untouched. Any promising new
policy needs its own subsequently fixed validation window.
