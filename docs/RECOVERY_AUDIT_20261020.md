# Recovery audit: restock prediction and departure delivery

The product target is an estimated next restock plus a departure/arrival plan
that can actually be followed. The original V2 graph, experimental board and
Travel Decisions must expose the same selected recommendation while keeping
the next restock distinct from a later reachable cycle. Physical depletion
is exactly zero; the arrival target is at least30 through the following10s.

## What the evidence currently establishes

The owner supplied two views of the same7560-row,35-cycle,24-item journal.
Frozen arrival scores and first near-term advice scores answer different
questions and select different records. They are not a paired comparison.
Panda emitted34 bounded proposals, Lion32; their research-only labels were
not admission rejections. Seven plushie specialists had no first near-term
advice in the nine observed UTC-hour buckets. The journal has no explicit
next-restock forecast fields, so it cannot establish next-drop timing error.

The separately retrieved historical artifact contains134 as-issued curves
per item for Camel/Nessie/Fox/Peony. Native proposed waits never fell below
five minutes: Camel minimum5/median85minutes, Nessie50/305, Fox5/400,
Peony10/132.5. These are diagnostic model proposals, not measured live
publication timestamps. Peony at09:00/09:05/09:10 proposed10:10/10:15/10:20.
The data show postponement; they do not prove that every target change was
wrong. Fox has three native errors and cannot support a clean comparison.
The source artifact metadata declares45 days and593715 change rows. The
production database may contain more; it has not yet been independently read.

## Concrete source inconsistency fixed, not deployed

V2's `_make_prediction` formerly tested recommended point departure and the
end of restock uncertainty minus flight time. Its HTTP/browser window logic
instead uses the estimated stocked interval ending at predicted depletion
minus a buffer. Those rules can disagree: a model point can already be past
while the modeled stocked window is still reachable.

The generator now calculates reachability from the same stocked-window
geometry and receives the existing lifetime estimate before chain selection.
The expected restock timestamp and model training are unchanged. Unknown or
nonpositive stocked intervals remain unavailable. Depletion annotation uses
the supplied historical clock, not the current wall clock. A regression
reproduces the discrepancy and verifies first-cycle selection, true expiry,
missing lifetime, impossible intervals and compatibility with the existing
graph window checks.

The HTTP layer already repairs some of the old disagreement. This source fix
is therefore not proof of improved real-world accuracy or an explanation for
all missing canary advice. It has not been installed on the VM or changed
production routing. V2's stocked lifetime is not a certified>=30 landing
window; actual arrival scoring must still use stock observations.

## Next evidence, using existing records

`research.saved_timeline_audit` reads the saved model journal without inference.
It separates future targets, five-minute targets whose original source expires
before departure, missing/rejected targets, repeated postponement, and targets
that elapsed between captures. It records actual query-gap statistics.

The same audit inventories the real collector history span and original V2
archive, reuses the existing read-only V134/V137 archive scorers, and checks
the local page routes. Missing archives or source caps are explicit; no
replacement predictions or accuracy claims are fabricated. Historical V137
cannot reconstruct the exact latest browser window because old archives did
not save all required lifetime fields; its documented comparison is narrower.
The audit reports source and journal metrics to one new owner-home JSON file.
It never starts a live sampler, refits models, changes services or deletes
files. An optional source-score phase evaluates existing V2 saved forecasts.

## Restoration and cleanup boundaries

The deployed `/experimental` source is not fully present in this research
checkout. Never replace the deployed `web/app.py` wholesale. The existing
private localhost8770 canary proxies the graph and serves all three views;
losing a Windows SSH tunnel can hide those pages while the VM stays running.
Check route status before assuming the site needs redeployment.

The audit includes a shallow inventory of owner-home project checkouts and
database sizes. No directory is declared safe to remove: dormant timers and
services may reference it. Review code references, retain the active collector,
selected model artifacts, actual decision journals and original V2 archive,
then prepare a specific cleanup list. No cleanup occurs in this change.

Do not start another live accuracy run until this audit is inspected. Use
historical data for model comparisons, preserve the original V2 control, and
report restock error, usable departure coverage, arrival success/known,
unknowns, actual waiting and postponed/missed opportunities together. Live
checks are for measured delivery/refresh behavior that history alone cannot
establish. No automatic model promotion follows from a small frozen score.

## Owner report inspected and scoring corrections, 2026-10-20

The owner supplied the complete saved JSON report, SHA256
`718ad8ae9024577dcc202cb829d36e53d28074d9b323b4401f820f13833d70f2`
(311111 bytes); its exact compressed copy is retained in the private repository.
It contains 7560 captured rows and all 24 target items have about 36.8–37.0
days between first and last stock observations. Span does not certify continuity.

Archived V2's matched reconstructed earliest UI advice was 65.72% stocked versus
62.89% leave-now on 2439 matched cases. These OLD results are not specialist
results, independent flights, or release qualification. The previously quoted
37.53% restock-window hits / 118.73 minute MAE reuse legacy stored labels.
Legacy matching is to completed NON-TINY cycles, not every physical restock;
projection groups are different populations. Extreme UK Xanax errors and sparse
flower archive samples require label/coverage investigation before ranking models.

### Concrete correction
V88 formerly checked only stock at the two poll endpoints. A transient sellout
and refill inside the bracket could incorrectly count as success; a brief stocked
interval between empty endpoints could incorrectly count as a known miss.
The checker now scans all intervening item deltas and poll providers. Threshold
excursions or provider switches that return to the original endpoint state are
UNKNOWN. Ordinary quantity changes on the same side of 30 remain scorable.
V88/V137 expose `poll-state-v2-continuous-bracket` to distinguish corrected results.
No corrected aggregate percentages have been computed on the owner's source yet.

### Independent physical event diagnostic
`research/physical_restock_identity.py` counts explicit 0->positive events,
including small refills. It freezes the first active item/hour forecast, uses
the explicitly saved Pn ordinal, never matches by nearest predicted timestamp,
preserves an observation-time bracket, and rejects ambiguous provider/coverage
or issue-straddling boundaries. This is a separate physical-ordinal diagnostic:
legacy normal-cycle Pn semantics are NOT certified or silently relabeled.
Optional `--with-physical-identity` on the existing saved-timeline audit records
the diagnostic without updating archive labels. It requires the owner source:
the sanitized runner snapshot lacks the archive/provider evidence needed here.

Local validation: 38 tests passed across V88, V115, V134, V137, saved-timeline
audit and physical identity, including sellout/refill, provider switch-and-return,
small refills, residual 1..29 stock, uncertain boundaries, frozen first issuance,
and query-only archive integration. No inference sweep, live recorder, service
change, routing change, or deletion performed. Future departure changes still
need historical validation with these corrected labels; no model improvement
or deployment claimed.

## Historical departure replay started, 2026-10-20

Reused immutable derived artifact f84ecf1dee518ab92984e2390d9826baf73afafbddb59eae7173b9ae7dd823ac.
Replayed all 37 five-minute visitor starts in its existing 09:00–12:00 UTC
Oct18 development window, each with a fixed eight-hour deadline and current
model/source reconfirmation. This adds no independent validation period.
Native policies for Camel, Nessie and Fox reached zero departures. Peony
front-of-winning-band:35 successes,2 unknown (16 distinct departure epochs),
mean wait99.84min. Camel front:17 successes,13 unknown,7 abstentions, only2
distinct departures, mean wait259.75min. Nessie front:37 abstentions.
Fox front:6 failures,31 abstentions,1 distinct departure; three native errors
disqualify a clean Fox comparison.

Specific bounded hypothesis: the template planner chooses a winning contiguous
near-max cluster by mean score/width and uses its center; this can discard an
earlier equally supported cluster. Research-only all_supported=True exposes the
UNION of existing near-max (.04 margin) template candidates to front/retention
policies, while preserving and parity-checking original native selection.
Only Nessie can enable this flag. No fit gate/score threshold relaxation,
new training labels, production route, raw stock export or gameplay changes.
Candidate scope is explicit in the report. Tests include earlier equal-score
cluster admission and lower-score earlier cluster rejection. 36 local checks
passed. A fixed one-item historical replay is being prepared, not a live canary.
