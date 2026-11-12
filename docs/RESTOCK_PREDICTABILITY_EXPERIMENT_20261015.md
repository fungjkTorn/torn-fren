# Physical-cycle predictability and clock-phase experiment

The recent arrival classifier and commitment policies did not give a balanced
replacement. The next round checks whether a different timing signal exists
before adding another departure policy. This is a diagnostic, not flight proof.

## Sequential physical-cycle regression

Issue a prediction at each clean observed 0-to-positive restock. Predict the
following full cycle, which must contain an observed positive-to-exactly-zero
transition and another clean restock. Quantity 1–29 stays positive. Gaps and
provider switches that contradict physical phase invalidate a cycle; benign
same-phase switches follow existing V145 continuity rules. Pending and unknown
cycles remain counted rather than becoming failures or fabricated durations.

The comparator predicts the median of the last 64 eligible completed cycles.
The challenger is ridge regression of log cycle duration, penalty 8, using the
same last 64 examples with a 32-cycle recency half-life. Inputs observed at the
new cycle's start are the last four relative cycle durations, recent cycle
scale, latest positive and empty durations, new batch quantity relative to
past batches, daily/hourly clock harmonics and provider identity. Normalize
only on past training rows. Bound the predicted log duration to the past
training range. No hyperparameter search on evaluation outcomes.

Require 24 eligible training rows with complete features. Every training
cycle ends at or before issuance; a just-observed completion may be used.
Training precedes the seven-day evaluation window rather than cold-starting
the learner. Score the median and ridge on exactly the same completed trials,
with MAE, p50/p90 absolute error, signed median, tolerance counts, paired
wins/losses and daily slices. Any same-window signal needs a subsequent
departure replay and fixed fresh-data validation.

The predeclared screening rule requires at least 30 scored cycles, >=10% MAE
reduction, no worse p90 error and more paired wins than losses. Passing is
only a signal for another experiment, never production readiness. A cycle
prediction made after a restock does not directly establish arrival accuracy
at a 149-minute lead, or predict an unobserved future depletion time.

## Clock-phase consistency

Test fixed periods 300,600,900,1800,3600,7200 seconds. Fit a +/-60s phase window
on the last 64 clean observed restock timestamps available one country-flight
before each evaluated event. This test is **event-conditioned**: its issue
clocks depend on the observed future event and its phase-hit fraction is not
forecast precision, restock recall or flight success.

Select the center on a 30-second grid using past events only. Require >=40%
training mass and >=35% in each chronological half. Compare with successful
poll phase mass in the same past window; require >=15 percentage-point excess
and at least 80% coverage of the period's 30-second poll bins. These controls
reject sparse polling-cadence artifacts. They cannot establish a game-server
tick or prove the provider country/item clocks were fresh. Preserve every
period's result, rejection count and control mass; do not promote the best
looking held-out period after inspection.

The isolated run evaluates the eight weak items plus Jaguar Plushie and Peony
as controls. Only the sanitized read-only database is accessed. Routine
approved source, all existing pages and the frozen forward protocol remain
unchanged. The separate collector freshness patch remains ready for VM-owner
activation; this experiment does not activate it.
