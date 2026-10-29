# Admin health and storage follow-up

User requested this during the seven-challenger week replay. Continue the replay;
no cleanup or deployment has been performed from the screenshot alone.

The supplied admin screenshot reports 31.1% disk used (14GB of 44GB), about 30GB
free, a 301MB collector database, and 59 backups consuming 4.3GB. These are
screenshot observations, not a fresh host storage inventory. Capacity is not
currently close to full. Backup retention is the first visible review candidate.

Admin health currently determines its top-level badge only from collector age.
Its auditor/profile counters are the legacy prediction system, not proof that
the ten-item first-release publisher or append-only evidence recorder is healthy.

Next implementation should report the actual publisher timer and service,
last successful batch, item count, source freshness, valid-until, per-country
clock status, evidence ledger health, current model SHA and publisher SHA. Keep
the running web checkout version separate from the deployed model identity.
Label legacy counters explicitly and do not let them imply current forecasts
are failing merely because their older model jobs were retired. Health must
distinguish collector health, publisher health, source freshness and disk state.

Before deletion, obtain a bounded read-only inventory of backup dates/sizes,
retired releases, old research snapshots, journals/logs, and package caches.
Check backup integrity and restore requirements before proposing retention.
Preserve collector observations, current and rollback releases, active research
sources and append-only forecast/evidence logs. Provide an explicit reviewed
cleanup list and retention policy; do not prune raw history to save a small
amount of space or run a broad filesystem deletion command.

The screenshot's database size/count growth should be monitored against time;
one screenshot cannot establish the daily growth rate or time until disk full.

## Staged implementation

services.admin_live_beta_health performs a bounded snapshot read and one-second
read-only ledger check, with no forecasting or production database writes.
services.admin_health reports model/publisher versions, last publication, live
roster count, advice states, country freshness, timer/service state and ledger
identity. A successful oneshot service being inactive between timer runs is
normal. Missing advice alone is not a service failure. Snapshot expiry, stale
source clocks, a lagging/mismatched ledger or a failed publisher degrades health.
Legacy audit counters are labelled and the web Git version is shown separately.
Disk usage at 85%/95% raises warning/critical storage state; the screenshot's
31.1% is below either threshold.

The revised admin page was checked at 1280px and 390px with a local fixture;
no JavaScript errors or horizontal overflow occurred. Unit tests cover stale
and malformed snapshots, roster count mismatch, wrong ledger model identity,
missing ledgers without creating files, read-only behavior and deployment
rollback after a failed API check.

deploy/Update_Admin_Health.ps1 packages exactly three health/UI files from Git
and uses the existing SSH key. Its default is a plan; -Apply backs up those
files, restarts only the web service and verifies the new API markers and
unchanged model SHA. Failure restores the original files. It does not update
the live model publisher, collector, timers or perform disk cleanup. This
package is prepared, not deployed. The standalone read-only inventory is
deploy/scripts/storage_inventory.py; it can optionally verify gzip integrity
of the latest backup, which is not the same as a verified SQLite restore.
