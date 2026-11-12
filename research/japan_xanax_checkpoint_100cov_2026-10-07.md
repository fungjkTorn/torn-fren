# Japan Xanax — 100% Valid-Coverage Research Checkpoint (2026-10-07)

Scope: Japan / Xanax only.

## Benchmark
- Coverage denominator = every valid/trustworthy opportunity after provider-bounce and collector-gap exclusions.
- No confidence gate may remove a valid opportunity from the benchmark.
- Primary metric = Xanax >=30 on landing at the earliest reachable stock opportunity.
- Secondary timing metrics = +10s, +1m, +3m.
- Invalid/malformed/collection-gap cases remain outside the denominator.

## Preserved results
V6 confidence frontier remains useful as evidence of predictable regimes:
- balanced gated subset: 55.7% exact, 65.7% +3m, 74.5% coverage
- high-confidence gated subset: 60.3% exact, 72.4% +3m, 61.7% coverage
These are NOT acceptable production coverage because valid opportunities are withheld.

## New 100%-coverage experiments

### Contextual expert router
Tested causal routing among 360 simple timer/lifetime experts using only fully resolved prior samples and observable width-regime context.
- Best exact: ~43.6%
- Best +3m at that point: ~50.0%
Result: reject. Context routing did not recover the hard cycles.

### Live censoring / sold-out-age update
Simulated updating the first future cooldown estimate as the item remained sold out approaching departure.
- Best static comparison in this family: 46.8% exact / 53.2% +3m
- Censor-conditioned versions were worse (~41.5% exact best)
Result: reject. Simple survival conditioning moves departure too late too often.

### Earliest-reachable P1/P2 routing
Checked whether the immediately next stock window (P1) could sometimes still be alive after the 149-minute Japan flight.
- Only 4 / 94 clean evaluation opportunities had P1 truly reachable.
- A causal classifier based on current width/peak/time generated too many false positives.
Result: do not route to P1 unless reachability can be predicted much more conservatively.

## Current conclusion
The remaining problem is not solved by abstention, simple context routing, or simple sold-out-age conditioning.
The V6 gated results prove some regimes are much easier, but the 100%-coverage model must learn more of the timer variation itself.

Next research should prioritize:
1. direct prediction of cooldown/timer variation rather than only a rolling center;
2. stronger causal distributional models for target-window start and width;
3. earliest-reachable target selection with calibrated reachability, not heuristic width gates;
4. probability calibration for landing, +10s, +1m, +3m;
5. preserve 100% valid-opportunity coverage throughout.
