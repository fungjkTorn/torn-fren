# Planner simulated-trip reporting correction

The old headline metric grouped forecasts by matched continuous availability windows and withheld the rate when historical revisions could not be matched. It could display 2/2 or a collecting message despite many saved forecasts. Forecast revisions, restocks and independent simulated trips are different counts; the correction does not turn every refresh into a trip.

## Agreed policy

`RECOMMENDED_DEPARTURE_FREEZE_V3` reconstructs the published recommendation stream chronologically. The currently recommended exact departure may change before departure; revisions, postponements, withdrawals and target changes are recorded separately. At that recommended departure, the trip freezes with its original departure, arrival and selected forecast. Later forecasts and outcomes cannot move it or replace a failed result. Repeated leave-now advice for the same target is not another trip. New qualified current-stock restocks, including surplus-to-base resets, can create a new target while availability remains continuous.

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
