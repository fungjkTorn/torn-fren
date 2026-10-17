# Japan Xanax coverage experiment v1

The inspected three-day renewal comparison reached 391/467 known successes
(83.73%) for sequence_blocks_peak, with 54.05% departure coverage and 201.3 min
average wait. Quantity continuation peak covered 76.50% but achieved only 68.84%
known success. These are different departure subsets, not equal-coverage gains.

Freeze seven research variants before this run: preserve the sequence primary and
fall back to quantity peak; preserve the primary and fall back to the rate model
only with sequence support >=.25; require both sequence and paired support >=.25
or >=.40; independently use sequence peak minus .10 with floor .15; or earliest
sequence support >=.30 or >=.45. Scenario support is not calibrated probability.
Fallback uses no outcomes, never overwrites an available primary, never extends
past eight hours, and takes the conservative adjacent support grid for off-grid
rate departures. All candidates retain five-minute replanning, 15-second
publication floor, exact-zero depletion anchors, >=30 arrival plus ten-second
grace, and causal past-only history.

Use six days ending at issue epoch1791956400 (aligned), before the first inspected
renewal issue1791956700. Report earlier three days, reserved later three days, and
all six days separately, with all original eight policies as controls. This older
window was not inspected for these combinations; it is not a pristine holdout
across all prior project research. Do not tune after reading the reserved half.

Compare success, coverage, unknown mass, mean waiting and daily consistency, plus
paired outcomes against sequence primary and rate control on the same starts.
A useful exploratory direction should reach at least65% coverage and75% known
success, improve coverage by at least10 percentage points over the same-window
sequence primary, and avoid extending its mean wait. These are screening goals,
not production approval gates or calibrated reliability guarantees. No automatic
model selection/promotion. If none passes, keep that rejection visible.

Only research code exports optional scenario curves. Calling the original model
without diagnostics returns unchanged predictions (tested). The currently running
24-item live recorder stays pinned to its existing source, process and journal.
