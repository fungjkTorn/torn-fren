# Additional paired Japan handoff shadow

Keep the existing24-item/eight-model recorder running. This separate bounded
Japan comparison tests the new180-second agreeing-zero handoff candidate against
the unchanged sequence reference, rate and leave-now controls on the exact same
issued observations. It does not replace the full roster or change recommendations.

Historical development: coverage54.05% ->76.27%, known success83.73% ->78.60%,
mean waiting201.3 ->192.6min; zero unknowns. New candidate518/659 known successes,
21 distinct departure epochs (11 successful,10 failed), not independent flights.
Daily success99.58%,74.16%,59.62%; daily coverage82.29%,72.57%,73.96%. This is
not a validated release winner. The600-second and longer handoffs regress badly
and are excluded from the paired live candidate. Default model training remains
strict and unchanged. Provider-specific clock verification remains outstanding.

Run `python -m research.japan_xanax.handoff_shadow record --source SOURCE
--journal NEW.sqlite --model-sha PIN --duration-seconds 28800` from its pinned
checkout. Existing NumPy canary venv is sufficient. Read-only source, new private
journal, five-minute atomic batches,15-second publication floor, <=30sec build,
source freshness at publication <=180sec. Exact-zero depletion remains required.
The journal and existing full-roster process are separate. Nohup survives SSH/laptop
disconnect but not VM reboot. Recording is bounded eight hours, not a permanent
production service.

`score --source SOURCE --journal NEW.sqlite --model-sha PIN` produces the standard
first-item/hour frozen diagnostic plus a separately labelled replay of recorded
five-minute replanning advice. Original source age is enforced at simulated
departure; forecast outcomes are never used to select departures. Incomplete
recorded eight-hour follow-up remains pending even if later truth is mature.
Only successfully recorded issue starts are included; capture outages are logged.
No actual player flights or calibrated probabilities. No automatic promotion.

The reporter validates journal model identity and preserves both files. Four paired
recorder tests cover genuine handoff plan restoration, atomic publication-floor
records, stale-publication rejection, and incomplete-follow-up scoring. The four
underlying handoff tests cover true-zero provenance, unchanged training identity,
provider disagreement, gaps, and no future-poll approval.

## VM legacy-stage startup correction

The initial31fd6ddd run failed before saving predictions because issued_plans
imported the quantity helper before source_data pinned the checkout. The helper's
legacy VM staging logic redirected research.__path__ to v160_stage, which lacks
continuous_departure_replay. This was an import-order bug, not a missing GitHub
file. The corrected function pins/loads source_data before helper imports.

A fresh-subprocess regression reproduces the exact old ModuleNotFoundError using
a legacy-stage mirror lacking the newer replay file. The correction passes with
that environment. Explicitly setting TORNFREN_REPLAY_WORK to the current checkout
and TORNFREN_REPLAY_PINNED_RESEARCH to its research directory before starting Python
also recovers the existing31fd6ddd pin without changing model source or results.
Both launch routes are tested with a real read-only collector fixture and checked
for unchanged source bytes. Add a foreground issued_plans preflight before nohup
to catch import/source errors before printing a recorder PID. Five paired tests pass.
Do not reuse/overwrite the failed run's journal; use a new timestamped journal.
