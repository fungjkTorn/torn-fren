# Fixed forward-period evaluation — October14 evening,2026

This capability freezes model source and a24h ISSUE window before future data arrive, then scores the SAME issues after their outcomes mature. It is a predeclared temporal reconstruction, not actual live issuance, purchases, or a blinded holdout. Exploratory research can continue; the validation source/window must not be silently changed to favor later winners.

New replay argument --issue-end separates issue-window end from the later snapshot truth cutoff. Default behavior is unchanged. As-of forecast data always stay<=each issue, including shared-stock context and completed-path training. Frozen-issue scores cover only the declared24h window.

Hourly replanning cohorts START only inside that window, but their plans may continue for up to8h afterward. The evaluator's start_before bound prevents those extra plans from creating additional cohorts. Later source evidence matures arrivals; absence of future plans must not turn an unfinished wait into an artificial abstention. Compact post_window_replanning_plans are retained in private report for audit.

A regression test verifies that extending truth past a fixed end preserves all earlier issue IDs, departures, event forecasts and path/selector evidence, while pending outcomes can mature. It verifies exactly24 hourly starts/item despite appended post-window replanning. Full/focused parity and future mutation checks remain.

Private protocol requests/forward_window_v1.json will pin source, future start/end and earliest truth-ready epoch. Validation runs only once a sanitized snapshot covers END+8h maximum wait+longest flight+190s evidence lag+300s issue allowance. All outputs stay in private artifacts; no raw stock DB. A done marker is written only AFTER successful artifact upload. Periodic exploratory replays continue independently.

Primary comparisons are regime70 vs local analog70 and regime80 vs local analog80, per item, with coverage, waiting, unknown/pending and same-start wins/losses. The model source is pinned before the period; any later design changes require a separately named future protocol. A single24h window has few independent starts per item and is a first forward check, not statistical certification or a90% guarantee.

No production route, model publisher assignment or live collector access changes.
