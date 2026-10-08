# V33 production-VM prospective capture, stage 1 (read-only private research)

**No public model routing change, no new Torn automation, no public model promotion.**
This branch is based precisely on `5b4958d`, currently installed on the
`profitability-v1` checkout. The V2 web endpoint, bot, poller, and arbitrage
services are not changed.

## One-time installation, review and manual smoke

Preconditions: the private authenticated endpoint already returned HTTP 200 and
`champion_executed=true` for Canada Bear Gall, with V2 unchanged. The
root-protected `/etc/torn-fren/private-shadow.env` must contain both shadow
flags set to `1`, an existing private token and pinned frozen V21 master path.

```bash
cd /opt/torn-fren
git status --short
git branch --show-current
git fetch origin release/vm-shadow-evidence-v33-20261008
git merge-base --is-ancestor HEAD FETCH_HEAD &&
  git branch "backup/pre-evidence-$(date +%Y%m%d-%H%M%S)" HEAD &&
  git merge --ff-only FETCH_HEAD

python3 -m py_compile research/v31_shadow_evidence_capture.py research/v33_private_shadow_sampler.py

sudo install -m 644 deploy/systemd/torn-fren-shadow-capture.service \
    /etc/systemd/system/torn-fren-shadow-capture.service
sudo install -m 644 deploy/systemd/torn-fren-shadow-capture.timer \
    /etc/systemd/system/torn-fren-shadow-capture.timer
sudo systemctl daemon-reload

# Important: ONE MANUAL CAPTURE ONLY. Do NOT enable timer yet.
sudo systemctl start torn-fren-shadow-capture.service
sudo systemctl show torn-fren-shadow-capture.service -p Result -p ExecMainStatus
sudo journalctl -u torn-fren-shadow-capture.service -n 15 --no-pager
```

Expected: `Result=success`, `ExecMainStatus=0`, and one of
`RECORDED` / `DUPLICATE_FIVE_MINUTE_SLOT` for `can:Bear Gall`. A
`PRIVATE_FAILURE_...` status is a real captured failure, NOT a successful
forecast. Record remains separate from collector stock-history data.

To inspect the non-secret evidence ledger:

```bash
sudo -u ubuntu python3 - <<'PY'
import sqlite3
from pathlib import Path
path=Path("/var/lib/torn-fren-shadow/capture.db")
print("Ledger exists:",path.is_file())
if path.is_file():
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as c:
        print("Attempts:",c.execute("SELECT COUNT(*) FROM shadow_capture_attempts").fetchone()[0])
        print("Status counts:",c.execute(
          "SELECT status,COUNT(*) FROM shadow_capture_attempts GROUP BY status").fetchall())
        print("Valid prediction rows:",c.execute(
          "SELECT COUNT(*) FROM shadow_decisions").fetchone()[0])
PY
```

The `shadow_decisions` table exists only if at least one private valid response
was accepted; if all attempts failed, report status without assuming it exists.

## Enable a schedule ONLY after the manual result and site health are verified

```bash
sudo systemctl enable --now torn-fren-shadow-capture.timer
systemctl list-timers --all torn-fren-shadow-capture.timer
```

The timer is disabled by default. It starts at :01/:06/:11/.../:56 each hour,
every five minutes. `Persistent=false` intentionally prevents historical
catch-up if the VM was off. Its unit runs as `ubuntu`, writes only to
`/var/lib/torn-fren-shadow/capture.db`, keeps the directory private, and uses
the already configured secret from systemd's protected EnvironmentFile.
Only `can:Bear Gall` is enabled initially; Canada Fire Hydrant can be added
later as a separate controlled change.

### Stop or rollback without disrupting production

```bash
sudo systemctl disable --now torn-fren-shadow-capture.timer
```

This **does not** stop the Torn Fren website, bot or poller and does not
disable the already-protected private endpoint. To also disable native
challenger inference, set `TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED=0` in
the root-protected env and restart only the web service. Preserve the evidence
ledger for audit; do not delete it as a rollback strategy.

## Release verification limits

- A valid capture records what V2 and V21 predicted, **not** whether either won.
- Every attempted tick is separately logged, including a rejected HTTP response.
  The V32 prospective scorer must be upgraded to reconcile failed attempts
  and missed timer ticks before reporting unbiased all-start success rates.
- A future scoring phase needs eligible stock outcomes >=30 on arrival +10 sec,
  reliable collector coverage, multiple independent stock windows, full
  frozen-native parity and fair V2 comparison. Do not score 15 correlated
  starts on a single stock window as 15 independent successes.
- Never paste a token or the env file contents into chat, GitHub, the service
  journal or any HTTP URL.
