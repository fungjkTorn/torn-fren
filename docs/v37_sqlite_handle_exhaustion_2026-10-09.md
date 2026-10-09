# V37 SQLite handle exhaustion — production hotfix candidate (NOT DEPLOYED)

**2026-10-09, Torn Fren / OCI 2 OCPU, 12 GB.**

## Direct production evidence

The user measured poller PID 2492 through /proc while the service
was `active` but the verified stock heartbeat was stale.

| FD target in /proc/2492/fd | Count |
|---|---:|
| /var/lib/torn-fren/stock_history.db | 510 |
| /var/lib/torn-fren/stock_history.db-wal | 167 |
| /var/lib/torn-fren/stock_history.db-shm | 1 |
| Other files/sockets | 3 |
| **Total** | **681** |
| Process **soft RLIMIT_NOFILE** | **1024** |
| Hard RLIMIT_NOFILE | 524288 |

**678 / 681 = 99.56% SQLite-associated file handles.** The poller
had consumed 66.5% of the soft FD allowance. This confirms substantial
database handle accumulation; the instantaneous sample does not prove
that exactly 1024 descriptors were reached during earlier failures.

Other user-supplied diagnostics:
- The database was 147 MiB; WAL 6.4 MiB and SHM 32 KiB.
- Mount `/dev/sda1`: 45 GB, 39 GB available, 13% used.
- Inodes only 3% used.
- `data` is symlink to `/var/lib/torn-fren`; user `ubuntu` has
  `rw-rw-r--` on `stock_history.db`.
- Separate `sqlite3.connect(...mode=ro)` and `SELECT 1` succeeded
  immediately. This points away from global disk/inode exhaustion;
  background process resource exhaustion remains the leading hypothesis.
- Poller logs contain `sqlite3.OperationalError: unable to open database
  file` during history-backed forecast calculation and increasingly long
  recovery cycles (1858.2s and 2400.6s).
- V37 poller recovery invalidation synchronously executes expensive
  historical continuity checks on the collector thread; **this is
  an independent verified architectural blockage**, addressed in the
  separate `research/v38-full-roster-live-prep-20261009` development
  branch, not by the FD-only changes here.

## Source-code reason and minimal FD fix

Python's standard `sqlite3.Connection.__exit__` commits/rolls back
transactions but **does not call `close()`**. V37's
`services.history_service._connect` is used by >20 `with _connect()`
contexts through the collector and model/audit stack. Connections
remain open until reclaimed, which in long-running threaded prediction
code can accumulate and exhaust FD headroom.

The surgical research-only hotfix started from the *exact production
commit* `062f3a27f33062b50b505f9f492b931e9c654cfd`
(also tagged `release/v37-v2-baseline-timeout-20261008`):

1. `services/history_service.py`: `_ClosingConnection(sqlite3.Connection)`
   invokes standard sqlite transaction exit then closes in `finally`.
   `_connect()` uses this factory and also closes the connection if
   setup PRAGMA fails.
2. `services/shadow_model_auditor.py`: own `_connect()` uses closing
   subclass.
3. `services/medium_model_lab.py` and `services/prediction_lab.py`:
   legacy catalog enumeration opens closing SQLite factory.
4. `tests/test_v37_sqlite_fd_hotfix.py`: commits/rollbacks, no use
   after `with`, `/proc/self/fd` stress across 2000 read/write
   operations, 500 Japan shadow reads, 400 legacy model enumerations,
   schema init compatibility.
5. `.github/workflows/v37-sqlite-fd-hotfix.yml`: execute tests and
   original frozen-V18 and rotating V37 shadow regressions.

**No keys, database snapshots, VM config, systemd unit, public routing,
 or production branch were modified.** This is GitHub source only.

## Release boundary

The user specifically directed that all hotfix code remain in GitHub
until they ask for deployment steps. **Do not send VM hotfix commands
or deploy automatically.** Before any future authorized release:
verify CI for current SHA; measure poller FD counts before/after
across >30min under load; verify database heartbeat <180s, forecast
continuity and shadow evidence; retain stable V37 release SHA and
rollback procedures. Repairing SQLite FDs does NOT alone fix the
blocking V37 synchronous recovery auditing.

The two changes are staged separately to minimize blast radius.
