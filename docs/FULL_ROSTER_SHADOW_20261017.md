# Full-roster shadow and per-item release

The existing localhost canary enables only 14 item recommendations (11 flowers,
Jaguar, Wolverine and Stingray). Its disabled items have not had live model
recommendations tested. The corrected shadow recorder always defaults to all 24
verified items, including Japan, UK and Canada Xanax and all ten plushies. The
original four unresolved names from the earlier 28-item list remain unresolved;
this does not claim coverage of 28 verified items.

Run `python -m research.japan_xanax.renewal_shadow record --source SOURCE
--journal NEW.sqlite --model-sha CHECKOUT_SHA --duration-seconds 28800` from the
pinned checkout. NumPy 1.26.4 is the only additional dependency. The source is
opened read-only. The journal must be a separate new file. Every five minutes
one atomic batch stores all 24 items across eight variants: paired recent cycles,
sequence continuation and quantity-adjusted continuation, each with peak and
60% scenario-agreement gates, plus leave-now and quantity-rate controls.
Scenario agreement is not a calibrated success probability. Insufficient cycles,
stale evidence and low support remain visible abstentions.

Exact depletion at quantity zero anchors restock. Quantity 30 is solely the
arrival availability threshold; arrival must retain availability through an
additional ten seconds. Broken collection/provider continuity and positive
top-ups reset the observed phase. No future row trains an issued prediction.

`score` reads the journal without changing it. Its primary sample is the first
observed issue per item, model and UTC hour. It reports successes, failures,
unknowns, pending and abstentions separately. These are correlated sampled stock
outcomes, not actual player flights. Future frozen departures have not been
reconfirmed, so this diagnostic alone cannot certify actionable travel advice.

The separate historical benchmark uses fixed five-minute starts, an eight-hour
maximum wait, causal five-minute replanning and a 15-second publication floor.
All eight variants use the same starts within an item. Three chronological daily
slices, coverage, unknown outcomes and paired comparisons remain in the report.
The first exploratory comparison runs Japan Xanax first, then seven weak
plushies, then the remaining roster. A sealed sanitized database copy fixes the
truth cutoff for the entire run. Historical selection needs a subsequent frozen
forward comparison; selecting on the evaluation window is not validation.

No command changes website assignments, starts game actions or promotes models.
Keep the current 14-item canary and its journal running alongside this process.
A release decision is per item: select and freeze a candidate, verify its accuracy,
coverage, unknown rate, wait time and publication/departure behavior on an unseen
window, then enable that item after integration checks. Strong items need not wait
for Japan Xanax, and a disabled website item must remain included in shadow tests.

This script records bounded eight-hour sessions; nohup survives SSH disconnects
and laptop sleep, but it is not a VM reboot service. The owner must start the new
process on the VM because the research runner cannot read the live collector.

## Comparable scorecards

`python -m research.shadow_scorecard --source SOURCE --journal EXISTING.sqlite
--expected-model-sha RECORDED_SHA` provides a read-only analysis of an existing
journal without restarting its recorder. The expected SHA identifies the recorded
model, independently of the newer reporting code. Every model uses the first
item/hour issue; missing model records remain missing, never substituted with a
later and potentially more favorable issue. Reports show proposal coverage,
known success, pending, unknown, abstentions, missing records, average waiting,
status/reason counts and paired wins/losses versus both controls. Immediate plans
and frozen future plans are separate. Neither table is a reconfirmed flight test.
