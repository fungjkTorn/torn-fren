# Torn-FREN Checkpoint 8 — sanitized publisher failure analysis (2026-11-12)

**Evidence time:** 2026-11-12 15:46:32 UTC; user-supplied `TORNFREN_PUBLISHER_FAILURE_DIAGNOSTIC_REDACTED_V1`. All observed checks read-only. No VM service was restarted or modified.

## Snapshot — separate actual failure from interpretation

| Service | State / exit | Verified command information | Journal summary in last 500 entries |
| --- | --- | --- | --- |
| `torn-fren-final-pair-beta.service` | failed / exit 1 at 15:45:37 UTC | uses external `final_pair_entry.py`; bounded reader drop-in present; no private Japan flag | 11 traceback lines, 12 broad `provider_unavailable` pattern matches; zero named exception classes |
| `torn-fren-japan-private.service` | failed / exit 1 at 15:46:10 UTC | directly runs `services.final_pair_live` with `--private-japan` | 26 traceback lines, 54 ValueError pattern matches |
| `torn-fren-next-six-beta.service` | last run successful | versioned source | no classified errors |
| `torn-fren-first-ten-beta.service` | activating at capture | versioned source | no classified errors |

**Important:** these counts represent matches to individual journal message lines, not necessarily distinct failures. The current `provider_unavailable` classifier matches the broad word `provider`, which may occur in traceback source code even when the underlying failure is different. This is not proof of a Torn API outage. The exact ValueError text was withheld; its cause has not been verified.

## Recovered final-pair wrapper

- `/usr/local/lib/torn-fren-publisher-recovery/final_pair_entry.py` was readable and SHA-256 hashed as `775e3f04b24ce18ce2ab7cdbf1ad71001fcdab01a08d1e49d6f8dc21b487e2c7`.
- The wrapper mentions `200000` but the sanitized diagnostic explicitly could **not verify effective override**. The deployment installer constructs a wrapper that checks an exact source fingerprint, changes `reader.MAX_ITEM_ROWS` from 50,000 to 200,000 in-memory, and then invokes `services.final_pair_live.main`.
- No model, health, input freshness, or wrapper assertion was validated from this file alone. Do not re-run the historical multi-purpose `Repair-TornFrenPublishers.py` script.

## Potential causal gate in reviewed code (hypothesis; not yet a diagnosis)

`services.first_release_source.refresh_tail` rejects an inference export if its last successful poll-heartbeat exceeds a **600-second** age, if the read-only collector latest successful poll heartbeat is older than **90 seconds**, or if required country clocks do not exist. These explicit ValueErrors could explain a failing cohort, but **the provided diagnostic does not contain heartbeat age or exception messages**. Both snapshots may have expired after earlier failures; the Japanese service is correctly flagged for private mode and could be failing for another reason.

Next step is a single *read-only* source-health and fixed-whitelist exception-reason report: last heartbeat ages (not DB rows/contents), recent publication freshness, and classified exception subtypes. Never export raw journal messages, raw ExecStart, secrets, stock-history rows, private evidence or arbitrary filenames.

## State of repository integration

- Public source PR #17 and isolated main-integration PR #18 are still drafts; main and local VS Code checkout remain untouched.
- 146 integration regression tests and all nine compatibility workflows passed on `0f83267e6b91900a97d37c7125e38d049dc575eb` before this diagnostic.
- Legacy V85 systemd service/timer removal **was completed and verified** in a separate operator step; its historical source and data were retained. Do not confuse it with these two currently enabled failing services.

**No repair or merge approved on diagnostic categories alone.**
