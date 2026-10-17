# Japan rechecked departure retention experiment v1

Recent-memory development on the same inspected three days did not improve the
accuracy/coverage tradeoff. Mean support at .30 reached83.22% coverage but60.78%
known success. The baseline83.73% start-weighted result involved13 distinct
chosen departure epochs: seven successful and six failed. These epochs are still
not independent flights. The issue-weighted rate must not be called an83.73%
chance of a successful flight.

Now test whether repeating the highest-support future target causes postponement
and prevents actual departures. Count baseline issues with/without forecasts,
near/far future plans and target movement. Keep default physical-zero prediction
model unchanged. Three execution challengers retain a previous, unexpired target
only if its CURRENT conservative interpolated scenario support is at least.20,
.30 or.40 and current source age plus15 seconds remains <=180. Cancel absent,
expired, stale or unsupported advice and use the newly issued default target.
Do not blindly commit to old forecasts. Item/provider discontinuity produces no
current scenario curve and cancels retention.

Use the identical development issues1791956700 through1792215600, truth cutoff
1792254014 and expected baseline391/467 with467/864 departure coverage. Retain
five-minute replanning, eight-hour max wait,15-second publication floor and
arrival>=30 through ten seconds. Source and outcome semantics are unchanged.
Record paired outcomes, daily slices, waiting, distinct departures and retention
rejection reasons. Hypothesis and policies declared after inspecting recent
recency results; not independent validation. No automatic promotion or changes
to the ongoing24-item live test.
