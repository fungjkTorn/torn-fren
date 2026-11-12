<#
  Copy a CONSISTENT sanitized research-only SQLite snapshot from the
  TORN-FREN VM onto this Windows PC for offline historical replay.
  No production collector, API requests, or service changes.
  Execute in PowerShell from repository root:
    .\scripts\copy_vm_history_to_pc.ps1
#>
param(
    [string]$VmHost = "150.136.108.146",
    [string]$SshKey = "$env:USERPROFILE\Desktop\.ssh\torn-fren.key",
    [string]$LocalDb = "$PSScriptRoot\..\historical_pc_data\stock_history_research.db"
)
$ErrorActionPreference = "Stop"
if (!(Test-Path -LiteralPath $SshKey -PathType Leaf)) {
    throw "SSH private key not found: $SshKey"
}
$Destination = [System.IO.Path]::GetFullPath($LocalDb)
$Folder = Split-Path -Parent $Destination
New-Item -ItemType Directory -Path $Folder -Force | Out-Null

# SQLite online backup rather than unsafe file copy. The original sanitized
# research DB is opened read-only. A disposable copy is staged under ubuntu.
$RemoteBackup = @'
import os, pwd, sqlite3, tempfile
source = "/var/lib/torn-fren-research/stock_history_research.db"
out = "/home/ubuntu/torn-fren-pc-research-snapshot.db"
src = sqlite3.connect("file:" + source + "?mode=ro", uri=True)
src.execute("PRAGMA query_only=ON")
meta = dict(src.execute("SELECT key,value FROM research_metadata"))
if meta.get("sanitized_stock_only") != "true" or meta.get("roster_size") != "24":
    raise SystemExit("REFUSED: not the sanctioned 24-item stock-only snapshot")
fd, tmp = tempfile.mkstemp(prefix=".torn-fren-history-", suffix=".db",
                           dir="/home/ubuntu")
os.close(fd)
try:
    dst = sqlite3.connect(tmp)
    src.backup(dst, pages=1000, sleep=0.05)
    dst.close()
    src.close()
    user = pwd.getpwnam("ubuntu")
    os.chown(tmp, user.pw_uid, user.pw_gid)
    os.chmod(tmp, 0o600)
    os.replace(tmp, out)
    print("SAFE_RESEARCH_SNAPSHOT_READY")
except Exception:
    if os.path.exists(tmp):
        os.unlink(tmp)
    raise
'@

Write-Host "Preparing consistent research-only snapshot on $VmHost ..."
$RemoteBackup | & ssh -T -i $SshKey "ubuntu@$VmHost" "sudo -n python3 -"
if ($LASTEXITCODE -ne 0) {
    throw "Remote backup failed. Verify SSH access and sudo -n permission."
}

Write-Host "Transferring sanitized history to $Destination ..."
$RemoteFile = "ubuntu@" + $VmHost + ":/home/ubuntu/torn-fren-pc-research-snapshot.db"
& scp -i $SshKey $RemoteFile "$Destination"
if ($LASTEXITCODE -ne 0) {
    throw "SCP failed. Research staging file remains on VM for recovery."
}

# Remove exactly the disposable copy this transfer created.
& ssh -T -i $SshKey "ubuntu@$VmHost" "rm -f -- /home/ubuntu/torn-fren-pc-research-snapshot.db"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Transfer succeeded; temporary staging copy could not be removed."
}
Write-Host ("LOCAL OFFLINE RESEARCH HISTORY: " + $Destination)
Write-Host ("Size (MB): " + [math]::Round((Get-Item -LiteralPath $Destination).Length / 1MB, 1))
Write-Host 'Next: py -3 scripts/run_pc_historical_sixcore.py --source ".\historical_pc_data\stock_history_research.db" --smoke'
