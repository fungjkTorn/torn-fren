# Component hybrids and causal per-item selection — October 14, 2026

User objective: improve consistency and reliability by combining useful parts of different models, rather than replacing every item with the latest model.

## Fixed experiment

All physical timing uses positive→exactly0 depletion and0→positive restock. Buying eligibility remains>=30. Existing zero baseline and full quantity-rate model remain unchanged.

Four ablations in research/zero_component_hybrids.py:
1. recent64: empirical physical stocked, zero-wait and>=30 lifetimes, last64 completed observations.
2. current_rate: quantity/rate for current physical residual only; empirical64 future stock lifetimes, zero waits and buying windows.
3. physical_rate: quantity/rate for current and future physical lifetimes; empirical64 zero waits and buying windows.
4. fast_wait: current_rate plus last8 completed physical zero waits.

Each uses quarter, midpoint and current-quarter arrival placements, fixed before evaluation. Existing rate code and quantities are sampled inventory decline; provider freshness and exact purchase truth remain unverified. Initial timing constants are research choices, not per-item tuning.

## Online selector

research/causal_policy_selector.py selects among12 experts: zero baseline and full-rate midpoint/current-quarter, plus four hybrids' midpoint/current-quarter variants. No legacy<30 restock-clock model is eligible.

At each fixed hourly start, every expert simulates the same five-minute replanning, freshness and8h maximum-wait rules used by the evaluator. A departure freezes only when it can execute before the next issue and within180s source freshness. No outcome is requested before departure+flight+190s (10s grace plus180s poll bracket). An entire expert cohort must resolve or abstain before joining the last72 completed-cohort training buffer. Unknown outcomes remain unknown.

Baseline is zero_anchored_current_quarter. To switch, an expert needs>=24 mutually resolved prior cohorts, coverage of>=80% of baseline-resolved training cohorts, and net wins>=max(4,1.64*sqrt(discordant pairs)). Rank qualifying experts by net matched arrival gain minus0.05 per extra mean waiting hour. These are predeclared conservative research rules, NOT statistical certification; starts are correlated. No calibrated success probability is claimed. All choices and training comparisons are journaled.

The selector's own replanned performance is evaluated independently: switching can change its behavior relative to each constituent. It is never scored as an oracle that chooses after seeing the current trip outcome. Training begins at the replay start; initial warmup is included.

## Reliability reporting

Full24-item /37-policy replay. Frozen issue comparisons and same-hourly-start wins/losses, unknowns/pending/abstentions, departure coverage and wait remain separate. Added chronological START-day replanning slices for every policy, allowing inspection of bad days instead of only pooled success. Event restock/true-zero/below30 audits cover each static hybrid; selector does not yet report a coherent separate timing-accuracy family.

Future-data perturbation tests compare earlier frozen departures/events AND selector identity/training evidence. Additional tests cover delayed evidence, baseline fallback, replacement/expiry, separate physical/buying clocks and component isolation.

This run is exploratory historical walk-forward reconstruction. The model design followed inspection of overlapping historical experiments, so even the latest-day result is not a pristine holdout. Fresh forward evidence is required before calling a policy consistently reliable or releasing it. No automatic readiness whitelist, publisher assignment or production deployment is changed.
