# TORN-FREN evidence synthesis — 2026-10-22

Research only. No production promotion is authorized by this document.

## Evidence layers now available

1. **Original specialist holdouts**
   - Monkey checkpoint4: 211/283 = 74.56%, 100% legacy holdout coverage.
   - Chamois checkpoint4: 208/283 = 73.50%, 100% legacy holdout coverage.
   - These are original specialist flight-selector holdouts, not directly comparable physical-restock forecasts.

2. **All24 frozen forward capture (Oct 19/20)**
   - 7,560 plan rows, 24 items, 9 modes.
   - Evidence-routed V164 primary portfolio: 44/47 known arrivals = 93.62%.
   - Earliest-reachable-restock scoring: 30/30 scored cases landed in the first reachable observed stock window.
   - Small sample; this is frozen shadow evidence, not actual player flights.

3. **30-day generic physical-restock tournament**
   - Useful as parameter / clock evidence, NOT as a replacement for item specialists.
   - At zero landing buffer, phase_empirical and phase_recursive_ridge average about
     67.4% restock timing within 5 minutes and 86.2% within 10 minutes, with ~5.9 min mean absolute timing error.
   - interval_median / interval_ridge are materially weaker timing clocks.
   - Weighted zero-buffer bounded policies: ~91.3% arrival success and ~89.2% future-restock arrival success, but only ~26.8% departure coverage.
   - Weighted zero-buffer expected policies: ~74.4% arrival success and ~68.0% future-restock arrival success, with ~70.4% coverage.
   - Across generic policies, later landing buffers improve future-restock arrival reliability:
     0s ~75.8%, +60s ~79.0%, +180s ~84.1%, +300s ~85.9%, +600s ~88.7%.
     This is a hypothesis for specialist/routed plans, not permission to apply the delay globally.

## Interpretation

The system should not select one generic restock model for all 24 items.

Instead:
- keep strong item specialists as incumbents;
- use generic physical clocks as event-timing/context features and challengers;
- expose at least two confidence concepts:
  - **expected / broader coverage** departure;
  - **bounded / conservative** departure;
- evaluate a landing safety buffer directly on frozen specialist/routed plans before adding it to routing;
- score whether a recommendation hits the **earliest actually reachable restock**, not merely whether stock exists at arrival.

## Immediate research action

V165 directly sweeps +0/+60/+180/+300/+600 seconds on the genuinely recorded frozen
primary/challenger/specialist plans from the all24 journal. It preserves the issue snapshot
and changes only the simulated departure/arrival time for scoring.

Promotion remains disabled. Japan Xanax remains NOT READY.
