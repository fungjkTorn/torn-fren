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
