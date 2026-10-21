# Shared stock-regime context — October14 evening,2026

Goal: test whether weak-item bad days are better explained by shared stock activity than by the target item's own recent history alone. Correlated activity is a predictive proxy, NOT evidence that another item's stock causes target demand.

## Fixed variants

zero_path_regime70 and zero_path_regime80 use the same completed historical trajectories,120s departure bins,8h maximum wait, physical zero phase and support/known-evidence rules as existing analog70/80. The existing recent/local path algorithms are unchanged. Shared-regime variants add a fixed equal distance contribution from four shared context coordinates; up to32 nearest paths, no hindsight-selected expert switching.

research/shared_stock_context.py reads only configured plushie histories in the same read-only SQLite transaction. The TARGET ITEM IS EXCLUDED from its own context (flowers/Xanax use all plushie peers). Require at least6 observed peer states, at most24h carried-forward changes, and no active collection gap.

Four coordinates:
- fraction of peers with physical positive stock, centered at0.5 and scaled4;
- fraction with>=30 buying stock, same scaling;
- mean fractional observed stock decline over600s, scaled4, at least3 eligible peers. Exclude zero starting quantity, any within-window top-up, provider change or known collection gap;
- median log(current completed positive-phase lifetime / median preceding64 same-item positive lifetimes) from peer phases ending in the last2h. Each ratio needs3 earlier completed same-item phases; pooled median needs6 closed peer phases. Sparse decline/lifetime evidence uses fixed neutral0, never a future-fit imputation.

Physical phases close only on positive->exactly0, not at<30. Lifetime ratios are computed when each phase closes using only preceding phases. Context queries use row/event timestamps<=query time. Future observations are inaccessible to earlier contexts even though offline arrays contain the whole snapshot. Provider-country freshness remains unverified: these are sampled stock activity, not certified purchases or live demand.

## Comparisons

Full mode42 policies; focused mode25, all24 items. New path_local_analog_comparisons compare regime70->analog70 and regime80->analog80 on the same hourly replanning starts, alongside existing zero baseline and fixed strong rate/hybrid references. Preserve coverage, unknown/pending/abstention outcomes, wait costs and daily slices. No global replacement of prior good candidates.

The failed automatic selector remains an unpromoted comparator; its expert roster does not include these new variants. No new policy enters publisher/readiness whitelists. Arrival-only models make no independent restock/depletion accuracy claim and support70/80 remains uncalibrated path agreement, not a success probability.

## Verification

Tests cover leave-one-item-out exclusion, future peer mutations, shorter dataset cutoff invariance, top-up/provider exclusions, missing/stale/gap abstention, and physical lifetime closing at zero rather than residual stock. Local variants are tested identical with/without shared context. Integrated future mutation alters every item's future stock; earlier departures and journal evidence must remain unchanged. Full/focused parity covers retained policy outcomes and all event audits.

Prior follow-up38662996880 succeeded and reproduced the previous highlighted local-path metrics on the same cutoff1792024856. No claim of new independent forward evidence. New regime accuracy is pending a separately pinned runner experiment. All results remain exploratory historical reconstruction on overlapping inspected history; fresh forward validation is required.
