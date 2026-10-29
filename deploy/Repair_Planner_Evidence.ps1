param([switch]$Apply, [string]$Repository = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
& git -C $Repository fetch origin release/first-ten-operation-sequence
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed.' }
$commit = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve reviewed Git release.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$archive = Join-Path $env:TEMP "torn-fren-planner-evidence-$stamp.zip"
$remote = "/home/ubuntu/torn-fren-planner-evidence-$stamp.zip"
$reportPath = Join-Path $env:USERPROFILE "Desktop\torn-fren-planner-evidence-$stamp.json"
$files = @('services/first_release_evidence.py', 'services/restock_signatures.py', 'services/simulated_trip_evidence.py', 'web/first_release_assets/beta.js', 'web/first_release_assets/board.html', 'deploy/scripts/repair_planner_evidence.py')
& git -C $Repository archive --format=zip "--output=$archive" $commit -- @files
if ($LASTEXITCODE -ne 0) { throw 'Cannot package planner evidence repair.' }
$installer = & git -C $Repository show "$commit`:deploy/scripts/repair_planner_evidence.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read evidence installer.' }
& scp -i $key $archive "ubuntu@150.136.108.146:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Planner evidence package upload failed.' }
$flag = if ($Apply) { '--apply' } else { '' }
$report = $installer | & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --archive $remote $flag"
$exitCode = $LASTEXITCODE
$report | Set-Content -Encoding utf8 -LiteralPath $reportPath
$report | Write-Output
Write-Host "Report saved to $reportPath"
if ($exitCode -ne 0) { throw 'Planner evidence repair did not complete; inspect the saved report.' }
if (!$Apply) { Write-Host 'Plan only. No deployment was performed. Run with -Apply when ready.' }
