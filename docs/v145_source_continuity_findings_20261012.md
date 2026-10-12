# V145 — usable observed phases across benign provider switches

## User rule and error correction

Agreed: A completed item-stock phase is usable when both its start and ending threshold transitions were actually observed. A provider switch in the middle that leaves stock>=30 (or stock<30) unchanged must NOT erase a known onset or clean completed duration. Preserve genuinely ambiguous transitions at the exact source boundary and recorded collection gaps as unverified.

Earlier statement that items with zero V128 arrival results had no good stock history was misleading. Uploaded user VM V144 audit showed **355 clean below30-to-atleast30 transitions**, **449 clean positive quantity jumps**, **1,516 provider switches**, and **3,040 CURRENT_PHASE_ONSET_UNKNOWN abstentions** out of **5,856 issued item-five-minute ticks** across 24 items. These are counts from stock-change collector snapshots, not certified actual in-game replenishment events.

Representative item diagnoses (24h):

| Item | Observed clean 30-unit crossings | Onset unknown | Other issues | Issued departure ticks |
|---|---:|---:|---|---:|
| Japan Xanax | 11 | 152 | 92 score-gated, NO_SUPPORTED_DEPARTURE | 0 |
| Peony | 5 | 176 | 68 INSUFFICIENT_COMPLETED_CYCLES | 0 |
| Edelweiss | 4 | 153 | 91 INSUFFICIENT_COMPLETED_CYCLES | 0 |
| UK Xanax | 4 | 160 | 84 INSUFFICIENT_COMPLETED_CYCLES | 0 |
| Nessie Plushie | 30 | 72 | — | 172 |
| Red Fox Plushie | 34 | 61 | — | 183 |

Every item experienced dozens of provider switches in the day, often 2–3 per hour; some flowers replenish only a few times daily. V128 fast_phases() in research/v128_full24_earliest_shadow.py directly resets phase_onset to None on any source change. That policy discards sound starts when quantity phase stays consistent through a switch. The newer code fixes that specific root cause.

## Implemented research-only challenger

`research/v145_provider_continuous_phases.py` implements `provider_continuous_phases(observations, *, asof, gaps=())` and a read-only `compare_phase_eligibility` function. It preserves observed HIGH/LOW phase starts and completed durations across provider switches that do not change the >=30 classification. The start and end still have to be direct within-provider observed threshold crossings. Source switches that coincide with a threshold disagreement, timestamp reversal or a collector gap are not treated as certified transitions.

Added tests/test_v145_provider_continuous_phases.py that demonstrates a genuinely observed stock period which V128 threw away, old/new parity without switches, rejection of cross-provider changes and gaps, recovery of sufficient completed phases to feed the UNCHANGED V128 arrival scoring curve, and no lookahead. Wired to the V85 GitHub CI workflow.

**NOT installed on VM or promoted.** This is a provider-continuity fix in an isolated research branch; it does not assert improved real-world departure success. We must compare V128 strict phase eligibility against V145 over the same as-issued VM observations and run forward validation before any canary.

## Captured website source reconciliation

User provided full current deployed source copies to this chat. Verified app.py SHA256 86e84488655ab8e83fc86965c846f13ff17da27b0f8edbeac3bf5f3e583a2657 and experimental.html SHA256 a9a47e0fe7d9b8139322873f27b31209862a8805296a9e5070ce7ff599069aa7 (matches prior V142 VM inspection). Detailed graph index.html SHA256 092215c3fddc45510c4c68d2f5e82895ff7692e2b75f7ba15129784e008a3b2b. Existing deployed app.py implements /experimental and the V41 API, while GitHub research web/app.py lacks those routes. Production may have V40_LIGHT_GRAPH enabled, pausing full expensive V2 by default; the frontend offers bounded backup. Preserve both existing modes. Future changes must be additive/reconciled.

## Next tests

1. Compare 24-item strict-V128 vs phase-continuous-V145 eligibility *on the same historical as-issued data*; count recovered real observed phases per item, not simply newly printed suggestions.
2. For items with newly complete phases, rerun the same Monte Carlo policy and calculate matched observed >=30-at-arrival proxy, abstention rate, time-to-leave, long-wait reasonableness, and forecast jitter. Do not drop unresolved arrival observations.
3. Treat Japan Xanax's separate 92 score-gate abstentions separately from its 152 unknown-onset abstentions; likewise assess Peony/Edelweiss/UK Xanax history sufficiency only after phase extraction improvement.
4. Merge into the existing actual deployed experimental/V2 source only after source diff, tests, rollback and approval; no live changes now.
