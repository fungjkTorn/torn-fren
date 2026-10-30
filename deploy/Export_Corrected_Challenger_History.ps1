param([string]$Repository = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$branch = 'release/first-ten-operation-sequence'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
& git -C $Repository fetch origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed.' }
$exporter = & git -C $Repository show "FETCH_HEAD`:research/export_challenger_history.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read reviewed exporter from fetched Git commit.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$remote = "/home/ubuntu/torn-fren-challenger-history-$stamp.sqlite"
$local = Join-Path $env:USERPROFILE "Desktop\torn-fren-challenger-history-$stamp.sqlite"
$report = $exporter | & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --source /opt/torn-fren/data/stock_history.db --output $remote --owner ubuntu"
if ($LASTEXITCODE -ne 0) { throw 'Read-only export failed; no replay was started.' }
$report | Write-Output
& scp -i $key "ubuntu@150.136.108.146:$remote" $local
if ($LASTEXITCODE -ne 0) { throw "Export exists at $remote but download failed." }
Write-Host "Stock-only replay database saved to $local"
Write-Host 'Upload this SQLite file for the pilot and seven-day replay. No live services were changed.'
