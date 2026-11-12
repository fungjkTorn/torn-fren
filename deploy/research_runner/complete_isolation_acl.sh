#!/usr/bin/env bash
# Opt-in follow-up after the snapshot installer correctly halted on a
# world-readable collector. Deny only tornresearch through a NAMED POSIX ACL
# on the REAL live-data directory (which /opt/torn-fren/data symlinks to).
# This does not chmod the live database or alter access for any other user.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: run only as ubuntu"; exit 1; }
sudo -n true || { echo "STOP: passwordless sudo unavailable"; exit 1; }

SRC=/opt/torn-fren/data/stock_history.db
DATA_LINK=/opt/torn-fren/data
RESEARCH=/var/lib/torn-fren-research/stock_history_research.db
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
TIMER=torn-fren-research-snapshot.timer
SERVICE=torn-fren-research-snapshot.service
USER=tornresearch

for tool in setfacl getfacl readlink stat systemctl; do
  command -v "$tool" >/dev/null || {
    echo "STOP: missing $tool. Install the Ubuntu acl package first."; exit 1;
  }
done
id "$USER" >/dev/null || { echo "STOP: no research user"; exit 1; }
[[ -L "$DATA_LINK" ]] || {
  echo "STOP: source data link changed since audit"; exit 1; }
real_data_dir=$(readlink -e -- "$DATA_LINK")
real_source=$(readlink -e -- "$SRC")
[[ "$real_source" == "$real_data_dir/stock_history.db" ]] || {
  echo "STOP: canonical data directory differs from collector target"; exit 1;
}
[[ "$real_data_dir" != "/" && "$real_data_dir" != "/opt" &&
   "$real_data_dir" != "/opt/torn-fren" &&
   "$real_data_dir" != "/home" &&
   "$real_data_dir" != "/var" &&
   "$real_data_dir" != "/var/lib" &&
   "$real_data_dir" != "/var/lib/torn-fren-research" ]] || {
 echo "STOP: refusing ACL on an overly broad system directory"; exit 1;
}
[[ -f "$real_source" && -f "$RESEARCH" && -r "$RESEARCH" ]] || {
  echo "STOP: collector or prior sanitized snapshot unavailable"; exit 1;
}
[[ $(stat -c %U -- "$real_source") == ubuntu ]] || {
  echo "STOP: collector owner has changed"; exit 1;
}
[[ $(stat -c %a -- "$real_source") == 664 ]] || {
  echo "STOP: collector mode has changed; reassess before installing"; exit 1;
}
[[ $(systemctl show "$SERVICE" -p Result --value) == success ]] || {
  echo "STOP: previous snapshot service was not successful"; exit 1;
}
[[ $(systemctl show "$TIMER" -p UnitFileState --value) == disabled ]] || {
  echo "STOP: snapshot timer state changed"; exit 1;
}
[[ $(systemctl show "$SERVICE" -p User --value) == ubuntu ]] || {
  echo "STOP: snapshot service is not the expected ubuntu-only exporter"; exit 1;
}
if ! sudo -n -u "$USER" test -r "$SRC"; then
  echo "ALREADY PROTECTED: research account cannot read collector."
  exit 0
fi
sudo -n -u "$USER" test -r "$RESEARCH" || {
  echo "STOP: research account cannot read the sanitized snapshot"; exit 1;
}
sudo -n -u ubuntu test -r "$SRC" || {
  echo "STOP: original owner cannot read collector"; exit 1;
}
sudo -n -u "$USER" test ! -r "$ROSTER" || {
  echo "STOP: private specialist roster exposed to research account"; exit 1;
}

echo "===== VERIFY EXISTING ACL SCOPE ====="
echo "Resolved live-data directory: $real_data_dir"
if sudo -n getfacl -cp -- "$real_data_dir" |
  grep -q '^user:tornresearch:'; then
  echo "STOP: an ACL for tornresearch already exists; manual inspection required"
  exit 1
fi

applied=0
rollback() {
  local status=$?
  if [[ "$applied" == 1 ]]; then
    echo "STOP: verification failed. Restoring previous live-directory ACL."
    sudo -n setfacl -x u:tornresearch -- "$real_data_dir" || true
  fi
  exit "$status"
}
trap rollback ERR

echo "===== DENY RESEARCH ACCOUNT FROM LIVE DATA ONLY ====="
# Named ACL entries override 'other::r-x' for this user specifically.
# No chmod, chown, source restart, or recursive permission changes.
sudo -n setfacl -m u:tornresearch:--- -- "$real_data_dir"
applied=1

echo "===== VERIFY ISOLATION AND KEEP PRODUCTION ACCESS ====="
if sudo -n -u "$USER" test -x "$real_data_dir"; then
  echo "STOP: research user can still traverse live data directory"
  false
fi
if sudo -n -u "$USER" test -r "$SRC"; then
  echo "STOP: research user can still read live collector"
  false
fi
sudo -n -u "$USER" test -r "$RESEARCH"
sudo -n -u "$USER" test ! -r "$ROSTER"
sudo -n -u ubuntu test -r "$SRC"
sudo -n -u ubuntu test -r "$ROSTER"
[[ $(stat -c %a -- "$real_source") == 664 ]] || {
  echo "STOP: live collector file permission changed unexpectedly"; false;
}
sudo -n -u ubuntu python3 -B - "$SRC" <<'CHECK_RO'
import sqlite3,sys
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=6) as db:
    db.execute("PRAGMA query_only=ON")
    x=db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    if x < 3:
        raise SystemExit("Live collector schema missing")
print("PRODUCTION LIVE DB READ-ONLY CHECK PASS")
CHECK_RO
sudo systemctl is-active --quiet torn-fren-v160-forward24.timer

# ACL verified: keep it on disk; continue the separate research timer only.
applied=0
trap - ERR
echo "===== ENABLE ONLY SANITIZED RESEARCH SNAPSHOT TIMER ====="
sudo systemctl enable --now "$TIMER"
sudo systemctl is-enabled --quiet "$TIMER"
sudo systemctl is-active --quiet "$TIMER"
echo "SUCCESS: isolated research account DENIED live database directory"
echo "SUCCESS: ubuntu production owner retains original collector access"
echo "SUCCESS: sanitized research snapshot available; research timer ACTIVE"
echo "No changes to live DB modes, main collector, websites, V160, or beta."
