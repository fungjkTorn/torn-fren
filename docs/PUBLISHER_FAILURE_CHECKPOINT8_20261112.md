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


## Additional static source-fingerprint discrepancy (pending live verification)

The current VM wrapper's **SHA-256** `775e3f04b24ce18ce2ab7cdbf1ad71001fcdab01a08d1e49d6f8dc21b487e2c7` exactly matches the *generated* wrapper body in the archived `Repair-TornFrenPublishers.py` source. This wrapper checks the AST hash of `research.v128_full24_earliest_shadow._read_item` before setting `reader.MAX_ITEM_ROWS=200000` and calling the final-pair publisher.

- Expected AST hash embedded in installed wrapper: `732b5802ccb2ddffa61088590393b78a30dc36d091115cbed80a8baf843128ac`.
- Actual AST hash calculated **offline from the captured November 11 versioned final-pair release source**: `a06b3b5b21c3d727e8d99d652110b0bf509795a9dd3fb2a7de7e1139622d77d7`.
- Public review source Git blob `research/v128_full24_earliest_shadow.py` is byte-identical to that captured release file, Git SHA `52c93b57e5959afeff093d55df1acd89e3e446bf`.

**Interpretation:** There is a reproducible incompatibility between the archived/source-captured reader and the installed wrapper's expected fingerprint. **This does not yet prove it causes the current VM failure**, because the live reader file may have changed since capture and the journal reason summary contains no precise assertion traceback. The correct next step is to compute the on-VM reader's AST fingerprint (read-only) and compare it with the wrapper's embedded expected hash. If they differ, do not simply remove the assertion: construct a new guarded wrapper for the verified source revision with a backup, stage-test it, and verify model health and snapshot freshness.

A single read-only root-cause script was prepared to report the current reader/wrapper fingerprints, input-heartbeat age, latest snapshot metadata and exact **whitelisted** error categories without exporting source content, full journal messages, raw commands, databases, keys or environment values. No VM repair has been executed.
