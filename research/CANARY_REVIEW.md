# Full24 canary review and shared input reads

The full24 recorder remains nine rows per item per successful cycle: eight
generic physical-zero variants/controls and the original specialist control.
Japan's incompatible legacy specialist is an explicit abstention; its eight
physical-zero variants remain included. A complete 216-row footprint does
not establish that the specialist inference succeeded.

The scorer now reads journal rows and capture attempts in one read-only
transaction, validates encoded identity and the zero/30/10 contract, and adds
`capture_diagnostics` to its JSON output. Original arrival scoring is unchanged.

| Diagnostic | Meaning |
| --- | --- |
| Complete24 row batches | Consecutive saved batches containing each of 24 × 9 item/model identities once |
| Model statuses | Every captured status per item/model, including errors and stale/passed targets |
| Eligible hours | UTC-hour buckets containing near-term advice; sampled capture coverage, not visitor success |
| Active window observed hours | Buckets from first recorded successful attempt through the last recorded attempt/publication, including partial hours |
| Hours without any capture | Entire skipped buckets inside that observed window; retained in the diagnostic coverage denominator |
| Distinct eligible departures | Unique target timestamps; repeated rows/targets are not independent flights |

The original `hourly_opportunities` metric counts captured hours. Its name and
meaning remain unchanged for compatibility. Use the new active-window metric
to see whole-hour collection gaps; neither metric is executable visitor
coverage from a continuous eight-hour session. The existing success/known
metrics remain sampled arrival availability, not actual flights, calibrated
probabilities, or restock/depletion timing accuracy. All nine models' results
remain in JSON; compact output shows the original specialist/rate pair,
specialist status counts, and all eight Japan variants. No best-model routing
or automatic promotion is added.

Capture previously used `source_data` once as a bootstrap and once per item,
repeatedly loading identical poll/gap histories and constructing unused arrival
truth evaluators. `capture_inputs` now loads the 24 item histories in one
read-only transaction, checks heartbeat/gaps and the bounded successful-poll
count once, and omits truth construction. It preserves item/poll/gap limits,
row validation, source cutoff and gap handling. A fixture comparison checks
every item's rows and gap predicates against the old reader and verifies
source bytes are unchanged. No VM performance improvement is asserted until
measured on representative data. Native model math and CPU admission remain
unchanged. This update does not change an already-running owner recorder.

The owner's last confirmed status on October19 was seven successful all24
cycles, 1512 saved rows, and collection started. Completion and overnight
accuracy require a fresh owner-VM report. Do not infer them from elapsed time.
