param([switch]$Apply, [string]$Repository = (Get-Location).Path)
$ErrorActionPreference = 'Stop'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
& git -C $Repository fetch origin release/first-ten-operation-sequence
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed.' }
$commit = (& git -C $Repository rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve release.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$archive = Join-Path $env:TEMP "torn-fren-six-challengers-$stamp.zip"
$remote = "/home/ubuntu/torn-fren-six-challengers-$stamp.zip"
$reportPath = Join-Path $env:USERPROFILE "Desktop\torn-fren-six-challengers-$stamp.json"
& git -C $Repository archive --format=zip "--output=$archive" $commit -- services research deploy web/first_release_bridge.py web/first_release_assets/beta.js
if ($LASTEXITCODE -ne 0) { throw 'Cannot package release.' }
$installer = & git -C $Repository show "$commit`:deploy/scripts/add_forward_challengers.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot read deployment helper.' }
& scp -i $key $archive "ubuntu@150.136.108.146:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
$flag = if ($Apply) { '--apply' } else { '' }
$report = $installer | & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --archive $remote --sha $commit $flag"
$exitCode = $LASTEXITCODE
$report | Set-Content -Encoding utf8 -LiteralPath $reportPath
$report | Write-Output
Write-Host "Report saved to $reportPath"
if ($exitCode -ne 0) { throw 'Six-item deployment did not complete; inspect the saved report.' }
