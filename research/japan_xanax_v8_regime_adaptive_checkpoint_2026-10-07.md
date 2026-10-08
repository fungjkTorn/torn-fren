# Japan Xanax V8 regime-adaptive research checkpoint — 2026-10-07

Scope: Japan Xanax only. Fresh snapshot:
- SHA256: d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583
- Japan Xanax rows: 8,609
- old frozen cutoff: 1791241426
- strict post-cutoff P2 opportunities: 21

## Frozen V7 prospective result
Using the executable V7 observation-lag implementation without retraining:
- exact: 7/21 = 33.3%
- +10s: 8/21 = 38.1%
- +1m: 8/21 = 38.1%
- +3m: 10/21 = 47.6%

This confirms the prior development result did not generalize cleanly into the newest regime.

## Regime finding
Recent stock lifetimes shortened sharply while cooldown timing remained much more stable. A causal regime indicator based on recent reconstructed width versus the preceding historical window falls strongly below 1.0 across most new opportunities.

## V8 direct rolling Ridge tournament
Features are available causally at the decision anchor and include:
- current reconstructed lifetime
- recent 3/5/10/20-cycle reconstructed lifetimes
- recent 3/5/10/20-cycle cooldowns
- most recent cooldowns and prior lifetime

Training labels are restricted to samples whose target windows fully resolved before the current decision anchor.

Promising configuration:
- direct prediction of target offset
- timing-only features
- last 60 resolved samples
- standardized Ridge, alpha=1

Results:
- pre-cutoff 96 opportunities: exact 42.7%, +10s 43.8%, +1m 47.9%, +3m 51.0%
- all 21 post-cutoff: exact 14/21 = 66.7%, +10s 66.7%, +1m 66.7%, +3m 16/21 = 76.2%
- first 10 post-cutoff: exact 70.0%, +3m 80.0%
- later 11 post-cutoff: exact 7/11 = 63.6%, +3m 8/11 = 72.7%

A nearby alpha=3 version gave:
- all 21 post-cutoff exact 61.9%, +1m 66.7%, +3m 76.2%
- later 11 exact 54.5%, +1m 63.6%, +3m 72.7%

## Residual-Ridge challenger
A model predicting residual correction on top of the V7 mechanics was also tested. Best notable run:
- timing features
- last 60 resolved samples
- Ridge alpha=1
- full residual correction

Results:
- all 21 post-cutoff exact 61.9%, +3m 71.4%
- later 11 exact 63.6%, +3m 72.7%

This improves substantially over frozen V7 but is slightly behind the direct rolling Ridge on the full new period.

## Regime-switch ensemble
A simple causal switch was tested:
- keep V7 in ordinary lifetime regimes
- switch to the rolling Ridge when recent 5-cycle reconstructed lifetime mean is <90% of the preceding historical mean

With Ridge alpha=1:
- pre-cutoff exact 49.0%, +3m 57.3%
- all 21 post-cutoff exact 66.7%, +1m 66.7%, +3m 76.2%
- later 11 exact 63.6%, +3m 72.7%

This preserves more old-regime V7 behavior while adapting to the new short-lifetime regime.

## Interpretation
The strongest current V8 signal is not a fixed time correction. The error direction changes through the new period, so a static +N-minute offset is inappropriate. Rolling timing-state regression adapts materially better.

The 21 post-cutoff opportunities have now been inspected and are no longer a pristine untouched holdout. Treat the later-11 split only as chronological development evidence, not a final external validation.

## Next tests
1. blocked walk-forward stability across several historical regimes;
2. feature ablation to find the smallest stable timing feature set;
3. robust/nonlinear challengers where computationally practical;
4. future-cycle shadow validation of the frozen V8 candidate;
5. do not expose calibrated probabilities until separately validated.
