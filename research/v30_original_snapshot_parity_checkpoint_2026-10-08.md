# V30 exact-source replay checkpoint (2026-10-08)

**Research only. No merge to main; no live deployment.**

The uploaded 126,734,336-byte archived SQLite file has SHA-256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`, exactly matching the original V21 source master. It holds 817,629 stock observations ending October 5, 2026. Tested read-only, not committed.

With period-specific history preparation, a local source-aligned compatibility replay reproduced **132/132 archived departures** on 12 deterministic historical holdout starts for each of 11 cohorts:

| Item | V19 | V20 | V21 |
|---|---:|---:|---:|
| Argentina Monkey Plushie | 12/12 | 12/12 | 12/12 |
| Argentina Tear Gas | 12/12 | 12/12 | 12/12 |
| China Peony | 12/12 | n/a | 12/12 |
| UK Red Fox Plushie | 12/12 | 12/12 | 12/12 |
| Totals | **48/48** | **36/36** | **48/48** |

All 11 cohorts also reproduced their saved cycle counts and historical feature point counts. Four corrections explain the earlier mismatches: V19's separate older cycle-preparation path; V20's original **300-second** replanning cadence (145 checks in 12 hours), previously mistaken for 900; historical coverage before poll-heartbeat tracking based on cross-item observation timestamps; and V21's observed quantity-at-arrival scoring override rather than V20's qualified-cycle windows.

The research branch updates the native V30 probe for the real V21 scoring override and fixes the old V24/V26/V30 cadence assumptions. Source-based CI passed after these corrections.

**Limitations:** 132/132 is source-aligned *compatibility-port* decision reproduction, not execution of original native planner modules against this uploaded archive. Original native modules are smoke-tested on synthetic SQLite in CI. V19/V20 saved masters do not embed source DB hashes. These archived decisions are not new independently observed profitable trips; native certification and untouched prospective validation remain required.

Audit and reproduction artifacts are available in the project chat as `V30_132_of_132_Same_Snapshot_Parity_Audit.json`, `V30_132_of_132_Same_Snapshot_Parity_Rows.csv`, and `Torn_Fren_V30_Same_Snapshot_Replay_Checkpoint.zip`. No database or API credentials committed.