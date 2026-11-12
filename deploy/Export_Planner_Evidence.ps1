param([string]$Repository = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
& git -C $Repository fetch origin release/first-ten-operation-sequence
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed.' }
$commit = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
$stock = & git -C $Repository show "$commit`:research/export_challenger_history.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read stock exporter.' }
$exporter = & git -C $Repository show "$commit`:research/export_planner_evidence.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read planner exporter.' }
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($stock -join "`n")))
$source = "STOCK_EXPORT_SOURCE_B64 = '$encoded'`n" + ($exporter -join "`n")
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$remote = "/home/ubuntu/torn-fren-planner-diagnostics-$stamp.zip"
$local = Join-Path $env:USERPROFILE "Desktop\torn-fren-planner-diagnostics-$stamp.zip"
$source | & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --ledger /var/lib/torn-fren-live-beta/forecasts.sqlite --collector /opt/torn-fren/data/stock_history.db --output $remote --owner ubuntu"
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic export failed; no service changes were requested.' }
& scp -i $key "ubuntu@150.136.108.146:$remote" $local
if ($LASTEXITCODE -ne 0) { throw "Export exists at $remote but download failed." }
Write-Host "Upload this diagnostic bundle: $local"
Write-Host 'No deployment, model inference, cleanup or service changes were performed.'
