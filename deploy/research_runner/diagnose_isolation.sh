#!/usr/bin/env bash
# Diagnostic only. Never changes modes, ACLs, services, users or databases.
set -euo pipefail
SRC=/opt/torn-fren/data/stock_history.db
SRCDIR=/opt/torn-fren/data
STAGE=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
STAGEDIR=/home/ubuntu/torn-fren-private-models
SNAP=/var/lib/torn-fren-research/stock_history_research.db
TIMER=torn-fren-research-snapshot.timer
SERVICE=torn-fren-research-snapshot.service
echo "===== RESEARCH ISOLATION READ-ONLY DIAGNOSIS ====="
echo "CURRENT_USER=$(id -un)"
echo "ACL_TOOL=$(command -v setfacl || echo unavailable)"
echo "FS_TYPE=$(stat -f -c %T "$SRCDIR" || echo unavailable)"
echo "===== RESEARCH ACCOUNT ====="
if id tornresearch >/dev/null 2>&1; then
  id tornresearch
else
  echo "RESEARCH_ACCOUNT_MISSING"
fi
echo "===== METADATA ONLY (NO STOCK DATA) ====="
for p in /opt /opt/torn-fren "$SRCDIR" "$SRC" /home/ubuntu   "$STAGEDIR" "$STAGE" /var/lib/torn-fren-research "$SNAP"; do
  if test -e "$p"; then
    stat -c '%A %a %U:%G %n' "$p"
  else
    echo "MISSING $p"
  fi
done
echo "===== NAMED ACLS ON ISOLATION BOUNDARIES ====="
if command -v getfacl >/dev/null 2>&1; then
  for p in "$SRCDIR" "$STAGEDIR"; do
    if test -d "$p"; then
      getfacl -cp "$p" | sed -n '1,16p'
    fi
  done
else
  echo "getfacl unavailable"
fi
echo "===== ACCOUNT READ TESTS ====="
if id tornresearch >/dev/null 2>&1; then
  for p in "$SRC" "$STAGE" "$SNAP"; do
    if sudo -n -u tornresearch test -r "$p"; then
      echo "RESEARCH_USER_CAN_READ $p"
    else
      echo "RESEARCH_USER_DENIED $p"
    fi
  done
fi
echo "===== SNAPSHOT SERVICE METADATA ====="
systemctl show "$SERVICE" --no-pager   -p LoadState -p ActiveState -p SubState -p Result || true
systemctl show "$TIMER" --no-pager   -p LoadState -p ActiveState -p UnitFileState || true
echo "===== DIAGNOSIS COMPLETE: NO WRITES ====="
