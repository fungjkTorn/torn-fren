param([switch]$Apply, [string]$Repository = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
& git -C $Repository fetch origin release/first-ten-operation-sequence
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed.' }
$commit = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve reviewed Git release.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$archive = Join-Path $env:TEMP "torn-fren-admin-$stamp.zip"
$remote = "/home/ubuntu/torn-fren-admin-$stamp.zip"
$reportPath = Join-Path $env:USERPROFILE "Desktop\torn-fren-admin-$stamp.json"
$files = @('services/admin_health.py', 'services/admin_live_beta_health.py', 'web/static/admin.html', 'deploy/scripts/update_admin_health.py')
& git -C $Repository archive --format=zip "--output=$archive" $commit -- @files
if ($LASTEXITCODE -ne 0) { throw 'Cannot package admin update.' }
$installer = & git -C $Repository show "$commit`:deploy/scripts/update_admin_health.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read admin installer.' }
& scp -i $key $archive "ubuntu@150.136.108.146:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Admin package upload failed.' }
$flag = if ($Apply) { '--apply' } else { '' }
$report = $installer | & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --archive $remote $flag"
$exitCode = $LASTEXITCODE
$report | Set-Content -Encoding utf8 -LiteralPath $reportPath
$report | Write-Output
Write-Host "Report saved to $reportPath"
if ($exitCode -ne 0) { throw 'Admin update did not complete; inspect the saved report.' }
if (!$Apply) { Write-Host 'Plan only. No deployment was performed. Run with -Apply when ready.' }
