# Japan departure trace and cadence experiment

Owner's19:37 EDT score:260 records/65 batches, sequence and zero_handoff180 each
0 simulated departures/65 starts, all pending; hourly frozen each1/1 known with
one pending proposal and four abstentions across six hourly issues. Rate model
9/34 known (25 failures), one unknown,30 pending;35/65 selected departures.
A successful frozen plan has not translated to a selected replanned departure.
The aggregate report cannot identify the exact withdrawal/postponement timeline.

Read-only target_trace accepts the existing journal plus its ORIGINAL recorded
model SHA, independently of reporting-code checkout. It counts absent forecasts,
distant targets, withdrawals, postponements, advances, missing reconfirmations,
source expiry and reached valid targets. Trace uses publication time, exclusive
300sec forecast validity and inclusive180sec source expiry. Missing source clocks
remain unrecorded, never assumed fresh. Examples and distinct eligible departure
epochs remain separate from correlated per-issue counts. No arrival accuracy is
inferred. It must run on the owner's VM to inspect the actual journal; recreated
history cannot be relabelled as actual recorded advice.

Separate historical experiment: same inspected three-day issues1791956700 through
1792215600 and truth cutoff1792254014. Compare unchanged sequence and zero180
models at300sec and60sec issuance. Same864 visitor starts every300sec for all four
policies, same15sec publication floor,8h maximum wait, exact-zero anchors and
arrival stock>=30 through ten seconds. New advice replaces old only when actually
published. Keep300sec forecast TTL and180sec source TTL at both cadences; no blind
commitments and no weakened freshness or support gates. Measure extra compute.

Recompute legacy five-minute evaluation separately and check fingerprints391/467
with467 departures for sequence,518/659 with659 departures for handoff. Report
publication-aware controls separately so an evaluator change cannot be mistaken
for an improved forecast. All scenarios use only observations available by each
issue. Trace historical predictions with8h of follow-up but count only original
864 issues. Distinct departures still aren't independent flights. Reused period
is development, not fresh validation; no automatic deployment/assignment changes.

Existing retentions20/30/40 and recency variants were already rejected; this tests
check cadence, not another blind commitment or repetition of those variants.
Leave both owner journals/processes intact. Also collect the existing full24-item
score: Japan progress must not consume the entire release decision for other items.
