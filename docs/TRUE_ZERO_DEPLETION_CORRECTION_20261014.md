# Physical depletion is zero — correction to the research clock

User correction, October14: true depletion means **quantity=0**. A
depletion-to-restock predictor must not start its empty-stock clock while
1–29 units remain. The target of30 units at arrival is separate.

The previous scorecard's columns labeled depletion actually measured
>=30 to<30 availability losses. They are relabeled in that saved report and
must not be cited as physical-depletion accuracy. The old phase models also
used below30 LOW phases; they remain explicit legacy availability baselines
in research comparisons, not corrected physical-clock models.

`research/true_zero_cycles.py` adds an independent zero-anchored family:

- Positive stock, including1, remains NONZERO. Only an observed positive->0
  crossing starts the EMPTY interval;0->positive ends it at replenishment.
- Quantity30 availability and its projected ending clock are trained
  separately. A current1–29 balance never supports a30-unit arrival window.
- Future physical-zero and below30 timestamps are separate fields. The shared
  V166 adapter preserves the explicit zero timestamp and never infers it from
  the availability cutoff. Repeated future restocks advance from physical
  zero plus observed empty duration.
- Zero onset records an observed bracket (after last positive, by first zero),
  rather than claiming the exact game event second is known from sampled data.
- Provider contradictions, gaps, initial unknown phase onset and insufficient
  target-availability history prevent unsupported anchoring/recommendations.
- Current and future model features only use completed history at issuance.

The historical replay now scores physical positive->0 depletion separately
from >=30-><30 availability loss, and scores true0->positive replenishments.
Legacy families with no explicit zero prediction have null/unsupported
physical-depletion accuracy, not a manufactured0% or a below30 proxy.
The changed truth protocol means old timing percentages are not directly
comparable. Arrival outcomes still require observed quantity>=30, with pending
and unknown separate. A zero clock is not a new accuracy claim.

Regression cases include100->20->1->0, repeated zero samples, true restock at
0->10 before later>=30 availability, separate predicted availability/zero
endpoints, provider/gap rejection and no future observation leakage.

This is isolated research source. Corrected true-zero numerical results require
the private replay after public CI passes. No website, collector, or deployed
incumbent has been changed.

The batch publisher defaults to true_zero_all. Legacy availability-clock
assignments require an explicit research-only opt-in; they are retained solely
for comparison. This source default does not change any existing live service.
