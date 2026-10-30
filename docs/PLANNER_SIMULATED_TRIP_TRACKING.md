# Planner simulated-trip reporting correction

The old headline metric grouped forecasts by matched continuous availability windows and withheld the rate when historical revisions could not be matched. It could display 2/2 or a collecting message despite many saved forecasts. Forecast revisions, restocks and independent simulated trips are different counts; the correction does not turn every refresh into a trip.

## Agreed policy

`RECOMMENDED_DEPARTURE_FREEZE_V5` reconstructs the published recommendation stream chronologically. The currently recommended exact departure may change before departure; revisions, postponements, withdrawals and target changes are recorded separately. At that recommended departure, the trip freezes with its original departure, arrival and selected forecast. Later forecasts and outcomes cannot move it or replace a failed result. Repeated leave-now advice for the same target is not another trip. New qualified current-stock restocks, including surplus-to-base resets, can create a new target while availability remains continuous.

A due departure is materialized when the next publication is processed, preserving the same ordering in backfill and incremental operation. Stale recommendations do not silently become trips. No actual player departure is required.

The last ten trips are ordered by frozen departure. Stock strictly greater than 30 at calculated arrival is success; 0 and 1–30 are failures, with separate failure classes. Polls must bracket arrival within 180 seconds, with no collection gap and a fresh country report at arrival. A threshold change inside that bracket is unknown. A provider change alone does not invalidate agreeing availability observations. A missing restock identity does not invalidate otherwise sufficient arrival evidence. Pending lasts until arrival plus the observation maturity allowance. The percentage uses known results among those ten; unknown and pending counts remain visible.

## Historical restock signatures

Profiles use available collector history strictly before tracking began, without a 48-hour training restriction. They are fixed and versioned, with observed bounds and sample counts exposed. A deterministic log-quantity mixture separates a compact normal-refill population from a distinct small or broadly scattered lower population. It does not split an ordinary variable quantity band merely because quantities vary. Fewer than five usable refill samples or an ambiguous band reaching 30 or below leaves the signature unconfirmed.

Qualified observations are zero-to-normal refills, in-stock increases whose increment and resulting quantity fit the normal band, and surplus-to-base resets. A reset base must have at least three prior clean examples above the learned normal maximum dropping to that recurring base. Same-provider consecutive observations are required and known collection gaps excluded. Quantities and timing are observations, not proof of a game event; polling can miss the actual initial quantity. A value inside the range is supporting evidence, not permission to classify every positive stock change as a refill. No item quantities are hardcoded.

Restock identity and unconfirmed test links are separate diagnostics. Unconfirmed links are not automatically failures or extra successful trips. When only an availability opening is known, it can identify a continuing recommendation episode without being promoted to a qualified restock.

## Migration and deployment

The raw issues, old outcomes and old target links remain intact. New append-only tables store profiles, frozen trips, outcomes, changes and restock events. Only the processing cursor is mutable. Repeating reconciliation must not create duplicate trips or change frozen timestamps.

`deploy/Repair_Planner_Evidence.ps1` fetches the reviewed release branch and packages the reporting files through Git. No GitHub Actions, package installation, model changes, collector changes or raw-data deletion are involved. Its default mode stages an overlay and reconciles a private SQLite backup against the VM's full collector history. The preview reports the active ten model/item pairs, learned ranges, frozen-trip counts and results. It does not edit the live ledger, service or UI.

`-Apply` also runs that preview, pauses the publisher timer, backs up the unit/UI/snapshot/ledger, initializes the derived evidence, and installs an overlay for reporting only. It keeps the original immutable model directory and native scheduling worker. It checks that a newer ten-item publication uses the same model SHA and the new evidence policy, then resumes the timer. Failed publication verification restores the previous unit, UI and snapshot; original evidence and new derived append-only records are retained.

The deployment requires the SSH key on the user's Windows machine. GitHub access permits preparing and pushing the fix but does not supply VM SSH credentials. Local validation cannot establish the current live-ten counts because the uploaded research database contains seven different items and the current production forecast ledger has not been uploaded.

## Validation

Regression tests cover chronological revision/freeze behavior, failed-target retry suppression, withdrawals and expiration, normal variable bands, small sellbacks, reset signatures, arrival evidence independent of restock boundaries, provider changes, threshold handling, idempotency, immutable raw and frozen evidence, private preview of the active ten only, and deployment rollback. Desktop and mobile browser fixtures check the updated status text and detail dialog. Real research-history checks validate quantity grouping mechanics only; they are not a new accuracy claim for the current live ten.

## Live-ledger audit and V4 correction (October 29)

The first deployment report confirmed V3 applied, but the subsequent public-feed audit found repeated Ceibo trips with the identical `restock:1793225633` identity. Its 117 reconstructed trips across the cohort must not be interpreted as 117 independent restocks or accepted accuracy evidence. V3 could discard a completed identity after the predicted window expired and a different target had become the newest completed trip. A later extended current-stock forecast could therefore create another test of the same restock. V3 also used publication-time availability as the origin for a forecast calculated at an earlier source cutoff, shifting future ordinals when a restock occurred during inference/publication.

V4 retains compact completed identities independently of window expiry and rechecks already tested targets at freeze. It chooses the forecast origin using the issue-time source cutoff. Later observed openings resolve target identity separately from the frozen forecast geometry. A versioned reconstruction preserves V3 records as an audit trail; it does not delete or overwrite them. Reports expose the duplicate-identity audit and deployment refuses to apply a preview with duplicate target groups or a missing audit. The installer supports upgrading the exact known V3 overlay while preserving the original native model directory.

New regressions reproduce forgotten-target re-entry after window expiry and a restock arriving between issue and publication. The existing seven-item forecast archive is a mechanics check, not a substitute for the current VM ledger preview. Heather's unusually broad learned quantity band (407–9,999 in the VM report) still merits a separate historical restock-signature review; V4 does not silently retune that band.

## V4 VM preview blocked (October 29, 7:53 PM ET)

The second report, `torn-fren-planner-evidence-20261029T235346Z.json`, returned `EVIDENCE_REPAIR_BLOCKED`. The private reconstruction still found duplicate observed target identities across all ten items. The apply guard returned before backup, service stop, live-ledger reconciliation or unit/UI replacement. V3 remained active. The passing sampled research checks did not establish correctness for the real publication stream; another deployment must not be requested on that evidence alone.

`deploy/Export_Planner_Evidence.ps1` collects an SQLite backup of the real planner ledger plus a sanitized export of up to 120 days of collector stock, polls, gaps and country clocks for the actual ten items. It downloads a private ZIP to the user's Desktop. It runs no model inference and changes no live service, database or deployment. The ledger includes preserved original forecasts and prior derived versions for reproducing the blocked audit. The existing stock export limits and integrity checks remain in force. This bundle is the required input for validating the next correction locally before another apply attempt.

## V5 verified against the actual production export

The uploaded diagnostic bundle contains 17,280 original item forecast rows from October 28, 12:57:01 PM ET through October 29, about 7:58 PM ET, with stock observations through 7:59:13 PM ET. V4's Ceibo duplicate was reproduced before changing the implementation. The source snapshot heartbeat for the problematic forecast was 1793225583, while the real opening was 1793225633 and the forecast issue clock was 1793225660. Although the opening preceded the issue clock, the saved model input still reported zero stock. Using issue time as the origin incorrectly shifted the future ordinal.

V5 derives the input cutoff from the saved source heartbeat and the item's saved last quantity-change timestamp, capped at issue time. It resolves both earlier and newly published advice against the same available observations before comparing target identities; the prior implementation resolved only the earlier side. Known observed identities compare symmetrically across future/current recommendation forms. Predicted window expiry never discards completed identities. All original V3 records remain preserved under their original policy.

Heather's pre-tracking history also exposed a quantity-grouping defect: isolating two tiny refills caused the first mixture pass to stop with a separate small-refill tail still inside the normal band. The same guarded split now repeats until stable. Heather's observed band is 9,668–9,999, with 30 small samples excluded, rather than 407–9,999 with only two excluded. Other live-ten learned bands are unchanged. The normal variable-band regression still preserves 1,000–2,500. Models and scheduling logic are unchanged.

The production reconstruction contains 60 frozen simulated trips and zero duplicate target groups across all ten items. Four chronological checkpoint reconciliations equal the batch result exactly; repeating reconciliation produces no changed results or new trips. Every frozen departure and arrival matches an original published recommendation exactly, and all original evidence table fingerprints are preserved. No model inference was run. The aggregate result is checked in as `docs/PLANNER_TRACKING_VALIDATION_20261029.json`. Reproduce it with:

```bash
PYTHONPATH=. python research/validate_planner_evidence.py --ledger /path/to/forecasts.sqlite --stock /path/to/stock_history.sqlite --checkpoint 1793206900 --checkpoint 1793225700 --checkpoint 1793281940
```

Small denominators remain possible and correct. Most flower items have only a few qualified restocks during this roughly 31-hour record; revisions do not manufacture extra independent trips. Crocus has one success among four known frozen trips in this export. This is a small-sample beta result, not a reason to substitute later successful revisions or a new accuracy claim from historical model fitting.

Deployment retains the duplicate guard in preview, final reconciliation, and new-publication verification. Runtime reporting also withholds the percentage if a duplicate identity appears, while the UI labels the result as under review. The upgrade and rollback checks retain the exact native model working directory. The VM still needs the reviewed V5 overlay applied using its existing Windows helper; GitHub preparation alone does not apply it.
